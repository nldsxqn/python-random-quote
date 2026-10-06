"""Play-money buy-in limits. There is no wallet and no cash."""

from dataclasses import dataclass

from app.engine.actions import IllegalActionError


@dataclass(frozen=True)
class BuyInConfig:
    minimum: int
    maximum: int
    unit: str

    def chip_bounds(self, big_blind: int) -> tuple[int, int]:
        if self.unit == "bb":
            return self.minimum * big_blind, self.maximum * big_blind
        return self.minimum, self.maximum


def parse_buyin(value: object) -> BuyInConfig:
    if not isinstance(value, dict):
        raise IllegalActionError("buy-in settings must include min, max, and unit")
    unit = value.get("unit")
    if unit not in {"bb", "chips"}:
        raise IllegalActionError("buy-in unit must be bb or chips")
    minimum = value.get("min")
    maximum = value.get("max")
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum <= 0:
        raise IllegalActionError("buy-in min must be a positive integer")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < minimum:
        raise IllegalActionError("buy-in max must be an integer greater than or equal to min")
    return BuyInConfig(minimum=minimum, maximum=maximum, unit=unit)


def require_buyin(config: BuyInConfig, big_blind: int, amount: int, *, adding: bool) -> None:
    low, high = config.chip_bounds(big_blind)
    if adding:
        if amount < low or amount > high:
            raise IllegalActionError(f"added chips must be from {low} to {high}")
        return
    if amount < low or amount > high:
        raise IllegalActionError(f"buy-in must be from {low} to {high}")
