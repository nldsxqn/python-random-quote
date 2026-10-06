"""No-limit betting rules. Opening bet is the big blind. Short all-ins do not reopen."""

from dataclasses import dataclass

from app.engine.actions import ActionType, IllegalActionError


def needs_action(status_active: bool, acted: bool, committed: int, current_bet: int) -> bool:
    if not status_active:
        return False
    if committed < current_bet:
        return True
    return not acted


def minimum_raise_to(current_bet: int, min_raise_increment: int) -> int:
    return current_bet + min_raise_increment


@dataclass(frozen=True)
class ActionEffect:
    fold: bool = False
    check: bool = False
    put: int = 0
    all_in: bool = False
    new_current_bet: int = 0
    new_increment: int = 0
    reopen: bool = False
    lock: bool = False


def resolve_action(
    *,
    kind: ActionType,
    amount: int | None,
    stack: int,
    committed: int,
    current_bet: int,
    min_raise_increment: int,
    big_blind: int,
    can_raise: bool,
) -> ActionEffect:
    _reject_amount(kind, amount)
    to_call = current_bet - committed
    if kind is ActionType.FOLD:
        return ActionEffect(fold=True)
    if kind is ActionType.CHECK:
        if to_call != 0:
            raise IllegalActionError("cannot check facing a bet")
        return ActionEffect(check=True)
    if kind is ActionType.CALL:
        return _call(stack, to_call, current_bet, min_raise_increment)
    if kind is ActionType.BET:
        return _bet(
            _chips(amount),
            stack,
            current_bet,
            big_blind,
        )
    if kind is ActionType.RAISE:
        return _raise(
            _chips(amount),
            stack,
            committed,
            current_bet,
            min_raise_increment,
            can_raise,
        )
    if kind is ActionType.ALL_IN:
        return _all_in(
            stack,
            committed,
            current_bet,
            min_raise_increment,
            big_blind,
            can_raise,
        )
    raise IllegalActionError(f"unknown action {kind}")


def _reject_amount(kind: ActionType, amount: int | None) -> None:
    takes_amount = kind in {ActionType.BET, ActionType.RAISE}
    if takes_amount and amount is None:
        raise IllegalActionError("this action needs an amount")
    if not takes_amount and amount is not None:
        raise IllegalActionError("this action does not take an amount")


def _chips(amount: int | None) -> int:
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise IllegalActionError("amount must be a positive integer")
    return amount


def _call(stack: int, to_call: int, current_bet: int, min_raise_increment: int) -> ActionEffect:
    if to_call <= 0:
        raise IllegalActionError("nothing to call")
    if stack < to_call:
        raise IllegalActionError("insufficient stack to call")
    return ActionEffect(
        put=to_call,
        all_in=stack == to_call,
        new_current_bet=current_bet,
        new_increment=min_raise_increment,
    )


def _bet(amount: int, stack: int, current_bet: int, big_blind: int) -> ActionEffect:
    if current_bet != 0:
        raise IllegalActionError("cannot bet facing a bet")
    if amount > stack:
        raise IllegalActionError("bet exceeds stack")
    if amount < big_blind:
        raise IllegalActionError("bet below minimum")
    return ActionEffect(
        put=amount,
        all_in=amount == stack,
        new_current_bet=amount,
        new_increment=amount,
        reopen=True,
    )


def _raise(
    target: int,
    stack: int,
    committed: int,
    current_bet: int,
    min_raise_increment: int,
    can_raise: bool,
) -> ActionEffect:
    if current_bet == 0:
        raise IllegalActionError("nothing to raise")
    if not can_raise:
        raise IllegalActionError("betting was not reopened")
    put = target - committed
    if put <= 0:
        raise IllegalActionError("raise must increase the street commitment")
    if put > stack:
        raise IllegalActionError("raise exceeds stack")
    if target < minimum_raise_to(current_bet, min_raise_increment):
        raise IllegalActionError("raise below minimum")
    increase = target - current_bet
    return ActionEffect(
        put=put,
        all_in=put == stack,
        new_current_bet=target,
        new_increment=increase,
        reopen=True,
    )


def _all_in(
    stack: int,
    committed: int,
    current_bet: int,
    min_raise_increment: int,
    big_blind: int,
    can_raise: bool,
) -> ActionEffect:
    if stack <= 0:
        raise IllegalActionError("no chips to go all-in")
    new_commit = committed + stack
    increase = new_commit - current_bet
    if increase > 0 and not can_raise:
        raise IllegalActionError("all-in raise is not allowed; betting was not reopened")
    if increase <= 0:
        return ActionEffect(
            put=stack,
            all_in=True,
            new_current_bet=current_bet,
            new_increment=min_raise_increment,
        )
    full = increase >= (big_blind if current_bet == 0 else min_raise_increment)
    if current_bet == 0 and not full:
        # Short opening shove. Later raises still use the big blind as the increment.
        return ActionEffect(
            put=stack,
            all_in=True,
            new_current_bet=new_commit,
            new_increment=min_raise_increment,
            lock=True,
        )
    if full:
        return ActionEffect(
            put=stack,
            all_in=True,
            new_current_bet=new_commit,
            new_increment=increase,
            reopen=True,
        )
    return ActionEffect(
        put=stack,
        all_in=True,
        new_current_bet=new_commit,
        new_increment=min_raise_increment,
        lock=True,
    )
