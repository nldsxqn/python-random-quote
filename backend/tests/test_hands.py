import pytest
from app.engine.actions import Action, IllegalActionError
from app.engine.cards import parse_card, parse_cards
from app.engine.deck import RiggedDeck, SeededDeck
from app.engine.game import CashGame
from app.engine.player import PlayerStatus
from app.engine.state import Street

SAFE_BOARD = "2c 7d 9h 3s 4c 5h 6d Jc"


def _assert_conserved(game: CashGame, total: int) -> None:
    assert game.chip_total() == total


def _finish(game: CashGame, total: int) -> None:
    _assert_conserved(game, total)
    while game.street is not Street.HAND_COMPLETE:
        game.apply(Action.fold())
        _assert_conserved(game, total)


def test_fold_win_hides_hole_cards_and_keeps_folded_chips() -> None:
    game = CashGame([100, 100, 100], button=0, small_blind=5, big_blind=10, deck=SeededDeck(4))
    total = 300
    game.start_hand()
    _assert_conserved(game, total)
    assert game.actor == 0
    game.apply(Action.fold())
    game.apply(Action.fold())
    assert game.street is Street.HAND_COMPLETE
    assert Street.SHOWDOWN not in game.street_path
    assert game.players[0].stack == 100
    assert game.players[1].stack == 95
    assert game.players[2].stack == 105
    _assert_conserved(game, total)
    view = game.public_view(2)
    assert view.players[2].hole_cards == game.players[2].hole
    assert view.players[0].hole_cards is None
    assert view.players[1].hole_cards is None
    folded = game.public_view(1)
    assert folded.players[1].hole_cards == game.players[1].hole
    assert folded.players[2].hole_cards is None


def test_aa_versus_kk_all_in() -> None:
    prefix = parse_cards(f"As Ks Ad Kd {SAFE_BOARD}")
    game = CashGame([100, 100], button=0, small_blind=1, big_blind=2, deck=RiggedDeck(prefix))
    game.start_hand()
    assert game.players[0].hole == (parse_card("As"), parse_card("Ad"))
    assert game.players[1].hole == (parse_card("Ks"), parse_card("Kd"))
    game.apply(Action.all_in())
    game.apply(Action.call())
    assert game.street is Street.HAND_COMPLETE
    assert Street.SHOWDOWN in game.street_path
    assert game.board == parse_cards("7d 9h 3s 5h Jc")
    assert game.players[0].stack == 200
    assert game.players[1].stack == 0
    assert game.players[1].status is PlayerStatus.ELIMINATED
    assert sum(player.stack for player in game.players) == 200
    shown = game.public_view(1)
    assert shown.players[0].hole_cards == game.players[0].hole
    assert shown.players[1].hole_cards == game.players[1].hole


def test_one_side_pot_awards_layers_separately() -> None:
    # Deal from SB (seat 1): QQ, AA, KK. Seat 2 wins the main pot; seat 0 wins the side pot.
    prefix = parse_cards(f"Qs As Ks Qd Ad Kd {SAFE_BOARD}")
    game = CashGame([100, 100, 50], button=0, small_blind=5, big_blind=10, deck=RiggedDeck(prefix))
    game.start_hand()
    game.apply(Action.all_in())
    game.apply(Action.all_in())
    game.apply(Action.all_in())
    assert game.street is Street.HAND_COMPLETE
    assert [(pot.amount, pot.eligible) for pot in game.pots] == [
        (150, (0, 1, 2)),
        (100, (0, 1)),
    ]
    assert [player.stack for player in game.players] == [100, 0, 150]
    assert sum(player.stack for player in game.players) == 250


def test_multiple_side_pots_and_folded_player_is_not_this_hand() -> None:
    # Deal from SB: KK, QQ, AA. Main pot to AA, next side pot to KK, last side pot returned.
    prefix = parse_cards(f"Ks Qs As Kd Qd Ad {SAFE_BOARD}")
    game = CashGame([100, 200, 300], button=0, small_blind=5, big_blind=10, deck=RiggedDeck(prefix))
    game.start_hand()
    game.apply(Action.all_in())
    game.apply(Action.all_in())
    game.apply(Action.all_in())
    assert [player.stack for player in game.players] == [300, 200, 100]
    assert [(pot.amount, pot.eligible) for pot in game.pots] == [
        (300, (0, 1, 2)),
        (200, (1, 2)),
        (100, (2,)),
    ]
    assert sum(player.stack for player in game.players) == 600


