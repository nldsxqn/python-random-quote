"""Bots act through the room, and only from a player's own observation."""

import json
import time
from pathlib import Path

import pytest
from app.bots.base import PokerBot
from app.bots.equity_bot import EquityBot
from app.bots.factory import make_bot
from app.bots.strategy import StrategyBot, load_fixture_store, spot_key
from app.engine.cards import parse_cards
from app.engine.deck import RiggedDeck, SeededDeck
from app.engine.state import Street
from app.main import app
from app.services.hub import RoomHub
from app.services.rooms import RoomService
from fastapi.testclient import TestClient

SHOWDOWN = parse_cards("As Ks Ad Kd 2c 7d 9h 3s 4c 5h 6d Jc")


@pytest.fixture(autouse=True)
def fresh_hub() -> None:
    app.state.hub = RoomHub()


def test_bots_do_not_import_the_server_hand_or_deck() -> None:
    root = Path(__file__).resolve().parents[1] / "app" / "bots"
    for path in root.rglob("*.py"):
        text = path.read_text()
        assert "app.engine.game" not in text
        assert "app.engine.deck" not in text
        assert "app.services" not in text
        assert "CashGame" not in text


def test_observation_hides_opponent_holes_and_the_deck() -> None:
    seen: dict = {}

    class Probe(PokerBot):
        def decide(self, observation: dict):
            seen["observation"] = observation
            return make_bot("rule", seed=1).decide(observation)

    service = RoomService()
    host = service.create("Host")
    service.add_bot(host["guest_token"], "rule", seat=0, bot=Probe())
    service.add_bot(host["guest_token"], "rule", seat=1, seed=2)
    service.set_deck(host["room_id"], RiggedDeck(list(SHOWDOWN)))
    service.start(host["guest_token"])
    observation = seen["observation"]
    blob = json.dumps(observation)
    assert observation["you"]["hole_cards"] == ["As", "Ad"]
    assert observation["you"]["position"] == "BTN"
    opponent = next(row for row in observation["players"] if row["seat"] != 0)
    assert opponent["hole_cards"] is None
    assert "Ks" not in blob
    assert "Kd" not in blob
    _assert_no_deck(observation)
    assert "deck" not in blob
    kinds = observation["game"]["legal_actions"]
    assert kinds
    action = make_bot("rule", seed=1).decide(observation)
    assert action.kind in kinds


def test_strategy_fixture_and_equity_fallback() -> None:
    store = load_fixture_store()
    fallback = _RecordingEquity()
    bot = StrategyBot(store, fallback, seed=4)
    opening = _opening_observation()
    assert store.lookup(opening) is not None
    assert spot_key(opening)[2] == "BTN"
    decision = bot.decide(opening)
    assert fallback.calls == 0
    assert decision.kind == "raise"
    assert decision.amount == 6

    missed = _opening_observation()
    missed["game"] = {**missed["game"], "board": ["2c", "7d", "9h"], "action_history": [
        {"action": "raise", "amount": 6},
    ]}
    assert store.lookup(missed) is None
    played = bot.decide(missed)
    assert fallback.calls == 1
    assert played.kind in missed["game"]["legal_actions"]

    service = RoomService()
    host = service.create("Host")
    service.sit(host["guest_token"], 1)
    table_fallback = _RecordingEquity()
    table_bot = StrategyBot(load_fixture_store(), table_fallback, seed=4)
    service.add_bot(host["guest_token"], "strategy", seat=0, bot=table_bot)
    service.set_deck(host["room_id"], SeededDeck(4))
    service.start(host["guest_token"])
    room = service.rooms[host["room_id"]]
    assert room.hand_history[0]["action"] == "raise"
    assert room.hand_history[0]["amount"] == 6
    assert table_fallback.calls == 0
    _finish_as_human(service, host["guest_token"], room)
    assert room.game is not None
    assert room.game.street is Street.HAND_COMPLETE
    assert table_fallback.calls >= 1
    assert room.bot_illegal == 0
    assert room.bot_deadlocks == 0


