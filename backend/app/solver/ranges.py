"""Range text to concrete two-card combos. No solver vendor code."""

from app.engine.cards import RANK_CHARS, SUITS, Card

_RANK = {char: index + 2 for index, char in enumerate(RANK_CHARS)}


def parse_range(text: str) -> list[tuple[Card, Card]]:
    raw = (text or "").replace(" ", "")
    if raw == "":
        return []
    combos: list[tuple[Card, Card]] = []
    seen: set[tuple[Card, Card]] = set()
    for token in raw.split(","):
        if token == "":
            continue
        for combo in _token(token):
            key = tuple(sorted(combo, key=lambda card: (card.rank, card.suit)))
            if key in seen:
                continue
            seen.add(key)
            combos.append(key)
    return combos


def remove_blockers(
    combos: list[tuple[Card, Card]],
    dead: set[Card],
) -> list[tuple[Card, Card]]:
    return [combo for combo in combos if combo[0] not in dead and combo[1] not in dead]


def matrix(combos: list[tuple[Card, Card]]) -> list[list[float]]:
    """13x13 weights. Pairs on the diagonal, suited above it, offsuit below."""
    grid = [[0.0 for _ in range(13)] for _ in range(13)]
    for left, right in combos:
        row = 14 - max(left.rank, right.rank)
        col = 14 - min(left.rank, right.rank)
        if left.rank == right.rank:
            grid[row][col] += 1
        elif left.suit == right.suit:
            high = 14 - max(left.rank, right.rank)
            low = 14 - min(left.rank, right.rank)
            grid[high][low] += 1
        else:
            high = 14 - max(left.rank, right.rank)
            low = 14 - min(left.rank, right.rank)
            grid[low][high] += 1
    return grid


def _token(token: str) -> list[tuple[Card, Card]]:
    plus = token.endswith("+")
    body = token[:-1] if plus else token
    if len(body) == 4 and _is_card(body[:2]) and _is_card(body[2:]):
        return [(_card(body[:2]), _card(body[2:]))]
    if len(body) == 2 and body[0] == body[1] and body[0] in _RANK:
        start = _RANK[body[0]]
        ranks = range(start, 15) if plus else range(start, start + 1)
        combos = []
        for rank in ranks:
            cards = [Card(rank, suit) for suit in SUITS]
            combos.extend((cards[i], cards[j]) for i in range(4) for j in range(i + 1, 4))
        return combos
    if len(body) == 3 and body[2] in {"s", "o"} and body[0] in _RANK and body[1] in _RANK:
        suited = body[2] == "s"
        high = max(_RANK[body[0]], _RANK[body[1]])
        low_start = min(_RANK[body[0]], _RANK[body[1]])
        lows = range(low_start, high) if plus else range(low_start, low_start + 1)
        combos = []
        for low in lows:
            if low == high:
                continue
            if suited:
                combos.extend((Card(high, suit), Card(low, suit)) for suit in SUITS)
            else:
                combos.extend(
                    (Card(high, left), Card(low, right))
                    for left in SUITS
                    for right in SUITS
                    if left != right
                )
        return combos
    raise ValueError(f"unknown range token {token}")


def _is_card(text: str) -> bool:
    return len(text) == 2 and text[0] in _RANK and text[1] in SUITS


def _card(text: str) -> Card:
    return Card(_RANK[text[0]], text[1])
