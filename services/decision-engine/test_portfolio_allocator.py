from dataclasses import dataclass

from portfolio_allocator import OpenExposure, PortfolioAllocator


@dataclass
class Candidate:
    candidate_id: str
    symbol: str
    strategy: str
    setup_score: float
    rr: float


@dataclass
class Committee:
    score: float


@dataclass
class Risk:
    approved: bool
    risk_pct: float


@dataclass
class Result:
    candidate: Candidate
    committee: Committee
    risk: Risk


def make(cid, symbol, score, risk=0.35, strategy="opening_range", rr=2.0):
    return Result(Candidate(cid, symbol, strategy, score, rr), Committee(score), Risk(True, risk))


def test_selects_only_best_five():
    allocator = PortfolioAllocator(max_same_factor_positions=10)
    candidates = [
        make("a", "EURUSD", 96),
        make("b", "USDJPY", 94),
        make("c", "XAUUSD", 92),
        make("d", "GER40", 90),
        make("e", "NAS100", 88),
        make("f", "GBPUSD", 80),
    ]
    plan = allocator.allocate(candidates)
    assert len(plan.selected) == 4  # 4 x .35 = 1.40%; fifth would exceed 1.50%
    assert plan.total_risk_pct <= 1.50


def test_does_not_force_five_positions():
    allocator = PortfolioAllocator(max_same_factor_positions=10)
    candidates = [make("a", "EURUSD", 95), make("b", "USDJPY", 50)]
    plan = allocator.allocate(candidates)
    assert [x.candidate.candidate_id for x in plan.selected] == ["a"]


def test_existing_positions_are_not_replaced():
    allocator = PortfolioAllocator(max_open_positions=5, max_same_factor_positions=10)
    open_positions = [OpenExposure(f"S{i}", "opening_range", 0.2) for i in range(5)]
    plan = allocator.allocate([make("new", "EURUSD", 99)], open_positions)
    assert not plan.selected
    assert any(d.candidate_id == "new" and "Maximum open positions" in d.reason for d in plan.decisions)


def test_correlated_factor_limit_blocks_extra_usd_exposure():
    allocator = PortfolioAllocator(max_same_factor_positions=2)
    open_positions = [
        OpenExposure("EURUSD", "opening_range", 0.25),
        OpenExposure("USDJPY", "opening_range", 0.25),
    ]
    plan = allocator.allocate([make("new", "GBPUSD", 99)], open_positions)
    assert not plan.selected
    assert any("Correlated factor exposure" in d.reason for d in plan.decisions)