def test_host_adds_and_removes_a_bot_without_breaking_the_table() -> None:
    with TestClient(app) as client:
        host = client.post("/rooms", json={"nickname": "Host"}).json()
        guest = client.post(
            "/rooms/join",
            json={"invite_code": host["invite_code"], "nickname": "Guest"},
        ).json()
        denied = client.post(
            f"/rooms/{host['room_id']}/bots",
            json={"guest_token": guest["guest_token"], "kind": "rule"},
        )
        assert denied.status_code == 403
        added = client.post(
            f"/rooms/{host['room_id']}/bots",
            json={"guest_token": host["guest_token"], "kind": "rule", "seed": 3},
        )
        assert added.status_code == 200
        body = added.json()
        assert body["kind"] == "rule"
        assert body["nickname"] == "RuleBot"
        assert "guest_token" not in body
        sat = client.post(
            f"/rooms/{host['room_id']}/sit",
            json={"guest_token": host["guest_token"], "seat": 1},
        )
        assert sat.status_code == 200
        started = client.post(
            f"/rooms/{host['room_id']}/start",
            json={"guest_token": host["guest_token"]},
        )
        assert started.status_code == 200
        state = client.get(
            f"/rooms/{host['room_id']}",
            params={"guest_token": host["guest_token"]},
        ).json()
        assert state["game"]["street"] in {"PREFLOP", "FLOP", "TURN", "RIVER", "HAND_COMPLETE"}
        if state["game"]["street"] != "HAND_COMPLETE":
            early = client.post(
                f"/rooms/{host['room_id']}/bots/remove",
                json={"guest_token": host["guest_token"], "seat": body["seat"]},
            )
            assert early.status_code == 400
            _act_until_done(host)
        removed = client.post(
            f"/rooms/{host['room_id']}/bots/remove",
            json={"guest_token": host["guest_token"], "seat": body["seat"]},
        )
        assert removed.status_code == 200
        after = client.get(
            f"/rooms/{host['room_id']}",
            params={"guest_token": host["guest_token"]},
        ).json()
        assert all(row["is_bot"] is False for row in after["players"])


def test_rule_bots_conserve_chips_for_ten_thousand_hands() -> None:
    service = RoomService()
    host = service.create("Host")
    service.add_bot(host["guest_token"], "rule", seed=11)
    service.add_bot(host["guest_token"], "rule", seed=29)
    started = time.perf_counter()
    hands = 0
    while hands < 10000 and time.perf_counter() - started < 60:
        _rebuy(service, host["room_id"])
        before = _chips(service, host["room_id"])
        service.set_deck(host["room_id"], SeededDeck(50_000 + hands))
        service.start(host["guest_token"])
        room = service.rooms[host["room_id"]]
        assert room.game is not None
        assert room.game.street is Street.HAND_COMPLETE
        assert _chips(service, host["room_id"]) == before
        hands += 1
    elapsed = time.perf_counter() - started
    room = service.rooms[host["room_id"]]
    assert room.bot_illegal == 0
    assert room.bot_deadlocks == 0
    if hands < 10000:
        rate = hands / elapsed if elapsed else 0
        pytest.fail(
            f"RuleBot simulation finished {hands} hands in {elapsed:.1f}s "
            f"({rate:.1f} hands/s). Chip, illegal-action, and deadlock checks stayed in place."
        )


