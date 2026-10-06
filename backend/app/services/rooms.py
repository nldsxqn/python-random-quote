"""In-memory rooms. The engine deals cards and applies actions; this module does not."""

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.bots.base import PokerBot
from app.bots.factory import make_bot
from app.engine.actions import Action, IllegalActionError
from app.engine.cards import Card
from app.engine.deck import DeckProvider
from app.engine.game import CashGame
from app.engine.player import Player
from app.engine.state import Street
from app.history.store import HandHistory
from app.rules.buyin import require_buyin
from app.rules.clock import ManualClock, SystemClock
from app.rules.selected import SelectedRules, merge_rules, parse_rules
from app.rules.timebank import remaining_seconds, timeout_action
from app.rules.topup import plan_top_up
from app.solver.live import study_advice

STARTING_STACK = 1000
DEFAULT_SMALL_BLIND = 1
DEFAULT_BIG_BLIND = 2
DEFAULT_SEATS = 6
_INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class RoomError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class Member:
    token: str
    nickname: str
    seat: int | None = None
    stack: int = 0
    connected: bool = False
    seen_connection: bool = False
    bot: PokerBot | None = None
    bot_kind: str | None = None


@dataclass
class Event:
    type: str
    data: dict


@dataclass
class Room:
    room_id: str
    invite_code: str
    host_token: str
    small_blind: int
    big_blind: int
    seat_count: int
    created_at: str
    members: dict[str, Member] = field(default_factory=dict)
    paused: bool = False
    pending_small_blind: int | None = None
    pending_big_blind: int | None = None
    pending_seats: int | None = None
    game: CashGame | None = None
    engine_seats: list[int] = field(default_factory=list)
    button_seat: int | None = None
    next_deck: DeckProvider | None = None
    events: list[Event] = field(default_factory=list)
    emitted: set[str] = field(default_factory=set)
    closed: bool = False
    rules_spec: dict = field(default_factory=dict)
    pending_rules_spec: dict | None = None
    hand_top_ups: list[dict[str, int]] = field(default_factory=list)
    clock: SystemClock | ManualClock = field(default_factory=SystemClock)
    action_deadline: float | None = None
    hand_history: list[dict] = field(default_factory=list)
    hand_started_at: str | None = None
    opening: list[dict] = field(default_factory=list)
    bot_illegal: int = 0
    bot_deadlocks: int = 0
    bots_running: bool = False
    gto_mode: str = "competitive"
    gto_cache: dict = field(default_factory=dict)
    variant: str = "nlhe"
    pending_variant: str | None = None
    tournament: bool = False
    levels: list = field(default_factory=lambda: [(1, 2), (2, 4), (5, 10)])
    hands_per_level: int = 5
    hands_played: int = 0
    hand_number: int = 0
    tournament_winner: str | None = None


