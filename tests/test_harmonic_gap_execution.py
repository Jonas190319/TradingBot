"""Offline gap-aware execution regression; no MT5 or orders."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services"/"mt5-engine"))
from sequential_research_execution import simulate_signals


def row(t, op, hi=None, lo=None):
    return {"time":t,"open":op,"high":op if hi is None else hi,
            "low":op if lo is None else lo}


def test_no_fill_across_closure():
    rows=[row(0,100),row(3600,110),row(3900,110)]
    r=simulate_signals(rows,[{"bar_index":0,"side":"long","stop":98,"target_rr":2}],
                       allow_gaps=True)
    assert r[0]["outcome"]=="no_fill_gap",r


def test_stop_gap_worse_than_stop():
    rows=[row(0,100),row(300,100,101,99),row(3900,90,92,89)]
    r=simulate_signals(rows,[{"bar_index":0,"side":"long","stop":95,"target_rr":2}],
                       allow_gaps=True,max_hold=2)
    assert r[0]["outcome"]=="stop_gap",r
    assert abs(r[0]["r"]+2)<1e-9,r


def test_gap_rejected_by_default():
    rows=[row(0,100),row(3600,110)]
    try:
        simulate_signals(rows,[])
    except ValueError:
        return
    raise AssertionError("Gaps must remain rejected by default")


if __name__=="__main__":
    test_no_fill_across_closure()
    print("PASS test_no_fill_across_closure")
    test_stop_gap_worse_than_stop()
    print("PASS test_stop_gap_worse_than_stop")
    test_gap_rejected_by_default()
    print("PASS test_gap_rejected_by_default")
