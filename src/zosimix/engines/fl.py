"""The FL engine: renders a mix state through FL Studio 20.9.2 (DESIGN.md §3.3, D63).

One render is one FL cycle (zosimix.fl.session): write the stems into the template's
slots, open a copy of the template in FL, set every insert over the bridge, save, close,
and render from the command line. That takes from seconds to a minute, so the agent's
previews stay on the offline engine (D36). This engine renders the final mix, for
listening and for the parity check against the offline engine.

How the mix state maps onto FL (calibration: D57, D60, D63):
  gain      the insert fader as close as it goes (it tops out at +5.59 dB and holds only
            certain positions); the exact remainder goes on PEQ2's main level
  pan       the channel-rack pan, which is exactly audio.pan_gains; the mixer pan stays centred
  polarity  the insert's polarity switch
  width     the insert's stereo separation, at the nearest 1/64 step
  eq        PEQ2 bands 1..7 in order; Q becomes PEQ2's width through the measured table;
            unused and neutral bands are disabled
  master    pulled down RENDER_HEADROOM_DB while rendering, so a loud mix can't clip FL's
            24-bit file; the render is scaled back up by the level FL reports for the master

Known, measured limits (D63): stereo separation moves in 1/64 steps, so widths are matched
to within about 0.008; EQ bands match FL's to within a few tenths of a dB.
"""

from __future__ import annotations

import copy

import numpy as np
import soundfile as sf

from zosimix import audio
from zosimix.engines.base import MixEngine
from zosimix.fl import controls, session, slots
from zosimix.fl.bridge import Bridge, BridgeError
from zosimix.mixstate import MAX_EQ_BANDS, EqBand, MixState, TrackState

MASTER = 0                      # mixer track 0 is the master
RENDER_HEADROOM_DB = 12.0       # room for +10 dB gain faults plus EQ boosts on a mix peaking at -1 dBFS
FADER_TOL_DB = 0.1              # close is enough: the exact remainder goes on PEQ2's main level


def _set_param(fl: Bridge, insert: int, param: int, pos: float) -> None:
    """Set one PEQ2 parameter and check FL holds it (stepped ones land exactly on a step)."""
    held = float(fl.call("set_param", insert, controls.EQ_SLOT, param, pos)[0])
    if abs(held - pos) > 1e-3:
        raise BridgeError(f"insert {insert} PEQ2 parameter {param}: set {pos}, FL holds {held}")


def _apply_band(fl: Bridge, insert: int, band_no: int, band: EqBand | None) -> None:
    if band is None or band.is_neutral():
        _set_param(fl, insert, controls.type_param(band_no), controls.eq_type_pos("disabled"))
        return
    passes = band.type in ("highpass", "lowpass")
    _set_param(fl, insert, controls.type_param(band_no), controls.eq_type_pos(band.type))
    _set_param(fl, insert, controls.freq_param(band_no), controls.eq_freq_pos(band.freq_hz))
    _set_param(fl, insert, controls.level_param(band_no), controls.eq_level_pos(0.0 if passes else band.gain_db))
    _set_param(fl, insert, controls.width_param(band_no), controls.eq_width_pos(band.type, band.q))
    _set_param(fl, insert, controls.order_param(band_no), controls.eq_order_pos("2"))     # 12 dB/octave


def apply_track(fl: Bridge, slot: int, name: str, t: TrackState) -> None:
    """Put one track's settings on its insert (slot k = insert k = channel k-1)."""
    fl.call("set_name", slot, name.replace(" ", "_"))
    # The fader holds only certain positions (e.g. -11.9986 dB for -12), and tops out at
    # +5.59 dB. Whatever it can't give goes on PEQ2's main level, which takes exact values.
    fader_db = controls.set_fader_db(fl, slot, min(t.gain_db, controls.FADER_MAX_DB), tol_db=FADER_TOL_DB)
    _set_param(fl, slot, controls.MAIN_LEVEL, controls.eq_level_pos(t.gain_db - fader_db))
    fl.set_and_confirm("set_chan_pan", "get_chan_pan", slot - 1, t.pan)
    fl.set_and_confirm("set_polarity", "get_polarity", slot, int(t.polarity))
    sep, _ = controls.sep_for_width(t.width)
    fl.set_and_confirm("set_sep", "get_sep", slot, sep, tol=0.02)
    for band_no in range(1, MAX_EQ_BANDS + 1):
        _apply_band(fl, slot, band_no, t.eq[band_no - 1] if band_no <= len(t.eq) else None)


class FLEngine(MixEngine):
    def __init__(self, stems: dict[str, np.ndarray], sample_rate: int) -> None:
        if len(stems) > slots.N_SLOTS:
            raise ValueError(f"{len(stems)} stems, but the FL template has {slots.N_SLOTS} slots")
        self.sample_rate = sample_rate
        self._stems = {name: audio.to_stereo(a) for name, a in stems.items()}
        self._state = MixState.neutral(list(self._stems))

    @property
    def stem_names(self) -> list[str]:
        return list(self._stems)

    def get_state(self) -> MixState:
        return copy.deepcopy(self._state)

    def set_state(self, state: MixState) -> None:
        state.validate()
        unknown = set(state.tracks) - set(self._stems)
        if unknown:
            raise ValueError(f"unknown stems in mix state: {sorted(unknown)}")
        merged = MixState.neutral(self.stem_names)
        merged.tracks.update(copy.deepcopy(state.tracks))
        self._state = merged

    def render_stems(self) -> dict[str, np.ndarray]:
        raise NotImplementedError("FL renders only the whole mix; per-stem previews come from the "
                                  "offline engine (D36)")

    def render(self) -> np.ndarray:
        """The full mix, rendered by FL. Same length as the longest stem."""
        length = max(a.shape[0] for a in self._stems.values())
        mapping = slots.write_song(self._stems, self.sample_rate)
        project = session.new_project("engine")
        with session.FLSession(project) as s:
            master_db = controls.set_fader_db(s.fl, MASTER, -RENDER_HEADROOM_DB, tol_db=FADER_TOL_DB)
            for slot, name in mapping.items():
                apply_track(s.fl, slot, name, self._state.tracks[name])
            s.save()
        wav = session.render(project, min_seconds=length / self.sample_rate)
        y, sr = sf.read(str(wav), dtype="float64", always_2d=True)
        if sr != self.sample_rate:
            raise ValueError(f"FL rendered at {sr} Hz, the song is at {self.sample_rate} Hz")
        out = np.zeros((length, 2))
        out[:min(length, len(y))] = y[:length]
        # Undo the master's headroom (by the level FL reports) and FL's tiny constant loss
        # on every path (0.99984, measured: controls.unity_gain).
        return out * audio.db_to_gain(-master_db) / controls.unity_gain()
