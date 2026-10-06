"""Statistics from stored hands only. Reserved player_statistics stays empty.

Definitions, using only rows written at hand completion:

- Hands played: hands in which the player was dealt cards.
- VPIP: hands where the player voluntarily put chips in preflop, divided by hands
  played. A call, bet, raise, or all-in counts. A blind, ante, straddle, bomb,
  check, or fold does not.
- PFR: hands where the player raised preflop, divided by hands played. A raise,
  or an all-in that increased the current bet, counts. A call, including a short
  all-in that only calls, does not.
- 3Bet: preflop raises made while facing exactly one earlier raise, divided by
  the times the player faced exactly one earlier raise. An open is not a 3-bet.
  A 4-bet is not a 3-bet. The value is null when the player had no such chance.
- CBet: flops where the last preflop raiser bet before anyone else bet the flop,
  divided by the flops where that player could still be first to bet. The value
  is null when there was no chance.
- BB/100: sum of (ending stack - starting stack) / big blind, divided by hands
  played, times 100. The chip change includes bounty transfers and rake, because
  those already sit in the ending stack.
- Fold to 3-bet: preflop folds while facing a 3-bet, divided by times the player
  faced a 3-bet. Null when there was no chance.
- WTSD: hands that reached showdown, divided by hands that saw a flop. Null when
  the player saw no flop. A flop was seen when the player did not fold preflop
  and the hand has a later-street action or stored flop cards.
- WSSD: showdowns where the ending stack is greater than the starting stack,
  divided by showdowns. Null when there was no showdown.
- Aggression factor: (bets + raises) / calls. Folds and checks are ignored. An
  all-in that raises counts as a raise. An all-in that does not raise counts as
  a call. Null when there were no calls. This is a ratio, not a percent.
- Fold to c-bet: folds facing the flop continuation bet, divided by times the
  player faced that bet. Null when there was no chance.
- ev_bb, gto_ev_bb, ev_loss_bb: sums of stored decision_analysis rows for the
  same player sample, in big blinds. Chosen EV is the stored chip EV divided by
  that hand's big blind. GTO EV is that value plus the stored ev_loss, which is
  already in big blinds. A missing stored number is skipped, not replaced. The
  field is null when the player has no analyzed decisions, or when none of those
  rows store the number.
- mistake_counts: counts of stored severity values. Zeros when there are no rows.

Filters keep a hand only when the player, position, date, blinds, and rule
settings all match. Dates compare the UTC calendar day of completion. Rule
settings match the canonical JSON object stored with the hand. An omitted filter
does not restrict that field. An optional street keeps hands that have an action
on that street. Aggression and the analysis sums then use only that street.
"""

from sqlalchemy import select

from app.database.models import ActionRow, BoardRow, DecisionAnalysis, Hand, HandPlayer
from app.history.store import HandHistory, canonical_rules

DEFINITIONS = {
    "hands_played": "Hands in which the player was dealt cards.",
    "vpip": "Percent of hands with a voluntary preflop call, bet, raise, or all-in.",
    "pfr": "Percent of hands with a preflop raise, including an all-in that raises.",
    "three_bet": "Percent of chances to reraise the first preflop raise. Null if none.",
    "cbet": "Percent of chances the preflop raiser was first to bet the flop. Null if none.",
    "bb_per_100": "Net chips, including bounty and rake, in big blinds per 100 hands.",
    "fold_to_3bet": "Percent of preflop folds while facing a 3-bet. Null if no chance.",
    "wtsd": "Percent of flop hands that reached showdown. Null if the player saw no flop.",
    "wssd": "Percent of showdowns won by ending stack. Null if there was no showdown.",
    "aggression_factor": "(Bets + raises) / calls. Null if there were no calls.",
    "fold_to_cbet": "Percent of folds facing the flop continuation bet. Null if no chance.",
    "ev_bb": "Sum of stored chosen-action EV, in big blinds. Null if no analyzed decision.",
    "gto_ev_bb": "Sum of stored chosen EV plus EV loss, in big blinds. Null if unavailable.",
    "ev_loss_bb": "Sum of stored EV loss, in big blinds. Null if no analyzed decision.",
    "mistake_counts": "Counts of Good, Small, Medium, Large, and Critical. Zeros if no rows.",
}

_MISTAKE_KEYS = ("good", "small", "medium", "large", "critical")


