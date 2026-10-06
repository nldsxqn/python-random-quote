import json
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.database.migrate import alembic_ini, upgrade_database
from app.database.models import (
    ActionRow,
    AnalysisJob,
    BoardRow,
    DecisionAnalysis,
    Hand,
    HandPlayer,
    Player,
    PlayerStatistics,
    PotRow,
    RoomRow,
    RuleEvent,
    TrainerSpot,
)
from app.db import create_db_engine
from app.engine.cards import parse_cards
from app.engine.deck import RiggedDeck
from app.engine.state import Street
from app.history.store import HandHistory
from app.main import app
from app.services.hub import RoomHub
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

SHOWDOWN = parse_cards("As Ks Ad Kd 2c 7d 9h 3s 4c 5h 6d Jc")
AA_KK = "As Ks Ad Kd 2c 7d 9h 3s 4c 5h 6d Jc 8c Kh 9c 4d"
SEVEN = parse_cards("7c Ah 2d Kd 9c 7h 7s 3c 8c 4c 6c 5d")
TABLES = {
    "players",
    "rooms",
    "hands",
    "hand_players",
    "actions",
    "boards",
    "pots",
    "rule_events",
    "analysis_jobs",
    "decision_analysis",
    "player_statistics",
    "trainer_spots",
}


@pytest.fixture
def api(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'hands.db'}"
    upgrade_database(url)
    store = HandHistory(create_db_engine(url))
    app.state.history = store
    app.state.hub = RoomHub(history=store)
    with TestClient(app) as client:
        yield client, store


def test_alembic_upgrade_on_a_temporary_database(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrate.db'}"
    config = Config(str(alembic_ini()))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    engine = create_db_engine(url)
    from sqlalchemy import inspect

    names = set(inspect(engine).get_table_names())
    assert TABLES <= names
    action_columns = {column["name"] for column in inspect(engine).get_columns("actions")}
    assert {"street", "pot_before", "stack_before", "acted_at", "amount"} <= action_columns
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(AnalysisJob)) == 0
        assert session.scalar(select(func.count()).select_from(DecisionAnalysis)) == 0
        assert session.scalar(select(func.count()).select_from(PlayerStatistics)) == 0
        assert session.scalar(select(func.count()).select_from(TrainerSpot)) == 0


def test_rigged_hand_round_trips_and_preflop_hides_the_flop(api) -> None:
    client, store = api
    service = app.state.hub.service
    host = service.create("Alice")
    guest = service.join(host["invite_code"], "Bob")
    service.sit(host["guest_token"], 0)
    service.sit(guest["guest_token"], 1)
    service.set_deck(host["room_id"], RiggedDeck(list(SHOWDOWN)))
    service.start(host["guest_token"])
    _check_down(service, host["room_id"])
    bot_host = service.create("Gina")
    service.sit(bot_host["guest_token"], 0)
    service.add_bot(bot_host["guest_token"], "rule", seed=1)
    service.start(bot_host["guest_token"])
    service.act(bot_host["guest_token"], "fold", None, "fold")
    room = service.rooms[host["room_id"]]
    game = room.game
    assert game is not None
    assert game.street is Street.HAND_COMPLETE
    live_board = [card.code for card in game.board]
    live_stacks = {
        room.engine_seats[player.seat]: player.stack for player in game.players
    }

    with store.sessions() as session:
        hand = session.scalar(select(Hand).where(Hand.room_id == host["room_id"]))
        assert hand is not None
        players = list(session.scalars(select(HandPlayer).where(HandPlayer.hand_id == hand.id)))
        bot_hand = session.scalar(select(Hand).where(Hand.room_id == bot_host["room_id"]))
        assert bot_hand is not None
        bot_players = list(
            session.scalars(select(HandPlayer).where(HandPlayer.hand_id == bot_hand.id))
        )
        assert any(player.is_bot for player in bot_players)
        boards = list(session.scalars(select(BoardRow).where(BoardRow.hand_id == hand.id)))
        stored_stacks = {player.seat: player.ending_stack for player in players}
        assert stored_stacks == live_stacks
        assert boards[0].cards == live_board
        assert {player.hole_cards[0] for player in players if player.nickname == "Alice"} == {"As"}

    listed = client.get("/hands", params={"room_id": host["room_id"]})
    assert listed.status_code == 200
    hand_id = listed.json()["hands"][0]["id"]
    final = client.get(f"/hands/{hand_id}/state", params={"index": 99, "viewer_seat": 0})
    assert final.status_code == 400
    detail = client.get(f"/hands/{hand_id}", params={"viewer_seat": 0}).json()
    done = client.get(
        f"/hands/{hand_id}/state",
        params={"index": detail["step_count"] - 1, "viewer_seat": 0},
    ).json()
    assert done["board"] == live_board
    assert {row["seat"]: row["stack"] for row in done["players"]} == live_stacks

    for index in (0, 1):
        state = client.get(
            f"/hands/{hand_id}/state",
            params={"index": index, "viewer_seat": 0},
        ).json()
        assert state["street"] == "PREFLOP"
        assert state["board"] == []
        if index == 0:
            assert state["hand_number"] == hand_id
            assert state["button_seat"] == state["small_blind_seat"]
            assert state["big_blind_seat"] != state["button_seat"]
            seats = {row["seat"]: row for row in state["players"]}
            assert seats[state["small_blind_seat"]]["committed_street"] == 1
            assert seats[state["big_blind_seat"]]["committed_street"] == 2
            assert seats[state["big_blind_seat"]]["status"] == "ACTIVE"
        encoded = json.dumps(state)
        for card in live_board:
            assert card not in encoded
        assert "Ks" not in encoded
        assert "Kd" not in encoded
        assert "As" in encoded
    hidden = client.get(f"/hands/{hand_id}/state", params={"index": 0}).json()
    assert "As" not in json.dumps(hidden)
    showdown = client.get(
        f"/hands/{hand_id}/state",
        params={"index": detail["jumps"]["showdown"], "viewer_seat": 0},
    ).json()
    assert "Ks" in json.dumps(showdown)
    assert showdown["showdown"] is True


