from app.engine.pot import Contribution, build_pots, odd_chip_order, split_amount


def test_single_pot_and_folded_chips() -> None:
    pots = build_pots(
        [
            Contribution(0, 100, folded=False),
            Contribution(1, 100, folded=True),
            Contribution(2, 100, folded=False),
        ]
    )
    assert len(pots) == 1
    assert pots[0].amount == 300
    assert pots[0].eligible == (0, 2)


def test_one_side_pot() -> None:
    pots = build_pots(
        [
            Contribution(0, 100, folded=False),
            Contribution(1, 100, folded=False),
            Contribution(2, 50, folded=False),
        ]
    )
    assert [(pot.amount, pot.eligible) for pot in pots] == [
        (150, (0, 1, 2)),
        (100, (0, 1)),
    ]


def test_multiple_side_pots() -> None:
    pots = build_pots(
        [
            Contribution(0, 100, folded=False),
            Contribution(1, 200, folded=False),
            Contribution(2, 300, folded=False),
        ]
    )
    assert [(pot.amount, pot.eligible) for pot in pots] == [
        (300, (0, 1, 2)),
        (200, (1, 2)),
        (100, (2,)),
    ]
    assert sum(pot.amount for pot in pots) == 600


def test_odd_chip_goes_left_of_the_button() -> None:
    ordered = odd_chip_order([0, 1], button=0, seat_count=3)
    assert ordered == [1, 0]
    assert split_amount(15, ordered) == {1: 8, 0: 7}
