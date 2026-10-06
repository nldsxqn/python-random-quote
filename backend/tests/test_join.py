"""A second browser joining a room, including a private-LAN page."""

import re

from app.config.settings import LAN_ORIGIN_REGEX
from app.main import app
from app.services.hub import RoomHub
from fastapi.testclient import TestClient

_ORIGIN = re.compile(LAN_ORIGIN_REGEX)


def test_origin_pattern_allows_lan_hosts_and_rejects_public_ones() -> None:
    assert _ORIGIN.fullmatch("http://localhost:3000")
    assert _ORIGIN.fullmatch("http://127.0.0.1:3000")
    assert _ORIGIN.fullmatch("http://[::1]:3000")
    assert _ORIGIN.fullmatch("http://10.1.2.3:3000")
    assert _ORIGIN.fullmatch("http://192.168.1.20:3000")
    assert _ORIGIN.fullmatch("http://172.16.5.5:3000")
    assert _ORIGIN.fullmatch("http://172.31.0.1:3000")
    assert _ORIGIN.fullmatch("http://desktop-pc:3000")
    assert _ORIGIN.fullmatch("https://files.local:3000")
    assert _ORIGIN.fullmatch("https://evil.example") is None
    assert _ORIGIN.fullmatch("http://8.8.8.8:3000") is None
    assert _ORIGIN.fullmatch("http://172.15.0.1:3000") is None
    assert _ORIGIN.fullmatch("http://172.32.0.1:3000") is None


def test_second_client_joins_from_a_lan_origin_and_websocket() -> None:
    app.state.hub = RoomHub()
    origin = "http://192.168.1.20:3000"
    with TestClient(app) as client:
        created = client.post(
            "/rooms",
            json={"nickname": "Alice"},
            headers={"Origin": "http://localhost:3000"},
        )
        assert created.status_code == 200
        code = created.json()["invite_code"]
        host_token = created.json()["guest_token"]
        with client.websocket_connect("/ws/room") as host:
            host.send_json({"type": "JOIN", "payload": {"guest_token": host_token}})
            assert host.receive_json()["type"] == "ROOM_JOINED"
            assert host.receive_json()["type"] == "GAME_STATE"

            preflight = client.options(
                "/rooms/join",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                    "Access-Control-Request-Private-Network": "true",
                },
            )
            assert preflight.status_code == 200
            assert preflight.headers["access-control-allow-origin"] == origin
            assert preflight.headers["access-control-allow-origin"] != "*"
            assert preflight.headers["access-control-allow-private-network"] == "true"

            denied = client.options(
                "/rooms/join",
                headers={
                    "Origin": "https://evil.example",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            assert denied.status_code == 400
            assert denied.headers.get("access-control-allow-origin") in {None, ""}

            joined = client.post(
                "/rooms/join",
                json={"invite_code": f"  {code.lower()}  ", "nickname": "Bob"},
                headers={"Origin": origin},
            )
            assert joined.status_code == 200
            assert joined.headers["access-control-allow-origin"] == origin
            assert joined.json()["invite_code"] == code

            notice = host.receive_json()
            assert notice["type"] == "PLAYER_JOINED"
            assert notice["payload"]["nickname"] == "Bob"
            host_state = host.receive_json()
            assert "Bob" in host_state["payload"]["spectators"]

            with client.websocket_connect("/ws/room") as guest:
                guest.send_json(
                    {"type": "JOIN", "payload": {"guest_token": joined.json()["guest_token"]}}
                )
                assert guest.receive_json()["type"] == "ROOM_JOINED"
                state = guest.receive_json()
                assert state["type"] == "GAME_STATE"
                assert state["payload"]["you"]["nickname"] == "Bob"
                assert "Alice" in state["payload"]["spectators"]

        blank = client.post("/rooms/join", json={"invite_code": code, "nickname": " "})
        assert blank.status_code == 400
        assert blank.json()["payload"]["message"] == "nickname must be 1 to 24 characters"
        missing = client.post("/rooms/join", json={"invite_code": code})
        assert missing.status_code == 422
        assert missing.json()["detail"][0]["msg"] == "Field required"
