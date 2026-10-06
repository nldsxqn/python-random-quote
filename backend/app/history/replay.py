"""Stepwise replay from stored rows. The live room is not required."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import ActionRow, BoardRow, Hand, HandPlayer, PotRow
from app.history.store import HandHistory

_STREET_CARDS = {"PREFLOP": 0, "FLOP": 3, "TURN": 4, "RIVER": 5}


def list_hands(
    history: HandHistory,
    *,
    room_id: str | None = None,
    limit: int = 50,
) -> dict:
    with history.sessions() as session:
        query = select(Hand).order_by(Hand.id.desc()).limit(limit)
        if room_id:
            query = query.where(Hand.room_id == room_id)
        hands = list(session.scalars(query))
        return {"hands": [_summary(session, hand) for hand in hands]}


def hand_detail(history: HandHistory, hand_id: int, viewer_seat: int | None) -> dict | None:
    with history.sessions() as session:
        hand = session.get(Hand, hand_id)
        if hand is None:
            return None
        loaded = _load(session, hand)
        steps = _steps(loaded)
        return {
            "id": hand.id,
            "room_id": hand.room_id,
            "started_at": hand.started_at,
            "completed_at": hand.completed_at,
            "small_blind": hand.small_blind,
            "big_blind": hand.big_blind,
            "button_seat": hand.button_seat,
            "table_settings": hand.table_settings,
            "rule_settings": hand.rule_settings,
            "showdown": hand.showdown,
            "step_count": len(steps),
            "jumps": _jumps(steps, hand.showdown),
            "players": [
                _player_view(player, viewer_seat, reveal=False) for player in loaded["players"]
            ],
            "actions": [_action_view(action) for action in loaded["actions"]],
        }


def state_at(
    history: HandHistory,
    hand_id: int,
    index: int,
    viewer_seat: int | None,
) -> dict | None:
    with history.sessions() as session:
        hand = session.get(Hand, hand_id)
        if hand is None:
            return None
        loaded = _load(session, hand)
        steps = _steps(loaded)
        if index < 0 or index >= len(steps):
            raise IndexError("action index is out of range")
        return _state(hand, loaded, steps, index, viewer_seat)


def _summary(session: Session, hand: Hand) -> dict:
    players = session.scalars(
        select(HandPlayer).where(HandPlayer.hand_id == hand.id).order_by(HandPlayer.seat)
    )
    return {
        "id": hand.id,
        "room_id": hand.room_id,
        "completed_at": hand.completed_at,
        "small_blind": hand.small_blind,
        "big_blind": hand.big_blind,
        "button_seat": hand.button_seat,
        "showdown": hand.showdown,
        "players": [
            {"seat": player.seat, "nickname": player.nickname, "position": player.position}
            for player in players
        ],
    }


def _load(session: Session, hand: Hand) -> dict:
    players = list(
        session.scalars(
            select(HandPlayer).where(HandPlayer.hand_id == hand.id).order_by(HandPlayer.seat)
        )
    )
    actions = list(
        session.scalars(
            select(ActionRow).where(ActionRow.hand_id == hand.id).order_by(ActionRow.order_index)
        )
    )
    boards = list(
        session.scalars(
            select(BoardRow).where(BoardRow.hand_id == hand.id).order_by(BoardRow.run_index)
        )
    )
    pots = list(
        session.scalars(select(PotRow).where(PotRow.hand_id == hand.id).order_by(PotRow.pot_index))
    )
    return {"players": players, "actions": actions, "boards": boards, "pots": pots}


def _shared(boards: list[BoardRow]) -> list[str]:
    runs = [list(board.cards) for board in boards]
    if not runs:
        return []
    if len(runs) == 1:
        return runs[0]
    prefix: list[str] = []
    for cards in zip(*runs, strict=False):
        if len(set(cards)) != 1:
            break
        prefix.append(cards[0])
    return prefix


def _steps(loaded: dict) -> list[dict]:
    actions: list[ActionRow] = loaded["actions"]
    shared = _shared(loaded["boards"])
    streets = [action.street for action in actions]
    opening = "PREFLOP"
    if streets:
        opening = "PREFLOP" if "PREFLOP" in streets else streets[0]
    elif len(shared) >= 3:
        opening = "FLOP"
    shown = 0 if opening == "PREFLOP" else min(3, len(shared))
    steps = [{"kind": "start", "street": opening, "shown": shown, "action_index": None}]

    def reveal(street: str) -> None:
        nonlocal shown
        target = min(_STREET_CARDS[street], len(shared))
        for length, name in ((3, "FLOP"), (4, "TURN"), (5, "RIVER")):
            if shown < length <= target:
                shown = length
                steps.append({"kind": "deal", "street": name, "shown": shown, "action_index": None})

    for index, action in enumerate(actions):
        reveal(action.street)
        steps.append(
            {"kind": "action", "street": action.street, "shown": shown, "action_index": index}
        )
    for length, name in ((3, "FLOP"), (4, "TURN"), (5, "RIVER")):
        if shown < length <= len(shared):
            shown = length
            steps.append({"kind": "deal", "street": name, "shown": shown, "action_index": None})
    final = "showdown" if any(player.showed for player in loaded["players"]) else "complete"
    steps.append(
        {
            "kind": final,
            "street": "SHOWDOWN" if final == "showdown" else "HAND_COMPLETE",
            "shown": len(shared) if final != "showdown" else len(shared),
            "action_index": None,
        }
    )
    return steps


def _jumps(steps: list[dict], showdown: bool) -> dict:
    def first(length: int) -> int | None:
        for index, step in enumerate(steps):
            if step["shown"] >= length and step["kind"] != "start":
                return index
        return None

    showdown_index = None
    if showdown:
        for index, step in enumerate(steps):
            if step["kind"] == "showdown":
                showdown_index = index
    return {
        "flop": first(3),
        "turn": first(4),
        "river": first(5),
        "showdown": showdown_index,
    }


def _state(
    hand: Hand,
    loaded: dict,
    steps: list[dict],
    index: int,
    viewer_seat: int | None,
) -> dict:
    step = steps[index]
    stacks = {player.seat: player.stack_after_posts for player in loaded["players"]}
    pot = sum(player.posted for player in loaded["players"])
    for earlier in steps[:index]:
        if earlier["kind"] != "action":
            continue
        action = loaded["actions"][earlier["action_index"]]
        stacks[action.seat] -= action.put_in
        pot += action.put_in
    final = step["kind"] in {"showdown", "complete"}
    if final:
        for player in loaded["players"]:
            stacks[player.seat] = player.ending_stack
        pot = sum(item.amount for item in loaded["pots"])
    shared = _shared(loaded["boards"])
    board = shared[: step["shown"]] if not (final and step["kind"] == "showdown") else shared
    if step["kind"] == "showdown":
        board = shared
    runs = []
    if step["kind"] == "showdown" and len(loaded["boards"]) > 1:
        runs = [list(item.cards) for item in loaded["boards"]]
        board = list(loaded["boards"][0].cards)
    reveal = step["kind"] == "showdown"
    bets, statuses = _seat_progress(loaded, steps, index)
    return {
        "hand_id": hand.id,
        "index": index,
        "step_count": len(steps),
        "street": step["street"],
        "board": board,
        "boards": runs,
        "pot": pot,
        "rake": hand.rake if final else 0,
        "bounty": hand.bounty if final else 0,
        "pots": [
            {
                "amount": item.amount,
                "eligible": list(item.eligible),
                "side_pot": item.side_pot,
            }
            for item in loaded["pots"]
        ]
        if final
        else [],
        "winners": list(hand.winners) if final else [],
        "button_seat": hand.button_seat,
        "small_blind_seat": hand.sb_seat,
        "big_blind_seat": hand.bb_seat,
        "hand_number": hand.id,
        "action": _step_action(step, loaded),
        "players": [
            {
                **_player_view(player, viewer_seat, reveal=reveal),
                "stack": stacks[player.seat],
                "committed_street": bets[player.seat],
                "status": statuses[player.seat],
                "is_button": player.seat == hand.button_seat,
            }
            for player in loaded["players"]
        ],
        "jumps": _jumps(steps, hand.showdown),
        "showdown": reveal,
    }


def _seat_progress(
    loaded: dict,
    steps: list[dict],
    index: int,
) -> tuple[dict[int, int], dict[int, str]]:
    """Street bets and fold status from stored posts and actions. The client only displays them."""
    players: list[HandPlayer] = loaded["players"]
    bets = {player.seat: player.posted for player in players}
    status = {
        player.seat: (
            "ALL_IN"
            if player.starting_stack > 0 and player.posted >= player.starting_stack
            else "ACTIVE"
        )
        for player in players
    }
    street = steps[0]["street"] if steps else "PREFLOP"

    def apply(item: dict) -> None:
        nonlocal street
        if item["kind"] == "deal":
            for seat in bets:
                bets[seat] = 0
            street = item["street"]
            return
        if item["kind"] != "action":
            return
        action: ActionRow = loaded["actions"][item["action_index"]]
        if action.street != street:
            for seat in bets:
                bets[seat] = 0
            street = action.street
        bets[action.seat] = bets.get(action.seat, 0) + int(action.put_in or 0)
        if action.action == "fold":
            status[action.seat] = "FOLDED"
        elif action.action == "all_in":
            status[action.seat] = "ALL_IN"

    for earlier in steps[:index]:
        apply(earlier)
    current = steps[index]
    if current["kind"] == "deal":
        apply(current)
    if current["kind"] in {"showdown", "complete"}:
        for seat in bets:
            bets[seat] = 0
    return bets, status


def _step_action(step: dict, loaded: dict) -> dict | None:
    if step["kind"] == "start":
        return {"action": "post", "street": step["street"], "seat": None, "amount": None}
    if step["kind"] == "deal":
        return {"action": "deal", "street": step["street"], "seat": None, "amount": None}
    if step["kind"] == "action":
        return _action_view(loaded["actions"][step["action_index"]])
    return {"action": step["kind"], "street": step["street"], "seat": None, "amount": None}


def _action_view(action: ActionRow) -> dict:
    return {
        "street": action.street,
        "seat": action.seat,
        "action": action.action,
        "amount": action.amount,
        "put_in": action.put_in,
        "pot_before": action.pot_before,
        "stack_before": action.stack_before,
        "acted_at": action.acted_at,
    }


def _player_view(player: HandPlayer, viewer_seat: int | None, *, reveal: bool) -> dict:
    holes = None
    if viewer_seat is not None and player.seat == viewer_seat:
        holes = list(player.hole_cards)
    elif reveal and player.showed:
        holes = list(player.hole_cards)
    return {
        "seat": player.seat,
        "nickname": player.nickname,
        "position": player.position,
        "is_bot": player.is_bot,
        "starting_stack": player.starting_stack,
        "ending_stack": player.ending_stack if reveal else None,
        "hole_cards": holes,
    }
