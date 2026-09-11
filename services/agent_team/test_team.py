from datetime import datetime, timedelta, timezone

from .base import AgentContext
from .execution_agent import ExecutionPolicy
from .models import Bar, MarketSnapshot, PortfolioState
from .orchestrator import ExpertTeam


def _bars(up: bool = True, n: int = 80):
    now = datetime.now(timezone.utc)
    bars = []
    price = 1.1000
    step = 0.0004 if up else -0.0004
    for i in range(n):
        open_ = price
        close = price + step
        high = max(open_, close) + 0.0002
        low = min(open_, close) - 0.0002
        bars.append(Bar(now - timedelta(minutes=(n - i) * 5), open_, high, low, close, 1000))
        price = close
    return tuple(bars)


def test_off_mode_never_executes():
    bars = _bars(True)
    market = MarketSnapshot("EURUSD", datetime.now(timezone.utc), bars[-1].close - 0.00005,
                            bars[-1].close + 0.00005, bars=bars, spread_points=10)
    portfolio = PortfolioState(equity=10000, balance=10000)
    team = ExpertTeam(execution_policy=ExecutionPolicy(mode="OFF"))
    result = team.run(AgentContext(market=market, portfolio=portfolio))
    assert result.execution.executable is False


def test_daily_loss_limit_vetoes_even_good_setup():
    bars = _bars(True)
    market = MarketSnapshot("EURUSD", datetime.now(timezone.utc), bars[-1].close - 0.00005,
                            bars[-1].close + 0.00005, bars=bars, spread_points=10)
    portfolio = PortfolioState(equity=9850, balance=10000, daily_pnl_pct=-1.6)
    team = ExpertTeam(execution_policy=ExecutionPolicy(mode="DEMO"), min_quality=0)
    result = team.run(AgentContext(market=market, portfolio=portfolio))
    assert result.execution.executable is False
    assert result.decision.risk_verdict.hard_veto is True


def test_live_requires_second_enable_flag():
    bars = _bars(True)
    market = MarketSnapshot("EURUSD", datetime.now(timezone.utc), bars[-1].close - 0.00005,
                            bars[-1].close + 0.00005, bars=bars, spread_points=10)
    portfolio = PortfolioState(equity=10000, balance=10000)
    team = ExpertTeam(execution_policy=ExecutionPolicy(mode="LIVE", live_execution_enabled=False), min_quality=0)
    result = team.run(AgentContext(market=market, portfolio=portfolio))
    assert result.execution.executable is False