class RoomService:
    def __init__(self, history: HandHistory | None = None) -> None:
        self.history = history
        self.rooms: dict[str, Room] = {}
        self.by_invite: dict[str, str] = {}
        self.by_token: dict[str, str] = {}

    def create(self, nickname: str) -> dict:
        name = _nickname(nickname)
        room = Room(
            room_id=secrets.token_hex(6),
            invite_code=self._invite_code(),
            host_token=secrets.token_urlsafe(24),
            small_blind=DEFAULT_SMALL_BLIND,
            big_blind=DEFAULT_BIG_BLIND,
            seat_count=DEFAULT_SEATS,
            created_at=datetime.now(UTC).isoformat(),
        )
        member = Member(token=room.host_token, nickname=name)
        room.members[member.token] = member
        self._index(room, member)
        return {
            "room_id": room.room_id,
            "invite_code": room.invite_code,
            "guest_token": member.token,
            "seat": None,
        }

    def join(self, invite_code: str, nickname: str) -> dict:
        name = _nickname(nickname)
        room = self._by_invite(invite_code)
        member = Member(token=secrets.token_urlsafe(24), nickname=name)
        room.members[member.token] = member
        self.by_token[member.token] = room.room_id
        self._add(room, "PLAYER_JOINED", {"nickname": name})
        self._push_state(room)
        return {
            "room_id": room.room_id,
            "invite_code": room.invite_code,
            "guest_token": member.token,
            "seat": None,
        }

    def sit(self, token: str, seat: int | None, amount: int | None = None) -> dict:
        room, member = self._require_member(token)
        self._reject_if_hand(room, "cannot sit during a hand")
        if member.seat is not None:
            raise RoomError("already seated")
        chosen = self._choose_seat(room, seat)
        stack = member.stack
        if stack <= 0:
            if amount is None:
                stack = STARTING_STACK
            else:
                stack = _positive_chips(amount, "buy-in must be a positive integer")
        elif amount is not None:
            raise RoomError("already holding chips; add chips instead")
        self._check_buyin(room, stack, adding=False)
        member.stack = stack
        member.seat = chosen
        self._push_state(room)
        return {"seat": chosen}

    def add_chips(self, token: str, amount: int) -> dict:
        room, member = self._require_member(token)
        self._reject_if_hand(room, "cannot add chips during a hand")
        if member.seat is None:
            raise RoomError("sit before adding chips")
        chips = _positive_chips(amount, "added chips must be a positive integer")
        rules = parse_rules(room.rules_spec)
        if rules.buy_in is not None:
            self._check_buyin(room, chips, adding=True)
            _low, high = rules.buy_in.chip_bounds(room.big_blind)
            if member.stack + chips > high:
                raise RoomError(f"stack cannot exceed {high}")
        member.stack += chips
        self._sync_member_stack(room, member)
        self._push_state(room)
        return {"stack": member.stack}

    def stand(self, token: str) -> dict:
        room, member = self._require_member(token)
        self._reject_if_hand(room, "cannot stand during a hand")
        if member.seat is None:
            raise RoomError("not seated")
        member.seat = None
        self._push_state(room)
        return {"seat": None}

    def leave(self, token: str) -> dict:
        room, member = self._require_member(token)
        self._reject_if_hand(room, "cannot leave during a hand")
        nickname = member.nickname
        self._remove_member(room, member)
        if room.members:
            if room.host_token == token:
                room.host_token = next(iter(room.members))
            self._add(room, "PLAYER_LEFT", {"nickname": nickname})
            self._push_state(room)
        else:
            room.closed = True
        return {"left": True}

    def connect(self, token: str) -> tuple[Room, Member, bool]:
        room, member = self._require_member(token)
        reconnected = member.seen_connection
        member.connected = True
        member.seen_connection = True
        return room, member, reconnected

    def mark_disconnected(self, token: str) -> None:
        found = self._find(token)
        if found is None:
            return
        found[1].connected = False

    def note_reconnected(self, room: Room, member: Member) -> None:
        self._add(room, "PLAYER_RECONNECTED", {"nickname": member.nickname})

    def start(self, token: str) -> str:
        room, _member = self._require_host(token, "only the host can start a hand")
        if room.paused:
            raise RoomError("table is paused")
        self._reject_if_hand(room, "hand already in progress")
        self._apply_pending(room)
        self._apply_tournament_level(room)
        rules = parse_rules(room.rules_spec)
        room.hand_top_ups = self._top_up_members(room, rules)
        lineup = self._chip_lineup(room)
        if len(lineup) < 2:
            raise RoomError("need at least 2 seated players with chips")
        advance = room.game is not None
        engine_rules = rules.for_engine()
        if self._can_reuse(room, lineup):
            assert room.game is not None
            self._install_deck(room, room.game)
            self._copy_stacks(room)
            room.game.rules = engine_rules
            room.game.small_blind = room.small_blind
            room.game.big_blind = room.big_blind
        else:
            seats = [seat for seat, _stack in lineup]
            stacks = [stack for _seat, stack in lineup]
            button = _button_index(seats, room.button_seat, advance)
            deck = room.next_deck
            room.next_deck = None
            room.game = CashGame(
                stacks,
                button=button,
                small_blind=room.small_blind,
                big_blind=room.big_blind,
                deck=deck,
                rules=engine_rules,
                variant=room.variant,
            )
            room.engine_seats = seats
        room.emitted = set()
        room.action_deadline = None
        room.hand_history = []
        try:
            room.game.start_hand()
        except IllegalActionError as exc:
            raise RoomError(str(exc)) from exc
        room.hand_number += 1
        self._sync_members(room)
        self._capture_opening(room)
        game = room.game
        assert game is not None
        self._add(
            room,
            "HAND_STARTED",
            {
                "button_seat": room.engine_seats[game.button],
                "small_blind_seat": _table_seat(room, game.sb_seat),
                "big_blind_seat": _table_seat(room, game.bb_seat),
                "small_blind": game.small_blind,
                "big_blind": game.big_blind,
            },
        )
        self._add(room, "CARDS_DEALT", {})
        self._emit_progress(room)
        self._push_state(room)
        self._run_bots(room)
        return room.room_id

    def pause(self, token: str, paused: bool) -> str:
        room, _member = self._require_host(token, "only the host can pause")
        if paused and self._in_hand(room):
            raise RoomError("cannot pause during a hand")
        room.paused = paused
        self._push_state(room)
        return room.room_id

    def update_settings(
        self,
        token: str,
        small_blind: int | None,
        big_blind: int | None,
        seats: int | None,
        rules: dict | None = None,
        gto_mode: str | None = None,
        variant: str | None = None,
        tournament: dict | None = None,
    ) -> str:
        room, _member = self._require_host(token, "only the host can change blinds")
        if seats is not None:
            _require_int(seats, "seats must be from 2 to 9")
            if not 2 <= seats <= 9:
                raise RoomError("seats must be from 2 to 9")
            occupied = [member.seat for member in room.members.values() if member.seat is not None]
            if any(seat >= seats for seat in occupied):
                raise RoomError("seat count is below an occupied seat")
        live_sb = room.pending_small_blind
        if live_sb is None:
            live_sb = room.small_blind
        live_bb = room.pending_big_blind
        if live_bb is None:
            live_bb = room.big_blind
        new_sb = live_sb if small_blind is None else small_blind
        new_bb = live_bb if big_blind is None else big_blind
        if small_blind is not None:
            _require_int(small_blind, "small blind must be less than big blind")
        if big_blind is not None:
            _require_int(big_blind, "small blind must be less than big blind")
        if not 0 < new_sb < new_bb:
            raise RoomError("small blind must be less than big blind")
        if self._in_hand(room):
            if small_blind is not None:
                room.pending_small_blind = small_blind
            if big_blind is not None:
                room.pending_big_blind = big_blind
            if seats is not None:
                room.pending_seats = seats
        else:
            room.small_blind = new_sb
            room.big_blind = new_bb
            room.pending_small_blind = None
            room.pending_big_blind = None
            if seats is not None:
                room.seat_count = seats
                room.pending_seats = None
            if room.game is not None:
                room.game.small_blind = room.small_blind
                room.game.big_blind = room.big_blind
        if rules is not None:
            self._store_rules(room, rules)
        if gto_mode is not None:
            if gto_mode not in {"competitive", "study"}:
                raise RoomError("gto mode must be competitive or study")
            room.gto_mode = gto_mode
            room.gto_cache.clear()
        if variant is not None:
            if variant not in {"nlhe", "short_deck"}:
                raise RoomError("variant must be nlhe or short_deck")
            if self._in_hand(room):
                room.pending_variant = variant
            else:
                room.variant = variant
                room.pending_variant = None
        if tournament is not None:
            self._store_tournament(room, tournament)
        self._push_state(room)
        return room.room_id

    def add_bot(
        self,
        token: str,
        kind: str,
        seat: int | None = None,
        seed: int | None = None,
        bot: PokerBot | None = None,
        amount: int | None = None,
    ) -> dict:
        room, _host = self._require_host(token, "only the host can add a bot")
        self._reject_if_hand(room, "cannot add a bot during a hand")
        if not isinstance(kind, str):
            raise RoomError("unknown bot")
        chosen_seed = 0 if seed is None else _require_int(seed, "bot seed must be an integer")
        try:
            seated_bot = bot if bot is not None else make_bot(kind, chosen_seed)
        except ValueError as exc:
            raise RoomError(str(exc)) from exc
        label = kind.strip().lower()
        member = Member(
            token=secrets.token_urlsafe(24),
            nickname=_bot_nickname(room, label),
            connected=True,
            seen_connection=True,
            bot=seated_bot,
            bot_kind=label,
        )
        room.members[member.token] = member
        self.by_token[member.token] = room.room_id
        self._add(room, "PLAYER_JOINED", {"nickname": member.nickname, "bot": label})
        try:
            seated = self.sit(member.token, seat, amount)
        except RoomError:
            self._remove_member(room, member)
            raise
        return {"seat": seated["seat"], "nickname": member.nickname, "kind": label}

    def remove_bot(self, token: str, seat: int) -> dict:
        _room, _host = self._require_host(token, "only the host can remove a bot")
        member = _member_at(_room, _require_int(seat, "seat is out of range"))
        if member is None or member.bot is None:
            raise RoomError("that seat is not a bot")
        return self.leave(member.token)

    def act(self, token: str, action: str, amount: object, request_id: object) -> str:
        room, _member = self._require_member(token)
        self._apply_action(room, token, action, amount, request_id)
        self._run_bots(room)
        return room.room_id

    def _apply_action(
        self,
        room: Room,
        token: str,
        action: str,
        amount: object,
        request_id: object,
    ) -> None:
        _room, member = self._require_member(token)
        if member.seat is None:
            raise RoomError("spectators cannot act")
        if room.game is None or not self._in_hand(room):
            raise RoomError("no hand in progress")
        engine_seat = _engine_index(room, member.seat)
        if engine_seat is None:
            raise RoomError("spectators cannot act")
        street = room.game.street.value
        player = room.game.players[engine_seat]
        pot_before = sum(person.committed_hand for person in room.game.players)
        stack_before = player.stack
        previous_bet = room.game.current_bet
        parsed = _action(action, amount)
        try:
            room.game.apply(parsed, engine_seat)
        except IllegalActionError as exc:
            raise RoomError(str(exc)) from exc
        put_in = stack_before - player.stack
        raised = action == "raise" or (
            action == "all_in" and player.committed_street > previous_bet
        )
        recorded = amount if action in {"bet", "raise"} else None
        room.hand_history.append(
            {
                "seat": member.seat,
                "nickname": member.nickname,
                "street": street,
                "action": action,
                "amount": recorded,
                "put_in": put_in,
                "pot_before": pot_before,
                "stack_before": stack_before,
                "raised": raised,
                "acted_at": datetime.now(UTC).isoformat(),
            }
        )
        self._sync_members(room)
        self._add(
            room,
            "ACTION_RESULT",
            {
                "request_id": request_id,
                "seat": member.seat,
                "nickname": member.nickname,
                "action": action,
                "amount": recorded,
            },
        )
        self._emit_progress(room)
        self._push_state(room)

    def vote_run_it_twice(self, token: str, accept: bool, request_id: object) -> str:
        room, member = self._require_member(token)
        if member.seat is None or room.game is None:
            raise RoomError("spectators cannot act")
        engine_seat = _engine_index(room, member.seat)
        if engine_seat is None:
            raise RoomError("not contesting this pot")
        if not isinstance(accept, bool):
            raise RoomError("run it twice vote must be yes or no")
        try:
            room.game.vote_run_it_twice(engine_seat, accept)
        except IllegalActionError as exc:
            raise RoomError(str(exc)) from exc
        self._sync_members(room)
        self._add(
            room,
            "RIT_VOTE",
            {
                "request_id": request_id,
                "seat": member.seat,
                "nickname": member.nickname,
                "accept": accept,
            },
        )
        self._emit_progress(room)
        self._push_state(room)
        self._run_bots(room)
        return room.room_id

    def decide_insurance(self, token: str, accept: bool, request_id: object) -> str:
        room, member = self._require_member(token)
        if member.seat is None or room.game is None:
            raise RoomError("spectators cannot act")
        engine_seat = _engine_index(room, member.seat)
        if engine_seat is None:
            raise RoomError("insurance is not offered")
        if not isinstance(accept, bool):
            raise RoomError("insurance answer must be yes or no")
        try:
            room.game.decide_insurance(engine_seat, accept)
        except IllegalActionError as exc:
            raise RoomError(str(exc)) from exc
        self._sync_members(room)
        self._add(
            room,
            "INSURANCE_DECISION",
            {
                "request_id": request_id,
                "seat": member.seat,
                "nickname": member.nickname,
                "accept": accept,
                "label": "simplified",
            },
        )
        self._emit_progress(room)
        self._push_state(room)
        self._run_bots(room)
        return room.room_id

    def resolve_time_bank(self, room_id: str) -> bool:
        room = self._require_room(room_id)
        game = room.game
        rules = parse_rules(room.rules_spec)
        if (
            game is None
            or rules.time_bank is None
            or game.actor is None
            or room.action_deadline is None
            or room.clock.now() < room.action_deadline
        ):
            return False
        engine_seat = game.actor
        try:
            action = timeout_action(game)
            game.apply(action, engine_seat)
        except IllegalActionError as exc:
            raise RoomError(str(exc)) from exc
        self._sync_members(room)
        table_seat = _table_seat(room, engine_seat)
        owner = _member_at(room, table_seat) if table_seat is not None else None
        self._add(
            room,
            "ACTION_RESULT",
            {
                "request_id": "timeout",
                "seat": table_seat,
                "nickname": owner.nickname if owner else "",
                "action": action.kind.value,
                "amount": None,
                "timeout": True,
            },
        )
        self._emit_progress(room)
        self._push_state(room)
        self._run_bots(room)
        return True

    def set_clock(self, room_id: str, clock: ManualClock) -> None:
        self._require_room(room_id).clock = clock

    def set_deck(self, room_id: str, deck: DeckProvider) -> None:
        room = self._require_room(room_id)
        if self._in_hand(room):
            raise RoomError("cannot change the deck during a hand")
        room.next_deck = deck

    def view(self, token: str) -> dict:
        room, member = self._require_member(token)
        payload = self.player_view(room, member)
        self._attach_study(room, member, payload)
        return payload

    def room_id_for(self, token: str) -> str:
        room, _member = self._require_member(token)
        return room.room_id

    def joined_message(self, room: Room, member: Member) -> dict:
        return {
            "type": "ROOM_JOINED",
            "payload": {
                "room_id": room.room_id,
                "invite_code": room.invite_code,
                "nickname": member.nickname,
                "seat": member.seat,
                "is_host": room.host_token == member.token,
            },
        }

    def render(self, room: Room, member: Member, event: Event) -> dict:
        if event.type == "GAME_STATE":
            payload = self.player_view(room, member)
            self._attach_study(room, member, payload)
            return {"type": "GAME_STATE", "payload": payload}
        if event.type == "CARDS_DEALT":
            return {"type": "CARDS_DEALT", "payload": {"hole_cards": self._own_holes(room, member)}}
        return {"type": event.type, "payload": event.data}

    def pull_events(self, room: Room) -> list[Event]:
        pending = room.events
        room.events = []
        return pending

    def discard_if_closed(self, room_id: str) -> None:
        room = self.rooms.get(room_id)
        if room is None or not room.closed:
            return
        self.rooms.pop(room.room_id, None)
        self.by_invite.pop(room.invite_code, None)
        for token in list(room.members):
            self.by_token.pop(token, None)

    def player_view(self, room: Room, member: Member) -> dict:
        game = room.game
        players = [
            self._player_row(room, member, seated)
            for seated in _seated(room)
        ]
        spectators = [
            person.nickname
            for person in room.members.values()
            if person.seat is None
        ]
        actor_seat = None
        board: list[str] = []
        pot = 0
        street = None
        to_call = 0
        min_raise_to = None
        legal: list[str] = []
        small_blind_seat = None
        big_blind_seat = None
        button_seat = room.button_seat
        live_sb = room.small_blind
        live_bb = room.big_blind
        if game is not None:
            live_sb = game.small_blind
            live_bb = game.big_blind
            street = game.street.value
            board = [card.code for card in game.board]
            pot = _pot_amount(game)
            button_seat = _table_seat(room, game.button)
            small_blind_seat = _table_seat(room, game.sb_seat)
            big_blind_seat = _table_seat(room, game.bb_seat)
            if game.actor is not None:
                actor_seat = _table_seat(room, game.actor)
            engine_seat = None if member.seat is None else _engine_index(room, member.seat)
            if engine_seat is not None and game.actor == engine_seat and self._in_hand(room):
                legal, to_call, min_raise_to = _legal(game, engine_seat)
            elif engine_seat is not None:
                player = game.players[engine_seat]
                to_call = max(0, game.current_bet - player.committed_street)
        return {
            "room_id": room.room_id,
            "invite_code": room.invite_code,
            "host": room.members[room.host_token].nickname,
            "created_at": room.created_at,
            "settings": {
                "small_blind": room.small_blind,
                "big_blind": room.big_blind,
                "seats": room.seat_count,
                "paused": room.paused,
                "pending_small_blind": room.pending_small_blind,
                "pending_big_blind": room.pending_big_blind,
                "pending_seats": room.pending_seats,
                "rules": room.rules_spec,
                "pending_rules": room.pending_rules_spec,
                "gto_mode": room.gto_mode,
                "variant": room.variant,
                "pending_variant": room.pending_variant,
                "tournament": _tournament_view(room),
            },
            "players": players,
            "spectators": spectators,
            "game": {
                "street": street,
                "board": board,
                "pot": pot,
                "actor_seat": actor_seat,
                "button_seat": button_seat,
                "small_blind_seat": small_blind_seat,
                "big_blind_seat": big_blind_seat,
                "small_blind": live_sb,
                "big_blind": live_bb,
                "to_call": to_call,
                "min_raise_to": min_raise_to,
                "legal_actions": legal,
                "rake": 0 if game is None else game.rake,
                "bounty": 0 if game is None else game.bounty,
                "bounty_payments": _bounty_rows(room, game),
                "rit_offer": bool(game and game.awaiting_rit),
                "rit_seats": _rit_seats(room) if game is not None and game.awaiting_rit else [],
                "boards": _public_boards(game),
                "remaining_seconds": remaining_seconds(room.action_deadline, room.clock.now()),
                "top_ups": list(room.hand_top_ups),
                "action_history": [dict(item) for item in room.hand_history],
                "insurance": _insurance_view(room, game),
                "hand_number": room.hand_number or None,
            },
            "you": {
                "nickname": member.nickname,
                "seat": member.seat,
                "is_host": room.host_token == member.token,
                "is_spectator": member.seat is None,
                "is_bot": member.bot is not None,
                "position": _position(room, member),
                "hole_cards": self._own_holes(room, member),
            },
        }

    def _attach_study(self, room: Room, member: Member, payload: dict) -> None:
        if member.bot is not None:
            return
        advice = study_advice(
            mode=room.gto_mode,
            in_hand=self._in_hand(room),
            player_count=0 if room.game is None else len(room.game.in_hand),
            street=None if room.game is None else room.game.street.value,
            board=payload["game"]["board"],
            pot=payload["game"]["pot"],
            effective_stack=_effective_stack(room, member),
            hero_cards=payload["you"]["hole_cards"] or [],
            hero_position=payload["you"]["position"] or "",
            to_call=payload["game"]["to_call"],
            cache=room.gto_cache,
        )
        if advice is not None:
            payload["you"]["gto"] = advice

    def _player_row(self, room: Room, viewer: Member, member: Member) -> dict:
        game = room.game
        engine_seat = None if member.seat is None else _engine_index(room, member.seat)
        status = "SEATED" if member.stack > 0 else "ELIMINATED"
        stack = member.stack
        committed_street = 0
        committed_hand = 0
        hole_cards = None
        is_button = member.seat == room.button_seat
        is_actor = False
        if game is not None and engine_seat is not None:
            player = game.players[engine_seat]
            status = player.status.value
            stack = player.stack
            committed_street = player.committed_street
            committed_hand = player.committed_hand
            hole_cards = self._visible_holes(room, viewer, engine_seat)
            is_button = game.button == engine_seat
            is_actor = game.actor == engine_seat
        return {
            "seat": member.seat,
            "nickname": member.nickname,
            "stack": stack,
            "status": status,
            "committed_street": committed_street,
            "committed_hand": committed_hand,
            "hole_cards": hole_cards,
            "is_button": is_button,
            "is_actor": is_actor,
            "connected": member.connected,
            "is_bot": member.bot is not None,
            "bot_kind": member.bot_kind,
        }

    def _own_holes(self, room: Room, member: Member) -> list[str] | None:
        if member.seat is None or room.game is None:
            return None
        engine_seat = _engine_index(room, member.seat)
        if engine_seat is None:
            return None
        return self._visible_holes(room, member, engine_seat)

    def _visible_holes(self, room: Room, viewer: Member, engine_seat: int) -> list[str] | None:
        game = room.game
        if game is None:
            return None
        player = game.players[engine_seat]
        if player.hole is None:
            return None
        viewer_seat = None if viewer.seat is None else _engine_index(room, viewer.seat)
        if engine_seat in game.showdown_seats or viewer_seat == engine_seat:
            return [card.code for card in player.hole]
        return None

    def _capture_opening(self, room: Room) -> None:
        game = room.game
        assert game is not None
        room.hand_started_at = datetime.now(UTC).isoformat()
        rows = []
        for engine_seat, table_seat in enumerate(room.engine_seats):
            player = game.players[engine_seat]
            member = _member_at(room, table_seat)
            hole = [card.code for card in player.hole] if player.hole else []
            rows.append(
                {
                    "seat": table_seat,
                    "engine_seat": engine_seat,
                    "nickname": member.nickname if member else "",
                    "is_bot": member is not None and member.bot is not None,
                    "position": _position(room, member) if member is not None else "",
                    "starting_stack": player.stack + player.committed_hand,
                    "posted": player.committed_hand,
                    "stack_after_posts": player.stack,
                    "hole_cards": hole,
                }
            )
        room.opening = rows

    def _showdown_data(self, room: Room) -> dict:
        game = room.game
        assert game is not None
        revealed = []
        for engine_seat in sorted(game.showdown_seats):
            player = game.players[engine_seat]
            table_seat = room.engine_seats[engine_seat]
            owner = _member_at(room, table_seat)
            revealed.append(
                {
                    "seat": table_seat,
                    "nickname": owner.nickname if owner else "",
                    "hole_cards": _codes(player.hole),
                }
            )
        return {"players": revealed}

    def _emit_progress(self, room: Room) -> None:
        game = room.game
        assert game is not None
        board = [card.code for card in game.board]
        interesting = {
            "FLOP": {"cards": board[:3]},
            "TURN": {"cards": board[3:4]},
            "RIVER": {"cards": board[4:5]},
            "SHOWDOWN": None,
        }
        for street in game.street_path:
            name = street.value
            if name not in interesting or name in room.emitted:
                continue
            payload = interesting[name]
            if name == "SHOWDOWN":
                payload = self._showdown_data(room)
            self._add(room, name, payload or {})
            room.emitted.add(name)
        if game.awaiting_rit and "RIT_OFFER" not in room.emitted:
            self._add(
                room,
                "RIT_OFFER",
                {"seats": _rit_seats(room), "street": game.street.value},
            )
            room.emitted.add("RIT_OFFER")
            room.action_deadline = None
            return
        if game.rit_result is not None and "RIT_RESULT" not in room.emitted:
            self._add(room, "RIT_RESULT", _public_rit(room, game.rit_result))
            room.emitted.add("RIT_RESULT")
        if game.awaiting_insurance and "INSURANCE_OFFER" not in room.emitted:
            self._add(room, "INSURANCE_OFFER", _insurance_payload(room, game))
            room.emitted.add("INSURANCE_OFFER")
            room.action_deadline = None
            return
        if game.street is Street.HAND_COMPLETE:
            if "HAND_COMPLETE" not in room.emitted:
                self._note_tournament(room)
                self._add(room, "HAND_COMPLETE", {"board": board})
                room.emitted.add("HAND_COMPLETE")
                if self.history is not None:
                    self.history.save_room(room)
            return
        if game.actor is not None:
            table_seat = room.engine_seats[game.actor]
            owner = _member_at(room, table_seat)
            payload = {"seat": table_seat, "nickname": owner.nickname if owner else ""}
            seconds = parse_rules(room.rules_spec).time_bank
            if owner is not None and owner.bot is not None:
                room.action_deadline = None
            elif seconds is not None:
                room.action_deadline = room.clock.now() + seconds.seconds
                payload["remaining_seconds"] = remaining_seconds(
                    room.action_deadline,
                    room.clock.now(),
                )
                payload["deadline"] = room.action_deadline
            else:
                room.action_deadline = None
            self._add(room, "ACTION_REQUIRED", payload)

    def _push_state(self, room: Room) -> None:
        self._add(room, "GAME_STATE", {})

    def _sync_members(self, room: Room) -> None:
        game = room.game
        if game is None:
            return
        for engine_seat, table_seat in enumerate(room.engine_seats):
            member = _member_at(room, table_seat)
            if member is not None:
                member.stack = game.players[engine_seat].stack
        room.button_seat = room.engine_seats[game.button]

    def _can_reuse(self, room: Room, lineup: list[tuple[int, int]]) -> bool:
        if room.game is None or room.game.street is not Street.HAND_COMPLETE:
            return False
        if room.game.variant != room.variant:
            return False
        return [seat for seat, _stack in lineup] == list(room.engine_seats)

    def _chip_lineup(self, room: Room) -> list[tuple[int, int]]:
        if room.game is not None and room.engine_seats:
            rows = []
            for table_seat in room.engine_seats:
                member = _member_at(room, table_seat)
                if member is None or member.stack <= 0:
                    return self._fresh_lineup(room)
                rows.append((table_seat, member.stack))
            fresh = self._fresh_lineup(room)
            if [seat for seat, _stack in fresh] != [seat for seat, _stack in rows]:
                return fresh
            return rows
        return self._fresh_lineup(room)

    def _fresh_lineup(self, room: Room) -> list[tuple[int, int]]:
        return [
            (member.seat, member.stack)
            for member in _seated(room)
            if member.seat is not None and member.stack > 0
        ]

    def _install_deck(self, room: Room, game: CashGame) -> None:
        if room.next_deck is None:
            return
        game.deck_provider = room.next_deck
        room.next_deck = None

    def _apply_pending(self, room: Room) -> None:
        if room.pending_small_blind is not None or room.pending_big_blind is not None:
            small = room.pending_small_blind
            if small is None:
                small = room.small_blind
            big = room.pending_big_blind
            if big is None:
                big = room.big_blind
            if not 0 < small < big:
                raise RoomError("small blind must be less than big blind")
            room.small_blind = small
            room.big_blind = big
            room.pending_small_blind = None
            room.pending_big_blind = None
        if room.pending_seats is not None:
            room.seat_count = room.pending_seats
            room.pending_seats = None
        if room.pending_rules_spec is not None:
            room.rules_spec = room.pending_rules_spec
            room.pending_rules_spec = None
        if room.pending_variant is not None:
            room.variant = room.pending_variant
            room.pending_variant = None

    def _store_tournament(self, room: Room, spec: dict) -> None:
        if spec is False or (isinstance(spec, dict) and spec.get("enabled") is False):
            room.tournament = False
            return
        if not isinstance(spec, dict):
            raise RoomError("tournament settings must be an object")
        raw_levels = spec.get("levels")
        if raw_levels is None:
            parsed = list(room.levels)
        else:
            parsed = []
            for level in raw_levels:
                if not isinstance(level, dict):
                    raise RoomError("blind level must be integers")
                small = level.get("small")
                big = level.get("big")
                if isinstance(small, bool) or isinstance(big, bool):
                    raise RoomError("blind level must be integers")
                if not isinstance(small, int) or not isinstance(big, int) or not 0 < small < big:
                    raise RoomError("blind level must be integers")
                parsed.append((small, big))
            if not parsed:
                raise RoomError("tournament needs a blind level")
        hands = spec.get("hands_per_level", room.hands_per_level)
        if isinstance(hands, bool) or not isinstance(hands, int) or hands < 1:
            raise RoomError("hands_per_level must be a positive integer")
        room.levels = parsed
        room.hands_per_level = hands
        room.tournament = True

    def _apply_tournament_level(self, room: Room) -> None:
        if not room.tournament:
            return
        seated = [
            member
            for member in room.members.values()
            if member.seat is not None and member.stack > 0
        ]
        if room.tournament_winner or len(seated) < 2:
            if room.tournament_winner is None and len(seated) == 1:
                room.tournament_winner = seated[0].nickname
            name = room.tournament_winner or "no winner"
            raise RoomError(f"tournament is complete: {name}")
        index = min(room.hands_played // room.hands_per_level, len(room.levels) - 1)
        small, big = room.levels[index]
        room.small_blind = small
        room.big_blind = big

    def _note_tournament(self, room: Room) -> None:
        if not room.tournament:
            return
        room.hands_played += 1
        seated = [
            member
            for member in room.members.values()
            if member.seat is not None and member.stack > 0
        ]
        if len(seated) == 1:
            room.tournament_winner = seated[0].nickname

    def _choose_seat(self, room: Room, seat: int | None) -> int:
        taken = {member.seat for member in room.members.values() if member.seat is not None}
        if seat is None:
            for candidate in range(room.seat_count):
                if candidate not in taken:
                    return candidate
            raise RoomError("no open seat")
        _require_int(seat, "seat is out of range")
        if seat not in range(room.seat_count):
            raise RoomError("seat is out of range")
        if seat in taken:
            raise RoomError("seat is taken")
        return seat

    def _invite_code(self) -> str:
        for _ in range(10):
            code = "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(6))
            if code not in self.by_invite:
                return code
        raise RoomError("could not allocate an invite code")

    def _index(self, room: Room, member: Member) -> None:
        self.rooms[room.room_id] = room
        self.by_invite[room.invite_code] = room.room_id
        self.by_token[member.token] = room.room_id

    def _remove_member(self, room: Room, member: Member) -> None:
        room.members.pop(member.token, None)
        self.by_token.pop(member.token, None)

    def _require_room(self, room_id: str) -> Room:
        room = self.rooms.get(room_id)
        if room is None:
            raise RoomError("room not found", 404)
        return room

    def _by_invite(self, invite_code: str) -> Room:
        room_id = self.by_invite.get(invite_code.strip().upper())
        if room_id is None:
            raise RoomError("room not found", 404)
        return self.rooms[room_id]

    def _find(self, token: str) -> tuple[Room, Member] | None:
        room_id = self.by_token.get(token)
        if room_id is None:
            return None
        room = self.rooms.get(room_id)
        if room is None:
            return None
        member = room.members.get(token)
        if member is None:
            return None
        return room, member

    def _require_member(self, token: str) -> tuple[Room, Member]:
        if not isinstance(token, str) or not token:
            raise RoomError("unknown guest token", 404)
        found = self._find(token)
        if found is None:
            raise RoomError("unknown guest token", 404)
        return found

    def _require_host(self, token: str, message: str) -> tuple[Room, Member]:
        room, member = self._require_member(token)
        if room.host_token != token:
            raise RoomError(message, 403)
        return room, member

    def _in_hand(self, room: Room) -> bool:
        if room.game is None:
            return False
        return room.game.street not in {Street.WAITING, Street.HAND_COMPLETE}

    def _reject_if_hand(self, room: Room, message: str) -> None:
        if self._in_hand(room):
            raise RoomError(message)

    def _add(self, room: Room, event_type: str, data: dict) -> None:
        room.events.append(Event(event_type, data))

    def _run_bots(self, room: Room) -> None:
        if room.bots_running:
            return
        room.bots_running = True
        try:
            for _ in range(400):
                game = room.game
                if game is None or game.actor is None or not self._in_hand(room):
                    return
                if game.awaiting_rit:
                    return
                table_seat = _table_seat(room, game.actor)
                member = _member_at(room, table_seat) if table_seat is not None else None
                if member is None or member.bot is None:
                    return
                observation = self.player_view(room, member)
                try:
                    decision = member.bot.decide(observation)
                    self._apply_action(
                        room,
                        member.token,
                        decision.kind,
                        decision.amount,
                        "bot",
                    )
                except RoomError:
                    room.bot_illegal += 1
                    fallback = _safe_kind(observation)
                    try:
                        self._apply_action(room, member.token, fallback, None, "bot")
                    except RoomError:
                        room.bot_deadlocks += 1
                        return
            room.bot_deadlocks += 1
        finally:
            room.bots_running = False

    def _store_rules(self, room: Room, patch: dict) -> None:
        base = room.pending_rules_spec if room.pending_rules_spec is not None else room.rules_spec
        try:
            merged = merge_rules(dict(base), patch)
        except IllegalActionError as exc:
            raise RoomError(str(exc)) from exc
        if self._in_hand(room):
            room.pending_rules_spec = merged
            return
        room.rules_spec = merged
        room.pending_rules_spec = None

    def _top_up_members(self, room: Room, rules: SelectedRules) -> list[dict[str, int]]:
        if rules.top_up is None:
            return []
        added: list[dict[str, int]] = []
        for member in _seated(room):
            if member.seat is None:
                continue
            new_stack, amount = plan_top_up(member.stack, rules.top_up, room.big_blind)
            if amount:
                member.stack = new_stack
                added.append({"seat": member.seat, "amount": amount})
        return added

    def _check_buyin(self, room: Room, amount: int, *, adding: bool) -> None:
        rules = parse_rules(room.rules_spec)
        if rules.buy_in is None:
            return
        try:
            require_buyin(rules.buy_in, room.big_blind, amount, adding=adding)
        except IllegalActionError as exc:
            raise RoomError(str(exc)) from exc

    def _copy_stacks(self, room: Room) -> None:
        if room.game is None:
            return
        for engine_seat, table_seat in enumerate(room.engine_seats):
            member = _member_at(room, table_seat)
            if member is not None:
                room.game.players[engine_seat].stack = member.stack

    def _sync_member_stack(self, room: Room, member: Member) -> None:
        if room.game is None or member.seat is None or self._in_hand(room):
            return
        engine_seat = _engine_index(room, member.seat)
        if engine_seat is None:
            return
        room.game.players[engine_seat].stack = member.stack


_POSITIONS = {
    2: ("BTN", "BB"),
    3: ("BTN", "SB", "BB"),
    4: ("BTN", "SB", "BB", "UTG"),
    5: ("BTN", "SB", "BB", "UTG", "CO"),
    6: ("BTN", "SB", "BB", "UTG", "HJ", "CO"),
    7: ("BTN", "SB", "BB", "UTG", "MP", "HJ", "CO"),
    8: ("BTN", "SB", "BB", "UTG", "UTG1", "MP", "HJ", "CO"),
    9: ("BTN", "SB", "BB", "UTG", "UTG1", "MP", "LJ", "HJ", "CO"),
}


def _bot_nickname(room: Room, kind: str) -> str:
    label = {"rule": "RuleBot", "equity": "EquityBot", "strategy": "StrategyBot"}.get(kind, "Bot")
    taken = {member.nickname for member in room.members.values()}
    if label not in taken:
        return label
    number = 2
    while f"{label} {number}" in taken:
        number += 1
    return f"{label} {number}"


def _position(room: Room, member: Member) -> str | None:
    if member.seat is None:
        return None
    if room.game is not None and room.engine_seats:
        seats = list(room.engine_seats)
        button = room.engine_seats[room.game.button]
    else:
        seats = [person.seat for person in _seated(room) if person.seat is not None]
        button = room.button_seat if room.button_seat in seats else None
        if button is None and seats:
            button = seats[0]
    if button is None or member.seat not in seats:
        return None
    ordered = sorted(seat for seat in seats if seat is not None)
    start = ordered.index(button)
    ring = ordered[start:] + ordered[:start]
    names = _POSITIONS.get(len(ring))
    if names is None:
        return None
    return names[ring.index(member.seat)]


def _safe_kind(observation: dict) -> str:
    legal = observation.get("game", {}).get("legal_actions") or []
    for kind in ("check", "call", "fold", "all_in"):
        if kind in legal:
            return kind
    if legal:
        return str(legal[0])
    return "check"


def _nickname(value: str) -> str:
    if not isinstance(value, str):
        raise RoomError("nickname must be 1 to 24 characters")
    name = value.strip()
    if not 1 <= len(name) <= 24 or any(ord(char) < 32 for char in name):
        raise RoomError("nickname must be 1 to 24 characters")
    return name


def _require_int(value: object, message: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RoomError(message)
    return value


def _action(name: object, amount: object) -> Action:
    if not isinstance(name, str):
        raise RoomError("unknown action")
    kind = name.strip().lower().replace("-", "_")
    if kind == "fold":
        return Action.fold()
    if kind == "check":
        return Action.check()
    if kind == "call":
        return Action.call()
    if kind == "all_in":
        return Action.all_in()
    if kind == "bet":
        return Action.bet(_require_int(amount, "amount must be a positive integer"))
    if kind == "raise":
        return Action.raise_to(_require_int(amount, "amount must be a positive integer"))
    raise RoomError("unknown action")


def _seated(room: Room) -> list[Member]:
    return sorted(
        (member for member in room.members.values() if member.seat is not None),
        key=lambda member: member.seat if member.seat is not None else 0,
    )


def _member_at(room: Room, seat: int) -> Member | None:
    for member in room.members.values():
        if member.seat == seat:
            return member
    return None


def _engine_index(room: Room, table_seat: int) -> int | None:
    try:
        return room.engine_seats.index(table_seat)
    except ValueError:
        return None


def _table_seat(room: Room, engine_seat: int | None) -> int | None:
    if engine_seat is None:
        return None
    if engine_seat not in range(len(room.engine_seats)):
        return None
    return room.engine_seats[engine_seat]


def _button_index(seats: list[int], previous: int | None, advance: bool) -> int:
    if previous is None or previous not in seats:
        if previous is None:
            return 0
        higher = [index for index, seat in enumerate(seats) if seat > previous]
        return higher[0] if higher else 0
    index = seats.index(previous)
    if not advance:
        return index
    return (index + 1) % len(seats)


def _tournament_view(room: Room) -> dict:
    if not room.levels:
        level = {"small": room.small_blind, "big": room.big_blind}
    else:
        index = min(room.hands_played // max(room.hands_per_level, 1), len(room.levels) - 1)
        small, big = room.levels[index]
        level = {"small": small, "big": big}
    return {
        "enabled": room.tournament,
        "level": level,
        "hands_played": room.hands_played,
        "hands_per_level": room.hands_per_level,
        "winner": room.tournament_winner,
    }


def _insurance_view(room: Room, game: CashGame | None) -> dict | None:
    if game is None or not game.awaiting_insurance or not game.insurance_quote:
        return None
    quote = dict(game.insurance_quote)
    quote["seat"] = _table_seat(room, int(quote["seat"]))
    quote["label"] = "simplified"
    return quote


def _insurance_payload(room: Room, game: CashGame) -> dict:
    shown = _insurance_view(room, game)
    if shown is None:
        return {"label": "simplified"}
    return shown


def _pot_amount(game: CashGame) -> int:
    if game.street is Street.HAND_COMPLETE:
        return sum(pot.amount for pot in game.pots)
    return sum(player.committed_hand for player in game.players)


def _effective_stack(room: Room, member: Member) -> int:
    game = room.game
    if game is None or member.seat is None:
        return member.stack
    engine_seat = _engine_index(room, member.seat)
    if engine_seat is None:
        return member.stack
    hero = game.players[engine_seat].stack
    others = [game.players[seat].stack for seat in game.in_hand if seat != engine_seat]
    if not others:
        return hero
    return min(hero, max(others))


def _legal(game: CashGame, engine_seat: int) -> tuple[list[str], int, int | None]:
    player: Player = game.players[engine_seat]
    to_call = max(0, game.current_bet - player.committed_street)
    actions = ["fold"]
    min_raise_to = None
    if to_call == 0:
        actions.append("check")
        if game.current_bet == 0 and player.stack >= game.big_blind:
            actions.append("bet")
        elif player.can_raise:
            covered = player.committed_street + player.stack
            minimum = game.current_bet + game.min_raise_increment
            if covered >= minimum:
                actions.append("raise")
                min_raise_to = minimum
        if player.stack > 0:
            actions.append("all_in")
    elif player.stack > to_call:
        actions.append("call")
        if player.can_raise:
            covered = player.committed_street + player.stack
            minimum = game.current_bet + game.min_raise_increment
            if covered >= minimum:
                actions.append("raise")
                min_raise_to = minimum
        if player.stack > 0:
            actions.append("all_in")
    elif player.stack == to_call:
        actions.append("call")
    elif player.stack > 0:
        actions.append("all_in")
    return actions, to_call, min_raise_to


def _rit_seats(room: Room) -> list[int]:
    game = room.game
    if game is None:
        return []
    seats = []
    for engine_seat in game._alive_seats():
        table_seat = _table_seat(room, engine_seat)
        if table_seat is not None:
            seats.append(table_seat)
    return seats


def _public_boards(game: CashGame | None) -> list[list[str]]:
    if game is None or not game.boards:
        return []
    return [[card.code for card in board] for board in game.boards]


def _bounty_rows(room: Room, game: CashGame | None) -> list[dict]:
    if game is None:
        return []
    return _public_payments(room, game.bounty_payments)


def _public_payments(room: Room, payments: list[dict]) -> list[dict]:
    rows = []
    for payment in payments:
        rows.append(
            {
                "seat": _table_seat(room, payment["seat"]),
                "winner": _table_seat(room, payment["winner"]),
                "amount": payment["amount"],
                "partial": payment["partial"],
            }
        )
    return rows


def _public_rit(room: Room, result: dict) -> dict:
    runs = []
    for run in result.get("runs", []):
        pots = []
        for pot in run["pots"]:
            pots.append(
                {
                    "amount": pot["amount"],
                    "eligible": [_table_seat(room, seat) for seat in pot["eligible"]],
                    "awards": [
                        {"seat": _table_seat(room, award["seat"]), "amount": award["amount"]}
                        for award in pot["awards"]
                    ],
                }
            )
        runs.append({"board": run["board"], "pots": pots})
    return {"accepted": result.get("accepted", False), "runs": runs}


def _positive_chips(amount: object, message: str) -> int:
    chips = _require_int(amount, message)
    if chips <= 0:
        raise RoomError(message)
    return chips


def _codes(hole: tuple[Card, Card] | None) -> list[str] | None:
    if hole is None:
        return None
    return [card.code for card in hole]
