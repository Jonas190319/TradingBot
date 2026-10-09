"""Offline integration checks: closed data, vetoes, persistence and virtual exits."""
import ast
import copy
import json
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from market_features import bars_from_rates, build_features, opening_range
from shadow_runtime import ShadowRuntime
from services.agent_team.models import Bar
from services.decision_engine.models import MarketSnapshot, Regime
from services.decision_engine.strategists import CORE_STRATEGISTS

NOW = datetime(2026, 10, 8, 14, 0, tzinfo=timezone.utc)


def bars(now=NOW):
    return tuple(Bar(now-timedelta(minutes=5*(60-i)), 100+i*.1,
                     101+i*.1, 99+i*.1, 100.1+i*.1, 100) for i in range(60))


class Database:
    def __init__(self):
        self.rows = {}
        self.fail_table = None
    def table(self, name):
        return Query(self, name)


class Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.filters, self.negated = [], False
        self.payload, self.operation, self.conflict = None, 'select', None
    def upsert(self, rows, on_conflict):
        self.payload, self.operation, self.conflict = rows, 'upsert', on_conflict
        return self
    def insert(self, rows):
        self.payload, self.operation = rows, 'insert'
        return self
    def update(self, row):
        self.payload, self.operation = row, 'update'
        return self
    def select(self, *args): return self
    def eq(self, key, value):
        self.filters.append(lambda row: row.get(key) == value)
        return self
    @property
    def not_(self):
        self.negated = True
        return self
    def is_(self, key, value):
        negated = self.negated
        self.filters.append(lambda row: (row.get(key) is not None) if negated else (row.get(key) is None))
        self.negated = False
        return self
    def order(self, *args, **kwargs): return self
    def limit(self, *args): return self
    def execute(self):
        if self.db.fail_table == self.name:
            raise ConnectionError('offline')
        rows = self.db.rows.setdefault(self.name, [])
        selected = [r for r in rows if all(f(r) for f in self.filters)]
        if self.operation in {'insert','upsert'}:
            incoming = self.payload if isinstance(self.payload, list) else [self.payload]
            for item in incoming:
                item = json.loads(json.dumps(item, allow_nan=False))
                match = None
                if self.conflict:
                    keys = self.conflict.split(',')
                    match = next((r for r in rows if all(r.get(k)==item.get(k) for k in keys)), None)
                if match is None: rows.append(item)
                else: match.update(item)
        elif self.operation == 'update':
            for row in selected: row.update(copy.deepcopy(self.payload))
        return SimpleNamespace(data=copy.deepcopy(selected))


def evaluate(runtime):
    return runtime.evaluate('EURUSD', NOW, 106, 106.02, .01, bars(),
                            SimpleNamespace(equity=5000,balance=5000), 0)


def test_forming_bar_excluded_and_bad_ohlc_rejected():
    def rate(ts):
        return dict(time=ts.timestamp(),open=100,high=101,low=99,close=100,tick_volume=20)
    assert len(bars_from_rates([rate(NOW-timedelta(minutes=5)),rate(NOW)],NOW)) == 1
    bad = rate(NOW-timedelta(minutes=5)); bad['high'] = 90
    with pytest.raises(ValueError,match='envelope'): bars_from_rates([bad],NOW)
    bad['high'] = float('nan')
    with pytest.raises(ValueError,match='Non-finite'): bars_from_rates([bad],NOW)


def test_duplicate_history_rejected():
    row = dict(time=(NOW-timedelta(minutes=5)).timestamp(),open=100,high=101,low=99,close=100,tick_volume=20)
    with pytest.raises(ValueError,match='duplicated'): bars_from_rates([row,row],NOW)


@pytest.mark.parametrize('problem', ['short','stale','gap'])
def test_history_guard(problem):
    sample = bars()
    if problem == 'short': sample = sample[-20:]
    if problem == 'gap': sample = sample[:-2] + (replace(sample[-1],ts=sample[-1].ts+timedelta(seconds=1)),)
    with pytest.raises(ValueError): build_features('EURUSD',NOW+timedelta(hours=1) if problem=='stale' else NOW,sample)


