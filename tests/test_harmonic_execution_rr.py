"""Offline regression for next-open 2R pricing and frozen pattern ATR."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ENGINE = ROOT / "services" / "mt5-engine"
sys.path.insert(0, str(ENGINE))
from sequential_research_execution import simulate_signals
from harmonic_tracker import HarmonicTracker


def test_next_open_rr():
    rows = [
        {"time": 0, "open": 100, "high": 101, "low": 99},
        {"time": 300, "open": 105, "high": 107, "low": 104},
        {"time": 600, "open": 107, "high": 116, "low": 106},
    ]
    outcome = simulate_signals(rows, [{"bar_index": 0, "side": "long",
                                        "stop": 100, "target_rr": 2}],
                               max_hold=2)
    assert len(outcome) == 1
    assert outcome[0]["outcome"] == "target"
    assert abs(outcome[0]["r"] - 2) < 1e-9


def test_frozen_atr():
    match = SimpleNamespace(pattern="gartley", direction="long")
    pivots = [SimpleNamespace(timestamp=str(i), kind="low" if i % 2 == 0 else "high",
                              price=float(100 + i)) for i in range(5)]
    t = HarmonicTracker(max_age_bars=48)
    t.update(0, SimpleNamespace(open=106, close=106), 1, [("EURUSD", match, pivots)])
    state = next(iter(t.active.values()))
    assert state.reference_atr == 1
    t.update(1, SimpleNamespace(open=106, close=106), 10)
    assert state.reference_atr == 1


if __name__ == "__main__":
    test_next_open_rr()
    print("PASS test_next_open_rr")
    test_frozen_atr()
    print("PASS test_frozen_atr")
