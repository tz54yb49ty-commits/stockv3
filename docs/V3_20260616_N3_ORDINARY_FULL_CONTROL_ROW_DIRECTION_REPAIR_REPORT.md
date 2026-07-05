# V3 20260616 N3 Ordinary/FULL Control Row Direction Repair Report

- result: `REPAIR_PASS`
- root_cause: reviewed manifest used direction=mixed for candidate audit rows but runtime candidate table accepts only buy/sell
- repair_policy: expand mixed candidate audit rows into canonical buy/sell rows; preserve deduped subscription rows with directions trace
- dry_run candidate rows: `2824 -> 5648`
- subscription rows preserved: `2824`
- pull_plan rows preserved: `6`
