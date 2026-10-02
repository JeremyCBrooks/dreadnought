"""Packages may only import from their own layer or the layers below it."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

ALLOWED: dict[str, set[str]] = {
    "data": {"data"},
    "engine": {"engine", "data"},
    "game": {"game", "world", "engine", "data"},
    "world": {"game", "world", "engine", "data"},
    "ui": {"ui", "game", "world", "engine", "data"},
}
PACKAGES = {*ALLOWED, "web"}


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _runtime_imports(path: Path) -> set[str]:
    """Top-level package names imported by *path* at runtime (TYPE_CHECKING blocks excluded)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    typing_only: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            for child in node.body:
                typing_only.update(id(n) for n in ast.walk(child))
    found: set[str] = set()
    for node in ast.walk(tree):
        if id(node) in typing_only:
            continue
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found & PACKAGES


@pytest.mark.parametrize("package", sorted(ALLOWED))
def test_package_only_imports_its_own_layer_or_below(package):
    violations = [
        f"{path.relative_to(ROOT).as_posix()} imports {target}"
        for path in sorted((ROOT / package).rglob("*.py"))
        for target in sorted(_runtime_imports(path) - ALLOWED[package])
    ]

    assert violations == []


@pytest.mark.parametrize("module", ["main", "web.server", "engine.game_state", "game.turn", "world.dungeon_gen"])
def test_module_imports_cleanly_in_a_fresh_process(module):
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", f"import {module}"], cwd=ROOT, capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
