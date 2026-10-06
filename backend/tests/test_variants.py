from app.engine.actions import Action
from app.engine.cards import parse_cards
from app.engine.deck import RiggedDeck
from app.engine.evaluator import evaluate
from app.engine.game import CashGame
from app.engine.short_deck import evaluate_short
from app.engine.state import Street
from app.main import app
from app.rules.selected import parse_rules
from app.services.hub import RoomHub
from fastapi.testclient import TestClient

LOSE = parse_cards("7c Ah 2d Ad 9c Jc Tc 3d 4h Ks 8s 5c")


def test_short_deck_changes_the_wheel_and_flush_without_changing_holdem() -> None:
    boat = evaluate(parse_cards("7h 7d"), parse_cards("7c Kd Ks 2c 3d"))
    flush = evaluate(parse_cards("Ah Kh"), parse_cards("Qh Jh 9h 2c 3d"))
    assert boat > flush
    short_flush = evaluate_short(parse_cards("Ah Kh"), parse_cards("Qh Jh 9h 8c 7d"))
    short_boat = evaluate_short(parse_cards("7c 7d"), parse_cards("7h Kd Ks 8c 6d"))
    assert short_flush > short_boat
    assert short_flush.category == "flush"
    assert short_boat.category == "full house"
    wheel = evaluate_short(parse_cards("Ah 6c"), parse_cards("7d 8c 9s Kd Qc"))
    kings = evaluate_short(parse_cards("Kd Kc"), parse_cards("7d 8c 9s Qh Js"))
    assert wheel.category == "straight"
    assert wheel > kings
    game = CashGame([40, 40], button=0, small_blind=1, big_blind=2, variant="short_deck")
    game.start_hand()
    assert len(game.deck) == 36
    game.apply(Action.fold())
    assert game.chip_total() == 80


def test_mississippi_and_custom_straddles_act_last_and_utg_still_posts() -> None:
    mississippi = CashGame(
        [100, 100, 100, 100],
        button=0,
        small_blind=5,
        big_blind=10,
        rules=parse_rules({"straddle": {"style": "mississippi", "amount_bb": 2}}),
    )
    mississippi.start_hand()
    assert mississippi.straddle_seat == 0
    assert mississippi.players[0].committed_street == 20
    assert mississippi.actor == 1
    custom = CashGame(
        [100, 100, 100, 100],
        button=0,
        small_blind=5,
        big_blind=10,
        rules=parse_rules({"straddle": {"style": "custom", "amount_bb": 2, "seat": 2}}),
    )
    custom.start_hand()
    assert custom.straddle_seat == 2
    assert custom.players[2].committed_street == 20
    assert custom.actor == 3
    utg = CashGame(
        [100, 100, 100],
        button=0,
        small_blind=5,
        big_blind=10,
        rules=parse_rules({"straddle": {"style": "utg", "amount_bb": 2}}),
    )
    utg.start_hand()
    assert utg.straddle_seat == 0
    assert utg.actor == 1


def test_double_board_bomb_awards_each_board_and_keeps_the_odd_chip() -> None:
    game = CashGame(
        [100, 100, 100],
        button=0,
        small_blind=5,
        big_blind=10,
        rules=parse_rules({"bomb_pot": {"amount": 1, "boards": 2}}),
    )
    game.start_hand()
    assert len(game.boards) == 2
    assert [len(board) for board in game.boards] == [3, 3]
    _check_down(game)
    assert game.street is Street.HAND_COMPLETE
    assert game.chip_total() == 300
    assert [len(board) for board in game.boards] == [5, 5]
    runs = game.board_result["runs"]
    assert sum(pot["amount"] for pot in runs[0]["pots"]) == 2
    assert sum(pot["amount"] for pot in runs[1]["pots"]) == 1


