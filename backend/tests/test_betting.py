import copy

import pytest
from app.engine.actions import Action, IllegalActionError
from app.engine.deck import SeededDeck
from app.engine.game import CashGame
from app.engine.player import PlayerStatus
from app.engine.state import Street


def _snapshot(game: CashGame) -> tuple[object, ...]:
    return (
        game.street,
        game.actor,
        game.current_bet,
        game.min_raise_increment,
        tuple(game.board),
        tuple(
            (
                player.stack,
                player.status,
                player.committed_street,
                player.committed_hand,
                player.acted,
                player.can_raise,
                player.hole,
            )
            for player in game.players
        ),
    )


def _assert_unchanged(game: CashGame, action: Action, seat: int | None = None) -> None:
    before = _snapshot(game)
    with pytest.raises(IllegalActionError):
        game.apply(action, seat)
    assert _snapshot(game) == before


def _three_flop(stacks: list[int] | None = None) -> CashGame:
    game = CashGame(
        stacks or [1000, 1000, 1000],
        button=0,
        small_blind=5,
        big_blind=10,
        deck=SeededDeck(1),
    )
    game.start_hand()
    assert game.actor == 0
    game.apply(Action.call())
    game.apply(Action.call())
    game.apply(Action.check())
    assert game.street is Street.FLOP
    assert game.actor == 1
    return game


def test_heads_up_blind_and_action_order() -> None:
    game = CashGame([1000, 1000], button=0, small_blind=5, big_blind=10, deck=SeededDeck(1))
    game.start_hand()
    assert game.sb_seat == 0
    assert game.bb_seat == 1
    assert game.actor == 0
    assert game.players[0].hole is not None
    assert game.players[0].hole[0] != game.players[1].hole[0]
    game.apply(Action.call())
    assert game.actor == 1
    game.apply(Action.check())
    assert game.street is Street.FLOP
    assert game.actor == 1


def test_multiway_action_order() -> None:
    game = CashGame(
        [1000, 1000, 1000, 1000],
        button=0,
        small_blind=5,
        big_blind=10,
        deck=SeededDeck(1),
    )
    game.start_hand()
    assert (game.sb_seat, game.bb_seat, game.actor) == (1, 2, 3)
    game.apply(Action.call())
    game.apply(Action.call())
    game.apply(Action.call())
    game.apply(Action.check())
    assert game.street is Street.FLOP
    assert game.actor == 1


def test_check_call_bet_raise_fold_and_minimums() -> None:
    game = _three_flop()
    _assert_unchanged(game, Action.bet(9))
    game.apply(Action.bet(10))
    assert game.current_bet == 10
    _assert_unchanged(game, Action.check())
    _assert_unchanged(game, Action.raise_to(19))
    game.apply(Action.raise_to(30))
    assert game.min_raise_increment == 20
    game.apply(Action.fold())
    assert game.players[0].status is PlayerStatus.FOLDED
    game.apply(Action.call())
    assert game.street is Street.TURN


def test_short_all_in_does_not_reopen_previous_bettor() -> None:
    game = _three_flop([1000, 1000, 25])
    game.apply(Action.bet(10))
    assert game.actor == 2
    game.apply(Action.all_in())
    assert game.players[2].status is PlayerStatus.ALL_IN
    assert game.players[2].committed_street == 15
    assert game.current_bet == 15
    assert game.min_raise_increment == 10
    assert game.actor == 0
    game.apply(Action.call())
    assert game.actor == 1
    _assert_unchanged(game, Action.raise_to(100))
    game.apply(Action.call())
    assert game.street is Street.TURN
    assert game.players[1].stack == 975


def test_seat_still_to_act_can_raise_over_a_short_all_in() -> None:
    game = _three_flop([1000, 1000, 25])
    game.apply(Action.bet(10))
    game.apply(Action.all_in())
    assert game.actor == 0
    game.apply(Action.raise_to(25))
    assert game.current_bet == 25
    assert game.actor == 1


def test_short_all_in_still_lets_an_unopened_seat_be_the_only_raiser() -> None:
    fresh = _three_flop([1000, 1000, 25])
    fresh.apply(Action.bet(10))
    fresh.apply(Action.all_in())
    before = copy.deepcopy(fresh)
    _assert_unchanged(fresh, Action.raise_to(50), seat=1)
    assert fresh.actor == before.actor == 0


def test_out_of_turn_is_rejected() -> None:
    game = CashGame([1000, 1000, 1000], button=0, small_blind=5, big_blind=10, deck=SeededDeck(2))
    game.start_hand()
    assert game.actor == 0
    _assert_unchanged(game, Action.fold(), seat=1)


def test_partial_blind_is_all_in() -> None:
    game = CashGame([3, 100], button=0, small_blind=5, big_blind=10, deck=SeededDeck(3))
    game.start_hand()
    assert game.players[0].status is PlayerStatus.ALL_IN
    assert game.players[0].committed_hand == 3
    assert game.players[0].stack == 0
    assert game.players[1].committed_hand == 10
    assert game.actor == 1
    assert Street.POSTING_BLINDS in game.street_path
