"""The room's selected rules. Disabled keys stay off and do not change the hand."""

from dataclasses import dataclass, replace

from app.engine.actions import IllegalActionError
from app.engine.plugins import HandRules
from app.rules.ante import AnteConfig, parse_ante, post_ante
from app.rules.bomb import BombConfig, parse_bomb, post_bomb
from app.rules.bounty import BountyConfig, apply_bounty, parse_bounty
from app.rules.buyin import BuyInConfig, parse_buyin
from app.rules.insurance import quote as insurance_quote
from app.rules.rake import RakeConfig, apply_rake, parse_rake
from app.rules.run_it_twice import eligible_for_offer, execute
from app.rules.straddle import StraddleConfig, parse_straddle, post_straddle
from app.rules.timebank import TimeBankConfig, parse_time_bank
from app.rules.topup import TopUpConfig, apply_top_up, parse_topup


@dataclass
class SelectedRules(HandRules):
    ante: AnteConfig | None = None
    straddle: StraddleConfig | None = None
    buy_in: BuyInConfig | None = None
    top_up: TopUpConfig | None = None
    time_bank: TimeBankConfig | None = None
    bounty: BountyConfig | None = None
    rake: RakeConfig | None = None
    bomb: BombConfig | None = None
    run_it_twice: bool = False
    insurance: bool = False
    spec: dict | None = None

    def for_engine(self) -> "SelectedRules":
        """Top-up, buy-in, and the clock are applied by the room, once."""
        return replace(self, top_up=None, buy_in=None, time_bank=None, spec=None)

    def apply_top_up(self, game: object) -> None:
        if self.top_up is not None:
            apply_top_up(game, self.top_up)

    def uses_bomb_pot(self, game: object) -> bool:
        return self.bomb is not None

    def post_bomb(self, game: object) -> None:
        if self.bomb is not None:
            post_bomb(game, self.bomb)

    def post_ante(self, game: object) -> None:
        if self.ante is not None:
            post_ante(game, self.ante)

    def post_straddle(self, game: object) -> None:
        if self.straddle is not None:
            post_straddle(game, self.straddle)

    def board_count(self, game: object) -> int:
        if self.bomb is None:
            return 1
        return self.bomb.boards

    def should_offer_insurance(self, game: object) -> bool:
        return self.insurance

    def insurance_quote(self, game: object) -> dict | None:
        if not self.insurance:
            return None
        return insurance_quote(game)

    def should_offer_run_it_twice(self, game: object) -> bool:
        return self.run_it_twice and eligible_for_offer(game)

    def resolve_run_it_twice(self, game: object, accepted: bool) -> None:
        if not accepted:
            game.rit_declined = True
            game.rit_result = {"accepted": False, "runs": []}
            game._autopilot()
            return
        execute(game, self.rake, self.bounty)

    def apply_rake(self, game: object, pots: list) -> list:
        if self.rake is None:
            return pots
        return apply_rake(game, self.rake, pots)

    def apply_bounty(self, game: object, winners: set[int]) -> None:
        if self.bounty is None:
            return
        apply_bounty(game, self.bounty, winners)


def parse_rules(spec: dict | None) -> SelectedRules:
    if not spec:
        return SelectedRules(spec={})
    if not isinstance(spec, dict):
        raise IllegalActionError("rules must be an object")
    rules = SelectedRules(
        ante=_optional("ante", spec, parse_ante),
        straddle=_optional("straddle", spec, parse_straddle),
        buy_in=_optional("buy_in", spec, parse_buyin),
        top_up=_optional("auto_top_up", spec, parse_topup),
        time_bank=_optional("time_bank", spec, parse_time_bank),
        bounty=_optional("seven_deuce", spec, parse_bounty),
        rake=_optional("rake", spec, parse_rake),
        bomb=_optional("bomb_pot", spec, parse_bomb),
        run_it_twice=_flag(spec.get("run_it_twice", False)),
        insurance=_insurance_flag(spec.get("insurance", False)),
        spec=dict(spec),
    )
    if rules.bomb is not None and rules.straddle is not None:
        raise IllegalActionError("a bomb pot starts on the flop, so a straddle is not available")
    return rules


def merge_rules(current: dict, patch: dict) -> dict:
    if not isinstance(patch, dict):
        raise IllegalActionError("rules must be an object")
    merged = dict(current)
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    parse_rules(merged)
    return merged


def _optional(key: str, spec: dict, parser):
    if key not in spec or spec[key] is None:
        return None
    return parser(spec[key])


def _flag(value: object) -> bool:
    if not isinstance(value, bool):
        raise IllegalActionError("run_it_twice must be true or false")
    return value


def _insurance_flag(value: object) -> bool:
    if value is False or value is None:
        return False
    if value is True:
        return True
    raise IllegalActionError("insurance must be true or false")
