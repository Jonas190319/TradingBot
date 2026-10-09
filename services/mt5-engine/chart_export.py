"""Local, read-only chart feed. Contains no keys and no broker order interface."""
import csv
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def file_symbol(symbol):
    return re.sub(r'[^A-Za-z0-9_.-]', '_', symbol)


def epoch(value):
    if not value:
        return 0
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.timestamp()


def field(value):
    return str(value).replace(';', ',').replace('\r', ' ').replace('\n', ' ')


class ChartExporter:
    def __init__(self, data_path, account_ref, universe):
        self.folder = Path(data_path) / 'MQL5' / 'Files' / 'TradingBotShadow'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.account_ref = account_ref
        self.universe = universe
        self.quotes = {}

    def write(self, symbol, runtime, now, quote, status):
        if quote:
            self.quotes[symbol] = quote
        latest = runtime.latest.get(symbol, {}) if runtime else {}
        signals = latest.get('signals', [])
        active = [v for (market, _), v in runtime.active.items() if market == symbol] if runtime else []
        last_quote = self.quotes.get(symbol)
        rows = [['HEADER', '1', self.universe[symbol], self.account_ref, epoch(now),
                 epoch(last_quote[0]) if last_quote else 0, epoch(latest.get('ts')),
                 latest.get('regime', 'unknown'), status, len(signals)]]
        for s in signals:
            rows.append(['AGENT', s['agent_type'], s['direction'], s['confidence'], s['risk_score']])
        for tracked in sorted(active, key=lambda row: row['candidate']['strategy']):
            c = tracked['candidate']
            distance = abs(c['entry']-c['stop_loss'])
            r = 0.0
            if last_quote and distance:
                price = last_quote[1] if c['direction']=='long' else last_quote[2]
                r = (price-c['entry'])/distance*(1 if c['direction']=='long' else -1)
            rows.append(['CANDIDATE', c['candidate_id'], c['strategy'], c['direction'],
                         c['entry'], c['stop_loss'], c['take_profit_1'], c.get('take_profit_2') or 0,
                         c['setup_score'], r, tracked['mfe_r'], tracked['mae_r']])
        rows.append(['END', len(rows)])
        # Reader accepts only complete frames; atomic replacement preserves the old
        # valid frame if Windows briefly denies replacement while MT5 reads it.
        destination = self.folder / (file_symbol(self.universe[symbol]) + '.csv')
        temp = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='',
                                             dir=self.folder, suffix='.tmp', delete=False) as out:
                temp = Path(out.name)
                csv.writer(out, delimiter=';', lineterminator='\r\n').writerows(
                    [[field(v) for v in row] for row in rows])
            os.replace(temp, destination)
        finally:
            if temp and temp.exists():
                temp.unlink()
