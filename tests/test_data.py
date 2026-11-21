import pandas as pd

from inventiq.catalog import OPTIONS, TODAY
from inventiq.data import synth


def test_generation_is_deterministic(data):
    history, current = data
    h2, c2 = synth.generate()
    assert history.equals(h2)
    assert current.equals(c2)


def test_history_only_holds_finished_stays(data):
    history, _ = data
    ends = pd.to_datetime(history["start"]) + pd.to_timedelta(history["nights"], unit="D")
    assert (ends <= pd.Timestamp(TODAY)).all()
    assert history["demand"].ge(0).all()
    assert not history.isna().any().any()


def test_one_current_row_per_option_at_its_real_lead(data):
    _, current = data
    assert list(current["option_id"]) == [o.id for o in OPTIONS]
    for o, lead in zip(OPTIONS, current["lead_days"], strict=True):
        assert lead == o.lead_days > 0


def test_option_window_is_scaled_to_its_peak():
    o = OPTIONS[0]
    level = synth._calendar(o, [o.start])
    assert abs(level[0] - o.peak) < 1e-6
