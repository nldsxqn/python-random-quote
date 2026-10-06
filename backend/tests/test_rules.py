"""Rule plugins. Standard NLHE is unchanged when every switch is off."""

import json
from contextlib import ExitStack
from pathlib import Path

import pytest
from app.engine.actions import Action, IllegalActionError
from app.engine.cards import parse_cards
from app.engine.deck import RiggedDeck
from app.engine.game import CashGame
from app.engine.player import PlayerStatus
from app.engine.state import Street
from app.main import app
from app.rules.clock import ManualClock
from app.rules.run_it_twice import run_share
from app.rules.selected import parse_rules
from app.services.hub import RoomHub
from fastapi.testclient import TestClient

AA_KK = "As Ks Ad Kd 2c 7d 9h 3s 4c 5h 6d Jc 8c Kh 9c 4d"
THREE_WAY = "Ks Qs As Kd Qd Ad 2c 7d 9h 3s 4c 5h 6d Jc 8c Kh 9c 4d"
FOUR_WAY = "Ks Qs Js As Kd Qd Jd Ad 2c 7d 9h 3s 4c 5h 6d 2h 8c Kh 9c 4d"
TIE_HU = "2c 4c 3d 5d 6c Ah Kh Qh 7c Jh 8c Th 9s 9c 8d 9d"
TIE_THREE = "2c 4c 6d 3d 5d 7d 8c Ah Kh Qh 9c Jh Tc Th 9s 9d 8d 9h"
SEVEN_DEUCE = "Ah Kh Qh Jh Th 7c Ad Kd Qd Jd Td 2d 3c 7h 7s 7d 4c 2h 5c 2s"


@pytest.fixture(autouse=True)
def fresh_hub() -> None:
    app.state.hub = RoomHub()


def test_engine_does_not_import_rules_or_fastapi() -> None:
    root = Path(__file__).resolve().parents[1] / "app" / "engine"
    for path in root.rglob("*.py"):
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                assert "fastapi" not in stripped
                assert "app.rules" not in stripped


def test_normal_ante_is_in_the_pot_before_action() -> None:
    game = _game([100, 100, 100], {"ante": {"mode": "normal", "amount": 1}}, sb=5, bb=10)
    game.start_hand()
    assert [player.hole is not None for player in game.players] == [True, True, True]
    assert [player.committed_street for player in game.players] == [0, 5, 10]
    assert [player.committed_hand for player in game.players] == [1, 6, 11]
    assert game._committed_total() == 18
    assert game.street is Street.PREFLOP
    assert game.actor == 0


def test_big_blind_ante_is_posted_once() -> None:
    game = _game([100, 100, 100], {"ante": {"mode": "bb_ante", "amount": 1}}, sb=5, bb=10)
    game.start_hand()
    assert [player.committed_hand for player in game.players] == [0, 5, 11]
    assert [player.committed_street for player in game.players] == [0, 5, 10]
    assert game._committed_total() == 16
    assert game.actor == 0


def test_utg_straddle_opens_left_of_the_straddler() -> None:
    rules = {"straddle": {"style": "utg", "amount_bb": 2}}
    game = _game([100, 100, 100], rules, sb=5, bb=10)
    game.start_hand()
    assert game.straddle_seat == 0
    assert game.players[0].committed_street == 20
    assert game.current_bet == 20
    assert game.min_raise_increment == 10
    assert game.actor == 1


def test_short_straddle_does_not_change_the_minimum_raise() -> None:
    rules = {"straddle": {"style": "utg", "amount_bb": 2}}
    game = _game([15, 100, 100], rules, sb=5, bb=10)
    game.start_hand()
    assert game.players[0].status is PlayerStatus.ALL_IN
    assert game.players[0].committed_street == 15
    assert game.min_raise_increment == 10
    assert game.actor == 1


def test_unknown_straddle_style_is_rejected() -> None:
    message = "straddle style must be utg, mississippi, or custom"
    with pytest.raises(IllegalActionError, match=message):
        parse_rules({"straddle": {"style": "button", "amount_bb": 2}})


