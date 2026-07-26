-- N6 shared-signal source and buyer-identity split.
-- REVIEWED MIGRATION: execute only through a separately authorized N6 gate.
-- Rewrites one scope helper and changes no business rows or table schemas.

BEGIN;

DO $preflight$
DECLARE
  function_oid oid;
  shared_relation_oid oid;
  function_proc record;
  actual_sha text;
  unexpected_execute boolean;
  shared_owner_name text;
  shared_constraint_count integer;
  shared_status_constraint_count integer;
  shared_trigger_count integer;
  unexpected_shared_privilege boolean;
  required_column_count integer;
BEGIN
  function_oid := pg_catalog.to_regprocedure(
    'public.n6_btrack_manual_signal_buy_current_scope('
    'bigint,text,bigint,bigint,bigint,text,text,numeric,text)'
  );
  shared_relation_oid := pg_catalog.to_regclass(
    'public.n6_ai_shared_signal_projection'
  );
  IF function_oid IS NULL OR shared_relation_oid IS NULL THEN
    RAISE EXCEPTION '076_required_dependency_missing';
  END IF;

  SELECT count(*)
    INTO required_column_count
  FROM pg_catalog.pg_attribute attribute
  WHERE attribute.attrelid = shared_relation_oid
    AND attribute.attnum > 0
    AND NOT attribute.attisdropped
    AND attribute.attname IN (
      'source_signal_projection_id',
      'user_projection_run_id',
      'source_event_id',
      'source_outbox_id',
      'source_action_event_id',
      'source_action_run_id',
      'for_trade_date',
      'asset_kind',
      'identity_key',
      'code',
      'name',
      'direction',
      'signal_type',
      'trigger_price',
      'action_price',
      'action_state',
      'action_mark',
      'shared_status'
    );
  IF required_column_count <> 18 THEN
    RAISE EXCEPTION '076_shared_projection_contract_drift';
  END IF;

  SELECT relation_owner.rolname
    INTO shared_owner_name
  FROM pg_catalog.pg_class relation
  JOIN pg_catalog.pg_roles relation_owner
    ON relation_owner.oid = relation.relowner
  WHERE relation.oid = shared_relation_oid
    AND relation.relkind = 'r';
  IF shared_owner_name IS DISTINCT FROM current_user THEN
    RAISE EXCEPTION '076_shared_projection_owner_drift';
  END IF;

  SELECT count(*)
    INTO shared_constraint_count
  FROM pg_catalog.pg_constraint constraint_row
  WHERE constraint_row.conrelid = shared_relation_oid
    AND (
      (
        constraint_row.contype = 'p'
        AND constraint_row.conkey = ARRAY[(
          SELECT attribute.attnum
          FROM pg_catalog.pg_attribute attribute
          WHERE attribute.attrelid = shared_relation_oid
            AND attribute.attname = 'source_signal_projection_id'
            AND NOT attribute.attisdropped
        )]::smallint[]
      )
      OR (
        constraint_row.contype = 'f'
        AND constraint_row.confrelid =
            pg_catalog.to_regclass('public.user_signal_projection')
        AND constraint_row.conkey = ARRAY[(
          SELECT attribute.attnum
          FROM pg_catalog.pg_attribute attribute
          WHERE attribute.attrelid = shared_relation_oid
            AND attribute.attname = 'source_signal_projection_id'
            AND NOT attribute.attisdropped
        )]::smallint[]
      )
      OR (
        constraint_row.contype = 'f'
        AND constraint_row.confrelid =
            pg_catalog.to_regclass('public.user_projection_run')
        AND constraint_row.conkey = ARRAY[(
          SELECT attribute.attnum
          FROM pg_catalog.pg_attribute attribute
          WHERE attribute.attrelid = shared_relation_oid
            AND attribute.attname = 'user_projection_run_id'
            AND NOT attribute.attisdropped
        )]::smallint[]
      )
    );
  IF shared_constraint_count <> 3 THEN
    RAISE EXCEPTION '076_shared_projection_key_drift';
  END IF;

  SELECT count(*)
    INTO shared_status_constraint_count
  FROM pg_catalog.pg_constraint constraint_row
  WHERE constraint_row.conrelid = shared_relation_oid
    AND constraint_row.contype = 'c'
    AND pg_catalog.pg_get_constraintdef(constraint_row.oid)
          LIKE '%shared_status%'
    AND pg_catalog.pg_get_constraintdef(constraint_row.oid)
          LIKE '%active%'
    AND pg_catalog.pg_get_constraintdef(constraint_row.oid)
          LIKE '%superseded%'
    AND pg_catalog.pg_get_constraintdef(constraint_row.oid)
          LIKE '%rejected%';
  IF shared_status_constraint_count <> 1 THEN
    RAISE EXCEPTION '076_shared_projection_status_constraint_drift';
  END IF;

  SELECT count(*)
    INTO shared_trigger_count
  FROM pg_catalog.pg_trigger trigger_row
  WHERE trigger_row.tgrelid =
        pg_catalog.to_regclass('public.user_signal_projection')
    AND trigger_row.tgname =
        'trg_055_n6_ai_shared_signal_projection_capture'
    AND trigger_row.tgfoid = pg_catalog.to_regprocedure(
          'public.n6_ai_shared_signal_projection_capture()'
        )
    AND trigger_row.tgenabled = 'O'
    AND trigger_row.tgtype = 5
    AND NOT trigger_row.tgisinternal;
  IF shared_trigger_count <> 1 THEN
    RAISE EXCEPTION '076_shared_projection_capture_trigger_drift';
  END IF;

  SELECT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_class relation
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        relation.relacl,
        pg_catalog.acldefault('r', relation.relowner)
      )
    ) acl
    WHERE relation.oid = shared_relation_oid
      AND acl.grantee <> relation.relowner
  ) INTO unexpected_shared_privilege;
  IF unexpected_shared_privilege THEN
    RAISE EXCEPTION '076_shared_projection_acl_drift';
  END IF;

  SELECT function_row.prosrc,
         function_row.prosecdef,
         function_row.provolatile,
         function_row.proparallel,
         function_row.proconfig,
         function_owner.rolname AS owner_name
    INTO function_proc
  FROM pg_catalog.pg_proc function_row
  JOIN pg_catalog.pg_roles function_owner
    ON function_owner.oid = function_row.proowner
  WHERE function_row.oid = function_oid;

  actual_sha := pg_catalog.encode(
    pg_catalog.sha256(
      pg_catalog.convert_to(function_proc.prosrc, 'UTF8')
    ),
    'hex'
  );
  IF function_proc.owner_name <> current_user
     OR function_proc.prosecdef IS DISTINCT FROM true
     OR function_proc.provolatile <> 'v'
     OR function_proc.proparallel <> 'u'
     OR function_proc.proconfig IS DISTINCT FROM
        ARRAY['search_path=pg_catalog']::text[]
     OR actual_sha <>
        'a12ae3e8e8040ecb7459d08c69d263feb578b10b86d150fdb11488f6b7779d49' THEN
    RAISE EXCEPTION '076_baseline_definition_drift';
  END IF;

  SELECT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_proc target
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        target.proacl,
        pg_catalog.acldefault('f', target.proowner)
      )
    ) acl
    WHERE target.oid = function_oid
      AND acl.privilege_type = 'EXECUTE'
      AND acl.grantee <> target.proowner
  ) INTO unexpected_execute;
  IF unexpected_execute THEN
    RAISE EXCEPTION '076_baseline_acl_drift';
  END IF;
