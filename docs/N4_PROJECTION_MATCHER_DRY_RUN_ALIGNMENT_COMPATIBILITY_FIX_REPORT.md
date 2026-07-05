# N4 Projection Matcher Dry-Run Alignment Compatibility Fix

Result: **FIX_PASS**

The runner now accepts both legacy `summary.matched_count/pending_count` and refreshed `reviewed_expected_counts.TriggerMatched/TriggerPendingMarketData`. Targeted tests passed (`27 OK`), compileall passed, and runner preflight now returns `PREFLIGHT_PASS` with P0/P1/P2=`0/0/0`.