def test_buyin_limits_sit_and_added_chips() -> None:
    with TestClient(app) as client:
        host = _create(client, "Host")
        guest = _join(client, host["invite_code"], "Guest")
        saved = client.post(
            f"/rooms/{host['room_id']}/settings",
            json={
                "guest_token": host["guest_token"],
                "rules": {"buy_in": {"min": 40, "max": 100, "unit": "chips"}},
            },
        )
        assert saved.status_code == 200
        short = _sit_amount(client, host, 0, 10)
        assert short.status_code == 400
        assert short.json()["payload"]["message"] == "buy-in must be from 40 to 100"
        high = _sit_amount(client, host, 0, 150)
        assert high.status_code == 400
        assert _sit_amount(client, host, 0, 50).status_code == 200
        over_add = client.post(
            f"/rooms/{host['room_id']}/chips",
            json={"guest_token": host["guest_token"], "amount": 60},
        )
        assert over_add.status_code == 400
        assert over_add.json()["payload"]["message"] == "stack cannot exceed 100"
        small_add = client.post(
            f"/rooms/{host['room_id']}/chips",
            json={"guest_token": host["guest_token"], "amount": 5},
        )
        assert small_add.status_code == 400
        assert "added chips must be from 40 to 100" in small_add.json()["payload"]["message"]
        added = client.post(
            f"/rooms/{host['room_id']}/chips",
            json={"guest_token": host["guest_token"], "amount": 40},
        )
        assert added.status_code == 200
        assert added.json()["stack"] == 90

        bb = client.post(
            f"/rooms/{host['room_id']}/settings",
            json={
                "guest_token": host["guest_token"],
                "rules": {"buy_in": {"min": 50, "max": 100, "unit": "bb"}},
            },
        )
        assert bb.status_code == 200
        denied = _sit_amount(client, guest, 1, 50)
        assert denied.status_code == 400
        assert denied.json()["payload"]["message"] == "buy-in must be from 100 to 200"
        assert _sit_amount(client, guest, 1, 100).status_code == 200
        assert _stacks(client, host)[1] == 100


def test_bot_buyin_uses_the_posted_amount() -> None:
    with TestClient(app) as client:
        host = _create(client, "Host")
        saved = client.post(
            f"/rooms/{host['room_id']}/settings",
            json={
                "guest_token": host["guest_token"],
                "rules": {"buy_in": {"min": 40, "max": 100, "unit": "chips"}},
            },
        )
        assert saved.status_code == 200
        missing = client.post(
            f"/rooms/{host['room_id']}/bots",
            json={"guest_token": host["guest_token"], "kind": "rule"},
        )
        assert missing.status_code == 400
        assert missing.json()["payload"]["message"] == "buy-in must be from 40 to 100"
        seated = client.post(
            f"/rooms/{host['room_id']}/bots",
            json={"guest_token": host["guest_token"], "kind": "rule", "amount": 40},
        )
        assert seated.status_code == 200
        assert _stacks(client, host)[seated.json()["seat"]] == 40


def test_auto_top_up_records_play_money_and_the_new_total() -> None:
    rules = {"auto_top_up": {"threshold_bb": 20, "target_bb": 50}}
    game = _game([10, 100], rules, sb=1, bb=2)
    game.start_hand()
    assert game.top_ups == [{"seat": 0, "amount": 90}]
    assert game.players[0].stack + game.players[0].committed_hand == 100
    assert game.players[1].stack + game.players[1].committed_hand == 100
    assert game.chip_total() == 200

    with TestClient(app) as client:
        host = _create(client, "Host")
        guest = _join(client, host["invite_code"], "Guest")
        _sit(client, host, 0)
        _sit(client, guest, 1)
        _rules(
            client,
            host,
            {"auto_top_up": {"threshold_bb": 20, "target_bb": 40}},
        )
        _member(host, 0).stack = 10
        started = client.post(
            f"/rooms/{host['room_id']}/start",
            json={"guest_token": host["guest_token"]},
        )
        assert started.status_code == 200
        state = _state(client, host)
        assert state["game"]["top_ups"] == [{"seat": 0, "amount": 70}]
        seated = {row["seat"]: row for row in state["players"]}
        assert seated[0]["stack"] + seated[0]["committed_hand"] == 80
        assert seated[1]["stack"] + seated[1]["committed_hand"] == 1000


