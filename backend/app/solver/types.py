"""Solver inputs and outputs. This is one decision, not a full-game solve."""

from dataclasses import dataclass, field


@dataclass
class SolveRequest:
    game_type: str = "nlhe"
    players: int = 2
    board: str = ""
    pot: int = 0
    effective_stack: int = 0
    hero_position: str = ""
    villain_position: str = ""
    hero_range: str = ""
    villain_range: str = ""
    action_history: list = field(default_factory=list)
    bet_sizes: list = field(default_factory=list)
    iterations: int = 160
    samples: int = 12

    def to_dict(self) -> dict:
        return {
            "game_type": self.game_type,
            "players": self.players,
            "board": self.board,
            "pot": self.pot,
            "effective_stack": self.effective_stack,
            "hero_position": self.hero_position,
            "villain_position": self.villain_position,
            "hero_range": self.hero_range,
            "villain_range": self.villain_range,
            "action_history": list(self.action_history),
            "bet_sizes": list(self.bet_sizes),
        }


@dataclass
class SolveResult:
    actions: list[str]
    frequencies: dict[str, float]
    evs: dict[str, float]
    strategy: dict
    exploitability: float | None
    metadata: dict

    def to_dict(self) -> dict:
        return {
            "actions": list(self.actions),
            "frequencies": dict(self.frequencies),
            "evs": dict(self.evs),
            "strategy": self.strategy,
            "exploitability": self.exploitability,
            "metadata": dict(self.metadata),
        }
