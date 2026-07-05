#!/usr/bin/env python3
"""Static layer-boundary checker for A股监控系统 v3.

This checker is CI/static-review tooling only. It must not import project
runtime modules, connect to databases, start workers, or mutate files.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


LAYER_BY_PACKAGE = {
    "ashare_v3.ingestion": "N1_ingestion",
    "ashare_v3.condition": "N2_condition",
    "ashare_v3.market": "N3_market_data",
    "ashare_v3.trigger": "N4_trigger",
    "ashare_v3.action": "N5_action",
    "ashare_v3.user": "N6_user",
}

LAYER_BY_PATH = {
    "src/ashare_v3/ingestion": "N1_ingestion",
    "src/ashare_v3/condition": "N2_condition",
    "src/ashare_v3/market": "N3_market_data",
    "src/ashare_v3/trigger": "N4_trigger",
    "src/ashare_v3/action": "N5_action",
    "src/ashare_v3/user": "N6_user",
}

FORBIDDEN_IMPORTS = {
    "N1_ingestion": {"N2_condition", "N3_market_data", "N4_trigger", "N5_action", "N6_user"},
    "N2_condition": {"N3_market_data", "N4_trigger", "N5_action", "N6_user"},
    "N3_market_data": {"N4_trigger", "N5_action", "N6_user"},
    "N4_trigger": {"N5_action", "N6_user"},
    "N5_action": {"N4_trigger", "N6_user"},
    "N6_user": {"N1_ingestion", "N2_condition", "N3_market_data", "N4_trigger", "N5_action"},
}


@dataclass(frozen=True)
class Violation:
    rule_id: str
    path: Path
    line: int
    reason: str

    def format(self) -> str:
        return f"{self.path}:{self.line}: {self.rule_id}: {self.reason}"


def normalize_path(path: Path) -> str:
    return path.as_posix().lstrip("./")


def layer_for_path(path: Path) -> str | None:
    normalized = normalize_path(path)
    for prefix, layer in LAYER_BY_PATH.items():
        if normalized.startswith(prefix + "/") or normalized == prefix:
            return layer
    return None


def layer_for_module(module: str | None) -> str | None:
    if not module:
        return None
    for prefix, layer in LAYER_BY_PACKAGE.items():
        if module == prefix or module.startswith(prefix + "."):
            return layer
    return None


def imported_modules(tree: ast.AST) -> Iterable[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            yield node.module or "", node.lineno


def check_file(path: Path, display_path: Path) -> list[Violation]:
    source_layer = layer_for_path(display_path)
    if source_layer is None or path.suffix != ".py":
        return []

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [
            Violation(
                "DRIFT_STATIC_PARSE_ERROR",
                display_path,
                exc.lineno or 1,
                "Python file cannot be parsed for static layer checks",
            )
        ]

    violations: list[Violation] = []
    forbidden_layers = FORBIDDEN_IMPORTS.get(source_layer, set())
    for module, line in imported_modules(tree):
        target_layer = layer_for_module(module)
        if target_layer in forbidden_layers:
            violations.append(
                Violation(
                    "DRIFT_CROSS_LAYER_IMPORT",
                    display_path,
                    line,
                    f"{source_layer} must not import {target_layer} module {module!r}",
                )
            )
    return violations


def collect_paths(root: Path, changed_files: list[str]) -> list[Path]:
    if changed_files:
        return [root / item for item in changed_files]
    return sorted((root / "src").glob("ashare_v3/**/*.py"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Static v3 layer-boundary drift checker")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--changed-files", nargs="*", default=[], help="Changed files to check")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    violations: list[Violation] = []
    for path in collect_paths(root, args.changed_files):
        if path.exists() and path.is_file():
            resolved = path.resolve()
            display_path = resolved.relative_to(root)
            violations.extend(check_file(resolved, display_path))

    for violation in violations:
        print(violation.format())
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
