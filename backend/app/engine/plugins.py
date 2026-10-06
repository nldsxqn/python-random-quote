"""Hooks the cash engine calls. Concrete rules live in app.rules and stay optional."""


class HandRules:
    """No-op rules. A hand with this object is standard NLHE."""

    def apply_top_up(self, game: object) -> None:
        return

    def uses_bomb_pot(self, game: object) -> bool:
        return False

    def post_bomb(self, game: object) -> None:
        return

    def post_ante(self, game: object) -> None:
        return

    def post_straddle(self, game: object) -> None:
        return

    def board_count(self, game: object) -> int:
        return 1

    def should_offer_insurance(self, game: object) -> bool:
        return False

    def insurance_quote(self, game: object) -> dict | None:
        return None

    def should_offer_run_it_twice(self, game: object) -> bool:
        return False

    def resolve_run_it_twice(self, game: object, accepted: bool) -> None:
        table = game
        table.rit_declined = True
        table.rit_result = {"accepted": False, "runs": []}
        table._autopilot()

    def apply_rake(self, game: object, pots: list) -> list:
        return pots

    def apply_bounty(self, game: object, winners: set[int]) -> None:
        return
