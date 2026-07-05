#!/usr/bin/env python3
"""Validate and print the real-execution configuration template."""

from __future__ import annotations

import argparse
import json

from ashare_v3.ingestion.real_execution_config import DEFAULT_REAL_EXECUTION_CONFIG, load_real_execution_config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=DEFAULT_REAL_EXECUTION_CONFIG, help="Real-execution TOML template path. Validation remains dry-run only.")
    args = parser.parse_args()

    config = load_real_execution_config(args.config)
    print(json.dumps(config.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