END
$preflight$;

DO $caller_preflight$
DECLARE
  expected record;
  function_oid oid;
  function_proc record;
  actual_sha text;
  expected_role_oid oid;
  expected_execute boolean;
  unexpected_execute boolean;
BEGIN
  FOR expected IN
    SELECT *
    FROM (VALUES
      (
        'public.n6_btrack_proposal_create(text,text,bigint)',
        '6c43e9c2426867d8d31d0827de83147893395ae923bb1b1bf83ea4b81654fd10',
        'n6_btrack_web'
      ),
      (
        'public.n6_executor_claim_proposal(bigint,text)',
        '3ba1cc351e64e8ae6aebafdb33f577f4cc7bd2a97d46c31203893994503f75cf',
        'n6_virtual_executor'
      ),
      (
        'public.n6_executor_claim_next_proposal(text)',
        '1a4e1ad18a987cf5fe5c89135fc064970f54c443ffe5674b8449054696232c3f',
        'n6_virtual_executor'
      )
    ) AS expected_functions(signature, source_sha, execute_role)
  LOOP
    function_oid := pg_catalog.to_regprocedure(expected.signature);
    expected_role_oid := CASE
      WHEN expected.execute_role IS NULL THEN NULL
      ELSE pg_catalog.to_regrole(expected.execute_role)
    END;
    IF function_oid IS NULL
       OR (
         expected.execute_role IS NOT NULL
         AND expected_role_oid IS NULL
       ) THEN
      RAISE EXCEPTION '076_required_caller_missing: %',
        expected.signature;
    END IF;
    SELECT function_row.prosrc,
           function_row.prosecdef,
           function_row.provolatile,
           function_row.proparallel,
           function_row.proconfig,
           function_owner.rolname AS owner_name
      INTO function_proc
    FROM pg_catalog.pg_proc function_row
    JOIN pg_catalog.pg_roles function_owner
      ON function_owner.oid = function_row.proowner
    WHERE function_row.oid = function_oid;
    actual_sha := pg_catalog.encode(
      pg_catalog.sha256(
        pg_catalog.convert_to(function_proc.prosrc, 'UTF8')
      ),
      'hex'
    );
    IF function_proc.owner_name <> current_user
       OR function_proc.prosecdef IS DISTINCT FROM true
       OR function_proc.provolatile <> 'v'
       OR function_proc.proparallel <> 'u'
       OR function_proc.proconfig IS DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
       OR actual_sha <> expected.source_sha THEN
      RAISE EXCEPTION '076_caller_definition_drift: %',
        expected.signature;
    END IF;

    IF expected_role_oid IS NULL THEN
      expected_execute := true;
    ELSE
      SELECT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc target
        CROSS JOIN LATERAL pg_catalog.aclexplode(
          COALESCE(
            target.proacl,
            pg_catalog.acldefault('f', target.proowner)
          )
        ) acl
        WHERE target.oid = function_oid
          AND acl.grantee = expected_role_oid
          AND acl.privilege_type = 'EXECUTE'
      ) INTO expected_execute;
    END IF;
    SELECT EXISTS (
      SELECT 1
      FROM pg_catalog.pg_proc target
      CROSS JOIN LATERAL pg_catalog.aclexplode(
        COALESCE(
          target.proacl,
          pg_catalog.acldefault('f', target.proowner)
        )
      ) acl
      WHERE target.oid = function_oid
        AND acl.privilege_type = 'EXECUTE'
        AND acl.grantee <> target.proowner
        AND (
          expected_role_oid IS NULL
          OR acl.grantee <> expected_role_oid
        )
    ) INTO unexpected_execute;
    IF expected_execute IS DISTINCT FROM true
       OR unexpected_execute THEN
      RAISE EXCEPTION '076_caller_acl_drift: %',
        expected.signature;
    END IF;
  END LOOP;
