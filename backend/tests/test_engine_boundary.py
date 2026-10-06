import ast
from pathlib import Path


def test_engine_package_does_not_import_fastapi() -> None:
    root = Path(__file__).resolve().parents[1] / "app" / "engine"
    offenders: list[str] = []
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            if any(name == "fastapi" or name.startswith("fastapi.") for name in modules):
                offenders.append(path.name)
    assert offenders == []
