from app.engine.cards import parse_cards
from app.engine.evaluator import evaluate


def strength(hole: str, board: str):
    return evaluate(parse_cards(hole), parse_cards(board))


def test_categories_and_ordering() -> None:
    high = strength("As Kd", "9c 7h 5d 3s 2c")
    pair = strength("As Ad", "9c 7h 5d 3s 2c")
    two_pair = strength("As Ad", "Kc Kh 5d 3s 2c")
    trips = strength("As Ad", "Ac 7h 5d 3s 2c")
    straight = strength("9h 8d", "7c 6s 5h 2d 3c")
    wheel = strength("Ah 2d", "3c 4s 5h 9d Td")
    six_high = strength("2c 3d", "4h 5s 6c 9d Td")
    flush = strength("Ah Kh", "Qh Jh 9h 2c 3d")
    full = strength("As Ad", "Ac Kh Kd 3s 2c")
    quads = strength("As Ad", "Ac Ah Kd 3s 2c")
    straight_flush = strength("Ah Kh", "Qh Jh Th 2c 3d")
    wheel_flush = strength("Ah 2h", "3h 4h 5h 9c Td")

    ordered = (high, pair, two_pair, trips, straight, flush, full, quads, straight_flush)
    assert [hand.category for hand in ordered] == [
        "High card",
        "One pair",
        "Two pair",
        "Three of a kind",
        "Straight",
        "Flush",
        "Full house",
        "Four of a kind",
        "Straight flush",
    ]
    assert wheel.category == "Straight"
    assert wheel_flush.category == "Straight flush"
    assert high < pair < two_pair < trips < straight < flush < full < quads < straight_flush
    assert wheel < six_high
    assert wheel_flush < straight_flush


def test_kickers_and_best_five() -> None:
    better_kicker = strength("As Kd", "Ac 9h 4d 3s 2c")
    worse_kicker = strength("Ad Qh", "Ac 9h 4d 3s 2c")
    assert better_kicker.category == "One pair"
    assert better_kicker > worse_kicker

    better_two = strength("As Kd", "Ad Kc 9h 4d 2c")
    worse_two = strength("As Qd", "Ad Qc 9h 4d 2c")
    assert better_two.category == "Two pair"
    assert better_two > worse_two

    # The hole pair is worse than the flush available in the seven cards.
    assert strength("As Ad", "Kh Qh Jh 9h 2h").category == "Flush"
    # Both players play the same board straight.
    assert strength("2c 3d", "Qs Js Ts 9c 8d") == strength("4h 5s", "Qs Js Ts 9c 8d")


def test_suits_do_not_break_ties() -> None:
    hearts = strength("Ah Kh", "Qh Jh 9h 2c 3d")
    diamonds = strength("Ad Kd", "Qd Jd 9d 2c 3d")
    assert hearts.category == "Flush"
    assert hearts == diamonds