def test_time_bank_timeout_folds_or_checks_without_sleeping() -> None:
    with TestClient(app) as client:
        host = _create(client, "Host")
        guest = _join(client, host["invite_code"], "Guest")
        _sit(client, host, 0)
        _sit(client, guest, 1)
        _rules(client, host, {"time_bank": {"seconds": 15}})
        clock = ManualClock()
        app.state.hub.service.set_clock(host["room_id"], clock)
        with ExitStack() as stack:
            host_ws = _connect(stack, client, host["guest_token"])
            guest_ws = _connect(stack, client, guest["guest_token"])
            client.post(
                f"/rooms/{host['room_id']}/start",
                json={"guest_token": host["guest_token"]},
            )
            opened = _until(host_ws, "ACTION_REQUIRED")
            _until(guest_ws, "GAME_STATE")
            required = opened[-1]["payload"]
            assert required["remaining_seconds"] == 15
            assert required["deadline"] == 15
            assert _state(client, host)["game"]["remaining_seconds"] == 15
            clock.advance(10)
            assert app.state.hub.service.resolve_time_bank(host["room_id"]) is False
            assert _state(client, host)["game"]["remaining_seconds"] == 5
            clock.advance(5)
            assert app.state.hub.service.resolve_time_bank(host["room_id"]) is True
            assert _state(client, host)["game"]["street"] == "HAND_COMPLETE"
            result = _latest(host["room_id"], "ACTION_RESULT")
            assert result["action"] == "fold"
            assert result["request_id"] == "timeout"
            assert result["timeout"] is True

        host = _create(client, "Host")
        guest = _join(client, host["invite_code"], "Guest")
        _sit(client, host, 0)
        _sit(client, guest, 1)
        _rules(client, host, {"time_bank": {"seconds": 8}})
        clock = ManualClock()
        app.state.hub.service.set_clock(host["room_id"], clock)
        with ExitStack() as stack:
            host_ws = _connect(stack, client, host["guest_token"])
            _connect(stack, client, guest["guest_token"])
            client.post(
                f"/rooms/{host['room_id']}/start",
                json={"guest_token": host["guest_token"]},
            )
            _until(host_ws, "GAME_STATE")
            host_ws.send_json(
                {"type": "PLAYER_ACTION", "request_id": "call", "payload": {"action": "call"}}
            )
            _until(host_ws, "GAME_STATE")
            assert _state(client, guest)["game"]["to_call"] == 0
            clock.advance(8)
            assert app.state.hub.service.resolve_time_bank(host["room_id"]) is True
            assert _latest(host["room_id"], "ACTION_RESULT")["action"] == "check"
            assert _state(client, host)["game"]["street"] == "FLOP"


def test_seven_deuce_bounty_pays_outside_the_pot() -> None:
    game = _game([100, 100, 100, 100, 100, 100], _bounty(10), deck=SEVEN_DEUCE, sb=1, bb=2)
    game.start_hand()
    assert game.players[0].hole == tuple(parse_cards("7c 2d"))
    _passive(game)
    assert game.street is Street.HAND_COMPLETE
    assert Street.SHOWDOWN in game.street_path
    assert sum(pot.amount for pot in game.pots) == 12
    assert game.bounty == 100
    assert [player.stack for player in game.players] == [210, 78, 78, 78, 78, 78]
    assert sum(player.stack for player in game.players) == 600
    assert sum(row["amount"] for row in game.bounty_payments) == 100
    assert {row["partial"] for row in game.bounty_payments} == {False}


def test_short_bounty_is_partial_and_stacks_stay_non_negative() -> None:
    stacks = [100, 100, 100, 10, 100, 100]
    game = _game(stacks, _bounty(10), deck=SEVEN_DEUCE, sb=1, bb=2)
    game.start_hand()
    assert game.actor == 3
    game.apply(Action.fold())
    _passive(game)
    partial = [row for row in game.bounty_payments if row["seat"] == 3]
    assert partial == [{"seat": 3, "winner": 0, "amount": 10, "partial": True}]
    assert game.bounty == 90
    assert game.players[3].stack == 0
    assert all(player.stack >= 0 for player in game.players)
    assert sum(player.stack for player in game.players) == 510