END
$caller_preflight$;

DO $rewrite$
DECLARE
  source_text text;
  old_text text;
  new_text text;
  occurrence_count integer;
BEGIN
  SELECT function_row.prosrc
    INTO source_text
  FROM pg_catalog.pg_proc function_row
  WHERE function_row.oid =
        'public.n6_btrack_manual_signal_buy_current_scope('
        'bigint,text,bigint,bigint,bigint,text,text,numeric,text)'
        ::regprocedure;

  old_text := $buyer_owned_projection_065$      AND projection.user_id = p_user_id
$buyer_owned_projection_065$;
  new_text := $shared_source_buyer_split_076$      AND EXISTS (
        SELECT 1
        FROM public.n6_ai_shared_signal_projection shared
        WHERE shared.source_signal_projection_id =
              projection.user_signal_projection_id
          AND shared.user_projection_run_id =
              projection.user_projection_run_id
          AND shared.source_event_id = projection.source_event_id
          AND shared.source_outbox_id IS NOT DISTINCT FROM
              projection.source_outbox_id
          AND shared.source_action_event_id =
              projection.source_action_event_id
          AND shared.source_action_run_id =
              projection.source_action_run_id
          AND shared.for_trade_date =
              pg_catalog.to_date(current_trade_date, 'YYYYMMDD')
          AND pg_catalog.to_char(
                shared.for_trade_date, 'YYYYMMDD'
              ) = COALESCE(
                projection.display_payload_json->>'for_trade_date',
                projection.source_payload_json->>'trade_date'
              )
          AND shared.asset_kind = projection.asset_kind
          AND shared.identity_key = projection.identity_key
          AND shared.code = projection.code
          AND shared.name = projection.name
          AND shared.direction = projection.direction
          AND shared.signal_type = projection.signal_type
          AND shared.action_state = projection.action_state
          AND shared.action_state = COALESCE(
                card.card_payload_json->>'action_state',
                projection.display_payload_json->>'action_state'
              )
          AND shared.action_mark IS NOT DISTINCT FROM
              projection.action_mark
          AND projection_run.source_layer = 'N5_action'
          AND projection_run.status = 'passed'
          AND projection_run.quality_summary_json
                ->>'b_track_signal_projection' = 'passed'
          AND shared.trigger_price IS NOT DISTINCT FROM
              CASE
                WHEN projection.display_payload_json->>'trigger_price'
                       ~ '^[0-9]+([.][0-9]+)?$'
                  THEN (
                         projection.display_payload_json->>'trigger_price'
                       )::numeric
              END
          AND shared.trigger_price IS NOT DISTINCT FROM
              CASE
                WHEN COALESCE(
                       card.card_payload_json->>'trigger_price',
                       projection.display_payload_json->>'trigger_price'
                     ) ~ '^[0-9]+([.][0-9]+)?$'
                  THEN COALESCE(
                         card.card_payload_json->>'trigger_price',
                         projection.display_payload_json->>'trigger_price'
                       )::numeric
              END
          AND shared.action_price IS NOT DISTINCT FROM
              CASE
                WHEN projection.display_payload_json->>'action_price'
                       ~ '^[0-9]+([.][0-9]+)?$'
                  THEN (
                         projection.display_payload_json->>'action_price'
                       )::numeric
              END
          AND shared.action_price IS NOT DISTINCT FROM
              CASE
                WHEN COALESCE(
                       card.card_payload_json->>'action_price',
                       projection.display_payload_json->>'action_price'
                     ) ~ '^[0-9]+([.][0-9]+)?$'
                  THEN COALESCE(
                         card.card_payload_json->>'action_price',
                         projection.display_payload_json->>'action_price'
                       )::numeric
              END
          AND shared.shared_status = 'active'
      )
