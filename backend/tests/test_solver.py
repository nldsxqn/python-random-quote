import json
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.database.migrate import alembic_ini
from app.database.models import AnalysisJob, DecisionAnalysis
from app.db import create_db_engine
from app.engine.deck import RiggedDeck
from app.engine.state import Street
from app.main import app
from app.services.hub import RoomHub
from app.solver.approx import APPROX_LABEL, approximate_mix
from app.solver.jobs import AnalysisStore
from app.solver.mock import MockSolverAdapter
from app.solver.ranges import parse_range
from app.solver.reference import ReferenceSolverAdapter
from app.solver.types import SolveRequest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

RIVER = "2c 7d 9h 4s 3c"
PREFIX = "As Ks Ad Kd 2c 7d 9h 3s 4c 5h 6d Jc"


def test_mock_solver_is_stable_and_labeled() -> None:
    adapter = MockSolverAdapter()
    first = adapter.solve_spot(SolveRequest())
    second = adapter.solve_spot(
        SolveRequest(players=6, board=RIVER, hero_range="AA", villain_range="KK")
    )
    assert first.to_dict() == second.to_dict()
    assert first.metadata["solver"] == "mock"
    assert first.metadata["label"] == "mock"
    assert first.metadata["mock"] is True
    assert first.metadata["exact"] is False
    assert first.frequencies == {"check": 0.55, "bet": 0.45}
    assert adapter.health_check() == {"status": "ok", "solver": "mock"}
    assert "Exact GTO" not in json.dumps(first.metadata)


def test_river_enumerates_one_heads_up_decision() -> None:
    result = ReferenceSolverAdapter().solve_spot(
        SolveRequest(
            players=2,
            board=RIVER,
            pot=20,
            effective_stack=100,
            hero_position="BTN",
            villain_position="BB",
            hero_range="AA",
            villain_range="KK",
            bet_sizes=[10],
            iterations=80,
        )
    )
    assert result.metadata["exact"] is True
    assert result.metadata["label"] == "heads-up one-decision"
    assert result.metadata["method"] == "enumerate"
    assert result.strategy["villain"]["fold"] > 0.8
    assert abs(sum(result.frequencies.values()) - 1) < 1e-9
    assert set(result.evs) == set(result.actions)
    assert all(isinstance(value, float) for value in result.evs.values())
    assert "Exact GTO" not in json.dumps(result.to_dict())


def test_flop_uses_monte_carlo_and_is_not_exact() -> None:
    result = ReferenceSolverAdapter().solve_spot(
        SolveRequest(
            players=2,
            board="2c 7d 9h",
            pot=20,
            effective_stack=80,
            hero_range="AsKd",
            villain_range="QcQd",
            bet_sizes=[10],
            iterations=6,
            samples=4,
        )
    )
    assert result.metadata["exact"] is False
    assert result.metadata["method"] == "monte_carlo"
    assert result.metadata["label"] == "heads-up one-decision"
    assert abs(sum(result.frequencies.values()) - 1) < 1e-9
    assert "Exact GTO" not in json.dumps(result.metadata)


def test_preflop_and_multiway_are_not_exact() -> None:
    adapter = ReferenceSolverAdapter()
    preflop = adapter.solve_spot(
        SolveRequest(players=2, board="", hero_range="AA", villain_range="KK")
    )
    multiway = adapter.solve_spot(
        SolveRequest(
            players=3,
            board=RIVER,
            pot=30,
            hero_range="AA",
            villain_range="KK",
        )
    )
    assert preflop.metadata["exact"] is False
    assert preflop.metadata["available"] is False
    assert multiway.metadata["exact"] is False
    assert multiway.metadata["available"] is False
    assert multiway.metadata["reason"] == "multiway"
    assert "Exact GTO" not in json.dumps(preflop.metadata)
    assert "Exact GTO" not in json.dumps(multiway.metadata)


def test_facing_a_bet_is_fold_or_call() -> None:
    result = ReferenceSolverAdapter().solve_spot(
        SolveRequest(
            players=2,
            board=RIVER,
            pot=30,
            effective_stack=100,
            hero_range="AA",
            villain_range="KK",
            action_history=[{"action": "bet", "amount": 10}],
        )
    )
    assert result.actions == ["fold", "call"]
    assert result.frequencies["call"] == 1
    assert result.metadata["exact"] is True


