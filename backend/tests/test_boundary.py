import json
from pathlib import Path

from app.solver.mccfr import MccfrSolverAdapter
from app.solver.types import SolveRequest
from app.solver.zeta import ZetaAdapter

RIVER = "2c 7d 9h 4s 3c"


def test_zeta_is_unavailable_and_not_vendored() -> None:
    adapter = ZetaAdapter()
    assert adapter.health_check()["status"] == "unavailable"
    result = adapter.solve_spot(
        SolveRequest(players=2, board=RIVER, hero_range="AA", villain_range="KK", pot=20)
    )
    assert result.metadata["exact"] is False
    assert result.metadata["available"] is False
    assert result.metadata["solver"] == "zeta"
    assert result.frequencies == {}
    assert "Exact GTO" not in json.dumps(result.to_dict())
    root = Path(__file__).resolve().parents[2]
    assert not (root / "zeta").exists()
    source = (root / "backend" / "app" / "solver" / "zeta.py").read_text()
    assert "import zeta" not in source


def test_mccfr_resolves_the_same_heads_up_river() -> None:
    result = MccfrSolverAdapter().solve_spot(
        SolveRequest(
            players=2,
            board=RIVER,
            pot=20,
            effective_stack=100,
            hero_range="AA",
            villain_range="KK",
            bet_sizes=[10],
            iterations=2000,
        )
    )
    assert result.metadata["solver"] == "mccfr"
    assert result.metadata["exact"] is True
    assert result.metadata["label"] == "heads-up one-decision"
    assert result.strategy["villain"]["fold"] > 0.7
    assert abs(sum(result.frequencies.values()) - 1) < 1e-9
    assert "Exact GTO" not in json.dumps(result.to_dict())


def test_mccfr_flop_and_multiway_are_not_exact() -> None:
    adapter = MccfrSolverAdapter()
    flop = adapter.solve_spot(
        SolveRequest(
            players=2,
            board="2c 7d 9h",
            pot=20,
            effective_stack=80,
            hero_range="AsKd",
            villain_range="QcQd",
            bet_sizes=[10],
            iterations=8,
            samples=2,
        )
    )
    multi = adapter.solve_spot(
        SolveRequest(players=3, board=RIVER, pot=20, hero_range="AA", villain_range="KK")
    )
    assert flop.metadata["exact"] is False
    assert flop.metadata["method"] == "mccfr-monte-carlo"
    assert multi.metadata["exact"] is False
    assert multi.metadata["available"] is False
    assert "Exact GTO" not in json.dumps(flop.metadata)
    assert "Exact GTO" not in json.dumps(multi.metadata)