def test_suited_seven_deuce_and_fold_win_pay_nothing() -> None:
    suited = SEVEN_DEUCE.replace("2d", "2c")
    game = _game([100, 100, 100, 100, 100, 100], _bounty(10), deck=suited, sb=1, bb=2)
    game.start_hand()
    _passive(game)
    assert game.bounty == 0
    assert game.bounty_payments == []
    assert [player.stack for player in game.players] == [110, 98, 98, 98, 98, 98]

    folded = _game([100, 100, 100], _bounty(10), deck="Ah Kh 7c Ad Kd 2d", sb=1, bb=2)
    folded.start_hand()
    folded.apply(Action.call())
    folded.apply(Action.fold())
    folded.apply(Action.fold())
    assert folded.street is Street.HAND_COMPLETE
    assert Street.SHOWDOWN not in folded.street_path
    assert folded.bounty == 0
    assert [player.stack for player in folded.players] == [103, 99, 98]


def test_run_it_twice_heads_up_and_socket_messages() -> None:
    game = _game([100, 100], {"run_it_twice": True}, deck=AA_KK)
    game.start_hand()
    _shove(game)
    assert game.awaiting_rit is True
    assert game.street is Street.FLOP
    assert len(game.board) == 3
    _vote(game, True)
    assert [player.stack for player in game.players] == [100, 100]
    assert game.rit_result["accepted"] is True
    assert game.boards[0] == parse_cards("7d 9h 3s 5h Jc")
    assert game.boards[1] == parse_cards("7d 9h 3s Kh 4d")
    assert [run["pots"][0]["amount"] for run in game.rit_result["runs"]] == [100, 100]

    with TestClient(app) as client:
        host = _create(client, "Host")
        guest = _join(client, host["invite_code"], "Guest")
        _sit(client, host, 0)
        _sit(client, guest, 1)
        _rules(client, host, {"run_it_twice": True})
        app.state.hub.service.set_deck(host["room_id"], RiggedDeck(parse_cards(AA_KK)))
        with ExitStack() as stack:
            host_ws = _connect(stack, client, host["guest_token"])
            guest_ws = _connect(stack, client, guest["guest_token"])
            client.post(
                f"/rooms/{host['room_id']}/start",
                json={"guest_token": host["guest_token"]},
            )
            _until(host_ws, "ACTION_REQUIRED")
            _until(guest_ws, "ACTION_REQUIRED")
            host_ws.send_json(
                {"type": "PLAYER_ACTION", "request_id": "shove", "payload": {"action": "all_in"}}
            )
            _until(guest_ws, "ACTION_REQUIRED")
            guest_ws.send_json(
                {"type": "PLAYER_ACTION", "request_id": "call", "payload": {"action": "all_in"}}
            )
            offer = _until(host_ws, "RIT_OFFER")
            _until(guest_ws, "RIT_OFFER")
            assert offer[-1]["type"] == "RIT_OFFER"
            assert offer[-1]["payload"]["seats"] == [0, 1]
            assert offer[-1]["payload"]["street"] == "FLOP"
            assert _state(client, host)["game"]["rit_offer"] is True
            assert _state(client, host)["game"]["legal_actions"] == []
            host_ws.send_json(
                {"type": "RIT_VOTE", "request_id": "yes", "payload": {"accept": True}}
            )
            guest_ws.send_json(
                {"type": "RIT_VOTE", "request_id": "yes-2", "payload": {"accept": True}}
            )
            finished = _until(host_ws, "HAND_COMPLETE")
            assert any(item["type"] == "RIT_VOTE" for item in finished)
            result = next(item for item in finished if item["type"] == "RIT_RESULT")
            assert result["payload"]["accepted"] is True
            assert len(result["payload"]["runs"]) == 2
            assert "deck" not in json.dumps(finished)