def test_run_it_twice_stores_both_boards(api) -> None:
    client, store = api
    service = app.state.hub.service
    host = service.create("Cara")
    guest = service.join(host["invite_code"], "Dan")
    service.sit(host["guest_token"], 0)
    service.sit(guest["guest_token"], 1)
    service.update_settings(host["guest_token"], None, None, None, {"run_it_twice": True})
    service.set_deck(host["room_id"], RiggedDeck(parse_cards(AA_KK)))
    service.start(host["guest_token"])
    service.act(host["guest_token"], "all_in", None, "a")
    service.act(guest["guest_token"], "all_in", None, "b")
    service.vote_run_it_twice(host["guest_token"], True, "y1")
    service.vote_run_it_twice(guest["guest_token"], True, "y2")
    game = service.rooms[host["room_id"]].game
    assert game is not None
    assert game.street is Street.HAND_COMPLETE
    expected = [[card.code for card in board] for board in game.boards]
    assert len(expected) == 2
    with store.sessions() as session:
        boards = list(session.scalars(select(BoardRow).order_by(BoardRow.run_index)))
        event = session.scalars(select(RuleEvent).where(RuleEvent.kind == "run_it_twice")).one()
    assert [board.cards for board in boards] == expected
    assert event.payload["accepted"] is True
    assert [run["board"] for run in event.payload["runs"]] == expected
    hand_id = client.get("/hands").json()["hands"][0]["id"]
    detail = client.get(f"/hands/{hand_id}", params={"viewer_seat": 0}).json()
    shown = client.get(
        f"/hands/{hand_id}/state",
        params={"index": detail["jumps"]["showdown"], "viewer_seat": 0},
    ).json()
    assert shown["boards"] == expected
    preflop = client.get(
        f"/hands/{hand_id}/state",
        params={"index": 0, "viewer_seat": 0},
    ).json()
    assert preflop["board"] == []
    assert preflop["boards"] == []


def test_bounty_and_rake_are_stored_apart_from_the_pot(api) -> None:
    _client, store = api
    service = app.state.hub.service
    host = service.create("Eve")
    guest = service.join(host["invite_code"], "Finn")
    service.sit(host["guest_token"], 0, 200)
    service.sit(guest["guest_token"], 1, 200)
    service.update_settings(
        host["guest_token"],
        None,
        None,
        None,
        {
            "rake": {"percentage": 50, "cap": 10, "no_flop_no_drop": True},
            "seven_deuce": {"payment_per_player_bb": 10, "require_showdown": True},
        },
    )
    service.set_deck(host["room_id"], RiggedDeck(list(SEVEN)))
    service.start(host["guest_token"])
    _check_down(service, host["room_id"])
    game = service.rooms[host["room_id"]].game
    assert game is not None
    assert game.rake > 0
    assert game.bounty > 0
    with store.sessions() as session:
        hand = session.scalars(select(Hand)).one()
        pots = list(session.scalars(select(PotRow)))
        events = {event.kind: event.payload for event in session.scalars(select(RuleEvent))}
        players = list(session.scalars(select(HandPlayer)))
    assert hand.rake == game.rake
    assert hand.bounty == game.bounty
    assert sum(pot.amount for pot in pots) + hand.rake == 4
    assert hand.bounty not in {pot.amount for pot in pots}
    assert events["rake"]["amount"] == game.rake
    assert events["bounty"]["amount"] == game.bounty
    assert sum(payment["amount"] for payment in events["bounty"]["payments"]) == game.bounty
    stored = {player.seat: player.ending_stack for player in players}
    live = {
        service.rooms[host["room_id"]].engine_seats[player.seat]: player.stack
        for player in game.players
    }
    assert stored == live
    assert sum(player.pot_payout for player in players) == sum(pot.amount for pot in pots)


