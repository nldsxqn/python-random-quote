import json
from contextlib import ExitStack

import pytest
from app.engine.cards import parse_cards
from app.engine.deck import RiggedDeck
from app.main import app
from app.services.hub import RoomHub
from fastapi.testclient import TestClient

SHOWDOWN_PREFIX = parse_cards("As Ks Ad Kd 2c 7d 9h 3s 4c 5h 6d Jc")


@pytest.fixture(autouse=True)
def fresh_hub() -> None:
    app.state.hub = RoomHub()


def test_rigged_showdown_hides_holes_and_rejects_illegal_actions() -> None:
    with TestClient(app) as client:
        alice = _create(client, "Alice")
        bob = _join(client, alice["invite_code"], "Bob")
        cara = _join(client, alice["invite_code"], "Cara")
        _sit(client, alice, 0)
        _sit(client, bob, 1)
        app.state.hub.service.set_deck(alice["room_id"], RiggedDeck(list(SHOWDOWN_PREFIX)))

        with ExitStack() as stack:
            sockets = {
                "alice": _connect(stack, client, alice["guest_token"]),
                "bob": _connect(stack, client, bob["guest_token"]),
                "cara": _connect(stack, client, cara["guest_token"]),
            }
            before = _state(client, alice)
            assert before["game"]["street"] is None

            started = client.post(
                f"/rooms/{alice['room_id']}/start",
                json={"guest_token": alice["guest_token"]},
            )
            assert started.status_code == 200
            opened = {name: _until(sock, "GAME_STATE") for name, sock in sockets.items()}

            assert _holes(opened["alice"], "CARDS_DEALT") == ["As", "Ad"]
            assert _holes(opened["bob"], "CARDS_DEALT") == ["Ks", "Kd"]
            assert _holes(opened["cara"], "CARDS_DEALT") is None
            _assert_hidden(opened["alice"], "Ks", "Kd")
            _assert_hidden(opened["bob"], "As", "Ad")
            _assert_hidden(opened["cara"], "As", "Ad", "Ks", "Kd")
            assert "deck" not in json.dumps(opened)

            snapshot = _state(client, alice)
            sockets["bob"].send_json(
                {
                    "type": "PLAYER_ACTION",
                    "request_id": "bob-early",
                    "payload": {"action": "raise", "amount": 120},
                }
            )
            illegal = sockets["bob"].receive_json()
            assert illegal["type"] == "ERROR"
            assert illegal["request_id"] == "bob-early"
            assert _state(client, alice)["game"] == snapshot["game"]

            sockets["cara"].send_json(
                {
                    "type": "PLAYER_ACTION",
                    "request_id": "watch",
                    "payload": {"action": "fold"},
                }
            )
            spectator_error = sockets["cara"].receive_json()
            assert spectator_error["type"] == "ERROR"
            assert "spectators cannot act" in spectator_error["payload"]["message"]
            assert _state(client, alice)["game"] == snapshot["game"]

            sockets["alice"].send_json(
                {
                    "type": "PLAYER_ACTION",
                    "request_id": "alice-shove",
                    "payload": {"action": "all_in"},
                }
            )
            alice_shove = _until(sockets["alice"], "GAME_STATE")
            _assert_hidden(alice_shove, "Ks", "Kd")
            sockets["bob"].send_json(
                {
                    "type": "PLAYER_ACTION",
                    "request_id": "bob-call",
                    "payload": {"action": "call"},
                }
            )
            alice_rest = _until(sockets["alice"], "HAND_COMPLETE")
            bob_rest = _until(sockets["bob"], "HAND_COMPLETE")
            cara_rest = _until(sockets["cara"], "HAND_COMPLETE")
            _assert_hidden(_before(alice_rest, "SHOWDOWN"), "Ks", "Kd")
            _assert_hidden(_before(bob_rest, "SHOWDOWN"), "As", "Ad")
            _assert_hidden(_before(cara_rest, "SHOWDOWN"), "As", "Ad", "Ks", "Kd")
            showdown = next(item for item in alice_rest if item["type"] == "SHOWDOWN")
            revealed = {
                row["seat"]: row["hole_cards"] for row in showdown["payload"]["players"]
            }
            assert revealed[0] == ["As", "Ad"]
            assert revealed[1] == ["Ks", "Kd"]

            final = _state(client, alice)
            assert final["game"]["street"] == "HAND_COMPLETE"
            stacks = {row["seat"]: row["stack"] for row in final["players"]}
            assert stacks == {0: 2000, 1: 0}
            assert "deck" not in json.dumps(final)