def statistics(
    history: HandHistory,
    *,
    player: str | None = None,
    position: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    small_blind: int | None = None,
    big_blind: int | None = None,
    rules: str | None = None,
    street: str | None = None,
) -> dict:
    wanted_rules = None if rules is None or rules == "" else canonical_rules(_parse_rules(rules))
    wanted_street = None if street is None or street == "" else street.upper()
    with history.sessions() as session:
        rows = list(session.scalars(select(HandPlayer)))
        hands = {hand.id: hand for hand in session.scalars(select(Hand))}
        actions = list(session.scalars(select(ActionRow).order_by(ActionRow.order_index)))
        boards = list(session.scalars(select(BoardRow)))
        decisions = list(session.scalars(select(DecisionAnalysis)))
    grouped: dict[int, list[ActionRow]] = {}
    for action in actions:
        grouped.setdefault(action.hand_id, []).append(action)
    flop_hands = {board.hand_id for board in boards if board.flop}

    played = 0
    vpip = 0
    pfr = 0
    three_chances = 0
    three_bets = 0
    cbet_chances = 0
    cbets = 0
    fold3_chances = 0
    fold3 = 0
    flops_seen = 0
    showdowns = 0
    showdown_wins = 0
    aggressive = 0
    calls = 0
    fold_cbet_chances = 0
    fold_cbets = 0
    bb_total = 0.0
    included: set[tuple[int, int]] = set()
    for row in rows:
        hand = hands.get(row.hand_id)
        if hand is None or not _matches(
            hand,
            row,
            player=player,
            position=position,
            date_from=date_from,
            date_to=date_to,
            small_blind=small_blind,
            big_blind=big_blind,
            rules=wanted_rules,
        ):
            continue
        hand_actions = grouped.get(hand.id, [])
        if wanted_street is not None and not any(
            action.street.upper() == wanted_street for action in hand_actions
        ):
            continue
        played += 1
        included.add((hand.id, row.seat))
        if _vpip(hand_actions, row.seat):
            vpip += 1
        if _pfr(hand_actions, row.seat):
            pfr += 1
        chance, made = _three_bet(hand_actions, row.seat)
        three_chances += chance
        three_bets += made
        chance, made = _cbet(hand_actions, row.seat)
        cbet_chances += chance
        cbets += made
        chance, made = _fold_to_3bet(hand_actions, row.seat)
        fold3_chances += chance
        fold3 += made
        reached = _reached_flop(hand_actions, hand.id in flop_hands)
        if _saw_flop(hand_actions, row.seat, reached):
            flops_seen += 1
            if _showdown(hand, row, hand_actions):
                showdowns += 1
                if row.ending_stack > row.starting_stack:
                    showdown_wins += 1
        bets, street_calls = _aggression(hand_actions, row.seat, wanted_street)
        aggressive += bets
        calls += street_calls
        chance, made = _fold_to_cbet(hand_actions, row.seat)
        fold_cbet_chances += chance
        fold_cbets += made
        if hand.big_blind:
            bb_total += (row.ending_stack - row.starting_stack) / hand.big_blind
    sample = [
        decision
        for decision in decisions
        if (decision.hand_id, decision.seat) in included
        and (
            wanted_street is None
            or (decision.street or "").upper() == wanted_street
        )
    ]
    ev_bb, gto_ev_bb, ev_loss_bb, mistakes = _analysis_totals(sample, hands)
    return {
        "hands_played": played,
        "vpip": _percent(vpip, played),
        "pfr": _percent(pfr, played),
        "three_bet": _percent(three_bets, three_chances),
        "three_bet_opportunities": three_chances,
        "cbet": _percent(cbets, cbet_chances),
        "cbet_opportunities": cbet_chances,
        "bb_per_100": None if played == 0 else (bb_total / played) * 100,
        "fold_to_3bet": _percent(fold3, fold3_chances),
        "wtsd": _percent(showdowns, flops_seen),
        "wssd": _percent(showdown_wins, showdowns),
        "aggression_factor": None if calls == 0 else aggressive / calls,
        "fold_to_cbet": _percent(fold_cbets, fold_cbet_chances),
        "ev_bb": ev_bb,
        "gto_ev_bb": gto_ev_bb,
        "ev_loss_bb": ev_loss_bb,
        "mistake_counts": mistakes,
        "definitions": DEFINITIONS,
    }


def _parse_rules(value: str) -> dict:
    import json

    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("rules filter must be a JSON object")
    return parsed


def _matches(
    hand: Hand,
    row: HandPlayer,
    *,
    player: str | None,
    position: str | None,
    date_from: str | None,
    date_to: str | None,
    small_blind: int | None,
    big_blind: int | None,
    rules: str | None,
) -> bool:
    if player is not None and row.nickname != player:
        return False
    if position is not None and row.position != position:
        return False
    day = hand.completed_at[:10]
    if date_from is not None and day < date_from:
        return False
    if date_to is not None and day > date_to:
        return False
    if small_blind is not None and hand.small_blind != small_blind:
        return False
    if big_blind is not None and hand.big_blind != big_blind:
        return False
    if rules is not None and canonical_rules(hand.rule_settings) != rules:
        return False
    return True


def _percent(count: int, total: int) -> float | None:
    if total == 0:
        return None
    return (count / total) * 100


def _vpip(actions: list[ActionRow], seat: int) -> bool:
    return any(
        action.seat == seat and action.street == "PREFLOP" and action.action in {
            "call",
            "bet",
            "raise",
            "all_in",
        }
        for action in actions
    )