def test_stats_fixture_matches_hand_calculated_numbers(api) -> None:
    client, store = api
    with store.sessions() as session:
        _stats_fixture(session)
        session.commit()
    alice = client.get(
        "/stats",
        params={
            "player": "Alice",
            "position": "BTN",
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "small_blind": 1,
            "big_blind": 2,
            "rules": "{}",
        },
    ).json()
    assert alice["hands_played"] == 2
    assert alice["vpip"] == 100
    assert alice["pfr"] == 100
    assert alice["three_bet"] is None
    assert alice["three_bet_opportunities"] == 0
    assert alice["cbet"] == 100
    assert alice["cbet_opportunities"] == 1
    assert alice["bb_per_100"] == -150
    bob = client.get(
        "/stats",
        params={
            "player": "Bob",
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "small_blind": 1,
            "big_blind": 2,
            "rules": "{}",
        },
    ).json()
    assert bob["hands_played"] == 2
    assert bob["vpip"] == 100
    assert bob["pfr"] == 50
    assert bob["three_bet"] == 50
    assert bob["three_bet_opportunities"] == 2
    assert bob["cbet"] is None
    assert bob["bb_per_100"] == 0
    later = client.get(
        "/stats",
        params={"player": "Alice", "date_from": "2026-02-01", "date_to": "2026-02-01"},
    ).json()
    assert later["hands_played"] == 1
    assert later["vpip"] == 0
    assert later["pfr"] == 0
    assert "voluntary preflop" in later["definitions"]["vpip"]


def test_extended_stats_from_a_stored_hand_and_analysis_row(api) -> None:
    client, store = api
    with store.sessions() as session:
        _stats_fixture(session)
        _extended_stats_rows(session)
        session.commit()
    alice = client.get(
        "/stats",
        params={
            "player": "Alice",
            "position": "BTN",
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "small_blind": 1,
            "big_blind": 2,
            "rules": "{}",
        },
    ).json()
    assert alice["fold_to_3bet"] == 100
    assert alice["wtsd"] == 0
    assert alice["wssd"] is None
    assert alice["aggression_factor"] is None
    assert alice["fold_to_cbet"] is None
    assert alice["ev_bb"] is None
    assert alice["gto_ev_bb"] is None
    assert alice["ev_loss_bb"] is None
    assert alice["mistake_counts"] == {
        "good": 0,
        "small": 0,
        "medium": 0,
        "large": 0,
        "critical": 0,
    }
    bob = client.get(
        "/stats",
        params={
            "player": "Bob",
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "small_blind": 1,
            "big_blind": 2,
            "rules": "{}",
        },
    ).json()
    assert bob["fold_to_3bet"] is None
    assert bob["wtsd"] == 0
    assert bob["wssd"] is None
    assert bob["aggression_factor"] == 1
    assert bob["fold_to_cbet"] == 100
    assert bob["ev_loss_bb"] is None
    cara = client.get("/stats", params={"player": "Cara"}).json()
    assert cara["hands_played"] == 1
    assert cara["fold_to_3bet"] == 0
    assert cara["wtsd"] == 100
    assert cara["wssd"] == 100
    assert cara["aggression_factor"] == 0.5
    assert cara["fold_to_cbet"] == 0
    assert cara["ev_bb"] == 3
    assert cara["gto_ev_bb"] == 5
    assert cara["ev_loss_bb"] == 2
    assert cara["mistake_counts"] == {
        "good": 0,
        "small": 1,
        "medium": 0,
        "large": 1,
        "critical": 0,
    }
    flop = client.get("/stats", params={"player": "Cara", "street": "flop"}).json()
    assert flop["hands_played"] == 1
    assert flop["aggression_factor"] == 0
    assert flop["ev_bb"] == 2
    assert flop["gto_ev_bb"] == 3.5
    assert flop["ev_loss_bb"] == 1.5
    assert flop["mistake_counts"]["large"] == 1
    assert flop["mistake_counts"]["small"] == 0
    river = client.get("/stats", params={"player": "Cara", "street": "RIVER"}).json()
    assert river["hands_played"] == 1
    assert river["aggression_factor"] is None
    assert river["ev_bb"] == 1
    assert river["gto_ev_bb"] == 1.5
    assert river["ev_loss_bb"] == 0.5
    assert river["mistake_counts"]["small"] == 1
    fay = client.get("/stats", params={"player": "Fay"}).json()
    assert fay["hands_played"] == 1
    assert fay["wtsd"] == 100
    assert fay["wssd"] == 100
    assert fay["ev_bb"] is None
    assert fay["mistake_counts"]["critical"] == 0


