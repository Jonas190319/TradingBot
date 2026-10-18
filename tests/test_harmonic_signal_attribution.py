"""Offline regression for per-signal harmonic attribution."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services"/"mt5-engine"))
from sequential_research_execution import simulate_signals


def test_signal_id_survives():
    rows=[{"time":300*i,"open":100,"high":103,"low":100,"close":101} for i in range(3)]
    x=simulate_signals(rows,[{"bar_index":0,"side":"long","stop":99,
                              "target_rr":2,"signal_id":"48:gartley:0"}])[0]
    assert x["signal_id"]=="48:gartley:0",x


def test_same_bar_ids_remain_distinct():
    rows=[{"time":300*i,"open":100,"high":103,"low":100,"close":101} for i in range(3)]
    signals=[{"bar_index":0,"side":"long","stop":99,"target_rr":2,
              "signal_id":name} for name in ("gartley","butterfly")]
    result=simulate_signals(rows,signals)
    assert len(result)==1,result
    assert result[0]["signal_id"]=="gartley",result


if __name__=="__main__":
    test_signal_id_survives()
    print("PASS test_signal_id_survives")
    test_same_bar_ids_remain_distinct()
    print("PASS test_same_bar_ids_remain_distinct")
