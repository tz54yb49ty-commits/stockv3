# V3 20260615 N6 Zero User Message CLI Exit Code Alignment

Result: `ALIGNMENT_PASS`

Gate: `V3_20260615_N6_ZERO_USER_MESSAGE_CLI_EXIT_CODE_ALIGNMENT_GATE`

Layer role: `N6_user`

## Scope

This gate aligns the N6 projection CLI wrapper success exit-code contract only.

Allowed change:

- `scripts/run_n6_projection_once.py` treats `PROJECTION_PASS_ZERO_USER_MESSAGES` as a successful report result.

Forbidden scope remains false:

- N6 projection execute
- database write
- N5 outbox/inbox/checkpoint consume or update
- scheduler restart
- worker start
- voice/mobile/sim/position/PnL/real trade
- old system touch

## Root Cause

`run_projection_shadow_execute()` can now return `PROJECTION_PASS_ZERO_USER_MESSAGES` for the 20260615 zero-user-message path. The CLI wrapper still returned exit code `0` only when `report.result == "EXECUTED"`, so a successful zero-user-message report was incorrectly surfaced as exit code `2`.

## Alignment

The CLI wrapper now has an explicit success result allowlist:

- `EXECUTED`
- `PROJECTION_PASS_ZERO_USER_MESSAGES`

All other report results, including `BLOCKED`, still return exit code `2`.

## Test Proof

Added `tests/test_n6_projection_cli.py`:

- `PROJECTION_PASS_ZERO_USER_MESSAGES` returns exit code `0`
- `BLOCKED` returns exit code `2`
- The CLI test uses a mocked runner report and does not read or write the database

Validation:

```text
PYTHONPATH=src:scripts:tests python3 -m unittest tests.test_n6_projection_cli tests.test_n6_projection_execute tests.test_n6_projection_plan
Ran 44 tests - OK

PYTHONPATH=src:scripts:tests python3 -m compileall -q src tests scripts
PASS

python3 -m json.tool docs/V3_20260615_N6_USER_PROJECTION_CONTRACT.json
python3 -m json.tool docs/V3_20260615_N6_USER_PROJECTION_PREFLIGHT.json
python3 -m json.tool docs/V3_20260615_N6_ZERO_USER_MESSAGE_RUNNER_ALIGNMENT.json
PASS
```

## Next Gate

Recommended next prompt:

```text
layer_role=N6_user

进入 V3_20260615_N6_USER_PROJECTION_EXECUTE_FINAL_GATE_REVIEW。

目标：
只读复核 20260615 zero-user-message N6 projection contract/preflight/runner/CLI alignment，确认是否允许进入用户 execute 确认点。

要求：
不 execute N6 projection，不写数据库，不消费/update N5 outbox/inbox/checkpoint，不重启 scheduler，不进入 voice/mobile/sim/position/PnL/real trade，不修改旧系统。

请复核：
1. N5 source action_run passed，ActionBlocked:pending=836。
2. user_message_event_filter=ActionEligible/ActionExecuted。
3. planned writes=user_projection_run=1, user_signal_projection=0, user_signal_card=0, user_notification_queue=0。
4. runner zero-user-message alignment PASS。
5. CLI exit-code alignment PASS：PROJECTION_PASS_ZERO_USER_MESSAGES -> exit code 0；BLOCKED -> non-zero。
6. rollback SQL scoped and hard-fail before DELETE/UPDATE。
7. forbidden scope proof。

输出：
FINAL_GATE_REVIEW_PASS / BLOCKED
source proof
zero-user-message proof
CLI exit-code proof
rollback proof
allowed execute command if PASS
```