$shared_source_buyer_split_076$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '076_scope_rewrite_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);

  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION '
    'public.n6_btrack_manual_signal_buy_current_scope('
    'p_principal_id bigint,p_principal_type text,p_user_id bigint,'
    'p_virtual_account_id bigint,p_signal_projection_id bigint,'
    'p_identity_key text,p_signal_reference_kind text,'
    'p_signal_reference_price numeric,p_for_trade_date text) '
    'RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L',
    source_text
  );

  SELECT function_row.prosrc
    INTO source_text
  FROM pg_catalog.pg_proc function_row
  WHERE function_row.oid =
        'public.n6_btrack_proposal_create(text,text,bigint)'
        ::regprocedure;
  old_text := $create_owner_projection_075$        AND p.user_id = (authority->>'user_id')::bigint
$create_owner_projection_075$;
  new_text := $create_shared_signal_076$        AND (
          (
            p.direction = 'buy'
            AND authority->>'principal_type' IN (
                  'admin', 'human_user'
                )
            AND EXISTS (
              SELECT 1
              FROM public.n6_ai_shared_signal_projection shared
              WHERE shared.source_signal_projection_id =
                    p.user_signal_projection_id
                AND shared.shared_status = 'active'
            )
          )
          OR (
            p.direction = 'sell'
            AND p.user_id = (authority->>'user_id')::bigint
          )
        )
