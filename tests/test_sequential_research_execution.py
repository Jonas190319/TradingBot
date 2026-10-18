"""Offline checks for sequential next-open research simulation."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services"/"mt5-engine"))
from sequential_research_execution import simulate_signals


def bars(opens):
    return [{"time":300*i,"open":p,"high":p+0.5,"low":p-0.5,"close":p} for i,p in enumerate(opens)]


class SequentialExecutionTests(unittest.TestCase):
    def test_next_open_not_signal_close(self):
        data=bars([100,102,104,106])
        result=simulate_signals(data,[{"bar_index":0,"side":"long","stop":100,"target":103}])
        self.assertEqual(result[0]["entry"],102)
        self.assertEqual(result[0]["outcome"],"target")

    def test_overlap_skipped(self):
        data=bars([100]*8)
        signals=[{"bar_index":i,"side":"long","stop":99,"target":102} for i in (0,1,2)]
        result=simulate_signals(data,signals,max_hold=4)
        self.assertEqual(len(result),1)

    def test_cost_worsens_entry(self):
        data=bars([100,100,102])
        signal={"bar_index":0,"side":"long","stop":99,"target":101}
        a=simulate_signals(data,[signal])[0]
        b=simulate_signals(data,[signal],cost_ticks=1,tick_size=0.1)[0]
        self.assertLess(b["r"],a["r"])

    def test_both_touch_ambiguous(self):
        data=bars([100,100])
        result=simulate_signals(data,[{"bar_index":0,"side":"long","stop":99.7,"target":100.3}])
        self.assertEqual(result[0]["outcome"],"ambiguous")

    def test_gaps_fail_closed(self):
        data=bars([100,100,100])
        data[2]["time"]+=300
        with self.assertRaises(ValueError):
            simulate_signals(data,[])


if __name__=="__main__":
    unittest.main()