@pytest.mark.parametrize('day,utc_hour', [('2026-03-06',14),('2026-03-10',13)])
def test_new_york_open_tracks_dst(day,utc_hour):
    opened = datetime.fromisoformat(f'{day}T{utc_hour}:30:00+00:00')
    sample = tuple(Bar(opened+timedelta(minutes=5*i),100,101+i,99,100,10) for i in range(3))
    assert opening_range('US500',opened+timedelta(minutes=15),sample)['or_ready']
    assert not opening_range('US500',opened+timedelta(minutes=14),sample)['or_ready']
    assert not opening_range('US500',opened+timedelta(minutes=15),sample[:-1])['or_ready']


@pytest.mark.parametrize('index', range(4))
@pytest.mark.parametrize('sign', [-1,1])
def test_all_four_strategies_long_and_short(index,sign):
    f = dict(atr=1, or_high=101,or_low=99, momentum_score=90,retest_quality=90,
             volume_score=90,trend_alignment=90,opening_range_quality=90,pullback_quality=90,
             momentum_turn=90,structure_score=90,adx=30,trend_bias=sign,
             compression_score=90,expansion_score=90,breakout_bias=sign,
             sweep_score=90,rejection_score=90,momentum_flip=90,sweep_side=-sign)
    price = 102 if sign>0 else 98
    c = CORE_STRATEGISTS[index].evaluate(MarketSnapshot(NOW,'EURUSD',price-.01,price+.01,.02,f),Regime.TREND)
    assert c is not None
    assert c.direction.value == ('long' if sign>0 else 'short')
    assert (c.entry-c.stop_loss)*sign>0 and (c.take_profit_1-c.entry)*sign>0
    assert c.rr >= 1.2


def test_pipeline_nine_agents_no_trade_dedup_and_json():
    db = Database(); runtime = ShadowRuntime(db,'demo-test')
    result = evaluate(runtime)
    assert result['signals']==9
    decision = db.rows['trade_decisions'][0]
    assert decision['decision']=='no_trade' and decision['risk_pct']==0
    assert decision['signal_snapshot']['executable'] is False
    assert {r['agent_type'] for r in db.rows['agent_signals']} == {'news','macro','technical','quant','regime','portfolio','risk','execution','improvement'}
    for r in db.rows['agent_signals']:
        if r['agent_type'] in {'news','macro','risk'}: assert r['direction']=='no_trade' and r['risk_score']==100
    assert evaluate(runtime) is None
    assert len(db.rows['trade_decisions'])==1 and len(db.rows['agent_signals'])==9
    fresh = ShadowRuntime(db,'demo-test'); evaluate(fresh)
    assert len(db.rows['trade_decisions'])==1 and len(db.rows['agent_signals'])==9


def test_failed_write_not_marked_complete_can_retry():
    db = Database(); runtime = ShadowRuntime(db,'demo-test'); db.fail_table='agent_signals'
    with pytest.raises(ConnectionError): evaluate(runtime)
    assert 'EURUSD' not in runtime.completed
    db.fail_table=None; evaluate(runtime)
    assert len(db.rows['trade_decisions'])==1 and len(db.rows['agent_signals'])==9