def test_live_mix_changes_with_holding_and_line() -> None:
    board = ["Kh", "8d", "3c", "2s"]
    legal = ["check", "bet", "all_in"]
    shared = {
        "board": board,
        "pot": 30,
        "to_call": 0,
        "street": "TURN",
        "position": "BTN",
        "legal_actions": legal,
        "player_count": 3,
        "effective_stack": 180,
        "hero_seat": 0,
        "stacks": [180, 160, 140],
    }
    pocket = approximate_mix(hero_cards=["As", "Ad"], action_history=_checks(), **shared)
    offs = approximate_mix(hero_cards=["7c", "2d"], action_history=_checks(), **shared)
    betting = approximate_mix(hero_cards=["Qc", "Jd"], action_history=_bets(), **shared)
    checked = approximate_mix(hero_cards=["Qc", "Jd"], action_history=_checks(), **shared)
    for mix in (pocket, offs, betting, checked):
        assert abs(sum(mix["frequencies"].values()) - 1) < 1e-6
        assert mix["metadata"]["exact"] is False
        assert mix["metadata"]["label"] == APPROX_LABEL
        assert "Exact GTO" not in json.dumps(mix)
    assert _apart(pocket["frequencies"], offs["frequencies"])
    assert _apart(betting["frequencies"], checked["frequencies"])


def test_ranges_parse_pairs_and_suited() -> None:
    assert len(parse_range("AA")) == 6
    assert len(parse_range("AKs")) == 4
    assert len(parse_range("AsKd")) == 1


def test_study_shows_a_mix_and_competitive_hides_it() -> None:
    app.state.hub = RoomHub()
    service = app.state.hub.service
    host = service.create("Alice")
    guest = service.join(host["invite_code"], "Bob")
    service.sit(host["guest_token"], 0)
    service.sit(guest["guest_token"], 1)
    service.set_deck(host["room_id"], RiggedDeck(parse_prefix()))
    service.start(host["guest_token"])
    room = service.rooms[host["room_id"]]
    _reach(service, host["room_id"], Street.RIVER)
    competitive = service.view(host["guest_token"])
    assert "gto" not in competitive["you"]
    hidden = service.player_view(room, room.members[host["guest_token"]])
    assert "gto" not in hidden["you"]
    service.update_settings(host["guest_token"], None, None, None, gto_mode="study")
    shown = service.view(host["guest_token"])
    advice = shown["you"]["gto"]
    assert advice["metadata"]["exact"] is True
    assert advice["metadata"]["label"] == "heads-up one-decision"
    assert abs(sum(advice["frequencies"].values()) - 1) < 1e-6
    assert "Exact GTO" not in json.dumps(advice)
    service.update_settings(host["guest_token"], None, None, None, gto_mode="competitive")
    assert "gto" not in service.view(host["guest_token"])["you"]


def test_multiway_hand_returns_frequencies() -> None:
    app.state.hub = RoomHub()
    service = app.state.hub.service
    host = service.create("Alice")
    bob = service.join(host["invite_code"], "Bob")
    cara = service.join(host["invite_code"], "Cara")
    service.sit(host["guest_token"], 0)
    service.sit(bob["guest_token"], 1)
    service.sit(cara["guest_token"], 2)
    service.start(host["guest_token"])
    view = service.view(host["guest_token"])
    advice = view["you"]["gto"]
    frequencies = advice["frequencies"]
    assert abs(sum(frequencies.values()) - 1) < 1e-6
    assert set(frequencies) == set(view["game"]["legal_actions"])
    assert advice["metadata"]["exact"] is False
    assert advice["metadata"]["label"] == APPROX_LABEL
    blob = json.dumps(view)
    assert "Real-time multiway GTO analysis is not available" not in blob
    assert "Exact GTO" not in blob
    host_seat = view["you"]["seat"]
    for row in view["players"]:
        if row["seat"] != host_seat:
            assert row["hole_cards"] is None
    assert "deck" not in view
    service.update_settings(host["guest_token"], None, None, None, gto_mode="study")
    study = service.view(host["guest_token"])["you"]["gto"]
    assert study["metadata"]["exact"] is False
    assert abs(sum(study["frequencies"].values()) - 1) < 1e-6
    assert "Real-time multiway GTO analysis is not available" not in json.dumps(study)