def _check_down(service, room_id: str) -> None:
    room = service.rooms[room_id]
    for step in range(40):
        game = room.game
        assert game is not None
        if game.street is Street.HAND_COMPLETE:
            return
        if game.actor is None:
            raise AssertionError(game.street)
        seat = room.engine_seats[game.actor]
        member = next(person for person in room.members.values() if person.seat == seat)
        if member.bot is not None:
            raise AssertionError("a bot was left to act")
        legal = service.view(member.token)["game"]["legal_actions"]
        if "check" in legal:
            service.act(member.token, "check", None, f"c{step}")
        elif "call" in legal:
            service.act(member.token, "call", None, f"c{step}")
        else:
            service.act(member.token, "fold", None, f"c{step}")
    raise AssertionError("hand did not finish")


def _stats_fixture(session: Session) -> None:
    """Two January 1/2 hands plus one later hand that the filters leave out.

    Hand 1: Alice opens on the button and bets the flop. Bob calls preflop and folds.
    Alice nets 0. Bob nets -6. One c-bet from one chance. Bob has a 3-bet chance and calls.
    Hand 2: Alice opens, Bob 3-bets, Alice folds. Alice nets -6. Bob nets +6.
    Bob's 3-bet is 1 of 2 chances. There is no flop.
    Hand 3: 2/5 on 2026-02-01 with an ante. Alice checks the big blind. It is not
    in the January 1/2 no-rule sample.
    """
    session.add(Player(id=1, nickname="Alice", created_at="2026-01-02T00:00:00+00:00"))
    session.add(Player(id=2, nickname="Bob", created_at="2026-01-02T00:00:00+00:00"))
    session.add(
        RoomRow(
            id="room",
            invite_code="STATS1",
            created_at="2026-01-02T00:00:00+00:00",
            small_blind=1,
            big_blind=2,
            seat_count=2,
        )
    )
    session.add(
        _hand(1, "2026-01-02T12:00:00+00:00", 1, 2, {}),
    )
    session.add(_hand(2, "2026-01-03T12:00:00+00:00", 1, 2, {}))
    session.add(
        _hand(
            3,
            "2026-02-01T12:00:00+00:00",
            2,
            5,
            {"ante": {"mode": "normal", "amount": 1}},
        )
    )
    session.add_all(
        [
            _seat(1, 1, 0, "BTN", 100, 100),
            _seat(1, 2, 1, "BB", 100, 94),
            _seat(2, 1, 0, "BTN", 100, 94),
            _seat(2, 2, 1, "BB", 100, 106),
            _seat(3, 1, 1, "BB", 100, 100),
            _seat(3, 2, 0, "BTN", 100, 100),
            _action(1, 0, 0, 1, "PREFLOP", "raise", 6, True),
            _action(1, 1, 1, 2, "PREFLOP", "call", None, False),
            _action(1, 2, 0, 1, "FLOP", "bet", 6, False),
            _action(1, 3, 1, 2, "FLOP", "fold", None, False),
            _action(2, 0, 0, 1, "PREFLOP", "raise", 6, True),
            _action(2, 1, 1, 2, "PREFLOP", "raise", 18, True),
            _action(2, 2, 0, 1, "PREFLOP", "fold", None, False),
            _action(3, 0, 1, 1, "PREFLOP", "check", None, False),
        ]
    )