def test_candidates_are_recorded_and_rejected_without_feeds(monkeypatch):
    import shadow_runtime
    original = shadow_runtime.build_features
    def features(*args):
        result = original(*args)
        result.update(trend_bias=1,pullback_quality=90,trend_alignment=90,adx=30,
                      or_high=105,or_low=104,retest_quality=90,opening_range_quality=90,
                      compression_score=90,expansion_score=90,breakout_bias=1,
                      sweep_side=-1,sweep_score=90,rejection_score=90)
        return result
    monkeypatch.setattr(shadow_runtime,'build_features',features)
    db=Database(); runtime=ShadowRuntime(db,'demo-test'); result=evaluate(runtime)
    assert result['candidates']==4
    assert len(db.rows['pretrade_events'])==12 and len(db.rows['shadow_outcomes'])==4
    assert all(not c['risk']['approved'] for c in db.rows['trade_decisions'][0]['signal_snapshot']['candidates'])
    assert not runtime.strategies.pretrade.events
    restored=ShadowRuntime(db,'demo-test'); restored.restore_tracking()
    assert len(restored.active)==4
    restored.observe('EURUSD',NOW+timedelta(minutes=1),120,120.02)
    assert not restored.active and len(restored.history)==4
    assert all(r['was_executed'] is False for r in db.rows['shadow_outcomes'])
    restarted=ShadowRuntime(db,'demo-test'); restarted.restore_tracking()
    assert len(restarted.history)==4
    evaluate(restarted)
    assert not restarted.active  # Same bar must not revive already closed virtual candidates.
    assert all(r.get('completed_at') for r in db.rows['shadow_outcomes'])
    other=ShadowRuntime(db,'other-account'); other.restore_tracking()
    assert not other.active and not other.history


@pytest.mark.parametrize('direction,price,reason',[('long',98,'sampled_stop'),('short',102,'sampled_stop'),('long',103,'sampled_tp1'),('short',97,'sampled_tp1')])
def test_virtual_quotes_use_close_side_and_sampled_gap(direction,price,reason):
    db=Database(); runtime=ShadowRuntime(db,'test')
    c=dict(candidate_id='test',symbol='EURUSD',strategy='trend_pullback',direction=direction,
           entry=100,stop_loss=99 if direction=='long' else 101,take_profit_1=102 if direction=='long' else 98,
           created_at=NOW.isoformat(),valid_until=(NOW+timedelta(minutes=45)).isoformat(),regime='trend',setup_score=90)
    tracked=dict(candidate=c,mfe_r=0,mae_r=0,session='Europe/London')
    runtime.active[('EURUSD','trend_pullback')]=tracked
    db.rows['shadow_outcomes']=[dict(candidate_id='test')]
    bid,ask = (price,price+.02) if direction=='long' else (price-.02,price)
    runtime.observe('EURUSD',NOW+timedelta(seconds=10),bid,ask)
    row=db.rows['shadow_outcomes'][0]
    assert row['metadata']['exit_reason']==reason
    assert row['realized_r']==pytest.approx((price-100)*(1 if direction=='long' else -1))
    assert not runtime.active


def test_runtime_and_bridge_contain_no_order_api():
    for name in ['main.py','shadow_runtime.py']:
        tree=ast.parse(Path(__file__).with_name(name).read_text())
        assert not any(isinstance(n,ast.Attribute) and n.attr in {'order_send','order_check'} for n in ast.walk(tree))


def load_bridge(monkeypatch):
    import importlib.util
    fake_mt5=SimpleNamespace(ACCOUNT_TRADE_MODE_DEMO=0,TIMEFRAME_M5=5)
    monkeypatch.setitem(sys.modules,'MetaTrader5',fake_mt5)
    spec=importlib.util.spec_from_file_location('test_bridge_main',Path(__file__).with_name('main.py'))
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module,fake_mt5


