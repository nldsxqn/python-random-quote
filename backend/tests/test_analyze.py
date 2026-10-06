import json
from pathlib import Path

import pytest
from app.analysis.review import classify_loss
from app.database.migrate import upgrade_database
from app.db import create_db_engine
from app.engine.cards import parse_cards
from app.engine.deck import RiggedDeck
from app.history.store import HandHistory
from app.main import app
from app.services.hub import RoomHub
from app.solver.ranges import matrix, parse_range
from fastapi.testclient import TestClient

PREFIX = parse_cards("As Ks Ad Kd 2c 7d 9h 3s 4c 5h 6d Jc")


@pytest.fixture
def api(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'analyze.db'}"
    upgrade_database(url)
    store = HandHistory(create_db_engine(url))
    app.state.history = store
    app.state.hub = RoomHub(history=store)
    with TestClient(app) as client:
        yield client


def test_loss_thresholds_and_range_matrix() -> None:
    assert classify_loss(0.099) == "Good"
    assert classify_loss(0.1) == "Small"
    assert classify_loss(0.49) == "Small"
    assert classify_loss(0.5) == "Medium"
    assert classify_loss(1.99) == "Medium"
    assert classify_loss(2) == "Large"
    assert classify_loss(5) == "Large"
    assert classify_loss(5.01) == "Critical"
    assert classify_loss(0.2, good=0.3) == "Good"
    grid = matrix(parse_range("AA,AKs,AKo"))
    assert len(grid) == 13
    assert len(grid[0]) == 13
    assert grid[0][0] == 6
    assert grid[0][1] == 4
    assert grid[1][0] == 12


def test_heads_up_fold_is_saved_and_the_answer_stays_hidden(api) -> None:
    client = api
    hand_id = _mistake(client)
    report = client.get(f"/analyze/hands/{hand_id}")
    assert report.status_code == 200
    body = report.json()
    assert body["tree"]["kind"] == "hand"
    river = [
        item
        for item in body["decisions"]
        if item["street"] == "RIVER" and item["action"] == "fold"
    ]
    assert river
    fold = river[0]
    assert fold["metadata"]["exact"] is True
    assert fold["metadata"]["label"] == "heads-up one-decision"
    assert fold["ev_loss_bb"] > 0.5
    assert fold["severity"] in {"Small", "Medium", "Large", "Critical"}
    assert len(fold["matrix"]) == 13
    assert "Exact GTO" not in json.dumps(body)
    spots = client.get("/trainer/spots").json()["spots"]
    assert spots
    hidden = json.dumps(spots)
    assert "frequencies" not in hidden
    assert "ev_loss" not in hidden
    assert "original_action" not in hidden
    prompt = client.get(f"/trainer/spots/{spots[0]['id']}")
    assert "frequencies" not in prompt.json()
    choice = prompt.json()["prompt"]["actions"][0]
    revealed = client.post(
        f"/trainer/spots/{spots[0]['id']}/answer",
        json={"action": choice},
    )
    assert revealed.status_code == 200
    answer = revealed.json()
    assert answer["your_action"] == choice
    assert answer["frequencies"]
    assert "evs" in answer
    assert answer["original_action"]
    assert answer["ev_loss"] is not None
    count = len(spots)
    again = client.get(f"/analyze/hands/{hand_id}")
    assert again.status_code == 200
    assert len(client.get("/trainer/spots").json()["spots"]) == count
    listed = client.get("/trainer/spots", params={"street": "RIVER"}).json()["spots"]
    assert listed
    assert client.get("/trainer/spots", params={"street": "PREFLOP"}).json()["spots"] == []
    future = client.get("/trainer/spots", params={"date_from": "2999-01-01"}).json()
    assert future["spots"] == []


def test_multiway_analysis_is_approximate(api) -> None:
    client = api
    service = app.state.hub.service
    host = service.create("Alice")
    bob = service.join(host["invite_code"], "Bob")
    cara = service.join(host["invite_code"], "Cara")
    service.sit(host["guest_token"], 0)
    service.sit(bob["guest_token"], 1)
    service.sit(cara["guest_token"], 2)
    service.set_deck(host["room_id"], RiggedDeck(list(PREFIX)))
    service.start(host["guest_token"])
    room = host["room_id"]
    _act(service, room, "Alice", "call", None)
    _act(service, room, "Bob", "call", None)
    _act(service, room, "Cara", "check", None)
    _act(service, room, "Bob", "bet", 30)
    _act(service, room, "Cara", "fold", None)
    _act(service, room, "Alice", "fold", None)
    hand_id = client.get("/hands").json()["hands"][0]["id"]
    body = client.get(f"/analyze/hands/{hand_id}").json()
    scored = [item for item in body["decisions"] if item["frequencies"]]
    multi = [item for item in scored if item["player_count"] >= 3]
    assert multi
    assert all(item["metadata"]["label"] == "Approximate Analysis" for item in multi)
    assert all(item["metadata"]["exact"] is False for item in scored)
    assert "Exact GTO" not in json.dumps(body)


def _mistake(client: TestClient) -> int:
    service = app.state.hub.service
    host = service.create("Alice")
    guest = service.join(host["invite_code"], "Bob")
    service.sit(host["guest_token"], 0)
    service.sit(guest["guest_token"], 1)
    service.set_deck(host["room_id"], RiggedDeck(list(PREFIX)))
    service.start(host["guest_token"])
    room = host["room_id"]
    _act(service, room, "Alice", "call", None)
    _act(service, room, "Bob", "check", None)
    _act(service, room, "Bob", "check", None)
    _act(service, room, "Alice", "check", None)
    _act(service, room, "Bob", "check", None)
    _act(service, room, "Alice", "check", None)
    _act(service, room, "Bob", "bet", 2)
    _act(service, room, "Alice", "fold", None)
    hands = client.get("/hands").json()["hands"]
    return hands[0]["id"]


def _act(service, room_id: str, nickname: str, action: str, amount: int | None) -> None:
    room = service.rooms[room_id]
    member = next(person for person in room.members.values() if person.nickname == nickname)
    service.act(member.token, action, amount, f"{nickname}-{action}-{amount}")