def _pfr(actions: list[ActionRow], seat: int) -> bool:
    return any(
        action.seat == seat and action.street == "PREFLOP" and action.raised
        for action in actions
    )


def _three_bet(actions: list[ActionRow], seat: int) -> tuple[int, int]:
    raises = 0
    chance = 0
    made = 0
    for action in actions:
        if action.street != "PREFLOP":
            continue
        if action.seat == seat and raises == 1 and chance == 0:
            chance = 1
            if action.raised:
                made = 1
        if action.raised:
            raises += 1
    return chance, made


def _cbet(actions: list[ActionRow], seat: int) -> tuple[int, int]:
    aggressor = None
    for action in actions:
        if action.street == "PREFLOP" and action.raised:
            aggressor = action.seat
    if aggressor != seat:
        return 0, 0
    flop_bet = False
    chance = 0
    made = 0
    for action in actions:
        if action.street != "FLOP":
            continue
        is_open_bet = action.action == "bet" or (
            action.action == "all_in" and action.raised and not flop_bet
        )
        if action.seat == seat and not flop_bet and chance == 0:
            chance = 1
            if is_open_bet:
                made = 1
        if is_open_bet or action.action == "raise":
            flop_bet = True
    return chance, made


def _fold_to_3bet(actions: list[ActionRow], seat: int) -> tuple[int, int]:
    raises = 0
    chance = 0
    folded = 0
    for action in actions:
        if action.street != "PREFLOP":
            continue
        if action.seat == seat and raises == 2 and chance == 0:
            chance = 1
            if action.action == "fold":
                folded = 1
        if action.raised:
            raises += 1
    return chance, folded


def _reached_flop(actions: list[ActionRow], has_board: bool) -> bool:
    if has_board:
        return True
    return any(action.street in {"FLOP", "TURN", "RIVER"} for action in actions)


def _saw_flop(actions: list[ActionRow], seat: int, reached: bool) -> bool:
    if not reached:
        return False
    folded = any(
        action.seat == seat and action.street == "PREFLOP" and action.action == "fold"
        for action in actions
    )
    return not folded


def _showdown(hand: Hand, row: HandPlayer, actions: list[ActionRow]) -> bool:
    folded = any(action.seat == row.seat and action.action == "fold" for action in actions)
    if folded:
        return False
    return bool(row.showed) or bool(hand.showdown)


def _aggression(
    actions: list[ActionRow],
    seat: int,
    street: str | None,
) -> tuple[int, int]:
    bets = 0
    calls = 0
    for action in actions:
        if action.seat != seat:
            continue
        if street is not None and action.street.upper() != street:
            continue
        if action.action in {"fold", "check"}:
            continue
        if action.action == "bet" or action.action == "raise":
            bets += 1
        elif action.action == "all_in" and action.raised:
            bets += 1
        elif action.action == "call" or (action.action == "all_in" and not action.raised):
            calls += 1
    return bets, calls


def _fold_to_cbet(actions: list[ActionRow], seat: int) -> tuple[int, int]:
    aggressor = None
    for action in actions:
        if action.street == "PREFLOP" and action.raised:
            aggressor = action.seat
    if aggressor is None or aggressor == seat:
        return 0, 0
    seen = False
    chance = 0
    folded = 0
    for action in actions:
        if action.street != "FLOP":
            continue
        opening = action.action == "bet" or (action.action == "all_in" and action.raised)
        if not seen and opening and action.seat == aggressor:
            seen = True
            continue
        if not seen and (opening or action.action == "raise"):
            return 0, 0
        if seen and action.seat == seat and chance == 0:
            chance = 1
            if action.action == "fold":
                folded = 1
    return chance, folded


def _analysis_totals(
    rows: list[DecisionAnalysis],
    hands: dict[int, Hand],
) -> tuple[float | None, float | None, float | None, dict[str, int]]:
    counts = {key: 0 for key in _MISTAKE_KEYS}
    if not rows:
        return None, None, None, counts
    ev_bb = 0.0
    gto_ev_bb = 0.0
    ev_loss_bb = 0.0
    have_ev = False
    have_gto = False
    have_loss = False
    for row in rows:
        severity = (row.severity or "").lower()
        if severity in counts:
            counts[severity] += 1
        if row.ev_loss is not None:
            ev_loss_bb += float(row.ev_loss)
            have_loss = True
        hand = hands.get(row.hand_id or -1)
        blind = None if hand is None else hand.big_blind
        if row.ev is None or not blind:
            continue
        chosen = float(row.ev) / blind
        ev_bb += chosen
        have_ev = True
        if row.ev_loss is not None:
            gto_ev_bb += chosen + float(row.ev_loss)
            have_gto = True
    return (
        ev_bb if have_ev else None,
        gto_ev_bb if have_gto else None,
        ev_loss_bb if have_loss else None,
        counts,
    )
