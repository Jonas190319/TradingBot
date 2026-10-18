"""Offline checks for persistent harmonic research tracking."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

MODULE = Path(__file__).resolve().parents[1] / "services" / "mt5-engine" / "harmonic_tracker.py"
spec = importlib.util.spec_from_file_location("harmonic_tracker", MODULE)
tracker_module = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = tracker_module
spec.loader.exec_module(tracker_module)
HarmonicTracker = tracker_module.HarmonicTracker


def sample():
    match = SimpleNamespace(pattern="gartley", direction="long")
    pivots = [SimpleNamespace(timestamp=f"2026-01-01T00:{i:02d}:00Z",
                              kind="low" if i % 2 == 0 else "high",
                              price=float(100 + i)) for i in range(5)]
    return ("EURUSD", match, pivots)


def candle(open_, close):
    return SimpleNamespace(open=open_, close=close)


def test_delayed_reentry_and_unique_signal():
    t = HarmonicTracker(max_age_bars=12)
    detected = [sample()]
    assert any(e[0] == "discovered" for e in t.update(0, candle(106, 106), 1, detected))
    assert not any(e[0] == "signal" for e in t.update(1, candle(106, 106), 1))
    assert any(e[0] == "signal" for e in t.update(2, candle(103.7, 104.2), 1))
    assert not any(e[0] == "signal" for e in t.update(3, candle(103.7, 104.2), 1, detected))


def test_invalidation():
    t = HarmonicTracker()
    t.update(0, candle(105, 105), 1, [sample()])
    events = t.update(1, candle(102, 102), 1)
    assert any(e[0] == "invalidated" for e in events)
    assert not t.active


def test_expiry():
    t = HarmonicTracker(max_age_bars=2)
    t.update(0, candle(106, 106), 1, [sample()])
    assert any(e[0] == "expired" for e in t.update(2, candle(106, 106), 1))


def test_reset_does_not_duplicate():
    t = HarmonicTracker()
    t.update(0, candle(106, 106), 1, [sample()])
    t.reset()
    assert not any(e[0] == "discovered" for e in t.update(10, candle(106, 106), 1, [sample()]))


if __name__ == "__main__":
    for test in (test_delayed_reentry_and_unique_signal, test_invalidation,
                 test_expiry, test_reset_does_not_duplicate):
        test()
        print(f"PASS {test.__name__}")
