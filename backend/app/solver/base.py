"""SolverAdapter is the only way the app asks for a strategy."""

from typing import Protocol

from app.solver.types import SolveRequest, SolveResult


class SolverAdapter(Protocol):
    def solve_spot(self, request: SolveRequest) -> SolveResult:
        """Return one decision. Callers must read metadata before trusting it."""

    def health_check(self) -> dict:
        """Report whether this adapter can be called."""