@pytest.mark.parametrize('tick_mode,bar_mode', [('utc','utc'),('pepperstone_server','utc'),('pepperstone_server','pepperstone_server')])
def test_one_cycle_end_to_end_with_mocked_mt5_and_storage(monkeypatch,capsys,tmp_path,tick_mode,bar_mode):
    bridge,mt5=load_bridge(monkeypatch)
    now=datetime.now(timezone.utc)
    now=now.replace(minute=(now.minute//5)*5,second=0,microsecond=0)
    rates=[dict(time=b.ts.timestamp(),open=b.open,high=b.high,low=b.low,close=b.close,tick_volume=b.volume) for b in bars(now)]
    from zoneinfo import ZoneInfo
    offset=(timedelta(hours=7)+now.astimezone(ZoneInfo('America/New_York')).utcoffset()).total_seconds()
    if bar_mode=='pepperstone_server':
        for row in rates: row['time']+=offset
    db=Database()
    settings=SimpleNamespace(supabase_url='https://example.supabase.co',supabase_service_role_key='not-a-key',
                             mt5_terminal_path='mock',mt5_login=123,mt5_password='local',mt5_server='Pepperstone-Demo',
                             expected_broker='Pepperstone',shadow_analysis_enabled=True,max_tick_age_seconds=60,telemetry_interval_seconds=2,
                             mt5_tick_time_mode=tick_mode, mt5_bar_time_mode='auto')
    account=SimpleNamespace(company='Pepperstone',server=settings.mt5_server,login=123,trade_mode=0,
                            balance=5000,equity=5000,currency='EUR')
    monkeypatch.setattr(bridge,'load_settings',lambda:settings)
    monkeypatch.setattr(bridge,'create_client',lambda *args:db)
    monkeypatch.setattr(bridge,'SYMBOL_ALIASES',{'EURUSD':('EURUSD',)})
    mt5.initialize=lambda **kwargs:True
    mt5.account_info=lambda:account
    mt5.terminal_info=lambda:SimpleNamespace(data_path=str(tmp_path))
    mt5.symbol_info=lambda symbol:SimpleNamespace(visible=True,point=.01)
    mt5.symbol_info_tick=lambda symbol:SimpleNamespace(bid=106,ask=106.02,time_msc=(datetime.now(timezone.utc).timestamp()+(offset if tick_mode=='pepperstone_server' else 0))*1000)
    mt5.positions_get=lambda:()
    mt5.copy_rates_from_pos=lambda *args:rates
    shutdown=[]; mt5.shutdown=lambda:shutdown.append(True)
    bridge.main(once=True)
    assert shutdown==[True]
    assert len(db.rows['market_context'])==1 and len(db.rows['agent_signals'])==9
    import csv
    with (tmp_path/'MQL5/Files/TradingBotShadow/EURUSD.csv').open(encoding='utf-8',newline='') as f:
        frame=list(csv.reader(f,delimiter=';'))
    assert len([r for r in frame if r[0]=='AGENT'])==9
    assert frame[-1]==['END',str(len(frame)-1)]
    assert 'orders=0' in capsys.readouterr().out


@pytest.mark.parametrize('case',['stale','crossed','nan','zero'])
def test_invalid_quote_not_published(monkeypatch,case):
    bridge,mt5=load_bridge(monkeypatch); db=Database()
    point=0 if case=='zero' else .01
    mt5.symbol_info=lambda symbol:SimpleNamespace(point=point)
    bid=float('nan') if case=='nan' else 100
    ask=99 if case=='crossed' else 100.02
    age=120 if case=='stale' else 0
    mt5.symbol_info_tick=lambda symbol:SimpleNamespace(bid=bid,ask=ask,time_msc=(datetime.now(timezone.utc).timestamp()-age)*1000)
    assert bridge.publish_tick(db,'EURUSD','EURUSD') is None
    assert not db.rows


def test_expired_virtual_candidate_and_periodic_checkpoint():
    db=Database(); runtime=ShadowRuntime(db,'test')
    c=dict(candidate_id='expiry',symbol='EURUSD',strategy='trend_pullback',direction='long',
           entry=100,stop_loss=99,take_profit_1=102,created_at=NOW.isoformat(),
           valid_until=(NOW+timedelta(minutes=45)).isoformat(),regime='trend',setup_score=90)
    runtime.active[('EURUSD','trend_pullback')]=dict(candidate=c,mfe_r=0,mae_r=0,session='Europe/London')
    db.rows['shadow_outcomes']=[dict(candidate_id='expiry')]
    runtime.observe('EURUSD',NOW+timedelta(minutes=2),100.5,100.52)
    assert runtime.active and db.rows['shadow_outcomes'][0]['mfe_r']==.5
    runtime.observe('EURUSD',NOW+timedelta(minutes=46),100.2,100.22)
    assert not runtime.active
    assert db.rows['shadow_outcomes'][0]['metadata']['exit_reason']=='horizon_expired'
    assert runtime.history[0].session=='Europe/London'
