"""Zeta is not vendored. This adapter only reports that the boundary is closed."""

from app.solver.types import SolveRequest, SolveResult


class ZetaAdapter:
    def health_check(self) -> dict:
        return {"status": "unavailable", "solver": "zeta", "reason": "zeta is not vendored"}

    def solve_spot(self, request: SolveRequest) -> SolveResult:
        del request
        return SolveResult(
            actions=[],
            frequencies={},
            evs={},
            strategy={},
            exploitability=None,
            metadata={
                "solver": "zeta",
                "label": "unavailable",
                "exact": False,
                "mock": False,
                "available": False,
                "reason": "zeta is not vendored",
            },
        )
