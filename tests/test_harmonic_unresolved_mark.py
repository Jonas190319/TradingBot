"""Offline regression for unresolved MTM, not executed PnL."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services"/"mt5-engine"))
from sequential_research_execution import simulate_signals


def test_unresolved_marked_separately():
    rows = [{"time":300*i,"open":100,"high":101,"low":99,"close":100+i}
            for i in range(5)]
    # Ensure OHLC envelope for changing closes.
    for row in rows:
        row["high"] = max(row["open"],row["close"])+1
    result=simulate_signals(rows,[{"bar_index":0,"side":"long","stop":95,
                                  "target_rr":20}],max_hold=2)
    assert len(result)==1
    x=result[0]
    assert x["outcome"]=="unresolved",x
    assert x["r"] is None,x
    assert abs(x["mark_r"]-0.4)<1e-9,x


def test_resolved_has_no_mark():
    rows=[{"time":300*i,"open":100,"high":105,"low":99,"close":101} for i in range(3)]
    result=simulate_signals(rows,[{"bar_index":0,"side":"long","stop":99,
                                  "target_rr":2}],max_hold=2)
    assert result[0]["outcome"]=="target",result
    assert "mark_r" not in result[0],result


if __name__=="__main__":
    test_unresolved_marked_separately()
    print("PASS test_unresolved_marked_separately")
    test_resolved_has_no_mark()
    print("PASS test_resolved_has_no_mark")