def _hand(hand_id: int, completed: str, small: int, big: int, rules: dict) -> Hand:
    return Hand(
        id=hand_id,
        room_id="room",
        started_at=completed,
        completed_at=completed,
        small_blind=small,
        big_blind=big,
        button_seat=0,
        sb_seat=0,
        bb_seat=1,
        opening_street="PREFLOP",
        table_settings={"small_blind": small, "big_blind": big, "seats": 2, "button": 0},
        rule_settings=rules,
        rake=0,
        bounty=0,
        showdown=False,
        all_in_seats=[],
        winners=[],
    )


def _seat(
    hand_id: int,
    player_id: int,
    seat: int,
    position: str,
    starting: int,
    ending: int,
) -> HandPlayer:
    return HandPlayer(
        hand_id=hand_id,
        player_id=player_id,
        seat=seat,
        position=position,
        nickname="Alice" if player_id == 1 else "Bob",
        is_bot=False,
        starting_stack=starting,
        posted=0,
        stack_after_posts=starting,
        ending_stack=ending,
        hole_cards=["As", "Ad"],
        pot_payout=0,
        bounty_payout=0,
        showed=False,
    )


def _action(
    hand_id: int,
    order_index: int,
    seat: int,
    player_id: int,
    street: str,
    action: str,
    amount: int | None,
    raised: bool,
) -> ActionRow:
    return ActionRow(
        hand_id=hand_id,
        order_index=order_index,
        street=street,
        seat=seat,
        player_id=player_id,
        action=action,
        amount=amount,
        put_in=0,
        pot_before=0,
        stack_before=100,
        raised=raised,
        acted_at="2026-01-02T12:00:00+00:00",
    )


def _extended_stats_rows(session: Session) -> None:
    """One analyzed showdown, plus an all-in hand whose flop exists only on the board."""
    session.add(Player(id=3, nickname="Cara", created_at="2026-01-02T00:00:00+00:00"))
    session.add(Player(id=4, nickname="Drew", created_at="2026-01-02T00:00:00+00:00"))
    session.add(Player(id=5, nickname="Fay", created_at="2026-01-02T00:00:00+00:00"))
    session.add(Player(id=6, nickname="Gina", created_at="2026-01-02T00:00:00+00:00"))
    showdown = _hand(4, "2026-01-04T12:00:00+00:00", 1, 2, {})
    showdown.showdown = True
    showdown.winners = [0]
    raced = _hand(5, "2026-01-05T12:00:00+00:00", 1, 2, {})
    raced.showdown = True
    raced.winners = [0]
    session.add(showdown)
    session.add(raced)
    session.add_all(
        [
            _named(4, 3, 0, "BTN", "Cara", 100, 130, True),
            _named(4, 4, 1, "BB", "Drew", 100, 70, True),
            _named(5, 5, 0, "BTN", "Fay", 100, 150, True),
            _named(5, 6, 1, "BB", "Gina", 100, 50, True),
            _action(4, 0, 0, 3, "PREFLOP", "raise", 6, True),
            _action(4, 1, 1, 4, "PREFLOP", "raise", 18, True),
            _action(4, 2, 0, 3, "PREFLOP", "call", None, False),
            _action(4, 3, 1, 4, "FLOP", "bet", 20, False),
            _action(4, 4, 0, 3, "FLOP", "call", None, False),
            _action(4, 5, 0, 3, "RIVER", "check", None, False),
            _action(5, 0, 0, 5, "PREFLOP", "all_in", None, True),
            _action(5, 1, 1, 6, "PREFLOP", "call", None, False),
            BoardRow(
                hand_id=5,
                run_index=0,
                flop=["Ah", "Kd", "2c"],
                turn="7s",
                river="9c",
                cards=["Ah", "Kd", "2c", "7s", "9c"],
            ),
            DecisionAnalysis(
                hand_id=4,
                street="flop",
                seat=0,
                position="BTN",
                action="call",
                ev=4,
                ev_loss=1.5,
                severity="Large",
            ),
            DecisionAnalysis(
                hand_id=4,
                street="river",
                seat=0,
                position="BTN",
                action="check",
                ev=2,
                ev_loss=0.5,
                severity="Small",
            ),
        ]
    )


def _named(
    hand_id: int,
    player_id: int,
    seat: int,
    position: str,
    nickname: str,
    starting: int,
    ending: int,
    showed: bool,
) -> HandPlayer:
    return HandPlayer(
        hand_id=hand_id,
        player_id=player_id,
        seat=seat,
        position=position,
        nickname=nickname,
        is_bot=False,
        starting_stack=starting,
        posted=0,
        stack_after_posts=starting,
        ending_stack=ending,
        hole_cards=["As", "Ad"],
        pot_payout=0,
        bounty_payout=0,
        showed=showed,
    )
