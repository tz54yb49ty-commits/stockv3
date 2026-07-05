#!/usr/bin/env python3
"""Run the N1 Fast Lane bundle wrapper in guarded validation mode."""

from __future__ import annotations

from ashare_v3.runtime.fastlane_contract import main_for_bundle


def main(argv: list[str] | None = None) -> int:
    return main_for_bundle("n1", argv)


if __name__ == "__main__":
    raise SystemExit(main())
