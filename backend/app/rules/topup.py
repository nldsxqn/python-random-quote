"""Play-money auto top-up. This does not move cash."""

from dataclasses import dataclass

from app.engine.actions import IllegalActionError


@dataclass(frozen=True)
class TopUpConfig:
    threshold_bb: int
    target_bb: int


def parse_topup(value: object) -> TopUpConfig:
    if not isinstance(value, dict):
        raise IllegalActionError("auto top-up settings must include threshold_bb and target_bb")
    threshold = value.get("threshold_bb")
    target = value.get("target_bb")
    if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold <= 0:
        raise IllegalActionError("auto top-up threshold_bb must be a positive integer")
    if isinstance(target, bool) or not isinstance(target, int) or target < threshold:
        raise IllegalActionError("auto top-up target_bb must be an integer at least the threshold")
    return TopUpConfig(threshold_bb=threshold, target_bb=target)


def plan_top_up(stack: int, config: TopUpConfig, big_blind: int) -> tuple[int, int]:
    threshold = config.threshold_bb * big_blind
    target = config.target_bb * big_blind
    if stack >= threshold or target <= stack:
        return stack, 0
    return target, target - stack


def apply_top_up(game: object, config: TopUpConfig) -> None:
    added_rows: list[dict[str, int]] = []
    for player in game.players:
        new_stack, added = plan_top_up(player.stack, config, game.big_blind)
        if added:
            player.stack = new_stack
            added_rows.append({"seat": player.seat, "amount": added})
    game.top_ups = added_rows
