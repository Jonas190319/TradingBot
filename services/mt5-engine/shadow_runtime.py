"""Expert team -> four strategists -> persisted SHADOW proposals. No broker orders."""
from dataclasses import asdict, replace
from collections import deque
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from services.agent_team.base import AgentContext
from services.agent_team.execution_agent import ExecutionPolicy
from services.agent_team.improvement_agent import ImprovementAgent, TradeRecord
from services.agent_team.models import AgentSignal, Direction, MarketSnapshot, PortfolioState
from services.agent_team.orchestrator import ExpertTeam
from services.decision_engine.models import AnalystView, Direction as StrategyDirection
from services.decision_engine.models import MarketSnapshot as StrategySnapshot, Regime
from services.decision_engine.orchestrator import ExpertTeamOrchestrator
from services.decision_engine.risk_manager import PortfolioState as StrategyPortfolio
from market_features import build_features


def jsonable(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if hasattr(value, 'value'):
        return value.value
    if hasattr(value, '__dataclass_fields__'):
        return jsonable(asdict(value))
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(v) for v in value]
    return value


class ShadowRuntime:
    def __init__(self, sb, account_key):
        self.sb = sb
        self.account_key = account_key
        self.team = ExpertTeam(execution_policy=ExecutionPolicy(mode='OFF'))
        self.strategies = ExpertTeamOrchestrator()
        self.improvement = ImprovementAgent()
        self.completed = {}
        self.history = []
        self.active = {}
        self.retired = deque(maxlen=5000)
        self.latest = {}

    def evaluate(self, symbol, now, bid, ask, point, bars, account, open_positions):
        if self.completed.get(symbol) == bars[-1].ts:
            return None
        features = build_features(symbol, now, bars)
        features['news_feed_connected'] = False
        features['macro_feed_connected'] = False
        spread = (ask-bid)/point
        portfolio = PortfolioState(equity=float(account.equity), balance=float(account.balance),
                                   open_positions=open_positions)
        market = MarketSnapshot(symbol, now, bid, ask, bars=bars, atr=features['atr'],
                                spread_points=spread, session=features['session'], extra=features)
        team_result = self.team.run(AgentContext(market=market, portfolio=portfolio))
        signals = list(team_result.signals)
        # An absent feed is an unknown risk, never evidence that no news exists.
        for i, signal in enumerate(signals):
            if signal.agent_type in {'news', 'macro'}:
                signals[i] = replace(signal, direction=Direction.NO_TRADE, confidence=100,
                                     risk_score=100, recommendation='SHADOW only: external feed missing',
                                     rationale='No authenticated news/economic calendar feed is configured.',
                                     payload={'feed_status': 'not_configured'})
        raw_regime = next(s.payload.get('regime', 'unknown') for s in signals if s.agent_type == 'regime')
        regime = Regime.DISLOCATION if raw_regime == 'chaos' else Regime(raw_regime)
        snapshot = StrategySnapshot(now, symbol, bid, ask, ask-bid, features)
        views = [AnalystView(s.agent_type, symbol, StrategyDirection(s.direction.value),
                             s.confidence, s.rationale, s.payload) for s in signals]
        # Historical drawdown/loss and stop-risk metrics are not yet reconciled.
        # Fail closed for funding rather than fabricate zero portfolio risk.
        state = StrategyPortfolio(float(account.equity), 0, 0, 0, 1.5, 0)
        candidates = [] if regime in {Regime.DISLOCATION, Regime.UNKNOWN, Regime.NEWS} else self.strategies.evaluate_market(snapshot, regime, views, state)
        evaluation_id = str(uuid5(NAMESPACE_URL, f'{self.account_key}:{symbol}:{bars[-1].ts.isoformat()}:shadow-v1'))
        events = []
        for result in candidates:
            old_id = result.candidate.candidate_id
            candidate_id = str(uuid5(NAMESPACE_URL, f'{evaluation_id}:{result.candidate.strategy}'))
            result.candidate.candidate_id = candidate_id
            result.committee.candidate_id = candidate_id
            result.pretrade_summary['candidate_id'] = candidate_id
            for event in self.strategies.pretrade.events.pop(old_id, []):
                row = event.to_dict()
                events.append(dict(candidate_id=candidate_id, ts=row['ts'], symbol=symbol,
                                   strategy=row['strategy'], stage=row['stage'], score=row['score'],
                                   bid=bid, ask=ask, spread=ask-bid, features=features, notes=row['notes']))
        allocation = self.strategies.allocate_portfolio(candidates)
        issues = ['execution_disabled', 'news_feed_missing', 'macro_feed_missing', 'portfolio_risk_history_unreconciled']
        summary = dict(mode='SHADOW', executable=False, account_ref=self.account_key,
                       bar_ts=bars[-1].ts.isoformat(), timeframe='M5', features=features,
                       regime=raw_regime, limitations=issues,
                       portfolio={'equity': portfolio.equity, 'balance': portfolio.balance,
                                  'open_positions': open_positions, 'risk_history_complete': False},
                       expert_portfolio_advisory=jsonable(team_result.decision),
                       candidates=jsonable(candidates), allocation=jsonable(allocation))
        top = candidates[0].candidate if candidates else None
        reason = f'SHADOW only; {len(candidates)} candidates; no orders; external feeds and complete portfolio risk data missing'
        decision = dict(id=evaluation_id, ts=now.isoformat(), symbol=symbol,
                        decision='no_trade', direction=top.direction.value if top else 'neutral',
                        quality_score=top.setup_score if top else 0, risk_pct=0,
                        proposed_entry=top.entry if top else None, proposed_sl=top.stop_loss if top else None,
                        proposed_tp=top.take_profit_1 if top else None, reason=reason, signal_snapshot=summary)
        extra = [
            AgentSignal(now, symbol, 'portfolio', Direction.NO_TRADE, 100, 100, 'Observe proposals only', reason,
                        {'allocation': jsonable(allocation), 'execution_enabled': False}),
            AgentSignal(now, symbol, 'risk', Direction.NO_TRADE, 100, 100, 'Funding veto',
                        'External feeds and historical portfolio risk metrics are incomplete.', {'hard_veto': True}),
            AgentSignal(now, symbol, 'execution', Direction.NO_TRADE, 100, 0, 'Execution disabled',
                        'This runtime has no order API.', {'executable': False, 'mode': 'OFF'}),
            AgentSignal(now, symbol, 'improvement', Direction.NEUTRAL, 0, 0, 'Research recommendations only',
                        'Sampled virtual outcomes are not realized broker trades.',
                        {'recommendations': jsonable(self.improvement.analyze(self.history)), 'sample_count': len(self.history)})
        ]
        signals += extra
        self.sb.table('trade_decisions').upsert(jsonable(decision), on_conflict='id').execute()
        rows = [dict(s.to_dict(), evaluation_id=evaluation_id) for s in signals]
        self.sb.table('agent_signals').upsert(jsonable(rows), on_conflict='evaluation_id,agent_type').execute()
        if events:
            self.sb.table('pretrade_events').upsert(jsonable(events), on_conflict='candidate_id,stage,ts').execute()
        # At most one active virtual candidate per symbol/strategy. Research only.
        for result in candidates:
            c = result.candidate
            key = (symbol, c.strategy)
            if key in self.active or c.candidate_id in self.retired:
                continue
            tracking = dict(candidate=c.to_dict(), mfe_r=0.0, mae_r=0.0,
                            account_ref=self.account_key,
                            session=features['session'],
                            last_observed_ts=now.isoformat(), sampled=True,
                            sampling_limit='Only sampled quotes; no fill, fees, slippage or intratick path reconstruction',
                            committee_score=result.committee.score)
            self.sb.table('shadow_outcomes').upsert(dict(candidate_id=c.candidate_id,
                strategy=c.strategy, symbol=symbol, regime=c.regime.value, session=features['session'],
                direction=c.direction.value, was_executed=False, committee_score=result.committee.score,
                setup_score=c.setup_score, metadata=jsonable(tracking)), on_conflict='candidate_id').execute()
            self.active[key] = tracking
        self.completed[symbol] = bars[-1].ts
        self.latest[symbol] = dict(ts=now.isoformat(), regime=raw_regime, signals=jsonable(rows))
        return dict(evaluation_id=evaluation_id, candidates=len(candidates), signals=len(signals), regime=raw_regime)

    def restore_tracking(self):
        rows = self.sb.table('shadow_outcomes').select('*').is_('completed_at', 'null').execute().data
        for row in rows:
            metadata = row.get('metadata') or {}
            if 'candidate' not in metadata:
                continue
            if metadata.get('account_ref') != self.account_key:
                continue
            metadata['resumed_after_restart'] = True
            self.active[(row['symbol'], row['strategy'])] = metadata
        outcomes = self.sb.table('shadow_outcomes').select('*').not_.is_('completed_at', 'null').order('completed_at', desc=True).limit(5000).execute().data
        for row in reversed(outcomes):
            if (row.get('metadata') or {}).get('account_ref') == self.account_key:
                self.retired.append(row['candidate_id'])
                self.history.append(TradeRecord(row['strategy'], row['symbol'], row['regime'],
                                                row.get('session') or 'unknown', float(row['realized_r'] or 0),
                                                quality_score=float(row['setup_score'] or 0)))

    def observe(self, symbol, now, bid, ask):
        for key, tracked in list(self.active.items()):
            if key[0] != symbol:
                continue
            c = tracked['candidate']
            long = c['direction'] == 'long'
            price = bid if long else ask
            distance = abs(c['entry']-c['stop_loss'])
            if distance <= 0:
                continue
            r = (price-c['entry'])/distance*(1 if long else -1)
            tracked['mfe_r'] = max(tracked['mfe_r'], r)
            tracked['mae_r'] = min(tracked['mae_r'], r)
            tracked['last_observed_ts'] = now.isoformat()
            tracked['account_ref'] = self.account_key
            stopped = price <= c['stop_loss'] if long else price >= c['stop_loss']
            target = price >= c['take_profit_1'] if long else price <= c['take_profit_1']
            expired = now >= datetime.fromisoformat(c['valid_until'])
            if not (stopped or target or expired):
                checkpoint = tracked.get('checkpoint_ts', c['created_at'])
                if (now-datetime.fromisoformat(checkpoint)).total_seconds() >= 60:
                    tracked['checkpoint_ts'] = now.isoformat()
                    self.sb.table('shadow_outcomes').update(dict(mfe_r=tracked['mfe_r'],
                        mae_r=tracked['mae_r'], metadata=jsonable(tracked))).eq('candidate_id', c['candidate_id']).execute()
                continue
            tracked['exit_reason'] = 'sampled_stop' if stopped else 'sampled_tp1' if target else 'horizon_expired'
            tracked['exit_price'] = price
            self.sb.table('shadow_outcomes').update(dict(realized_r=r, mfe_r=tracked['mfe_r'],
                mae_r=tracked['mae_r'], completed_at=now.isoformat(), metadata=jsonable(tracked))).eq('candidate_id', c['candidate_id']).execute()
            self.history.append(TradeRecord(c['strategy'], symbol, c['regime'], tracked.get('session', 'unknown'), r,
                                            quality_score=c['setup_score']))
            self.history = self.history[-5000:]
            self.retired.append(c['candidate_id'])
            del self.active[key]