def test_reconnect_receives_state_and_can_act() -> None:
    with TestClient(app) as client:
        alice = _create(client, "Alice")
        bob = _join(client, alice["invite_code"], "Bob")
        _sit(client, alice, 0)
        _sit(client, bob, 1)
        with ExitStack() as stack:
            alice_ws = _connect(stack, client, alice["guest_token"])
            bob_ws = _connect(stack, client, bob["guest_token"])
            client.post(
                f"/rooms/{alice['room_id']}/start",
                json={"guest_token": alice["guest_token"]},
            )
            _until(alice_ws, "ACTION_REQUIRED")
            _until(bob_ws, "ACTION_REQUIRED")
            alice_ws.send_json(
                {"type": "PLAYER_ACTION", "request_id": "complete", "payload": {"action": "call"}}
            )
            _until(alice_ws, "ACTION_REQUIRED")
            _until(bob_ws, "ACTION_REQUIRED")

        with client.websocket_connect("/ws/room") as bob_ws:
            bob_ws.send_json({"type": "JOIN", "payload": {"guest_token": bob["guest_token"]}})
            joined = bob_ws.receive_json()
            state = bob_ws.receive_json()
            assert joined["type"] == "ROOM_JOINED"
            assert state["type"] == "GAME_STATE"
            assert state["payload"]["game"]["actor_seat"] == 1
            assert state["payload"]["you"]["seat"] == 1
            bob_ws.send_json(
                {"type": "PLAYER_ACTION", "request_id": "back", "payload": {"action": "check"}}
            )
            followed = _until(bob_ws, "ACTION_RESULT")
            assert followed[-1]["payload"]["action"] == "check"
            assert all(item["type"] != "ERROR" for item in followed)
            restored = _state(client, bob)
            assert restored["game"]["street"] == "FLOP"


def test_non_host_cannot_change_blinds_and_host_change_waits_for_next_hand() -> None:
    with TestClient(app) as client:
        alice = _create(client, "Alice")
        bob = _join(client, alice["invite_code"], "Bob")
        _sit(client, alice, 0)
        _sit(client, bob, 1)
        denied = client.post(
            f"/rooms/{alice['room_id']}/settings",
            json={"guest_token": bob["guest_token"], "big_blind": 10},
        )
        assert denied.status_code == 403
        assert denied.json()["type"] == "ERROR"
        assert _state(client, alice)["settings"]["big_blind"] == 2

        with ExitStack() as stack:
            alice_ws = _connect(stack, client, alice["guest_token"])
            bob_ws = _connect(stack, client, bob["guest_token"])
            client.post(
                f"/rooms/{alice['room_id']}/start",
                json={"guest_token": alice["guest_token"]},
            )
            _until(alice_ws, "ACTION_REQUIRED")
            _until(bob_ws, "ACTION_REQUIRED")
            paused = client.post(
                f"/rooms/{alice['room_id']}/pause",
                json={"guest_token": bob["guest_token"], "paused": True},
            )
            assert paused.status_code == 403
            changed = client.post(
                f"/rooms/{alice['room_id']}/settings",
                json={"guest_token": alice["guest_token"], "big_blind": 10},
            )
            assert changed.status_code == 200
            live = _state(client, alice)
            assert live["game"]["big_blind"] == 2
            assert live["settings"]["big_blind"] == 2
            assert live["settings"]["pending_big_blind"] == 10
            alice_ws.send_json(
                {"type": "PLAYER_ACTION", "request_id": "fold", "payload": {"action": "fold"}}
            )
            _until(alice_ws, "HAND_COMPLETE")

        again = client.post(
            f"/rooms/{alice['room_id']}/start",
            json={"guest_token": alice["guest_token"]},
        )
        assert again.status_code == 200
        nxt = _state(client, alice)
        assert nxt["game"]["big_blind"] == 10
        assert nxt["settings"]["pending_big_blind"] is None


