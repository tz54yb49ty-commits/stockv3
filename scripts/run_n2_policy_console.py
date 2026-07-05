#!/usr/bin/env python3
"""Run the local N2 policy console MVP.

The console is dry-run only. It does not execute overwrite, pull market data,
start workers, or touch downstream layers.
"""

from __future__ import annotations

from ashare_v3.web.n2_policy_console import main


if __name__ == "__main__":
    main()
