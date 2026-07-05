# N2 level score canonical alignment report

status: DRY_RUN_PASS_PREFLIGHT_BLOCKED_BY_031_SCHEMA

source_trade_date / for_trade_date / prev_trade_date: 20260529 / 20260601 / 20260529

## Row counts

- condition_basis: {'stock': 5506, 'index': 83, 'board': 428}
- condition_pool: {'stock': 4106, 'index': 21, 'board': 284}
- minute_target_scope: {'stock': 4106, 'index': 21, 'board': 284}
- condition_display_basis: {'stock': 1871, 'index': 9, 'board': 127}

## Golden level scores

- 000543 皖能电力: level_up_score=3124, level_down_score=0, transitions={'Y': 'volume_up', 'Q': 'volume_up', 'M': 'volume_up', 'W': 'volume_up', 'D': 'volume_up'}
- 000600 建投能源: level_up_score=3124, level_down_score=0, transitions={'Y': 'volume_up', 'Q': 'volume_up', 'M': 'volume_up', 'W': 'volume_up', 'D': 'volume_up'}
- 300327 中颖电子: level_up_score=2999, level_down_score=125, transitions={'Y': 'volume_up', 'Q': 'low_volume_up', 'M': 'volume_up', 'W': 'volume_up', 'D': 'volume_up'}

## Preflight

- execute_allowed=False
- blocked_reasons=['active_run_exists', 'schema_not_migrated', 'user_confirmation_required']
- schema_ready=False
- level_score_fields_ready=False

## Boundary

- writes_performed=false
- will_execute_sql=false
- no N3/N4/N5/N6
- 031 migration required before execute