def test_simplified_insurance_can_be_accepted_or_declined() -> None:
    locked = _all_in(insurance=True)
    assert locked.awaiting_insurance
    quote = locked.insurance_quote
    assert quote["label"] == "simplified"
    assert len(locked.board) == 4
    locked.decide_insurance(quote["seat"], True)
    assert locked.street is Street.HAND_COMPLETE
    assert locked.insurance_result["accepted"] is True
    assert locked.insurance_result["label"] == "simplified"
    assert all(player.stack >= 0 for player in locked.players)
    assert locked.chip_total() == 20
    assert quote["premium"] + quote["payout"] == 20

    declined = _all_in(insurance=True)
    declined.decide_insurance(declined.insurance_quote["seat"], False)
    assert declined.insurance_result["accepted"] is False
    assert len(declined.board) == 5
    assert declined.chip_total() == 20

    plain = _all_in(insurance=False)
    assert plain.street is Street.HAND_COMPLETE
    assert plain.awaiting_insurance is False
    assert len(plain.board) == 5


def test_tournament_busts_out_and_names_a_chip_winner() -> None:
    app.state.hub = RoomHub()
    service = app.state.hub.service
    host = service.create("Alice")
    guest = service.join(host["invite_code"], "Bob")
    service.sit(host["guest_token"], 0, 2)
    service.sit(guest["guest_token"], 1, 100)
    service.update_settings(
        host["guest_token"],
        None,
        None,
        None,
        tournament={
            "enabled": True,
            "hands_per_level": 1,
            "levels": [{"small": 1, "big": 2}, {"small": 5, "big": 10}],
        },
    )
    service.set_deck(host["room_id"], RiggedDeck(list(LOSE)))
    service.start(host["guest_token"])
    service.act(host["guest_token"], "all_in", None, "shove")
    service.act(guest["guest_token"], "check", None, "check")
    view = service.view(host["guest_token"])
    tournament = view["settings"]["tournament"]
    assert tournament["winner"] == "Bob"
    assert tournament["hands_played"] == 1
    assert "prize" not in tournament
    try:
        service.start(host["guest_token"])
    except Exception as exc:
        assert "tournament is complete: Bob" in str(exc)
    else:
        raise AssertionError("a finished tournament started another hand")


def test_tournament_blind_level_advances_and_settings_lists_the_database() -> None:
    app.state.hub = RoomHub()
    service = app.state.hub.service
    host = service.create("Cara")
    guest = service.join(host["invite_code"], "Dan")
    service.sit(host["guest_token"], 0)
    service.sit(guest["guest_token"], 1)
    service.update_settings(
        host["guest_token"],
        None,
        None,
        None,
        tournament={
            "enabled": True,
            "hands_per_level": 1,
            "levels": [{"small": 1, "big": 2}, {"small": 5, "big": 10}],
        },
    )
    service.start(host["guest_token"])
    service.act(host["guest_token"], "fold", None, "fold")
    service.start(host["guest_token"])
    live = service.view(host["guest_token"])
    assert live["game"]["big_blind"] == 10
    assert "prize" not in live["settings"]["tournament"]
    with TestClient(app) as client:
        body = client.get("/settings").json()
    assert body["cash_settlement"] is False
    assert "database_path" in body
    assert body["gto_modes"] == ["competitive", "study"]
    assert "mississippi" in body["straddle_styles"]
    assert "short_deck" in body["variants"]


def _all_in(*, insurance: bool) -> CashGame:
    rules = parse_rules({"insurance": True}) if insurance else None
    game = CashGame([10, 10], button=0, small_blind=1, big_blind=2, rules=rules)
    game.start_hand()
    game.apply(Action.all_in())
    game.apply(Action.call())
    return game


def _check_down(game: CashGame) -> None:
    for _ in range(24):
        if game.street is Street.HAND_COMPLETE:
            return
        assert game.actor is not None
        player = game.players[game.actor]
        if player.committed_street == game.current_bet:
            game.apply(Action.check())
        else:
            game.apply(Action.call())
    raise AssertionError(game.street)
