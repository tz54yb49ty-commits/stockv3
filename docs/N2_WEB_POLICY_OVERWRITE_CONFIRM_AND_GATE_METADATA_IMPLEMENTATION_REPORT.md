# N2 Web Policy Overwrite Confirm And Gate Metadata Implementation Report

```text
result=IMPLEMENTATION_PASS
layer_role=N2_condition
writes_performed=false
database_written=false
overwrite_executed=false
registry_command_executed=false
rollback_sql_executed=false
downstream_layers_entered=false
worker_started=false
outbox_inbox_checkpoint_touched=false
```

## Implementation Summary

本轮只补齐 8782 N2 Web Policy 默认策略发布闭环的实现前置项，没有执行 N2 overwrite，也没有写 condition 正式表。

- 新增 copy-only overwrite 二次确认页：`GET /execute-overwrite`。
- 新增 copy-only 二次确认 API：`POST /api/n2/policy/confirm-overwrite`。
- 二次确认仅在 latest gate exists、`gate_result=PASS`、gate `policy_hash` 等于当前 `configs/n2_policy/default_policy_draft.json` 的 `policy_hash`、且 `source_trade_date` 匹配时开放。
- 用户必须输入 `proposed_run_id` 或 `policy_hash`；成功后只返回 `WAIT_MANUAL_CONFIRM` 和可复制命令，不执行写库。
- execute gate artifact 补齐 policy/governance metadata。
- 每日 runner policy 前提审计已固化为只读函数；发现 scheduler/registry 覆盖 `--policy` 时会 BLOCK。
- `plan_condition_execute_contract.py` / `plan_condition_execute_preflight.py` 已和正式 execute runner 使用同一 policy loader，并把 `condition_pool_policy` 传入 pool/scope dry-run。

## Second Confirm Page Proof

页面展示：

```text
current_active_run_id
proposed_run_id
policy_version
policy_hash
policy_diff_summary
expected_rows
rollback_sql_path
execute_command_candidate
N3 不自动 rebuild
N4/N5/N6 不自动重放
```

安全状态：

```text
confirm_result=WAIT_MANUAL_CONFIRM
execute_authorized=false
writes_performed=false
database_written=false
```

## Gate Metadata Proof

Gate artifact 必须包含并已实现：

```text
policy_path=configs/n2_policy/default_policy_draft.json
policy_version
policy_hash
previous_policy_hash
policy_diff_summary
scope_delta_summary
expected_rows
rollback_sql_path
execute_command_candidate
execute_authorized=false
writes_performed=false
database_written=false
n3_rebuild_required=true
n3_lineage_auto_switch=false
forbidden_scopes
```

## Daily Runner Policy Proof

只读审计结果：

```text
audit_result=PASS
runner_path=scripts/run_condition_layer_execute.py
runner_uses_default_policy_draft_when_policy_missing=true
default_policy_path=configs/n2_policy/default_policy_draft.json
default_policy_hash=ded5432ff4769260061449f15a2edcc18e4ea3fe3874e26b42287ca1953cb576
default_policy_version=v4
scheduler_registry_policy_override_detected=false
```

## Forbidden Scope Proof

```text
N2 overwrite executed=false
condition tables written=false
registry command executed=false
rollback SQL executed=false
N3/N4/N5/N6 entered=false
market data pulled=false
worker started=false
outbox/inbox/checkpoint touched=false
old system touched=false
```

## Validation

```text
python3 -m compileall scripts/run_condition_layer_execute.py scripts/plan_condition_execute_contract.py scripts/plan_condition_execute_preflight.py src/ashare_v3/condition/web_policy.py src/ashare_v3/web/n2_policy_console.py tests/test_n2_web_policy.py
PASS

PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n2_web_policy.py'
37 OK

PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_condition_full_dry_run_policy_alignment.py'
5 OK

PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_condition*.py'
269 OK

PYTHONPATH=src python3 -m unittest discover -s tests
1641 OK
```

## Remaining Blockers

```text
none
```

## Next Gate

```text
allow_enter_N2_WEB_POLICY_EXECUTE_FINAL_GATE_REVIEW=true
```