def test_equity_bots_finish_hands_without_illegal_actions() -> None:
    service = RoomService()
    host = service.create("Host")
    left = EquityBot(
        tightness=0.05, aggression=0.3, bluff_frequency=0.0, simulation_count=2, seed=5
    )
    right = EquityBot(
        tightness=0.05, aggression=0.3, bluff_frequency=0.0, simulation_count=2, seed=6
    )
    service.add_bot(host["guest_token"], "equity", bot=left)
    service.add_bot(host["guest_token"], "equity", bot=right)
    for hand in range(20):
        _rebuy(service, host["room_id"])
        before = _chips(service, host["room_id"])
        service.set_deck(host["room_id"], SeededDeck(80 + hand))
        service.start(host["guest_token"])
        room = service.rooms[host["room_id"]]
        assert room.game is not None
        assert room.game.street is Street.HAND_COMPLETE
        assert _chips(service, host["room_id"]) == before
    room = service.rooms[host["room_id"]]
    assert room.bot_illegal == 0
    assert room.bot_deadlocks == 0


class _RecordingEquity(EquityBot):
    def __init__(self) -> None:
        super().__init__(
            tightness=0.0,
            aggression=0.2,
            bluff_frequency=0.0,
            simulation_count=2,
            seed=3,
        )
        self.calls = 0

    def decide(self, observation: dict):
        self.calls += 1
        return super().decide(observation)


def _opening_observation() -> dict:
    return {
        "settings": {"small_blind": 1, "big_blind": 2},
        "you": {"seat": 0, "position": "BTN", "hole_cards": ["As", "Ad"]},
        "players": [
            {
                "seat": 0,
                "stack": 999,
                "committed_street": 1,
                "committed_hand": 1,
                "status": "ACTIVE",
                "hole_cards": ["As", "Ad"],
            },
            {
                "seat": 1,
                "stack": 998,
                "committed_street": 2,
                "committed_hand": 2,
                "status": "ACTIVE",
                "hole_cards": None,
            },
        ],
        "game": {
            "street": "PREFLOP",
            "board": [],
            "pot": 3,
            "big_blind": 2,
            "to_call": 1,
            "min_raise_to": 4,
            "legal_actions": ["fold", "call", "raise", "all_in"],
            "action_history": [],
        },
    }


def _finish_as_human(service: RoomService, token: str, room) -> None:
    for step in range(24):
        game = room.game
        assert game is not None
        if game.street is Street.HAND_COMPLETE or game.actor is None:
            return
        seat = room.engine_seats[game.actor]
        member = next(person for person in room.members.values() if person.seat == seat)
        if member.bot is not None:
            raise AssertionError("a bot was left to act")
        view = service.view(token)
        legal = view["game"]["legal_actions"]
        if "check" in legal:
            service.act(token, "check", None, f"h{step}")
        elif "call" in legal:
            service.act(token, "call", None, f"h{step}")
        else:
            service.act(token, "fold", None, f"h{step}")


def _act_until_done(host: dict) -> None:
    service = app.state.hub.service
    room = service.rooms[host["room_id"]]
    for step in range(24):
        game = room.game
        if game is None or game.street is Street.HAND_COMPLETE or game.actor is None:
            return
        seat = room.engine_seats[game.actor]
        if seat != host_seat(room, host["guest_token"]):
            raise AssertionError(seat)
        legal = service.view(host["guest_token"])["game"]["legal_actions"]
        if "check" in legal:
            service.act(host["guest_token"], "check", None, f"t{step}")
        elif "call" in legal:
            service.act(host["guest_token"], "call", None, f"t{step}")
        else:
            service.act(host["guest_token"], "fold", None, f"t{step}")
    raise AssertionError("hand did not finish")


def host_seat(room, token: str) -> int | None:
    return room.members[token].seat


def _rebuy(service: RoomService, room_id: str) -> None:
    room = service.rooms[room_id]
    for member in list(room.members.values()):
        if member.seat is not None and member.bot is not None and member.stack <= 0:
            service.add_chips(member.token, 1000)


def _chips(service: RoomService, room_id: str) -> int:
    room = service.rooms[room_id]
    return sum(member.stack for member in room.members.values() if member.seat is not None)


def _assert_no_deck(value: object) -> None:
    if isinstance(value, dict):
        assert "deck" not in value
        for item in value.values():
            _assert_no_deck(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_deck(item)