$create_shared_signal_076$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '076_create_source_rewrite_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);
  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION public.n6_btrack_proposal_create('
    'p_session_token_hash text,p_source_type text,p_source_id bigint) '
    'RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L',
    source_text
  );

  SELECT function_row.prosrc
    INTO source_text
  FROM pg_catalog.pg_proc function_row
  WHERE function_row.oid =
        'public.n6_executor_claim_proposal(bigint,text)'
        ::regprocedure;
  old_text := $explicit_claim_scope_075$WHERE proposal_id=p_proposal_id AND proposal_status='confirmed' AND public.n6_btrack_regular_trade_session_open() AND (expires_at>pg_catalog.now() OR (principal_type IN ('admin','human_user') AND user_id IS NOT NULL AND actor_ai_user_id IS NULL AND source_ai_decision_id IS NULL AND source_type='signal' AND proposal_side='buy' AND source_signal_projection_id IS NOT NULL AND source_virtual_position_id IS NULL AND public.n6_btrack_manual_signal_buy_current_scope(principal_id,principal_type,user_id,virtual_account_id,source_signal_projection_id,identity_key,signal_reference_kind,signal_reference_price,source_lineage_json->>'for_trade_date'))) RETURNING * INTO row_value;$explicit_claim_scope_075$;
  new_text := $explicit_claim_scope_076$WHERE proposal_id=p_proposal_id
    AND proposal_status='confirmed'
    AND public.n6_btrack_regular_trade_session_open()
    AND CASE
      WHEN principal_type IN ('admin','human_user')
       AND user_id IS NOT NULL
       AND actor_ai_user_id IS NULL
       AND source_ai_decision_id IS NULL
       AND source_type='signal'
       AND proposal_side='buy'
       AND source_signal_projection_id IS NOT NULL
       AND source_virtual_position_id IS NULL
        THEN public.n6_btrack_manual_signal_buy_current_scope(
          principal_id,principal_type,user_id,virtual_account_id,
          source_signal_projection_id,identity_key,
          signal_reference_kind,signal_reference_price,
          source_lineage_json->>'for_trade_date'
        )
      ELSE expires_at>pg_catalog.now()
    END
  RETURNING * INTO row_value;$explicit_claim_scope_076$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '076_explicit_claim_rewrite_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);
  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION public.n6_executor_claim_proposal('
    'p_proposal_id bigint,p_executor_run_id text) '
    'RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L',
    source_text
  );

  SELECT function_row.prosrc
    INTO source_text
  FROM pg_catalog.pg_proc function_row
  WHERE function_row.oid =
        'public.n6_executor_claim_next_proposal(text)'
        ::regprocedure;
  old_text := $claim_next_scope_075$      AND (
        p.expires_at > pg_catalog.now()
        OR (
          p.principal_type IN ('admin', 'human_user')
          AND p.user_id IS NOT NULL
          AND p.actor_ai_user_id IS NULL
          AND p.source_ai_decision_id IS NULL
          AND p.source_type = 'signal'
          AND p.proposal_side = 'buy'
          AND p.source_signal_projection_id IS NOT NULL
          AND p.source_virtual_position_id IS NULL
          AND public.n6_btrack_manual_signal_buy_current_scope(
            p.principal_id, p.principal_type, p.user_id,
            p.virtual_account_id, p.source_signal_projection_id,
            p.identity_key, p.signal_reference_kind,
            p.signal_reference_price,
            p.source_lineage_json->>'for_trade_date'
          )
        )
      )
$claim_next_scope_075$;
  new_text := $claim_next_scope_076$      AND CASE
        WHEN p.principal_type IN ('admin', 'human_user')
         AND p.user_id IS NOT NULL
         AND p.actor_ai_user_id IS NULL
         AND p.source_ai_decision_id IS NULL
         AND p.source_type = 'signal'
         AND p.proposal_side = 'buy'
         AND p.source_signal_projection_id IS NOT NULL
         AND p.source_virtual_position_id IS NULL
          THEN public.n6_btrack_manual_signal_buy_current_scope(
            p.principal_id, p.principal_type, p.user_id,
            p.virtual_account_id, p.source_signal_projection_id,
            p.identity_key, p.signal_reference_kind,
            p.signal_reference_price,
            p.source_lineage_json->>'for_trade_date'
          )
        ELSE p.expires_at > pg_catalog.now()
      END