def _create(client: TestClient, nickname: str) -> dict:
    response = client.post("/rooms", json={"nickname": nickname})
    assert response.status_code == 200
    body = response.json()
    assert body["seat"] is None
    assert body["room_id"]
    assert body["invite_code"]
    assert body["guest_token"]
    return body


def _join(client: TestClient, invite_code: str, nickname: str) -> dict:
    response = client.post("/rooms/join", json={"invite_code": invite_code, "nickname": nickname})
    assert response.status_code == 200
    body = response.json()
    assert body["guest_token"]
    assert body["seat"] is None
    return body


def _sit(client: TestClient, player: dict, seat: int) -> None:
    response = client.post(
        f"/rooms/{player['room_id']}/sit",
        json={"guest_token": player["guest_token"], "seat": seat},
    )
    assert response.status_code == 200
    assert response.json()["seat"] == seat


def _state(client: TestClient, player: dict) -> dict:
    response = client.get(
        f"/rooms/{player['room_id']}",
        params={"guest_token": player["guest_token"]},
    )
    assert response.status_code == 200
    return response.json()


def _connect(stack: ExitStack, client: TestClient, token: str):
    socket = stack.enter_context(client.websocket_connect("/ws/room"))
    socket.send_json({"type": "JOIN", "payload": {"guest_token": token}})
    assert socket.receive_json()["type"] == "ROOM_JOINED"
    assert socket.receive_json()["type"] == "GAME_STATE"
    return socket


def test_player_view_numbers_the_hand_and_names_the_blinds() -> None:
    with TestClient(app) as client:
        alice = _create(client, "Alice")
        bob = _join(client, alice["invite_code"], "Bob")
        cara = _join(client, alice["invite_code"], "Cara")
        _sit(client, alice, 0)
        _sit(client, bob, 1)
        _sit(client, cara, 2)
        before = _state(client, alice)
        assert before["game"]["hand_number"] is None
        assert before["game"]["small_blind_seat"] is None
        assert before["game"]["big_blind_seat"] is None
        started = client.post(
            f"/rooms/{alice['room_id']}/start",
            json={"guest_token": alice["guest_token"]},
        )
        assert started.status_code == 200
        live = _state(client, alice)
        assert live["game"]["hand_number"] == 1
        assert live["game"]["button_seat"] == 0
        assert live["game"]["small_blind_seat"] == 1
        assert live["game"]["big_blind_seat"] == 2
        assert live["you"]["hole_cards"] is not None


def _until(socket, event_type: str, limit: int = 20) -> list[dict]:
    found: list[dict] = []
    for _ in range(limit):
        message = socket.receive_json()
        found.append(message)
        if message["type"] == event_type:
            return found
    raise AssertionError(found)


def _holes(messages: list[dict], event_type: str):
    for message in messages:
        if message["type"] == event_type:
            return message["payload"].get("hole_cards")
    return None


def _before(messages: list[dict], event_type: str) -> list[dict]:
    prefix: list[dict] = []
    for message in messages:
        if message["type"] == event_type:
            break
        prefix.append(message)
    return prefix


def _assert_hidden(messages: list[dict], *cards: str) -> None:
    blob = json.dumps(messages)
    for card in cards:
        assert card not in blob
