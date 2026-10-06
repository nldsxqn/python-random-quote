"""One NLHE cash table. FastAPI must not be imported from here."""

import copy

from app.engine.actions import Action, IllegalActionError
from app.engine.betting import ActionEffect, needs_action, resolve_action
from app.engine.cards import Card, standard_deck
from app.engine.deck import DeckProvider, SystemRandomDeck
from app.engine.evaluator import HandStrength, canonical_category, evaluate
from app.engine.player import Player, PlayerStatus
from app.engine.plugins import HandRules
from app.engine.pot import Contribution, Pot, build_pots, odd_chip_order, split_amount
from app.engine.short_deck import evaluate_short, short_deck
from app.engine.state import PublicPlayer, PublicView, Street


class CashGame:
    """Standard no-limit hold'em cash hand. Integer chips. 2–9 seats."""

    def __init__(
        self,
        stacks: list[int],
        *,
        button: int,
        small_blind: int,
        big_blind: int,
        deck: DeckProvider | None = None,
        rules: HandRules | None = None,
        variant: str = "nlhe",
    ) -> None:
        if variant not in {"nlhe", "short_deck"}:
            raise IllegalActionError("variant must be nlhe or short_deck")
        self._require_table(stacks, button, small_blind, big_blind)
        self.variant = variant
        self.players = [Player(seat=index, stack=stack) for index, stack in enumerate(stacks)]
        self.button = button
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.deck_provider: DeckProvider = deck if deck is not None else SystemRandomDeck()
        self.starting_chips = sum(stacks)
        self.street = Street.WAITING
        self.street_path: list[Street] = [Street.WAITING]
        self.board: list[Card] = []
        self.deck: list[Card] = []
        self.draw_index = 0
        self.actor: int | None = None
        self.sb_seat: int | None = None
        self.bb_seat: int | None = None
        self.current_bet = 0
        self.min_raise_increment = big_blind
        self.in_hand: set[int] = set()
        self.showdown_seats: set[int] = set()
        self.pots: list[Pot] = []
        self.rules: HandRules = rules if rules is not None else HandRules()
        self.straddle_seat: int | None = None
        self.awaiting_rit = False
        self.rit_votes: dict[int, bool] = {}
        self.rit_declined = False
        self.rit_result: dict | None = None
        self.boards: list[list[Card]] = []
        self.rake = 0
        self.bounty = 0
        self.bounty_payments: list[dict] = []
        self.top_ups: list[dict[str, int]] = []
        self.awaiting_insurance = False
        self.insurance_resolved = False
        self.insurance_quote: dict | None = None
        self.insurance_result: dict | None = None
        self.board_result: dict | None = None
        self.settlement: list[dict] = []

    def start_hand(self) -> None:
        if self.street not in {Street.WAITING, Street.HAND_COMPLETE}:
            raise IllegalActionError("hand already in progress")
        self._reset_rule_fields()
        self.rules.apply_top_up(self)
        live = [player.seat for player in self.players if player.stack > 0]
        if len(live) < 2:
            raise IllegalActionError("need at least 2 players with chips")
        button = self.button
        if self.street is Street.HAND_COMPLETE:
            button = self._next_with_chips(self.button)
        if self.variant == "short_deck":
            order = self.deck_provider.shuffle(short_deck())
            self._require_short_deck(order)
        else:
            order = self.deck_provider.shuffle(standard_deck())
            self._require_deck(order)
        self.button = button
        self._prepare_players()
        self.deck = order
        self.draw_index = 0
        self.board = []
        self.pots = []
        self.showdown_seats = set()
        self.street_path = []
        self._set_street(Street.POSTING_BLINDS)
        if self.rules.uses_bomb_pot(self):
            self._assign_blind_seats()
            self.rules.post_ante(self)
            self.rules.post_bomb(self)
            self._deal_hole_cards()
            self._set_street(Street.PREFLOP)
            self._deal_next_street()
            self._open_postflop()
        else:
            self._assign_blind_seats()
            self.rules.post_ante(self)
            self._post_blind_chips()
            self.rules.post_straddle(self)
            self._deal_hole_cards()
            self._set_street(Street.PREFLOP)
            self._open_preflop()
        self._autopilot()

    def post_dead(self, seat: int, amount: int) -> int:
        """Put chips in the pot without counting them as a street bet."""
        player = self.players[seat]
        put = min(amount, player.stack)
        if put < 0:
            put = 0
        player.stack -= put
        player.committed_hand += put
        if player.stack == 0 and put > 0:
            player.status = PlayerStatus.ALL_IN
        return put

    def vote_run_it_twice(self, seat: int, accept: bool) -> None:
        if not self.awaiting_rit:
            raise IllegalActionError("run it twice is not offered")
        if not isinstance(accept, bool):
            raise IllegalActionError("run it twice vote must be yes or no")
        alive = self._alive_seats()
        if seat not in alive:
            raise IllegalActionError("not contesting this pot")
        if seat in self.rit_votes:
            raise IllegalActionError("already voted")
        self.rit_votes[seat] = accept
        if len(self.rit_votes) < len(alive):
            return
        self.awaiting_rit = False
        self.rules.resolve_run_it_twice(self, all(self.rit_votes.values()))

    def decide_insurance(self, seat: int, accept: bool) -> None:
        if not self.awaiting_insurance or self.insurance_quote is None:
            raise IllegalActionError("insurance is not offered")
        if not isinstance(accept, bool):
            raise IllegalActionError("insurance answer must be yes or no")
        if seat != self.insurance_quote["seat"]:
            raise IllegalActionError("only the quoted player can answer")
        quote = self.insurance_quote
        self.awaiting_insurance = False
        self.insurance_resolved = True
        self.insurance_result = {**quote, "accepted": accept, "label": "simplified"}
        if accept:
            self._settle_insurance(quote)
        self._autopilot()

    def _reset_rule_fields(self) -> None:
        self.straddle_seat = None
        self.awaiting_rit = False
        self.rit_votes = {}
        self.rit_declined = False
        self.rit_result = None
        self.boards = []
        self.board_result = None
        self.awaiting_insurance = False
        self.insurance_resolved = False
        self.insurance_quote = None
        self.insurance_result = None
        self.rake = 0
        self.bounty = 0
        self.bounty_payments = []
        self.top_ups = []
        self.settlement = []

    def apply(self, action: Action, seat: int | None = None) -> None:
        snapshot = copy.deepcopy(self.__dict__)
        try:
            self._apply(action, seat)
        except IllegalActionError:
            self.__dict__.clear()
            self.__dict__.update(snapshot)
            raise

    def public_view(self, viewer: int) -> PublicView:
        if viewer not in range(len(self.players)):
            raise IllegalActionError("unknown seat")
        revealed = self.showdown_seats
        players = tuple(
            PublicPlayer(
                seat=player.seat,
                stack=player.stack,
                status=player.status,
                committed_street=player.committed_street,
                committed_hand=player.committed_hand,
                hole_cards=self._visible_hole(player, viewer, revealed),
            )
            for player in self.players
        )
        pot = 0 if self.street is Street.HAND_COMPLETE else self._committed_total()
        return PublicView(
            street=self.street,
            button=self.button,
            small_blind_seat=self.sb_seat,
            big_blind_seat=self.bb_seat,
            actor=self.actor,
            board=tuple(self.board),
            pot=pot,
            pots=tuple(self.pots),
            players=players,
        )

    def chip_total(self) -> int:
        total = sum(player.stack for player in self.players)
        if self.street not in {Street.WAITING, Street.HAND_COMPLETE}:
            total += self._committed_total()
        return total

    def _apply(self, action: Action, seat: int | None) -> None:
        if self.actor is None:
            raise IllegalActionError("no action is pending")
        actor = self.actor
        if seat is not None and seat != actor:
            raise IllegalActionError("out of turn")
        player = self.players[actor]
        if player.status is not PlayerStatus.ACTIVE:
            raise IllegalActionError("player cannot act")
        effect = resolve_action(
            kind=action.kind,
            amount=action.amount,
            stack=player.stack,
            committed=player.committed_street,
            current_bet=self.current_bet,
            min_raise_increment=self.min_raise_increment,
            big_blind=self.big_blind,
            can_raise=player.can_raise,
        )
        self._perform(player, effect)
        if self._alive_count() <= 1:
            self.actor = None
        else:
            self.actor = self._next_to_act(actor)
        self._autopilot()

    def _perform(self, player: Player, effect: ActionEffect) -> None:
        if effect.fold:
            player.status = PlayerStatus.FOLDED
            player.acted = True
            return
        if effect.check:
            player.acted = True
            return
        player.stack -= effect.put
        player.committed_street += effect.put
        player.committed_hand += effect.put
        player.status = PlayerStatus.ALL_IN if effect.all_in else PlayerStatus.ACTIVE
        player.acted = True
        self.current_bet = effect.new_current_bet
        self.min_raise_increment = effect.new_increment
        if effect.reopen:
            self._reopen_others(player.seat)
        elif effect.lock:
            self._lock_previous_actors(player.seat)

    def _autopilot(self) -> None:
        for _ in range(12):
            if (
                self.awaiting_rit
                or self.awaiting_insurance
                or self.street is Street.HAND_COMPLETE
                or self.actor is not None
            ):
                return
            alive = self._alive_seats()
            if len(alive) <= 1:
                self._finish(showdown=False)
                return
            if self.street is Street.RIVER:
                self._finish(showdown=True)
                return
            if self.street not in {Street.PREFLOP, Street.FLOP, Street.TURN}:
                raise RuntimeError(f"cannot progress from {self.street}")
            if self.rules.should_offer_run_it_twice(self):
                self.awaiting_rit = True
                self.rit_votes = {}
                self.actor = None
                return
            active = self._active_count()
            if (
                self.street is Street.TURN
                and active < 2
                and not self.insurance_resolved
                and self.rules.should_offer_insurance(self)
            ):
                quote = self.rules.insurance_quote(self)
                if quote is not None:
                    self.awaiting_insurance = True
                    self.insurance_quote = quote
                    self.actor = None
                    return
            self._deal_next_street()
            if active >= 2:
                self._open_postflop()
                continue
            self.actor = None
        raise RuntimeError("hand progress did not settle")

    def _finish(self, *, showdown: bool) -> None:
        ranks: dict[int, HandStrength] | None = None
        if showdown:
            self._set_street(Street.SHOWDOWN)
            self.showdown_seats = set(self._alive_seats())
            ranks = {
                seat: self._rank(self.players[seat].hole or (), self.board)
                for seat in self.showdown_seats
            }
            if len(self.boards) == 2 and all(len(board) == 5 for board in self.boards):
                self._pay_two_boards()
                for player in self.players:
                    if player.stack == 0:
                        player.status = PlayerStatus.ELIMINATED
                self.actor = None
                self._set_street(Street.HAND_COMPLETE)
                return
        else:
            self.showdown_seats = set()
        self._pay(ranks)
        for player in self.players:
            if player.stack == 0:
                player.status = PlayerStatus.ELIMINATED
        self.actor = None
        self._set_street(Street.HAND_COMPLETE)

    def _pay(self, ranks: dict[int, HandStrength] | None) -> None:
        self._set_street(Street.PAYOUT)
        contributions = [
            Contribution(
                seat,
                self.players[seat].committed_hand,
                self.players[seat].status is PlayerStatus.FOLDED,
            )
            for seat in sorted(self.in_hand)
        ]
        self.pots = self.rules.apply_rake(self, build_pots(contributions))
        if ranks is None:
            winners = self._alive_seats()
            if len(winners) != 1:
                raise RuntimeError("fold win needs one remaining player")
            total = sum(pot.amount for pot in self.pots)
            self.players[winners[0]].stack += total
            self._note_winner(winners[0], total, None)
            self.rules.apply_bounty(self, set(winners))
            return
        showdown_winners: set[int] = set()
        for pot in self.pots:
            eligible = [seat for seat in pot.eligible if seat in ranks]
            if not eligible:
                raise RuntimeError("pot has no eligible winner")
            if pot.amount <= 0:
                continue
            best = max(ranks[seat] for seat in eligible)
            tied = [seat for seat in eligible if ranks[seat] == best]
            showdown_winners.update(tied)
            ordered = odd_chip_order(tied, self.button, len(self.players))
            for seat, chips in split_amount(pot.amount, ordered).items():
                self.players[seat].stack += chips
                self._note_winner(seat, chips, ranks[seat])
        self.rules.apply_bounty(self, showdown_winners)

    def _prepare_players(self) -> None:
        for player in self.players:
            player.hole = None
            player.committed_street = 0
            player.committed_hand = 0
            player.acted = False
            player.can_raise = True
            if player.stack <= 0:
                player.status = PlayerStatus.ELIMINATED
            else:
                player.status = PlayerStatus.ACTIVE
        self.in_hand = {player.seat for player in self.players if player.stack > 0}

    def _assign_blind_seats(self) -> None:
        if len(self.in_hand) == 2:
            self.sb_seat = self.button
            self.bb_seat = self._next_in_hand(self.button)
        else:
            self.sb_seat = self._next_in_hand(self.button)
            self.bb_seat = self._next_in_hand(self.sb_seat)

    def _post_blind_chips(self) -> None:
        if self.sb_seat is None or self.bb_seat is None:
            raise RuntimeError("blind seats are missing")
        self._take(self.sb_seat, self.small_blind)
        self._take(self.bb_seat, self.big_blind)

    def _post_blinds(self) -> None:
        self._assign_blind_seats()
        self._post_blind_chips()

    def _take(self, seat: int, amount: int) -> None:
        player = self.players[seat]
        put = min(amount, player.stack)
        player.stack -= put
        player.committed_street += put
        player.committed_hand += put
        if player.stack == 0:
            player.status = PlayerStatus.ALL_IN

    def _deal_hole_cards(self) -> None:
        order = self._ring(self.sb_seat)
        first = [self._draw() for _ in order]
        second = [self._draw() for _ in order]
        for seat, left, right in zip(order, first, second, strict=True):
            self.players[seat].hole = (left, right)

    def _rank(self, hole: tuple[Card, ...] | tuple, board: list[Card]) -> HandStrength:
        if self.variant == "short_deck":
            return evaluate_short(hole, board)
        return evaluate(hole, board)

    def _settle_insurance(self, quote: dict) -> None:
        payout = int(quote["payout"])
        premium = int(quote["premium"])
        hero = int(quote["seat"])
        others = [seat for seat in self._alive_seats() if seat != hero]
        for player in self.players:
            player.committed_hand = 0
            player.committed_street = 0
        self.players[hero].stack += payout
        if not others:
            return
        ordered = odd_chip_order(others, self.button, len(self.players))
        base, extra = divmod(premium, len(ordered))
        for index, seat in enumerate(ordered):
            self.players[seat].stack += base + (1 if index < extra else 0)

    def _pay_two_boards(self) -> None:
        self._set_street(Street.PAYOUT)
        contributions = [
            Contribution(
                seat,
                self.players[seat].committed_hand,
                self.players[seat].status is PlayerStatus.FOLDED,
            )
            for seat in sorted(self.in_hand)
        ]
        self.pots = self.rules.apply_rake(self, build_pots(contributions))
        runs = []
        winners: set[int] = set()
        for index, board in enumerate(self.boards):
            ranks = {
                seat: self._rank(self.players[seat].hole or (), board)
                for seat in self.showdown_seats
            }
            pot_rows = []
            for pot in self.pots:
                portion = pot.amount // 2 + (pot.amount % 2 if index == 0 else 0)
                awards, tied = self._award_portion(pot.eligible, portion, ranks)
                winners.update(tied)
                pot_rows.append(
                    {"amount": portion, "eligible": list(pot.eligible), "awards": awards}
                )
            runs.append({"board": [card.code for card in board], "pots": pot_rows})
        self.board_result = {"boards": 2, "runs": runs}
        self.rules.apply_bounty(self, winners)

    def _award_portion(
        self,
        eligible: tuple[int, ...],
        amount: int,
        ranks: dict[int, HandStrength],
    ) -> tuple[list[dict], set[int]]:
        seats = [seat for seat in eligible if seat in ranks]
        if not seats or amount <= 0:
            return [], set()
        best = max(ranks[seat] for seat in seats)
        tied = [seat for seat in seats if ranks[seat] == best]
        ordered = odd_chip_order(tied, self.button, len(self.players))
        awards = []
        for seat, chips in split_amount(amount, ordered).items():
            self.players[seat].stack += chips
            awards.append({"seat": seat, "amount": chips})
            self._note_winner(seat, chips, ranks.get(seat))
        return awards, set(tied)

    def _note_winner(self, seat: int, amount: int, strength: HandStrength | None) -> None:
        """Record a pot award. Fold wins carry no made hand."""
        if amount < 0:
            return
        category = None if strength is None else canonical_category(strength.category)
        cards = list(strength.cards) if strength is not None and strength.cards else None
        rank_index = None if strength is None else strength.index
        for row in self.settlement:
            if row["seat"] != seat:
                continue
            row["amount"] += amount
            if rank_index is not None and (row["index"] is None or rank_index >= row["index"]):
                row["category"] = category
                row["cards"] = cards
                row["index"] = rank_index
            return
        self.settlement.append(
            {
                "seat": seat,
                "amount": amount,
                "category": category,
                "cards": cards,
                "index": rank_index,
            }
        )

    def _deal_next_street(self) -> None:
        if self.rules.board_count(self) == 2:
            self._deal_double_board()
            return
        self._draw()
        if self.street is Street.PREFLOP:
            self.board.extend([self._draw(), self._draw(), self._draw()])
            self._set_street(Street.FLOP)
            return
        if self.street is Street.FLOP:
            self.board.append(self._draw())
            self._set_street(Street.TURN)
            return
        if self.street is Street.TURN:
            self.board.append(self._draw())
            self._set_street(Street.RIVER)
            return
        raise RuntimeError("no further street")

    def _deal_double_board(self) -> None:
        if self.street is Street.PREFLOP:
            self.boards = [[], []]
            for index in range(2):
                self._draw()
                self.boards[index].extend([self._draw(), self._draw(), self._draw()])
            self.board = list(self.boards[0])
            self._set_street(Street.FLOP)
            return
        if self.street is Street.FLOP:
            nxt = Street.TURN
        elif self.street is Street.TURN:
            nxt = Street.RIVER
        else:
            raise RuntimeError("no further street")
        for index in range(2):
            self._draw()
            self.boards[index].append(self._draw())
        self.board = list(self.boards[0])
        self._set_street(nxt)

    def _open_preflop(self) -> None:
        self.current_bet = max(self.players[seat].committed_street for seat in self.in_hand)
        if self.straddle_seat is None:
            self.min_raise_increment = self.big_blind
        for seat in self.in_hand:
            player = self.players[seat]
            player.acted = False
            player.can_raise = True
        self.actor = self._seat_from(self._first_preflop_seat())

    def _open_postflop(self) -> None:
        for seat in self.in_hand:
            player = self.players[seat]
            player.committed_street = 0
            if player.status is PlayerStatus.ACTIVE:
                player.acted = False
                player.can_raise = True
        self.current_bet = 0
        self.min_raise_increment = self.big_blind
        self.actor = self._seat_from(self._next_seat(self.button))

    def _first_preflop_seat(self) -> int:
        if self.straddle_seat is not None:
            return self._next_in_hand(self.straddle_seat)
        if len(self.in_hand) == 2:
            return self.button
        if self.bb_seat is None:
            raise RuntimeError("big blind missing")
        return self._next_seat(self.bb_seat)

    def _seat_from(self, start: int) -> int | None:
        if self._needs(start):
            return start
        return self._next_to_act(start)

    def _needs(self, seat: int) -> bool:
        player = self.players[seat]
        return needs_action(
            player.status is PlayerStatus.ACTIVE and seat in self.in_hand,
            player.acted,
            player.committed_street,
            self.current_bet,
        )

    def _next_to_act(self, after: int) -> int | None:
        seat = after
        for _ in range(len(self.players)):
            seat = self._next_seat(seat)
            if self._needs(seat):
                return seat
        return None

    def _reopen_others(self, actor: int) -> None:
        for seat in self.in_hand:
            if seat == actor:
                continue
            player = self.players[seat]
            if player.status is PlayerStatus.ACTIVE:
                player.acted = False
                player.can_raise = True

    def _lock_previous_actors(self, actor: int) -> None:
        for seat in self.in_hand:
            if seat == actor:
                continue
            player = self.players[seat]
            if player.status is PlayerStatus.ACTIVE and player.acted:
                player.can_raise = False

    def _alive_seats(self) -> list[int]:
        return [
            seat
            for seat in sorted(self.in_hand)
            if self.players[seat].status is not PlayerStatus.FOLDED
        ]

    def _alive_count(self) -> int:
        return len(self._alive_seats())

    def _active_count(self) -> int:
        return sum(player.status is PlayerStatus.ACTIVE for player in self.players)

    def _ring(self, start: int) -> list[int]:
        order = [start]
        seat = self._next_in_hand(start)
        while seat != start:
            order.append(seat)
            seat = self._next_in_hand(seat)
        return order

    def _next_in_hand(self, seat: int) -> int:
        start = seat
        seat = self._next_seat(seat)
        while seat != start:
            if seat in self.in_hand:
                return seat
            seat = self._next_seat(seat)
        raise RuntimeError("no other player in the hand")

    def _next_with_chips(self, seat: int) -> int:
        start = seat
        seat = self._next_seat(seat)
        while seat != start:
            if self.players[seat].stack > 0:
                return seat
            seat = self._next_seat(seat)
        raise IllegalActionError("no player has chips")

    def _next_seat(self, seat: int) -> int:
        return (seat + 1) % len(self.players)

    def _draw(self) -> Card:
        card = self.deck[self.draw_index]
        self.draw_index += 1
        return card

    def _committed_total(self) -> int:
        return sum(player.committed_hand for player in self.players)

    def _visible_hole(
        self,
        player: Player,
        viewer: int,
        revealed: set[int],
    ) -> tuple[Card, Card] | None:
        if player.hole is None:
            return None
        if player.seat == viewer or player.seat in revealed:
            return player.hole
        return None

    def _set_street(self, street: Street) -> None:
        self.street = street
        self.street_path.append(street)

    @staticmethod
    def _require_table(stacks: list[int], button: int, small_blind: int, big_blind: int) -> None:
        if not 2 <= len(stacks) <= 9:
            raise IllegalActionError("table must have 2 to 9 players")
        if button not in range(len(stacks)):
            raise IllegalActionError("button seat is out of range")
        for stack in stacks:
            if isinstance(stack, bool) or not isinstance(stack, int) or stack <= 0:
                raise IllegalActionError("stacks must be positive integers")
        if (
            isinstance(small_blind, bool)
            or isinstance(big_blind, bool)
            or not isinstance(small_blind, int)
            or not isinstance(big_blind, int)
            or small_blind <= 0
            or big_blind <= small_blind
        ):
            raise IllegalActionError("blinds must be positive integers and the big blind larger")

    @staticmethod
    def _require_deck(order: list[Card]) -> None:
        if len(order) != 52 or set(order) != set(standard_deck()):
            raise IllegalActionError("deck must contain each of the 52 cards once")

    @staticmethod
    def _require_short_deck(order: list[Card]) -> None:
        if len(order) != 36 or set(order) != set(short_deck()):
            raise IllegalActionError("short deck must contain each of the 36 cards once")