def test_run_it_twice_three_ways_and_side_pots() -> None:
    game = _game([100, 100, 100], {"run_it_twice": True}, deck=THREE_WAY, sb=5, bb=10)
    game.start_hand()
    _shove(game)
    _vote(game, True)
    assert [player.stack for player in game.players] == [150, 150, 0]

    sided = _game([100, 200, 300], {"run_it_twice": True}, deck=THREE_WAY, sb=5, bb=10)
    sided.start_hand()
    _shove(sided)
    _vote(sided, True)
    assert [player.stack for player in sided.players] == [150, 350, 100]
    eligibles = [pot["eligible"] for pot in sided.rit_result["runs"][0]["pots"]]
    assert eligibles == [[0, 1, 2], [1, 2], [2]]
    assert sum(player.stack for player in sided.players) == 600


def test_run_it_twice_on_the_flop_and_the_turn() -> None:
    flop = _game([100, 100], {"run_it_twice": True}, deck=AA_KK)
    flop.start_hand()
    flop.apply(Action.call())
    flop.apply(Action.check())
    assert flop.street is Street.FLOP
    assert all(player.stack > 0 for player in flop.players)
    _shove(flop)
    assert flop.awaiting_rit is True
    assert flop.street is Street.FLOP
    assert len(flop.board) == 3
    _vote(flop, True)
    assert len(flop.boards[0]) == 5
    assert flop.boards[0][:3] == flop.boards[1][:3]

    turn = _game([100, 100], {"run_it_twice": True}, deck=AA_KK)
    turn.start_hand()
    turn.apply(Action.call())
    turn.apply(Action.check())
    turn.apply(Action.check())
    turn.apply(Action.check())
    assert turn.street is Street.TURN
    assert len(turn.board) == 4
    _shove(turn)
    assert turn.awaiting_rit is True
    assert turn.street is Street.TURN
    _vote(turn, True)
    assert turn.boards[0][:4] == turn.boards[1][:4]
    assert len(turn.boards[0]) == 5
    assert [player.stack for player in turn.players] == [100, 100]

    river = _game([100, 100], {"run_it_twice": True}, deck=AA_KK)
    river.start_hand()
    _to_street(river, Street.RIVER)
    _shove(river)
    assert river.awaiting_rit is False
    assert river.street is Street.HAND_COMPLETE
    assert river.boards == []


def test_one_rejection_runs_once() -> None:
    game = _game([100, 100], {"run_it_twice": True}, deck=AA_KK)
    game.start_hand()
    _shove(game)
    game.vote_run_it_twice(0, True)
    assert game.awaiting_rit is True
    game.vote_run_it_twice(1, False)
    assert game.rit_declined is True
    assert game.rit_result == {"accepted": False, "runs": []}
    assert game.street is Street.HAND_COMPLETE
    assert game.board == parse_cards("7d 9h 3s 5h Jc")
    assert [player.stack for player in game.players] == [200, 0]


def test_multiple_side_pots_keep_their_players() -> None:
    game = _game([40, 80, 120, 160], {"run_it_twice": True}, deck=FOUR_WAY, sb=1, bb=2)
    game.start_hand()
    _shove(game)
    _vote(game, True)
    first = game.rit_result["runs"][0]["pots"]
    assert [pot["amount"] for pot in first] == [80, 60, 40, 20]
    assert [pot["eligible"] for pot in first] == [[0, 1, 2, 3], [1, 2, 3], [2, 3], [3]]
    assert [player.stack for player in game.players] == [80, 200, 80, 40]
    assert sum(player.stack for player in game.players) == 400


def test_tied_runs_and_the_odd_chip() -> None:
    assert run_share(11, 0) == 6
    assert run_share(11, 1) == 5
    tied = _game([100, 100], {"run_it_twice": True}, deck=TIE_HU)
    tied.start_hand()
    _shove(tied)
    _vote(tied, True)
    assert [player.stack for player in tied.players] == [100, 100]
    assert tied.rit_result["runs"][0]["pots"][0]["awards"] == [
        {"seat": 1, "amount": 50},
        {"seat": 0, "amount": 50},
    ]

    odd = _game([5, 5, 5], {"run_it_twice": True}, deck=TIE_THREE, sb=1, bb=2)
    odd.start_hand()
    _shove(odd)
    _vote(odd, True)
    amounts = [pot["amount"] for pot in odd.rit_result["runs"][0]["pots"]]
    assert amounts[0] == 8
    assert odd.rit_result["runs"][1]["pots"][0]["amount"] == 7
    assert [player.stack for player in odd.players] == [4, 6, 5]
    assert sum(player.stack for player in odd.players) == 15


