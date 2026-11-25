"""The mix state: everything the agent is allowed to change, in real units (DESIGN.md §3.3).

One MixState is the single source of truth that both engines render:
  - the offline engine applies it to the stem WAVs in Python (EQ: zosimix.eq), and
  - the FL engine translates it into fader, knob and Parametric EQ 2 moves.
It is also the human-readable "mix recipe" a run produces.

Values are stored in real units (dB, Hz, Q) rather than FL's normalized 0..1 knob
positions. Converting between the two is the FL engine's job, guided by calibration.

The action space deliberately mirrors what the FL bridge can do (D12, D13):
fader gain, pan, polarity, stereo width, and up to 7 Parametric EQ 2 bands per track.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

EQ_BAND_TYPES = ("peaking", "low_shelf", "high_shelf", "highpass", "lowpass")
MAX_EQ_BANDS = 7                # Fruity Parametric EQ 2 has 7 bands

# Limits, checked by validate(). Gain is the *total* gain: FL's fader tops out at
# +5.6 dB, so the FL engine will put any extra boost on PEQ2's main level (D43).
GAIN_DB = (-60.0, 18.0)
PAN = (-1.0, 1.0)
WIDTH = (0.0, 2.0)
EQ_FREQ_HZ = (20.0, 20000.0)
EQ_GAIN_DB = (-18.0, 18.0)
EQ_Q = (0.1, 18.0)


@dataclass
class EqBand:
    type: str = "peaking"
    freq_hz: float = 1000.0
    gain_db: float = 0.0        # ignored by highpass/lowpass
    q: float = 1.0              # highpass/lowpass: the bump at the cutoff (0.707 = none)

    def is_neutral(self) -> bool:
        return self.type in ("peaking", "low_shelf", "high_shelf") and self.gain_db == 0.0


@dataclass
class TrackState:
    gain_db: float = 0.0
    pan: float = 0.0            # -1 hard left .. 0 centre .. +1 hard right (a balance control)
    polarity: bool = False      # True = inverted
    width: float = 1.0          # 0 mono .. 1 unchanged .. 2 twice the side signal
    eq: list[EqBand] = field(default_factory=list)

    def is_neutral(self) -> bool:
        return (self.gain_db == 0.0 and self.pan == 0.0 and not self.polarity and self.width == 1.0
                and all(b.is_neutral() for b in self.eq))


@dataclass
class MixState:
    tracks: dict[str, TrackState] = field(default_factory=dict)

    @classmethod
    def neutral(cls, stem_names: list[str]) -> MixState:
        """The starting point of every task: all faders at 0 dB, centred, flat EQ."""
        return cls({name: TrackState() for name in stem_names})

    def to_dict(self) -> dict:
        return {name: asdict(t) for name, t in self.tracks.items()}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> MixState:
        """Build and validate a state from JSON-like data.

        The data may come from an agent's hand-written mix_state.json (plain baseline), so
        every problem raises with a readable message: TypeError for a wrong shape, type or
        unknown key, ValueError for a value out of range. The grader catches both and grades
        the answer as "no changes" (D50)."""
        if not isinstance(data, dict):
            raise TypeError(f"a mix state must be an object of stem name -> settings, got {type(data).__name__}")
        tracks = {}
        for name, t in data.items():
            if not isinstance(t, dict):
                raise TypeError(f"{name}: settings must be an object, got {type(t).__name__}")
            t = dict(t)
            eq = t.get("eq", [])
            if not isinstance(eq, list) or not all(isinstance(b, dict) for b in eq):
                raise TypeError(f"{name}.eq must be a list of band objects")
            t["eq"] = [EqBand(**b) for b in eq]
            tracks[name] = TrackState(**t)
        state = cls(tracks)
        state.validate()
        return state

    def validate(self) -> None:
        """Raise ValueError with a readable message for anything outside the action space."""
        def check(name: str, value: float, bounds: tuple[float, float]) -> None:
            # bool is a subclass of int in Python, so rule it out explicitly
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name}={value!r} is not a number")
            if not bounds[0] <= value <= bounds[1]:             # also rejects NaN
                raise ValueError(f"{name}={value} is outside the allowed range {bounds}")

        for stem, t in self.tracks.items():
            check(f"{stem}.gain_db", t.gain_db, GAIN_DB)
            check(f"{stem}.pan", t.pan, PAN)
            check(f"{stem}.width", t.width, WIDTH)
            if not isinstance(t.polarity, bool):                # the string "false" would be truthy
                raise TypeError(f"{stem}.polarity={t.polarity!r} must be true or false")
            if len(t.eq) > MAX_EQ_BANDS:
                raise ValueError(f"{stem}: {len(t.eq)} EQ bands, the maximum is {MAX_EQ_BANDS}")
            for i, b in enumerate(t.eq):
                if b.type not in EQ_BAND_TYPES:
                    raise ValueError(f"{stem}.eq[{i}].type={b.type!r}; allowed: {EQ_BAND_TYPES}")
                check(f"{stem}.eq[{i}].freq_hz", b.freq_hz, EQ_FREQ_HZ)
                check(f"{stem}.eq[{i}].gain_db", b.gain_db, EQ_GAIN_DB)
                check(f"{stem}.eq[{i}].q", b.q, EQ_Q)
