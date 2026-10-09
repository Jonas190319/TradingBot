import csv
from pathlib import Path
from types import SimpleNamespace

import pytest

from chart_export import ChartExporter
from test_shadow import NOW, Database, ShadowRuntime, evaluate


def read(exporter):
    with (exporter.folder/'EURUSD.csv').open(encoding='utf-8',newline='') as f:
        return list(csv.reader(f,delimiter=';'))


def test_feed_exports_nine_agents_and_complete_frame_without_credentials(tmp_path):
    db=Database(); runtime=ShadowRuntime(db,'Pepperstone-Demo:123'); evaluate(runtime)
    feed=ChartExporter(tmp_path,'Pepperstone-Demo:123',{'EURUSD':'EURUSD'})
    feed.write('EURUSD',runtime,NOW,(NOW,106,106.02,.01),'observing')
    rows=read(feed)
    assert rows[0][:4]==['HEADER','1','EURUSD','Pepperstone-Demo:123']
    assert rows[0][9]=='9'
    assert len([r for r in rows if r[0]=='AGENT'])==9
    assert rows[-1]==['END',str(len(rows)-1)]
    assert not list(feed.folder.glob('*.tmp'))
    text=(feed.folder/'EURUSD.csv').read_text()
    assert 'SUPABASE' not in text and 'password' not in text and 'sb_secret' not in text


@pytest.mark.parametrize('direction,expected_r',[('long',.5),('short',-.52)])
def test_active_candidate_prices_and_sampled_r(tmp_path,direction,expected_r):
    runtime=SimpleNamespace(latest={},active={('EURUSD','trend_pullback'):dict(
        candidate=dict(candidate_id='test',strategy='trend_pullback',direction=direction,
                       entry=100,stop_loss=99,take_profit_1=102,take_profit_2=103,setup_score=90),mfe_r=.6,mae_r=-.2)})
    feed=ChartExporter(tmp_path,'demo',{'EURUSD':'EURUSD'})
    feed.write('EURUSD',runtime,NOW,(NOW,100.5,100.52,.01),'observing')
    row=next(r for r in read(feed) if r[0]=='CANDIDATE')
    assert len(row)==12 and row[4:8]==['100','99','102','103']
    assert float(row[9])==pytest.approx(expected_r)


def test_missing_quote_keeps_actual_old_timestamp_and_warning(tmp_path):
    feed=ChartExporter(tmp_path,'demo',{'EURUSD':'EURUSD'})
    feed.write('EURUSD',None,NOW,(NOW,100,101,1),'ready')
    from datetime import timedelta
    feed.write('EURUSD',None,NOW+timedelta(minutes=2),None,'no fresh quote; orders disabled')
    rows=read(feed)
    assert float(rows[0][4])-float(rows[0][5])==120
    assert rows[0][8]=='no fresh quote, orders disabled'  # Protocol delimiter cannot leak into fields.


def test_atomic_failure_preserves_previous_valid_frame(tmp_path,monkeypatch):
    import chart_export
    feed=ChartExporter(tmp_path,'demo',{'EURUSD':'EURUSD'})
    feed.write('EURUSD',None,NOW,None,'waiting')
    original=(feed.folder/'EURUSD.csv').read_bytes()
    def denied(*args): raise PermissionError('reader busy')
    monkeypatch.setattr(chart_export.os,'replace',denied)
    with pytest.raises(PermissionError): feed.write('EURUSD',None,NOW,None,'new')
    assert (feed.folder/'EURUSD.csv').read_bytes()==original
    assert not list(feed.folder.glob('*.tmp'))


def test_indicator_is_read_only_and_has_stale_account_and_frame_guards():
    source=(Path(__file__).resolve().parents[2]/'mt5/Indicators/TradingBotShadow.mq5').read_text()
    assert not any(token in source for token in ['OrderSend(', 'OrderSendAsync(', 'CTrade', '#import', 'WebRequest('])
    assert 'ACCOUNT_TRADE_MODE_DEMO' in source and 'head[3]!=account' in source
    assert 'age>30' in source and 'quote_age<=60' in source and 'tail[0]!="END"' in source
