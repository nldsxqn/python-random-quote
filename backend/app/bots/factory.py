"""Build the three bots the host can seat."""

from app.bots.base import PokerBot
from app.bots.equity_bot import EquityBot
from app.bots.rule_bot import RuleBot
from app.bots.strategy import StrategyBot, load_fixture_store

_KINDS = {"rule", "equity", "strategy"}


def make_bot(kind: str, seed: int = 0) -> PokerBot:
    name = kind.strip().lower()
    if name == "rule":
        return RuleBot(seed=seed)
    if name == "equity":
        return EquityBot(seed=seed, simulation_count=40)
    if name == "strategy":
        fallback = EquityBot(seed=seed, simulation_count=20, bluff_frequency=0.0)
        return StrategyBot(load_fixture_store(), fallback, seed=seed)
    known = ", ".join(sorted(_KINDS))
    raise ValueError(f"unknown bot {kind!r}; expected {known}")
