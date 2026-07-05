#!/usr/bin/env python3
"""Top-level static drift checker for A股监控系统 v3.

This checker is CI/static-review tooling only. It performs text and AST checks
without importing project runtime modules or mutating repository files.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


LAYER_TOKENS = {
    "N1_ingestion": ("ingestion", "official_daily", "source_facts"),
    "N2_condition": ("condition", "condition_layer", "condition_basis", "condition_pool"),
    "N3_market_data": ("market", "market_data", "realtime_snapshot", "minute_bar", "subscription"),
    "N4_trigger": ("trigger", "TriggerMatched", "TriggerStateChanged", "TriggerPendingMarketData"),
    "N5_action": ("action", "ActionExecuted", "ActionBlocked", "ActionEligible", "ActionSkipped"),
    "N6_user": ("user", "projection", "voice", "mobile", "sim"),
}

EXECUTION_WORDS = (
    "execute",
    "run_once",
    "worker",
    "consume",
    "outbox",
    "rollback",
)

ORCHESTRATION_SCRIPT_PREFIXES = (
    "scripts/",
    "src/ashare_v3/runtime/",
    "src/ashare_v3/runtime_control/",
)


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


def line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def detected_layers(text: str) -> set[str]:
    result: set[str] = set()
    for layer, tokens in LAYER_TOKENS.items():
        if any(token in text for token in tokens):
            result.add(layer)
    return result


def has_execution_word(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in EXECUTION_WORDS)


def is_orchestration_candidate(path: Path) -> bool:
    normalized = normalize_path(path)
    return normalized.startswith(ORCHESTRATION_SCRIPT_PREFIXES)


def check_orchestration(path: Path, display_path: Path) -> list[Violation]:
    if path.suffix not in {".py", ".sh", ".md", ".sql", ".json"}:
        return []

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []

    layers = detected_layers(text)
    if len(layers) < 2 or not has_execution_word(text):
        return []

    normalized = normalize_path(display_path)
    if not is_orchestration_candidate(display_path) and not normalized.startswith("scripts/"):
        return []

    runtime_layers = {"N3_market_data", "N4_trigger", "N5_action", "N6_user"}
    if len(layers & runtime_layers) >= 2:
        return [
            Violation(
                "DRIFT_ORCHESTRATION_CHAIN",
                display_path,
                1,
                "file appears to coordinate multiple runtime layers: " + ", ".join(sorted(layers)),
            )
        ]
    return []


def check_n4_action_leak(path: Path, display_path: Path) -> list[Violation]:
    normalized = normalize_path(display_path)
    if not normalized.startswith("src/ashare_v3/trigger/"):
        return []
    text = path.read_text(encoding="utf-8")
    if re.search(r"\b(ActionExecuted|ActionBlocked|ActionEligible|ActionSkipped|action_state|action_mark)\b", text):
        match = re.search(r"\b(ActionExecuted|ActionBlocked|ActionEligible|ActionSkipped|action_state|action_mark)\b", text)
        return [
            Violation(
                "DRIFT_LAYER_BOUNDARY_VIOLATION",
                display_path,
                line_for_offset(text, match.start()) if match else 1,
                "N4_trigger file contains N5 action-execution vocabulary",
            )
        ]
    return []


def check_n5_trigger_leak(path: Path, display_path: Path) -> list[Violation]:
    normalized = normalize_path(display_path)
    if not normalized.startswith("src/ashare_v3/action/"):
        return []
    text = path.read_text(encoding="utf-8")
    if re.search(r"\b(TriggerMatched|TriggerPendingMarketData|trigger_matcher|trigger_state)\b", text):
        match = re.search(r"\b(TriggerMatched|TriggerPendingMarketData|trigger_matcher|trigger_state)\b", text)
        return [
            Violation(
                "DRIFT_LAYER_BOUNDARY_VIOLATION",
                display_path,
                line_for_offset(text, match.start()) if match else 1,
                "N5_action file contains N4 trigger-execution vocabulary",
            )
        ]
    return []


def parse_imports(path: Path, display_path: Path) -> list[Violation]:
    if path.suffix != ".py":
        return []
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [
            Violation(
                "DRIFT_STATIC_PARSE_ERROR",
                display_path,
                exc.lineno or 1,
                "Python file cannot be parsed for drift checks",
            )
        ]
    return []


def collect_paths(root: Path, changed_files: list[str]) -> list[Path]:
    if changed_files:
        return [root / item for item in changed_files]
    candidates: list[Path] = []
    for prefix in ("src", "scripts", "tests", "configs", "sql"):
        base = root / prefix
        if base.exists():
            candidates.extend(path for path in base.rglob("*") if path.is_file())
    return sorted(candidates)


def run_subcheck(script: Path, root: Path, changed_files: list[str]) -> int:
    cmd = [sys.executable, str(script), "--root", str(root)]
    if changed_files:
        cmd.append("--changed-files")
        cmd.extend(changed_files)
    return subprocess.call(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(description="Static v3 drift prevention checker")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--changed-files", nargs="*", default=[], help="Changed files to check")
    parser.add_argument("--skip-subchecks", action="store_true", help="Do not invoke layer/signal subchecks")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    violations: list[Violation] = []

    for path in collect_paths(root, args.changed_files):
        if not path.exists() or not path.is_file():
            continue
        resolved = path.resolve()
        rel = resolved.relative_to(root)
        violations.extend(parse_imports(resolved, rel))
        violations.extend(check_orchestration(resolved, rel))
        violations.extend(check_n4_action_leak(resolved, rel))
        violations.extend(check_n5_trigger_leak(resolved, rel))

    for violation in violations:
        print(violation.format())

    subcheck_status = 0
    if not args.skip_subchecks:
        here = Path(__file__).resolve().parent
        for script_name in ("layer_boundary_check.py", "signal_guard.py"):
            subcheck_status |= run_subcheck(here / script_name, root, args.changed_files)

    return 1 if violations or subcheck_status else 0


if __name__ == "__main__":
    raise SystemExit(main())
