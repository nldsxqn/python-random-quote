"""A stable fake solve for tests and the UI. It is not a strategy."""

from app.solver.types import SolveRequest, SolveResult

_MOCK = SolveResult(
    actions=["check", "bet"],
    frequencies={"check": 0.55, "bet": 0.45},
    evs={"check": 1.0, "bet": 1.0},
    strategy={"hero": {"check": 0.55, "bet": 0.45}, "villain": {"fold": 0.4, "call": 0.6}},
    exploitability=None,
    metadata={"solver": "mock", "label": "mock", "exact": False, "mock": True},
)


class MockSolverAdapter:
    def health_check(self) -> dict:
        return {"status": "ok", "solver": "mock"}

    def solve_spot(self, request: SolveRequest) -> SolveResult:
        del request
        return SolveResult(
            actions=list(_MOCK.actions),
            frequencies=dict(_MOCK.frequencies),
            evs=dict(_MOCK.evs),
            strategy={
                "hero": dict(_MOCK.strategy["hero"]),
                "villain": dict(_MOCK.strategy["villain"]),
            },
            exploitability=None,
            metadata=dict(_MOCK.metadata),
        )
