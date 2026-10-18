"""Offline M5 coverage audit tests; no MT5 connection required."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "mt5-engine"))
from audit_harmonic_coverage import coverage


def test_one_long_segment():
    rows = [{"time": i*300} for i in range(400)]
    x = coverage(rows)
    assert x["evaluated"] == 99
    assert x["skipped_warmup"] == 301
    assert x["skipped_short"] == 0
    assert x["eligible_segments"] == 1


def test_short_sessions_excluded():
    rows = [{"time": i*300} for i in range(288)]
    rows += [{"time": 100000+i*300} for i in range(288)]
    x = coverage(rows)
    assert x["evaluated"] == 0
    assert x["skipped_short"] == 576
    assert x["segments"] == 2


def test_empty():
    assert coverage([])["coverage_pct"] == 0


if __name__ == "__main__":
    test_one_long_segment()
    print("PASS test_one_long_segment")
    test_short_sessions_excluded()
    print("PASS test_short_sessions_excluded")
    test_empty()
    print("PASS test_empty")
