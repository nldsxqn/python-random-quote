from app.engine.cards import parse_cards, standard_deck
from app.engine.deck import RiggedDeck, SeededDeck, SystemRandomDeck


def test_seeded_deck_is_stable_and_system_random_is_a_permutation() -> None:
    fresh = standard_deck()
    first = SeededDeck(7).shuffle(fresh)
    second = SeededDeck(7).shuffle(fresh)
    other = SeededDeck(8).shuffle(fresh)
    assert first == second
    assert first != other
    assert set(first) == set(fresh)

    shuffled = SystemRandomDeck().shuffle(fresh)
    assert set(shuffled) == set(fresh)
    assert len(shuffled) == 52


def test_rigged_deck_draws_the_prefix_first() -> None:
    prefix = parse_cards("As Kd Qh")
    deck = RiggedDeck(prefix).shuffle(standard_deck())
    assert deck[:3] == prefix
    assert set(deck) == set(standard_deck())