$claim_next_scope_076$;
  occurrence_count := (
    pg_catalog.length(source_text)
    - pg_catalog.length(pg_catalog.replace(source_text, old_text, ''))
  ) / pg_catalog.length(old_text);
  IF occurrence_count <> 1 THEN
    RAISE EXCEPTION '076_claim_next_rewrite_mismatch';
  END IF;
  source_text := pg_catalog.replace(source_text, old_text, new_text);
  EXECUTE pg_catalog.format(
    'CREATE OR REPLACE FUNCTION public.n6_executor_claim_next_proposal('
    'p_executor_run_id text) '
    'RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER '
    'SET search_path=pg_catalog AS %L',
    source_text
  );
END
$rewrite$;

REVOKE ALL ON FUNCTION
  public.n6_btrack_manual_signal_buy_current_scope(
    bigint,text,bigint,bigint,bigint,text,text,numeric,text
  )
  FROM PUBLIC, n6_btrack_web, n6_virtual_executor, n6_ai_agent,
       n6_quote_writer;

REVOKE ALL ON FUNCTION public.n6_btrack_proposal_create(text,text,bigint)
  FROM PUBLIC, n6_virtual_executor, n6_ai_agent, n6_quote_writer;
GRANT EXECUTE ON FUNCTION
  public.n6_btrack_proposal_create(text,text,bigint)
  TO n6_btrack_web;

REVOKE ALL ON FUNCTION public.n6_executor_claim_proposal(bigint,text)
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer;
GRANT EXECUTE ON FUNCTION
  public.n6_executor_claim_proposal(bigint,text)
  TO n6_virtual_executor;

REVOKE ALL ON FUNCTION public.n6_executor_claim_next_proposal(text)
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer;
GRANT EXECUTE ON FUNCTION
  public.n6_executor_claim_next_proposal(text)
  TO n6_virtual_executor;

DO $postflight$
DECLARE
  function_oid oid;
  function_proc record;
  actual_sha text;
  unexpected_execute boolean;
BEGIN
  function_oid := pg_catalog.to_regprocedure(
    'public.n6_btrack_manual_signal_buy_current_scope('
    'bigint,text,bigint,bigint,bigint,text,text,numeric,text)'
  );
  SELECT function_row.prosrc,
         function_row.prosecdef,
         function_row.provolatile,
         function_row.proparallel,
         function_row.proconfig,
         function_owner.rolname AS owner_name
    INTO function_proc
  FROM pg_catalog.pg_proc function_row
  JOIN pg_catalog.pg_roles function_owner
    ON function_owner.oid = function_row.proowner
  WHERE function_row.oid = function_oid;
  actual_sha := pg_catalog.encode(
    pg_catalog.sha256(
      pg_catalog.convert_to(function_proc.prosrc, 'UTF8')
    ),
    'hex'
  );
  IF function_oid IS NULL
     OR function_proc.owner_name <> current_user
     OR function_proc.prosecdef IS DISTINCT FROM true
     OR function_proc.provolatile <> 'v'
     OR function_proc.proparallel <> 'u'
     OR function_proc.proconfig IS DISTINCT FROM
        ARRAY['search_path=pg_catalog']::text[]
     OR actual_sha <>
        'fa772cb72c1751060032552865350dc6f8dedcdc413bcab5a4e5e789600bcd3a' THEN
    RAISE EXCEPTION '076_postflight_definition_drift';
  END IF;

  SELECT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_proc target
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        target.proacl,
        pg_catalog.acldefault('f', target.proowner)
      )
    ) acl
    WHERE target.oid = function_oid
      AND acl.privilege_type = 'EXECUTE'
      AND acl.grantee <> target.proowner
  ) INTO unexpected_execute;
  IF unexpected_execute THEN
    RAISE EXCEPTION '076_postflight_acl_drift';
  END IF;
