#!/usr/bin/env python3
"""Static signal guard for A股监控系统 v3.

This checker enforces active signal vocabulary in changed files. It is static
CI tooling only and must not execute project runtime behavior.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


ACTIVE_SIGNAL_WHITELIST = {
    "B_BUY",
    "S_SELL",
    "BUY:FULL",
    "SELL:FULL",
    "BUY_HINT",
    "SELL_HINT",
}

LEGACY_SIGNALS = {
    "B_BUY_30M_VOL",
    "S_SELL_30M_SHRINK",
}

HISTORICAL_PATH_MARKERS = (
    "REPORT",
    "POST_REVIEW",
    "ROLLBACK",
    "HISTORICAL",
    "compatibility",
    "rollback",
)

ACTIVE_PATH_PREFIXES = (
    "src/",
    "scripts/",
    "tests/",
    "configs/",
)

ACTIVE_SQL_MARKERS = (
    "schema",
    "migration",
)

SIGNAL_PATTERN = re.compile(
    r"\b(?:B_BUY_30M_VOL|S_SELL_30M_SHRINK|B_BUY|S_SELL|BUY:FULL|SELL:FULL|BUY_HINT|SELL_HINT)\b"
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


def is_historical_evidence_path(path: Path) -> bool:
    normalized = normalize_path(path)
    return any(marker in normalized for marker in HISTORICAL_PATH_MARKERS)


def is_active_path(path: Path) -> bool:
    normalized = normalize_path(path)
    if normalized.startswith(ACTIVE_PATH_PREFIXES):
        return True
    if normalized.startswith("sql/") and any(marker in normalized for marker in ACTIVE_SQL_MARKERS):
        return True
    return False


def check_file(path: Path, display_path: Path) -> list[Violation]:
    if is_historical_evidence_path(display_path) and not is_active_path(display_path):
        return []

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []

    violations: list[Violation] = []
    active = is_active_path(display_path)
    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in SIGNAL_PATTERN.finditer(line):
            signal = match.group(0)
            if signal in LEGACY_SIGNALS and active:
                violations.append(
                    Violation(
                        "DRIFT_LEGACY_SIGNAL_ACTIVE_PATH",
                        display_path,
                        line_no,
                        f"legacy signal {signal!r} is forbidden in active decision paths",
                    )
                )
            elif signal not in ACTIVE_SIGNAL_WHITELIST and signal not in LEGACY_SIGNALS:
                violations.append(
                    Violation(
                        "DRIFT_SIGNAL_NOT_WHITELISTED",
                        display_path,
                        line_no,
                        f"signal {signal!r} is not in active whitelist",
                    )
                )
    return violations


def collect_paths(root: Path, changed_files: list[str]) -> list[Path]:
    if changed_files:
        return [root / item for item in changed_files]
    candidates: list[Path] = []
    for prefix in ("src", "scripts", "tests", "configs", "sql"):
        base = root / prefix
        if base.exists():
            candidates.extend(path for path in base.rglob("*") if path.is_file())
    return sorted(candidates)


def main() -> int:
    parser = argparse.ArgumentParser(description="Static v3 signal drift guard")
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