def test_rake_comes_out_of_the_pot_and_skips_a_preflop_fold() -> None:
    rules = {"rake": {"percentage": 5, "cap": 10, "no_flop_no_drop": True}}
    game = _game([100, 100], rules, deck=AA_KK)
    game.start_hand()
    _shove(game)
    assert game.rake == 10
    assert sum(pot.amount for pot in game.pots) == 190
    assert [player.stack for player in game.players] == [190, 0]
    assert game.chip_total() == 190

    folded = _game([100, 100], rules, sb=1, bb=2)
    folded.start_hand()
    folded.apply(Action.fold())
    assert folded.rake == 0
    assert folded.board == []
    assert [player.stack for player in folded.players] == [99, 101]

    dropping = {"rake": {"percentage": 50, "cap": 100, "no_flop_no_drop": False}}
    taxed = _game([100, 100], dropping, sb=1, bb=2)
    taxed.start_hand()
    taxed.apply(Action.fold())
    assert taxed.rake == 1
    assert [player.stack for player in taxed.players] == [99, 100]
    assert taxed.chip_total() == 199


def test_bomb_pot_starts_on_the_flop_and_rejects_a_second_board() -> None:
    game = _game([100, 100, 100], {"bomb_pot": {"amount": 10, "boards": 1}}, sb=5, bb=10)
    game.start_hand()
    assert game.street is Street.FLOP
    assert len(game.board) == 3
    assert [player.committed_hand for player in game.players] == [10, 10, 10]
    assert [player.committed_street for player in game.players] == [0, 0, 0]
    assert game.actor == 1
    assert game._committed_total() == 30

    double = parse_rules({"bomb_pot": {"amount": 10, "boards": 2}})
    assert double.bomb is not None and double.bomb.boards == 2
    with pytest.raises(IllegalActionError, match="bomb pot boards must be 1 or 2"):
        parse_rules({"bomb_pot": {"amount": 10, "boards": 3}})
    with pytest.raises(IllegalActionError, match="a straddle is not available"):
        parse_rules(
            {
                "bomb_pot": {"amount": 10, "boards": 1},
                "straddle": {"style": "utg", "amount_bb": 2},
            }
        )


def test_host_rule_changes_apply_on_the_next_hand() -> None:
    with TestClient(app) as client:
        host = _create(client, "Host")
        guest = _join(client, host["invite_code"], "Guest")
        _sit(client, host, 0)
        _sit(client, guest, 1)
        denied = client.post(
            f"/rooms/{host['room_id']}/settings",
            json={"guest_token": guest["guest_token"], "rules": {"run_it_twice": True}},
        )
        assert denied.status_code == 403
        client.post(
            f"/rooms/{host['room_id']}/start",
            json={"guest_token": host["guest_token"]},
        )
        changed = _rules(client, host, {"ante": {"mode": "normal", "amount": 1}})
        assert changed.status_code == 200
        live = _state(client, host)
        assert live["settings"]["rules"] == {}
        assert live["settings"]["pending_rules"]["ante"]["amount"] == 1
        assert live["players"][0]["committed_hand"] == 1
        client.post(
            f"/rooms/{host['room_id']}/settings",
            json={
                "guest_token": host["guest_token"],
                "rules": {"straddle": {"style": "button", "amount_bb": 2}},
            },
        )
        rejected = client.post(
            f"/rooms/{host['room_id']}/settings",
            json={
                "guest_token": host["guest_token"],
                "rules": {"straddle": {"style": "button", "amount_bb": 2}},
            },
        )
        assert rejected.status_code == 400
        message = rejected.json()["payload"]["message"]
        assert message == "straddle style must be utg, mississippi, or custom"
        with ExitStack() as stack:
            host_ws = _connect(stack, client, host["guest_token"])
            host_ws.send_json(
                {"type": "PLAYER_ACTION", "request_id": "fold", "payload": {"action": "fold"}}
            )
            _until(host_ws, "HAND_COMPLETE")
        again = client.post(
            f"/rooms/{host['room_id']}/start",
            json={"guest_token": host["guest_token"]},
        )
        assert again.status_code == 200
        nxt = _state(client, host)
        assert nxt["settings"]["pending_rules"] is None
        assert nxt["settings"]["rules"]["ante"] == {"mode": "normal", "amount": 1}
        button = next(row for row in nxt["players"] if row["is_button"])
        assert button["committed_hand"] == button["committed_street"] + 1


