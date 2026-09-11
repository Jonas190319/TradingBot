from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import AgentSignal, EconomicEvent, MarketSnapshot, NewsItem, PortfolioState


@dataclass(frozen=True)
class AgentContext:
    market: MarketSnapshot
    economic_events: tuple[EconomicEvent, ...] = ()
    news: tuple[NewsItem, ...] = ()
    portfolio: PortfolioState | None = None


class Agent(Protocol):
    name: str

    def analyze(self, context: AgentContext) -> AgentSignal:
        ...


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def sign(value: float, dead_zone: float = 0.0) -> int:
    if value > dead_zone:
        return 1
    if value < -dead_zone:
        return -1
    return 0


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return (sum((v - m) ** 2 for v in values) / (len(values) - 1)) ** 0.5
