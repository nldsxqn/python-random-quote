"""Run it twice. Each pot is split across two boards and awarded separately."""

from app.engine.evaluator import evaluate
from app.engine.player import PlayerStatus
from app.engine.pot import Contribution, build_pots, odd_chip_order, split_amount
from app.engine.state import Street
from app.rules.bounty import BountyConfig, apply_bounty
from app.rules.rake import RakeConfig, apply_rake


def eligible_for_offer(game: object) -> bool:
    if game.rit_declined or game.awaiting_rit:
        return False
    if game.street not in {Street.FLOP, Street.TURN}:
        return False
    alive = game._alive_seats()
    if len(alive) < 2:
        return False
    return all(game.players[seat].status is PlayerStatus.ALL_IN for seat in alive)


def run_share(amount: int, run_index: int) -> int:
    """Run 1 receives the extra chip when the pot does not divide evenly."""
    half, extra = divmod(amount, 2)
    if run_index == 0:
        return half + extra
    return half


def execute(game: object, rake: RakeConfig | None, bounty: BountyConfig | None) -> None:
    contributions = [
        _contribution(game, seat)
        for seat in sorted(game.in_hand)
    ]
    pots = build_pots(contributions)
    if rake is not None:
        pots = apply_rake(game, rake, pots)
    else:
        game.rake = 0
    prefix = list(game.board)
    first = _runout(game, prefix)
    second = _runout(game, prefix)
    boards = [first, second]
    game.board = list(first)
    game.boards = boards
    game._set_street(Street.SHOWDOWN)
    game.showdown_seats = set(game._alive_seats())
    runs: list[dict] = []
    winners: set[int] = set()
    for index, board in enumerate(boards):
        ranks = {
            seat: evaluate(game.players[seat].hole or (), board)
            for seat in game.showdown_seats
        }
        pot_rows = []
        for pot in pots:
            portion = run_share(pot.amount, index)
            awards, tied = _award(game, pot.eligible, portion, ranks)
            if portion > 0:
                winners.update(tied)
            pot_rows.append({"amount": portion, "eligible": list(pot.eligible), "awards": awards})
        runs.append({"board": [card.code for card in board], "pots": pot_rows})
    game.pots = pots
    game.rit_result = {"accepted": True, "runs": runs}
    if bounty is not None:
        apply_bounty(game, bounty, winners)
    for player in game.players:
        if player.stack == 0:
            player.status = PlayerStatus.ELIMINATED
    game.actor = None
    game._set_street(Street.HAND_COMPLETE)


def _contribution(game: object, seat: int) -> Contribution:
    player = game.players[seat]
    return Contribution(
        seat,
        player.committed_hand,
        player.status is PlayerStatus.FOLDED,
    )


def _runout(game: object, prefix: list) -> list:
    board = list(prefix)
    while len(board) < 5:
        game._draw()
        board.append(game._draw())
    return board


def _award(
    game: object,
    eligible: tuple[int, ...],
    amount: int,
    ranks: dict,
) -> tuple[list[dict], set[int]]:
    seats = [seat for seat in eligible if seat in ranks]
    if not seats or amount <= 0:
        return [], set()
    best = max(ranks[seat] for seat in seats)
    tied = [seat for seat in seats if ranks[seat] == best]
    ordered = odd_chip_order(tied, game.button, len(game.players))
    awards = []
    for seat, chips in split_amount(amount, ordered).items():
        game.players[seat].stack += chips
        awards.append({"seat": seat, "amount": chips})
    return awards, set(tied)