def test_tie_odd_chip_goes_to_the_left_of_the_button() -> None:
    # Seat 0 and seat 1 both have ace-king. Seat 2 has queen-jack. Board misses.
    prefix = parse_cards("Ah Qh As Kc Jh Kd 4d 2c 3d 5h 6s 8s 7d 9c")
    game = CashGame([5, 5, 5], button=0, small_blind=1, big_blind=2, deck=RiggedDeck(prefix))
    game.start_hand()
    game.apply(Action.all_in())
    game.apply(Action.all_in())
    game.apply(Action.all_in())
    assert game.street is Street.HAND_COMPLETE
    assert [player.stack for player in game.players] == [7, 8, 0]
    assert sum(player.stack for player in game.players) == 15


def test_chip_conservation_through_a_showdown() -> None:
    game = CashGame([80, 90, 70], button=1, small_blind=5, big_blind=10, deck=SeededDeck(11))
    total = 240
    game.start_hand()
    _assert_conserved(game, total)
    while game.street is not Street.HAND_COMPLETE:
        actor = game.actor
        assert actor is not None
        player = game.players[actor]
        to_call = game.current_bet - player.committed_street
        if to_call == 0:
            game.apply(Action.check())
        elif player.stack > to_call:
            game.apply(Action.call())
        else:
            game.apply(Action.all_in())
        _assert_conserved(game, total)
    assert sum(player.stack for player in game.players) == total
    assert Street.SHOWDOWN in game.street_path


def test_two_three_and_nine_player_hands_and_button_moves() -> None:
    heads_up = CashGame([50, 50], button=1, small_blind=5, big_blind=10, deck=SeededDeck(2))
    heads_up.start_hand()
    _finish(heads_up, 100)
    assert heads_up.street is Street.HAND_COMPLETE

    three = CashGame([40, 40, 40], button=2, small_blind=5, big_blind=10, deck=SeededDeck(3))
    three.start_hand()
    _finish(three, 120)

    nine = CashGame([100] * 9, button=0, small_blind=1, big_blind=2, deck=SeededDeck(9))
    nine.start_hand()
    assert nine.actor == 3
    _finish(nine, 900)
    assert nine.players[2].stack == 101
    nine.start_hand()
    assert nine.button == 1
    assert nine.sb_seat == 2
    assert nine.bb_seat == 3
    assert nine.actor == 4


def test_eliminated_player_is_skipped_next_hand() -> None:
    prefix = parse_cards("As 4h Ks Ad 3d Kd 2c 7c 9d 5s 6h 8c Tc Jh")
    game = CashGame(
        [10, 1000, 1000],
        button=0,
        small_blind=5,
        big_blind=10,
        deck=RiggedDeck(prefix),
    )
    game.start_hand()
    game.apply(Action.all_in())
    game.apply(Action.all_in())
    game.apply(Action.fold())
    assert game.players[0].status is PlayerStatus.ELIMINATED
    assert game.players[0].stack == 0
    assert sum(player.stack for player in game.players) == 2010
    game.start_hand()
    assert game.button == 1
    assert game.sb_seat == 1
    assert game.bb_seat == 2
    assert game.actor == 1
    assert game.players[0].hole is None
    assert game.players[0].status is PlayerStatus.ELIMINATED
    dealt = [seat for seat, player in enumerate(game.players) if player.hole is not None]
    assert dealt == [1, 2]


def test_illegal_action_during_showdown_runout_does_not_apply() -> None:
    game = CashGame([100, 100], button=0, small_blind=1, big_blind=2, deck=SeededDeck(1))
    game.start_hand()
    game.apply(Action.all_in())
    game.apply(Action.call())
    assert game.street is Street.HAND_COMPLETE
    with pytest.raises(IllegalActionError):
        game.apply(Action.check())
    assert game.street is Street.HAND_COMPLETE


def test_status_enum_includes_unused_seat_states() -> None:
    assert {status.name for status in PlayerStatus} >= {
        "ACTIVE",
        "FOLDED",
        "ALL_IN",
        "SITTING_OUT",
        "DISCONNECTED",
        "ELIMINATED",
    }