def test_a_bot_observation_has_no_gto() -> None:
    app.state.hub = RoomHub()
    service = app.state.hub.service
    host = service.create("Alice")
    service.sit(host["guest_token"], 0)
    service.add_bot(host["guest_token"], "rule", 1, 1)
    service.update_settings(host["guest_token"], None, None, None, gto_mode="study")
    service.start(host["guest_token"])
    room = service.rooms[host["room_id"]]
    bot = next(member for member in room.members.values() if member.bot is not None)
    assert "gto" not in service.player_view(room, bot)["you"]
    assert "gto" not in service.view(bot.token)["you"]


def test_solve_endpoint_persists_and_hides_live_competitive(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'solver.db'}"
    config = Config(str(alembic_ini()))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    engine = create_db_engine(url)
    app.state.analysis = AnalysisStore(engine)
    with TestClient(app) as client:
        health = client.get("/solver/health", params={"adapter": "mock"})
        assert health.status_code == 200
        assert health.json() == {"status": "ok", "solver": "mock"}
        live = client.post(
            "/solver/solve",
            json={"adapter": "mock", "during_hand": True, "mode": "competitive", "player_count": 2},
        )
        assert live.status_code == 200
        assert "frequencies" not in live.json()
        multi = client.post(
            "/solver/solve",
            json={"adapter": "reference", "during_hand": True, "mode": "study", "player_count": 3},
        )
        multi_body = multi.json()
        assert "frequencies" in multi_body
        assert abs(sum(multi_body["frequencies"].values()) - 1) < 1e-6
        assert multi_body["metadata"]["exact"] is False
        assert "Real-time multiway GTO analysis is not available" not in json.dumps(multi_body)
        assert "Exact GTO" not in json.dumps(multi_body)
        saved = client.post(
            "/solver/solve",
            json={"adapter": "mock", "mode": "posthand", "hero_range": "AA", "villain_range": "KK"},
        )
        assert saved.status_code == 200
        assert saved.json()["metadata"]["mock"] is True
        assert saved.json()["frequencies"]["check"] == 0.55
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(AnalysisJob)) == 3
        assert session.scalar(select(func.count()).select_from(DecisionAnalysis)) == 3


def _apart(left: dict[str, float], right: dict[str, float]) -> bool:
    keys = set(left) | set(right)
    return any(abs(left.get(key, 0.0) - right.get(key, 0.0)) > 0.03 for key in keys)


def _checks() -> list[dict]:
    return [
        {"seat": 1, "street": "FLOP", "action": "check", "amount": None, "raised": False},
        {"seat": 2, "street": "FLOP", "action": "check", "amount": None, "raised": False},
    ]


def _bets() -> list[dict]:
    return [
        {
            "seat": 1,
            "street": "FLOP",
            "action": "bet",
            "amount": 18,
            "put_in": 18,
            "pot_before": 12,
            "raised": True,
        },
        {
            "seat": 2,
            "street": "FLOP",
            "action": "raise",
            "amount": 48,
            "pot_before": 30,
            "raised": True,
        },
        {"seat": 1, "street": "FLOP", "action": "call", "amount": None, "raised": False},
    ]


def parse_prefix():
    from app.engine.cards import parse_cards

    return parse_cards(PREFIX)


def _reach(service, room_id: str, street: Street) -> None:
    room = service.rooms[room_id]
    for step in range(40):
        game = room.game
        assert game is not None
        if game.street is street and game.actor is not None:
            return
        if game.street is Street.HAND_COMPLETE or game.actor is None:
            raise AssertionError(game.street)
        seat = room.engine_seats[game.actor]
        member = next(person for person in room.members.values() if person.seat == seat)
        legal = service.player_view(room, member)["game"]["legal_actions"]
        if "check" in legal:
            service.act(member.token, "check", None, f"s{step}")
        elif "call" in legal:
            service.act(member.token, "call", None, f"s{step}")
        else:
            service.act(member.token, "fold", None, f"s{step}")
    raise AssertionError("street not reached")