def _game(
    stacks: list[int],
    spec: dict,
    *,
    deck: str | None = None,
    sb: int = 1,
    bb: int = 2,
) -> CashGame:
    provider = None if deck is None else RiggedDeck(parse_cards(deck))
    return CashGame(
        stacks,
        button=0,
        small_blind=sb,
        big_blind=bb,
        deck=provider,
        rules=parse_rules(spec),
    )


def _bounty(payment: int) -> dict:
    return {"seven_deuce": {"payment_per_player_bb": payment}}


def _passive(game: CashGame) -> None:
    while game.actor is not None and game.street is not Street.HAND_COMPLETE:
        player = game.players[game.actor]
        to_call = game.current_bet - player.committed_street
        if to_call > 0 and player.stack <= to_call:
            game.apply(Action.all_in())
        elif to_call > 0:
            game.apply(Action.call())
        else:
            game.apply(Action.check())


def _shove(game: CashGame) -> None:
    while game.actor is not None:
        game.apply(Action.all_in())


def _vote(game: CashGame, accept: bool) -> None:
    for seat in game._alive_seats():
        if seat not in game.rit_votes:
            game.vote_run_it_twice(seat, accept)


def _to_street(game: CashGame, street: Street) -> None:
    while game.street is not street:
        if game.actor is None:
            raise AssertionError(game.street)
        player = game.players[game.actor]
        to_call = game.current_bet - player.committed_street
        game.apply(Action.check() if to_call == 0 else Action.call())


def _create(client: TestClient, nickname: str) -> dict:
    response = client.post("/rooms", json={"nickname": nickname})
    assert response.status_code == 200
    return response.json()


def _join(client: TestClient, invite_code: str, nickname: str) -> dict:
    response = client.post("/rooms/join", json={"invite_code": invite_code, "nickname": nickname})
    assert response.status_code == 200
    return response.json()


def _sit(client: TestClient, player: dict, seat: int) -> None:
    response = _sit_amount(client, player, seat, None)
    assert response.status_code == 200


def _sit_amount(client: TestClient, player: dict, seat: int, amount: int | None):
    body: dict[str, object] = {"guest_token": player["guest_token"], "seat": seat}
    if amount is not None:
        body["amount"] = amount
    return client.post(f"/rooms/{player['room_id']}/sit", json=body)


def _rules(client: TestClient, host: dict, rules: dict):
    return client.post(
        f"/rooms/{host['room_id']}/settings",
        json={"guest_token": host["guest_token"], "rules": rules},
    )


def _state(client: TestClient, player: dict) -> dict:
    response = client.get(
        f"/rooms/{player['room_id']}",
        params={"guest_token": player["guest_token"]},
    )
    assert response.status_code == 200
    return response.json()


def _stacks(client: TestClient, player: dict) -> dict[int, int]:
    return {row["seat"]: row["stack"] for row in _state(client, player)["players"]}


def _member(player: dict, seat: int):
    room = app.state.hub.service.rooms[player["room_id"]]
    found = next(member for member in room.members.values() if member.seat == seat)
    return found


def _connect(stack: ExitStack, client: TestClient, token: str):
    socket = stack.enter_context(client.websocket_connect("/ws/room"))
    socket.send_json({"type": "JOIN", "payload": {"guest_token": token}})
    assert socket.receive_json()["type"] == "ROOM_JOINED"
    assert socket.receive_json()["type"] == "GAME_STATE"
    return socket


def _latest(room_id: str, event_type: str) -> dict:
    room = app.state.hub.service.rooms[room_id]
    found = [event.data for event in room.events if event.type == event_type]
    assert found, [event.type for event in room.events]
    return found[-1]


def _until(socket, event_type: str, limit: int = 30) -> list[dict]:
    found: list[dict] = []
    for _ in range(limit):
        message = socket.receive_json()
        found.append(message)
        if message["type"] == event_type:
            return found
    raise AssertionError(found)