END
$postflight$;

DO $caller_postflight$
DECLARE
  expected record;
  function_oid oid;
  function_proc record;
  actual_sha text;
  expected_role_oid oid;
  expected_execute boolean;
  unexpected_execute boolean;
BEGIN
  FOR expected IN
    SELECT *
    FROM (VALUES
      (
        'public.n6_btrack_proposal_create(text,text,bigint)',
        'a8a87ee9e97fdd3b8f865f90947fc6caf593d81f23174b0351365f8f3897cbff',
        'n6_btrack_web'
      ),
      (
        'public.n6_executor_claim_proposal(bigint,text)',
        'f5e8fadd1b27576726e819cdc696324732b1930652590c9c13dd8151297bb5e3',
        'n6_virtual_executor'
      ),
      (
        'public.n6_executor_claim_next_proposal(text)',
        'f4bfb58c249441c5d4c4af72b163e22ce1f85edcc6abe634314b2c12805c78c6',
        'n6_virtual_executor'
      )
    ) AS expected_functions(signature, source_sha, execute_role)
  LOOP
    function_oid := pg_catalog.to_regprocedure(expected.signature);
    expected_role_oid := CASE
      WHEN expected.execute_role IS NULL THEN NULL
      ELSE pg_catalog.to_regrole(expected.execute_role)
    END;
    IF function_oid IS NULL
       OR (
         expected.execute_role IS NOT NULL
         AND expected_role_oid IS NULL
       ) THEN
      RAISE EXCEPTION '076_postflight_caller_missing: %',
        expected.signature;
    END IF;
    SELECT function_row.prosrc,
           function_row.prosecdef,
           function_row.provolatile,
           function_row.proparallel,
           function_row.proconfig,
           function_owner.rolname AS owner_name
      INTO function_proc
    FROM pg_catalog.pg_proc function_row
    JOIN pg_catalog.pg_roles function_owner
      ON function_owner.oid = function_row.proowner
    WHERE function_row.oid = function_oid;
    actual_sha := pg_catalog.encode(
      pg_catalog.sha256(
        pg_catalog.convert_to(function_proc.prosrc, 'UTF8')
      ),
      'hex'
    );
    IF function_proc.owner_name <> current_user
       OR function_proc.prosecdef IS DISTINCT FROM true
       OR function_proc.provolatile <> 'v'
       OR function_proc.proparallel <> 'u'
       OR function_proc.proconfig IS DISTINCT FROM
          ARRAY['search_path=pg_catalog']::text[]
       OR actual_sha <> expected.source_sha THEN
      RAISE EXCEPTION '076_postflight_caller_definition_drift: %',
        expected.signature;
    END IF;

    IF expected_role_oid IS NULL THEN
      expected_execute := true;
    ELSE
      SELECT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc target
        CROSS JOIN LATERAL pg_catalog.aclexplode(
          COALESCE(
            target.proacl,
            pg_catalog.acldefault('f', target.proowner)
          )
        ) acl
        WHERE target.oid = function_oid
          AND acl.grantee = expected_role_oid
          AND acl.privilege_type = 'EXECUTE'
      ) INTO expected_execute;
    END IF;
    SELECT EXISTS (
      SELECT 1
      FROM pg_catalog.pg_proc target
      CROSS JOIN LATERAL pg_catalog.aclexplode(
        COALESCE(
          target.proacl,
          pg_catalog.acldefault('f', target.proowner)
        )
      ) acl
      WHERE target.oid = function_oid
        AND acl.privilege_type = 'EXECUTE'
        AND acl.grantee <> target.proowner
        AND (
          expected_role_oid IS NULL
          OR acl.grantee <> expected_role_oid
        )
    ) INTO unexpected_execute;
    IF expected_execute IS DISTINCT FROM true
       OR unexpected_execute THEN
      RAISE EXCEPTION '076_postflight_caller_acl_drift: %',
        expected.signature;
    END IF;
  END LOOP;
END
$caller_postflight$;

COMMIT;
