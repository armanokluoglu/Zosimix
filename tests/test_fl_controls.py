"""FL knob conversions (D57). Pure functions, so these run without FL."""

import json

import pytest

from zosimix.fl import controls


def probe() -> dict:
    return json.loads(controls.PROBE.read_text(encoding="utf-8"))


def test_eq_frequency_matches_what_fl_displays():
    assert controls.eq_freq_pos(20) == pytest.approx(0.0)
    assert controls.eq_freq_pos(20000) == pytest.approx(1.0)
    # FL showed 1262 Hz at position 0.6 and 80 Hz at 0.2
    assert controls.eq_freq_pos(1262) == pytest.approx(0.6, abs=1e-3)
    assert controls.eq_freq_pos(80) == pytest.approx(0.2, abs=1e-3)


def test_eq_level_is_linear_around_half():
    assert controls.eq_level_pos(0) == 0.5
    assert controls.eq_level_pos(-18) == 0.0
    assert controls.eq_level_pos(18) == 1.0


def test_stepped_choices_land_on_fls_steps():
    sweep = probe()["peq2"][str(controls.type_param(1))]["sweep"]
    shown_at = {round(held, 4): text for _, held, text in sweep}
    assert shown_at[round(controls.eq_type_pos("peaking"), 4)] == "Peaking"
    assert shown_at[round(controls.eq_type_pos("highpass"), 4)] == "High_pass"
    assert shown_at[round(controls.eq_type_pos("disabled"), 4)] == "Disabled"
    orders = probe()["peq2"][str(controls.order_param(1))]["sweep"]
    order_at = {round(held, 4): text for _, held, text in orders}
    assert order_at[round(controls.eq_order_pos("2"), 4)] == "2"


def test_parameter_indices_match_the_probe_names():
    names = {int(k): v["name"] for k, v in probe()["peq2"].items()}
    for band in (1, 4, 7):
        assert names[controls.level_param(band)] == f"Band_{band}_level"
        assert names[controls.freq_param(band)] == f"Band_{band}_freq"
        assert names[controls.width_param(band)] == f"Band_{band}_width"
        assert names[controls.type_param(band)] == f"Band_{band}_type"
        assert names[controls.order_param(band)] == f"Band_{band}_order"
    assert names[controls.MAIN_LEVEL] == "Main_level"


def test_fader_table():
    assert controls.fader_pos(0.0) == pytest.approx(0.8, abs=1e-3)
    assert controls.fader_pos(controls.FADER_MAX_DB) == pytest.approx(1.0, abs=1e-3)
    with pytest.raises(ValueError):
        controls.fader_pos(6.0)
