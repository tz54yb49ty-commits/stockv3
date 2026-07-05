#!/usr/bin/env python3
"""N6 initial admin bootstrap entry point.

Without both --execute and --user-confirmed this writes only preflight report
artifacts. It does not consume N5 outbox, create sessions, start workers, push
notifications, or place trades.
"""

from __future__ import annotations

from ashare_v3.user.admin_bootstrap import main


if __name__ == "__main__":
    raise SystemExit(main())
