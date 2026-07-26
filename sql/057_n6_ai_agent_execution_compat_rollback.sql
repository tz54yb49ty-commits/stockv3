-- Roll back only N6 AI Agent v1 execution compatibility functions.
-- Preserve 041-056 schema, roles, credentials, AI decisions, and all account history.

BEGIN;

DO $preflight$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM public.n6_virtual_trade_proposal proposal
    WHERE proposal.principal_type = 'ai_user'
      AND proposal.proposal_status IN ('pending', 'confirmed', 'processing')
  ) THEN
    RAISE EXCEPTION '057 rollback blocked: active AI proposal exists';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.n6_virtual_position position
    WHERE position.principal_type = 'ai_user'
      AND position.position_status = 'open_virtual'
      AND position.quantity > 0
  ) THEN
    RAISE EXCEPTION '057 rollback blocked: open AI position requires stop protection';
  END IF;
END
$preflight$;

CREATE OR REPLACE FUNCTION public.n6_quote_writer_scope(
  p_quote_minute timestamptz
)
RETURNS TABLE (
  principal_id bigint,
  principal_type text,
  virtual_account_id bigint,
  identity_key text
)
LANGUAGE sql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
  WITH active_account AS (
    SELECT a.virtual_account_id, a.principal_id, a.principal_type,
           principal.owner_user_id
    FROM public.n6_virtual_account a
    JOIN public.n6_principal principal
      ON principal.principal_id = a.principal_id
     AND principal.principal_type = a.principal_type
     AND principal.principal_status = 'active'
    WHERE a.virtual_account_status = 'active'
      AND a.principal_type IN ('admin', 'human_user')
  ), candidate AS (
    SELECT a.principal_id, a.principal_type, a.virtual_account_id,
           position.identity_key
    FROM active_account a
    JOIN public.n6_virtual_position position
      ON position.virtual_account_id = a.virtual_account_id
     AND position.principal_id = a.principal_id
     AND position.principal_type = a.principal_type
    WHERE position.asset_kind = 'stock'
      AND position.position_status = 'open_virtual'
      AND position.quantity > 0
      AND position.identity_key ~ '^stock:(SH|SZ|BJ):[0-9]{6}$'

    UNION

    SELECT a.principal_id, a.principal_type, a.virtual_account_id,
           proposal.identity_key
    FROM active_account a
    JOIN public.n6_virtual_trade_proposal proposal
      ON proposal.virtual_account_id = a.virtual_account_id
     AND proposal.principal_id = a.principal_id
     AND proposal.principal_type = a.principal_type
     AND proposal.user_id = a.owner_user_id
    JOIN public.user_signal_projection source
      ON source.user_signal_projection_id =
           proposal.source_signal_projection_id
     AND source.user_id = proposal.user_id
     AND source.asset_kind = proposal.asset_kind
     AND source.identity_key = proposal.identity_key
     AND source.direction = proposal.proposal_side
    WHERE proposal.asset_kind = 'stock'
      AND proposal.proposal_side = 'buy'
      AND proposal.source_type = 'signal'
      AND proposal.source_id =
            proposal.source_signal_projection_id::text
      AND proposal.source_virtual_position_id IS NULL
      AND proposal.proposal_status IN ('pending', 'confirmed')
      AND proposal.expires_at > pg_catalog.clock_timestamp()
      AND proposal.identity_key ~ '^stock:(SH|SZ|BJ):[0-9]{6}$'
  )
  SELECT candidate.principal_id, candidate.principal_type,
         candidate.virtual_account_id, candidate.identity_key
  FROM candidate
  WHERE p_quote_minute IS NOT NULL
    AND pg_catalog.date_trunc('minute', p_quote_minute) = p_quote_minute
    AND p_quote_minute = (
      pg_catalog.date_trunc(
        'minute',
        pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai'
      ) AT TIME ZONE 'Asia/Shanghai'
    )
    AND (p_quote_minute AT TIME ZONE 'Asia/Shanghai')::date =
          (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date
    AND (
      (p_quote_minute AT TIME ZONE 'Asia/Shanghai')::time
        BETWEEN time '09:30' AND time '11:30'
      OR
      (p_quote_minute AT TIME ZONE 'Asia/Shanghai')::time
        BETWEEN time '13:00' AND time '15:00'
    )
    AND EXISTS (
      SELECT 1
      FROM public.common_trade_calendar calendar
      WHERE calendar.trade_date = pg_catalog.to_char(
              p_quote_minute AT TIME ZONE 'Asia/Shanghai', 'YYYYMMDD'
            )
        AND calendar.is_open = true
    )
$function$;

CREATE OR REPLACE FUNCTION public.n6_quote_writer_save_run(
  p_principal_id bigint,
  p_principal_type text,
  p_quote_minute timestamptz,
  p_run_status text,
  p_scoped_identity_count integer,
  p_passed_count integer,
  p_not_ready_count integer,
  p_started_at timestamptz,
  p_completed_at timestamptz,
  p_scope_identity_keys jsonb,
  p_batches jsonb
)
RETURNS integer
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  target_run_id bigint;
  inserted_count integer := 0;
  payload_count integer := 0;
  payload_passed_count integer := 0;
  payload_not_ready_count integer := 0;
  batch_value jsonb;
  item_value jsonb;
  batch_item_count integer;
  batch_passed_count integer;
  batch_requested_at timestamptz;
  batch_completed_at timestamptz;
BEGIN
  IF p_principal_id IS NULL
     OR p_principal_id <= 0
     OR p_principal_type NOT IN ('admin', 'human_user')
     OR p_quote_minute IS NULL
     OR pg_catalog.date_trunc('minute', p_quote_minute) <> p_quote_minute
     OR p_quote_minute <> (
       pg_catalog.date_trunc(
         'minute',
         pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai'
       ) AT TIME ZONE 'Asia/Shanghai'
     )
     OR (p_quote_minute AT TIME ZONE 'Asia/Shanghai')::date <>
          (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date
     OR NOT (
       (p_quote_minute AT TIME ZONE 'Asia/Shanghai')::time
         BETWEEN time '09:30' AND time '11:30'
       OR
       (p_quote_minute AT TIME ZONE 'Asia/Shanghai')::time
         BETWEEN time '13:00' AND time '15:00'
     )
     OR NOT EXISTS (
       SELECT 1
       FROM public.common_trade_calendar calendar
       WHERE calendar.trade_date = pg_catalog.to_char(
               p_quote_minute AT TIME ZONE 'Asia/Shanghai', 'YYYYMMDD'
             )
         AND calendar.is_open = true
     )
     OR p_run_status IS NULL
     OR p_run_status NOT IN ('passed', 'partial', 'failed')
     OR p_scoped_identity_count IS NULL
     OR p_scoped_identity_count <= 0
     OR p_passed_count IS NULL
     OR p_passed_count < 0
     OR p_not_ready_count IS NULL
     OR p_not_ready_count < 0
     OR p_scoped_identity_count <> p_passed_count + p_not_ready_count
     OR p_started_at IS NULL
     OR p_completed_at IS NULL
     OR p_started_at < p_quote_minute
     OR p_started_at >= p_quote_minute + interval '60 seconds'
     OR p_completed_at < p_started_at
     OR p_completed_at >= p_quote_minute + interval '75 seconds'
     OR p_started_at < pg_catalog.clock_timestamp() - interval '75 seconds'
     OR p_completed_at > pg_catalog.clock_timestamp() + interval '5 seconds'
     OR pg_catalog.jsonb_typeof(p_scope_identity_keys) <> 'array'
     OR pg_catalog.jsonb_typeof(p_batches) <> 'array' THEN
    RAISE EXCEPTION '051 invalid quote-writer payload';
  END IF;

  IF (
    SELECT count(*)
    FROM pg_catalog.jsonb_array_elements(p_scope_identity_keys) scope(value)
    WHERE pg_catalog.jsonb_typeof(scope.value) <> 'string'
       OR scope.value #>> '{}' !~ '^stock:(SH|SZ|BJ):[0-9]{6}$'
  ) <> 0
     OR (
       SELECT count(*) FROM pg_catalog.jsonb_array_elements(p_scope_identity_keys)
     ) <> p_scoped_identity_count
     OR (
       SELECT count(DISTINCT (value #>> '{}'))
       FROM pg_catalog.jsonb_array_elements(p_scope_identity_keys)
     ) <> p_scoped_identity_count THEN
    RAISE EXCEPTION '051 invalid scope identity payload';
  END IF;

  FOR batch_value IN
    SELECT value FROM pg_catalog.jsonb_array_elements(p_batches)
  LOOP
    IF pg_catalog.jsonb_typeof(batch_value) <> 'object'
       OR (SELECT count(*) FROM pg_catalog.jsonb_object_keys(batch_value)) <> 10
       OR NOT batch_value ?& ARRAY[
         'contract_version', 'batch_id', 'source_adapter', 'source_version',
         'source_time_semantics', 'requested_at', 'completed_at',
         'batch_status', 'item_count', 'items'
       ]
       OR EXISTS (
         SELECT 1 FROM pg_catalog.jsonb_each(batch_value) field(key, value)
         WHERE (
           field.key IN (
             'contract_version', 'batch_id', 'source_adapter',
             'source_version', 'source_time_semantics', 'requested_at',
             'completed_at', 'batch_status'
           ) AND pg_catalog.jsonb_typeof(field.value) <> 'string'
         ) OR (
           field.key = 'item_count'
           AND pg_catalog.jsonb_typeof(field.value) <> 'number'
         )
       )
       OR batch_value->>'contract_version' <> '1.0.0'
       OR batch_value->>'source_adapter' <> 'mootdx.std'
       OR batch_value->>'source_time_semantics' <>
            'provider_intraday_time_without_trade_date'
       OR COALESCE(batch_value->>'source_version', '') = ''
       OR batch_value->>'batch_id' !~
            '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
       OR batch_value->>'batch_status' NOT IN ('passed', 'partial', 'failed')
       OR batch_value->>'item_count' !~ '^[1-9][0-9]*$'
       OR (batch_value->>'item_count')::integer > 80
       OR pg_catalog.jsonb_typeof(batch_value->'items') <> 'array' THEN
      RAISE EXCEPTION '051 malformed quote batch';
    END IF;

    batch_requested_at := (batch_value->>'requested_at')::timestamptz;
    batch_completed_at := (batch_value->>'completed_at')::timestamptz;
    IF batch_requested_at IS NULL
       OR batch_completed_at IS NULL
       OR batch_requested_at < p_quote_minute
       OR batch_completed_at < batch_requested_at
       OR batch_completed_at > p_completed_at THEN
      RAISE EXCEPTION '051 invalid quote batch time';
    END IF;

    batch_item_count := 0;
    batch_passed_count := 0;
    FOR item_value IN
      SELECT value
      FROM pg_catalog.jsonb_array_elements(batch_value->'items')
    LOOP
      IF pg_catalog.jsonb_typeof(item_value) <> 'object'
         OR (SELECT count(*) FROM pg_catalog.jsonb_object_keys(item_value)) <> 13
         OR NOT item_value ?& ARRAY[
           'identity_key', 'exchange', 'market', 'stock_code',
           'current_price', 'last_close', 'day_open', 'day_high', 'day_low',
           'source_time_text', 'fetched_at', 'quality_status', 'quality_reason'
         ]
         OR EXISTS (
           SELECT 1 FROM pg_catalog.jsonb_each(item_value) field(key, value)
           WHERE (
             field.key IN (
               'identity_key', 'exchange', 'stock_code', 'fetched_at',
               'quality_status', 'quality_reason'
             ) AND pg_catalog.jsonb_typeof(field.value) <> 'string'
           ) OR (
             field.key IN (
               'current_price', 'last_close', 'day_open', 'day_high',
               'day_low', 'source_time_text'
             ) AND pg_catalog.jsonb_typeof(field.value) NOT IN ('string', 'null')
           ) OR (
             field.key = 'market'
             AND pg_catalog.jsonb_typeof(field.value) NOT IN ('number', 'null')
           )
         )
         OR item_value->>'identity_key' !~ '^stock:(SH|SZ|BJ):[0-9]{6}$'
         OR item_value->>'exchange' NOT IN ('SH', 'SZ', 'BJ')
         OR item_value->>'stock_code' !~ '^[0-9]{6}$'
         OR pg_catalog.split_part(item_value->>'identity_key', ':', 2) <>
              item_value->>'exchange'
         OR pg_catalog.split_part(item_value->>'identity_key', ':', 3) <>
              item_value->>'stock_code'
         OR item_value->>'quality_status' NOT IN ('passed', 'not_ready')
         OR item_value->>'quality_reason' NOT IN (
              'ok', 'missing', 'identity_mismatch', 'invalid_price',
              'invalid_source_time', 'provider_error', 'unsupported_exchange'
            ) THEN
        RAISE EXCEPTION '051 malformed quote item';
      END IF;

      IF item_value->>'quality_status' = 'passed' THEN
        IF item_value->>'quality_reason' <> 'ok'
           OR item_value->>'exchange' = 'BJ'
           OR item_value->>'market' !~ '^[01]$'
           OR (item_value->>'exchange' = 'SH' AND item_value->>'market' <> '1')
           OR (item_value->>'exchange' = 'SZ' AND item_value->>'market' <> '0')
           OR item_value->>'current_price' !~ '^[0-9]+([.][0-9]+)?$'
           OR (item_value->>'current_price')::numeric <= 0
           OR item_value->>'day_low' !~ '^[0-9]+([.][0-9]+)?$'
           OR (item_value->>'day_low')::numeric <= 0
           OR COALESCE(item_value->>'source_time_text', '') !~
                '^(?:[01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9](?:[.][0-9]+)?)?$'
           OR EXISTS (
             SELECT 1
             FROM pg_catalog.jsonb_each(item_value) price(key, value)
             WHERE price.key IN ('last_close', 'day_open', 'day_high')
               AND price.value <> 'null'::jsonb
               AND (
                 price.value #>> '{}' !~ '^-?[0-9]+([.][0-9]+)?$'
               )
           ) THEN
          RAISE EXCEPTION '051 invalid passed quote item';
        END IF;
        batch_passed_count := batch_passed_count + 1;
        payload_passed_count := payload_passed_count + 1;
      ELSE
        IF item_value->>'quality_reason' = 'ok'
           OR EXISTS (
             SELECT 1
             FROM pg_catalog.jsonb_each(item_value) nullable(key, value)
             WHERE nullable.key IN (
               'current_price', 'last_close', 'day_open', 'day_high',
               'day_low', 'source_time_text'
             )
               AND nullable.value <> 'null'::jsonb
           ) THEN
          RAISE EXCEPTION '051 invalid not-ready quote item';
        END IF;
        payload_not_ready_count := payload_not_ready_count + 1;
      END IF;

      IF (item_value->>'fetched_at')::timestamptz IS NULL
         OR (item_value->>'fetched_at')::timestamptz < batch_requested_at
         OR (item_value->>'fetched_at')::timestamptz > batch_completed_at THEN
        RAISE EXCEPTION '051 invalid item fetched_at';
      END IF;
      batch_item_count := batch_item_count + 1;
      payload_count := payload_count + 1;
    END LOOP;

    IF batch_item_count <> (batch_value->>'item_count')::integer
       OR (batch_passed_count = batch_item_count
           AND batch_value->>'batch_status' <> 'passed')
       OR (batch_passed_count = 0
           AND batch_value->>'batch_status' <> 'failed')
       OR (batch_passed_count > 0 AND batch_passed_count < batch_item_count
           AND batch_value->>'batch_status' <> 'partial') THEN
      RAISE EXCEPTION '051 quote batch count/status mismatch';
    END IF;
  END LOOP;

  IF payload_count <> p_scoped_identity_count
     OR payload_passed_count <> p_passed_count
     OR payload_not_ready_count <> p_not_ready_count
     OR (payload_passed_count = payload_count
         AND p_run_status <> 'passed')
     OR (payload_passed_count = 0
         AND p_run_status <> 'failed')
     OR (payload_passed_count > 0 AND payload_not_ready_count > 0
         AND p_run_status <> 'partial')
     OR (
       SELECT count(DISTINCT item.value->>'identity_key')
       FROM pg_catalog.jsonb_array_elements(p_batches) batch(value)
       CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(
         batch.value->'items'
       ) item(value)
     ) <> payload_count THEN
    RAISE EXCEPTION '051 quote payload aggregate mismatch';
  END IF;

  IF EXISTS (
    (
      SELECT value #>> '{}' AS identity_key
      FROM pg_catalog.jsonb_array_elements(p_scope_identity_keys)
      EXCEPT
      SELECT item.value->>'identity_key'
      FROM pg_catalog.jsonb_array_elements(p_batches) batch(value)
      CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(
        batch.value->'items'
      ) item(value)
    )
    UNION ALL
    (
      SELECT item.value->>'identity_key'
      FROM pg_catalog.jsonb_array_elements(p_batches) batch(value)
      CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(
        batch.value->'items'
      ) item(value)
      EXCEPT
      SELECT value #>> '{}' AS identity_key
      FROM pg_catalog.jsonb_array_elements(p_scope_identity_keys)
    )
  ) THEN
    RAISE EXCEPTION '051 scope and batch identity sets differ';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_catalog.jsonb_array_elements(p_batches) batch(value)
    CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(
      batch.value->'items'
    ) item(value)
    WHERE NOT EXISTS (
      SELECT 1
      FROM public.n6_quote_writer_scope(p_quote_minute) allowed
      WHERE allowed.principal_id = p_principal_id
        AND allowed.principal_type = p_principal_type
        AND allowed.identity_key = item.value->>'identity_key'
    )
  ) THEN
    RAISE EXCEPTION '051 quote payload outside authorized scope';
  END IF;

  INSERT INTO public.n6_virtual_quote_run (
    principal_id, quote_minute, run_status, scoped_identity_count,
    passed_count, not_ready_count, inserted_snapshot_count,
    started_at, completed_at
  ) VALUES (
    p_principal_id, p_quote_minute, p_run_status, p_scoped_identity_count,
    p_passed_count, p_not_ready_count, 0, p_started_at, p_completed_at
  )
  ON CONFLICT (principal_id, quote_minute) DO NOTHING
  RETURNING quote_run_id INTO target_run_id;

  IF target_run_id IS NULL THEN
    SELECT run.quote_run_id INTO STRICT target_run_id
    FROM public.n6_virtual_quote_run run
    WHERE run.principal_id = p_principal_id
      AND run.quote_minute = p_quote_minute
    FOR UPDATE;
  END IF;

  WITH flattened AS (
    SELECT batch.value AS batch, item.value AS item
    FROM pg_catalog.jsonb_array_elements(p_batches) batch(value)
    CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(
      batch.value->'items'
    ) item(value)
  )
  INSERT INTO public.n6_virtual_quote_snapshot (
    identity_key, exchange, stock_code, quote_minute, provider_batch_id,
    provider_contract_version, source_adapter, source_version,
    source_time_semantics, requested_at, completed_at, batch_status,
    market, current_price, last_close, day_open, day_high, day_low,
    source_time_text, fetched_at, quality_status, quality_reason
  )
  SELECT item->>'identity_key', item->>'exchange', item->>'stock_code',
         p_quote_minute, (batch->>'batch_id')::uuid,
         batch->>'contract_version',
         batch->>'source_adapter', batch->>'source_version',
         batch->>'source_time_semantics',
         (batch->>'requested_at')::timestamptz,
         (batch->>'completed_at')::timestamptz, batch->>'batch_status',
         NULLIF(item->>'market', '')::integer,
         NULLIF(item->>'current_price', '')::numeric,
         NULLIF(item->>'last_close', '')::numeric,
         NULLIF(item->>'day_open', '')::numeric,
         NULLIF(item->>'day_high', '')::numeric,
         NULLIF(item->>'day_low', '')::numeric,
         NULLIF(item->>'source_time_text', ''),
         (item->>'fetched_at')::timestamptz,
         item->>'quality_status', item->>'quality_reason'
  FROM flattened
  ON CONFLICT (identity_key, quote_minute) DO NOTHING;
  GET DIAGNOSTICS inserted_count = ROW_COUNT;

  IF EXISTS (
    WITH flattened AS (
      SELECT batch.value AS batch, item.value AS item
      FROM pg_catalog.jsonb_array_elements(p_batches) batch(value)
      CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(
        batch.value->'items'
      ) item(value)
    )
    SELECT 1
    FROM flattened
    LEFT JOIN public.n6_virtual_quote_snapshot snapshot
      ON snapshot.identity_key = flattened.item->>'identity_key'
     AND snapshot.quote_minute = p_quote_minute
    WHERE snapshot.virtual_quote_snapshot_id IS NULL
       OR snapshot.exchange IS DISTINCT FROM flattened.item->>'exchange'
       OR snapshot.stock_code IS DISTINCT FROM flattened.item->>'stock_code'
       OR snapshot.provider_batch_id IS DISTINCT FROM
            (flattened.batch->>'batch_id')::uuid
       OR snapshot.provider_contract_version IS DISTINCT FROM
            flattened.batch->>'contract_version'
       OR snapshot.source_adapter IS DISTINCT FROM
            flattened.batch->>'source_adapter'
       OR snapshot.source_version IS DISTINCT FROM
            flattened.batch->>'source_version'
       OR snapshot.source_time_semantics IS DISTINCT FROM
            flattened.batch->>'source_time_semantics'
       OR snapshot.requested_at IS DISTINCT FROM
            (flattened.batch->>'requested_at')::timestamptz
       OR snapshot.completed_at IS DISTINCT FROM
            (flattened.batch->>'completed_at')::timestamptz
       OR snapshot.batch_status IS DISTINCT FROM
            flattened.batch->>'batch_status'
       OR snapshot.market IS DISTINCT FROM
            NULLIF(flattened.item->>'market', '')::integer
       OR snapshot.current_price IS DISTINCT FROM
            NULLIF(flattened.item->>'current_price', '')::numeric
       OR snapshot.last_close IS DISTINCT FROM
            NULLIF(flattened.item->>'last_close', '')::numeric
       OR snapshot.day_open IS DISTINCT FROM
            NULLIF(flattened.item->>'day_open', '')::numeric
       OR snapshot.day_high IS DISTINCT FROM
            NULLIF(flattened.item->>'day_high', '')::numeric
       OR snapshot.day_low IS DISTINCT FROM
            NULLIF(flattened.item->>'day_low', '')::numeric
       OR snapshot.source_time_text IS DISTINCT FROM
            NULLIF(flattened.item->>'source_time_text', '')
       OR snapshot.fetched_at IS DISTINCT FROM
            (flattened.item->>'fetched_at')::timestamptz
       OR snapshot.quality_status IS DISTINCT FROM
            flattened.item->>'quality_status'
       OR snapshot.quality_reason IS DISTINCT FROM
            flattened.item->>'quality_reason'
  ) THEN
    RAISE EXCEPTION '051 existing quote snapshot conflicts with payload';
  END IF;

  WITH flattened AS (
    SELECT item.value AS item
    FROM pg_catalog.jsonb_array_elements(p_batches) batch(value)
    CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(
      batch.value->'items'
    ) item(value)
  )
  INSERT INTO public.n6_virtual_quote_run_identity (
    quote_run_id, virtual_quote_snapshot_id, identity_key,
    quality_status, quality_reason
  )
  SELECT target_run_id, snapshot.virtual_quote_snapshot_id,
         snapshot.identity_key, snapshot.quality_status,
         snapshot.quality_reason
  FROM flattened
  JOIN public.n6_virtual_quote_snapshot snapshot
    ON snapshot.identity_key = flattened.item->>'identity_key'
   AND snapshot.quote_minute = p_quote_minute
  ON CONFLICT (quote_run_id, identity_key) DO NOTHING;

  UPDATE public.n6_virtual_quote_run run
  SET scoped_identity_count = evidence.scoped_count,
      passed_count = evidence.passed_count,
      not_ready_count = evidence.scoped_count - evidence.passed_count,
      run_status = CASE
        WHEN evidence.scoped_count = 0 THEN 'no_scope'
        WHEN evidence.passed_count = evidence.scoped_count THEN 'passed'
        WHEN evidence.passed_count = 0 THEN 'failed'
        ELSE 'partial'
      END,
      inserted_snapshot_count =
        run.inserted_snapshot_count + inserted_count,
      started_at = LEAST(run.started_at, p_started_at),
      completed_at = GREATEST(run.completed_at, p_completed_at)
  FROM (
    SELECT count(*)::integer AS scoped_count,
           count(*) FILTER (
             WHERE quality_status = 'passed'
               AND quality_reason = 'ok'
           )::integer AS passed_count
    FROM public.n6_virtual_quote_run_identity
    WHERE quote_run_id = target_run_id
  ) evidence
  WHERE run.quote_run_id = target_run_id;

  RETURN inserted_count;
END
$function$;

CREATE OR REPLACE FUNCTION public.n6_executor_evaluate_next_stop_loss(
  p_executor_run_id text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  position_row public.n6_virtual_position%ROWTYPE;
  first_quote public.n6_virtual_quote_snapshot%ROWTYPE;
  confirm_quote public.n6_virtual_quote_snapshot%ROWTYPE;
  terminal_proposal public.n6_virtual_trade_proposal%ROWTYPE;
  owner_user_id bigint;
  current_trade_date date;
  current_trade_date_count integer;
  matured_quantity numeric(24,4);
  new_proposal_id bigint;
  source_key text;
  confirm_key text;
  rearmed boolean := false;
BEGIN
  IF p_executor_run_id IS NULL OR pg_catalog.btrim(p_executor_run_id) = ''
     OR pg_catalog.length(p_executor_run_id) > 200 THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'invalid_request');
  END IF;
  SELECT pg_catalog.to_date(pg_catalog.min(c.trade_date), 'YYYYMMDD'), count(*)
    INTO current_trade_date, current_trade_date_count
  FROM public.common_trade_calendar c
  WHERE c.trade_date = pg_catalog.to_char(
          pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai', 'YYYYMMDD'
        )
    AND c.is_open = true;
  IF current_trade_date_count <> 1
     OR NOT (
       (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::time
         BETWEEN time '09:30' AND time '11:30'
       OR (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::time
         BETWEEN time '13:00' AND time '15:00'
     ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true, 'status', 'not_ready', 'reason', 'open_trade_session_required'
    );
  END IF;

  SELECT p.* INTO position_row
  FROM public.n6_virtual_position p
  WHERE p.asset_kind = 'stock'
    AND p.identity_key ~ '^stock:(SH|SZ):[0-9]{6}$'
    AND p.position_status = 'open_virtual'
    AND p.quantity > 0
    AND p.holding_episode_no > 0
    AND p.stop_loss_status = 'frozen'
    AND p.stop_loss_effective_trade_date <= current_trade_date
    AND p.stop_loss_price > 0
    AND p.stop_loss_price::text NOT IN ('NaN', 'Infinity', '-Infinity')
    AND EXISTS (
      SELECT 1 FROM public.n6_principal principal
      WHERE principal.principal_id = p.principal_id
        AND principal.principal_type = p.principal_type
        AND principal.principal_status = 'active'
        AND principal.owner_user_id IS NOT NULL
    )
    AND EXISTS (
      SELECT 1 FROM public.n6_virtual_position_lot l
      WHERE l.virtual_position_id = p.virtual_position_id
        AND l.virtual_account_id = p.virtual_account_id
        AND l.principal_id = p.principal_id
        AND l.principal_type = p.principal_type
        AND l.identity_key = p.identity_key
        AND l.holding_episode_no = p.holding_episode_no
        AND l.remaining_quantity > 0
        AND l.available_trade_date <= current_trade_date
        AND l.lot_status IN ('locked_t1', 'available')
    )
    AND NOT EXISTS (
      SELECT 1 FROM public.n6_virtual_trade_proposal active
      WHERE active.principal_id = p.principal_id
        AND active.principal_type = p.principal_type
        AND active.virtual_account_id = p.virtual_account_id
        AND active.source_type = 'stop_loss'
        AND active.source_virtual_position_id = p.virtual_position_id
        AND active.holding_episode_no = p.holding_episode_no
        AND active.identity_key = p.identity_key
        AND active.proposal_side = 'sell'
        AND active.proposal_status IN ('pending', 'confirmed', 'processing', 'executed')
    )
    AND EXISTS (
      SELECT 1
      FROM public.n6_virtual_quote_snapshot q2
      JOIN public.n6_virtual_quote_snapshot q1
        ON q1.identity_key = q2.identity_key
       AND q1.quote_minute = q2.quote_minute - interval '1 minute'
      WHERE q2.virtual_quote_snapshot_id = (
        SELECT latest.virtual_quote_snapshot_id
        FROM public.n6_virtual_quote_snapshot latest
        WHERE latest.identity_key = p.identity_key
        ORDER BY latest.quote_minute DESC, latest.virtual_quote_snapshot_id DESC
        LIMIT 1
      )
        AND q1.identity_key = p.identity_key
        AND q1.exchange = pg_catalog.split_part(p.identity_key, ':', 2)
        AND q2.exchange = q1.exchange AND q2.exchange IN ('SH', 'SZ')
        AND q1.quality_status = 'passed' AND q1.quality_reason = 'ok'
        AND q2.quality_status = 'passed' AND q2.quality_reason = 'ok'
        AND q1.current_price > 0 AND q2.current_price > 0
        AND q1.current_price::text NOT IN ('NaN', 'Infinity', '-Infinity')
        AND q2.current_price::text NOT IN ('NaN', 'Infinity', '-Infinity')
        AND q1.current_price <= p.stop_loss_price
        AND q2.current_price <= p.stop_loss_price
        AND (q2.quote_minute AT TIME ZONE 'Asia/Shanghai')::date = current_trade_date
        AND q1.quote_minute >= pg_catalog.clock_timestamp() - interval '120 seconds'
        AND q2.quote_minute >= pg_catalog.clock_timestamp() - interval '120 seconds'
        AND q1.quote_minute <= pg_catalog.clock_timestamp()
        AND q2.quote_minute <= pg_catalog.clock_timestamp()
        AND q1.fetched_at >= q1.quote_minute AND q2.fetched_at >= q2.quote_minute
        AND q1.fetched_at >= pg_catalog.clock_timestamp() - interval '120 seconds'
        AND q2.fetched_at >= pg_catalog.clock_timestamp() - interval '120 seconds'
        AND q1.fetched_at <= pg_catalog.clock_timestamp()
        AND q2.fetched_at <= pg_catalog.clock_timestamp()
    )
    AND (
      NOT EXISTS (
        SELECT 1 FROM public.n6_virtual_trade_proposal terminal
        WHERE terminal.source_type = 'stop_loss'
          AND terminal.proposal_side = 'sell'
          AND terminal.principal_id = p.principal_id
          AND terminal.principal_type = p.principal_type
          AND terminal.virtual_account_id = p.virtual_account_id
          AND terminal.identity_key = p.identity_key
          AND terminal.source_virtual_position_id = p.virtual_position_id
          AND terminal.holding_episode_no = p.holding_episode_no
          AND terminal.proposal_status IN ('expired', 'rejected', 'failed')
      )
      OR EXISTS (
        SELECT 1
        FROM public.n6_virtual_trade_proposal terminal
        JOIN public.n6_virtual_quote_snapshot r1 ON r1.identity_key = p.identity_key
        JOIN public.n6_virtual_quote_snapshot r2
          ON r2.identity_key = r1.identity_key
         AND r2.quote_minute = r1.quote_minute + interval '1 minute'
        WHERE terminal.proposal_id = (
          SELECT last_terminal.proposal_id
          FROM public.n6_virtual_trade_proposal last_terminal
          WHERE last_terminal.source_type = 'stop_loss'
            AND last_terminal.source_virtual_position_id = p.virtual_position_id
            AND last_terminal.holding_episode_no = p.holding_episode_no
            AND last_terminal.proposal_side = 'sell'
            AND last_terminal.principal_id = p.principal_id
            AND last_terminal.principal_type = p.principal_type
            AND last_terminal.virtual_account_id = p.virtual_account_id
            AND last_terminal.identity_key = p.identity_key
            AND last_terminal.proposal_status IN ('expired', 'rejected', 'failed')
          ORDER BY last_terminal.updated_at DESC, last_terminal.proposal_id DESC
          LIMIT 1
        )
          AND terminal.source_type = 'stop_loss'
          AND terminal.proposal_side = 'sell'
          AND terminal.principal_id = p.principal_id
          AND terminal.principal_type = p.principal_type
          AND terminal.virtual_account_id = p.virtual_account_id
          AND terminal.identity_key = p.identity_key
          AND terminal.source_virtual_position_id = p.virtual_position_id
          AND terminal.holding_episode_no = p.holding_episode_no
          AND terminal.proposal_status IN ('expired', 'rejected', 'failed')
          AND r1.quote_minute > terminal.updated_at
          AND r2.quote_minute < (
            SELECT latest.quote_minute - interval '1 minute'
            FROM public.n6_virtual_quote_snapshot latest
            WHERE latest.identity_key = p.identity_key
            ORDER BY latest.quote_minute DESC, latest.virtual_quote_snapshot_id DESC
            LIMIT 1
          )
          AND r1.exchange = pg_catalog.split_part(p.identity_key, ':', 2)
          AND r2.exchange = r1.exchange AND r1.exchange IN ('SH', 'SZ')
          AND (r1.quote_minute AT TIME ZONE 'Asia/Shanghai')::date = current_trade_date
          AND (r2.quote_minute AT TIME ZONE 'Asia/Shanghai')::date = current_trade_date
          AND r1.quality_status = 'passed' AND r1.quality_reason = 'ok'
          AND r2.quality_status = 'passed' AND r2.quality_reason = 'ok'
          AND r1.current_price > p.stop_loss_price
          AND r2.current_price > p.stop_loss_price
          AND r1.current_price::text NOT IN ('NaN', 'Infinity', '-Infinity')
          AND r2.current_price::text NOT IN ('NaN', 'Infinity', '-Infinity')
          AND r1.fetched_at >= r1.quote_minute AND r2.fetched_at >= r2.quote_minute
          AND r1.fetched_at <= r1.quote_minute + interval '120 seconds'
          AND r2.fetched_at <= r2.quote_minute + interval '120 seconds'
          AND r1.quote_minute <= pg_catalog.clock_timestamp()
          AND r2.quote_minute <= pg_catalog.clock_timestamp()
          AND r1.fetched_at <= pg_catalog.clock_timestamp()
          AND r2.fetched_at <= pg_catalog.clock_timestamp()
      )
    )
  ORDER BY p.virtual_position_id
  FOR UPDATE SKIP LOCKED
  LIMIT 1;
  IF NOT FOUND THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true, 'status', 'not_ready', 'reason', 'no_evaluation_candidate'
    );
  END IF;

  WITH locked_lots AS (
    SELECT l.remaining_quantity
    FROM public.n6_virtual_position_lot l
    WHERE l.virtual_position_id = position_row.virtual_position_id
      AND l.virtual_account_id = position_row.virtual_account_id
      AND l.principal_id = position_row.principal_id
      AND l.principal_type = position_row.principal_type
      AND l.identity_key = position_row.identity_key
      AND l.holding_episode_no = position_row.holding_episode_no
      AND l.remaining_quantity > 0
      AND l.available_trade_date <= current_trade_date
      AND l.lot_status IN ('locked_t1', 'available')
    FOR UPDATE
  )
  SELECT pg_catalog.sum(l.remaining_quantity)
    INTO matured_quantity
  FROM locked_lots l;
  IF pg_catalog.coalesce(matured_quantity, 0) <= 0 THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true, 'status', 'not_ready', 'reason', 't1_matured_lot_required'
    );
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.n6_virtual_trade_proposal p
    WHERE p.principal_id = position_row.principal_id
      AND p.principal_type = position_row.principal_type
      AND p.virtual_account_id = position_row.virtual_account_id
      AND p.source_type = 'stop_loss'
      AND p.source_virtual_position_id = position_row.virtual_position_id
      AND p.holding_episode_no = position_row.holding_episode_no
      AND p.identity_key = position_row.identity_key
      AND p.proposal_side = 'sell'
      AND p.proposal_status IN ('pending', 'confirmed', 'processing', 'executed')
    FOR UPDATE
  ) THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true, 'status', 'not_ready',
      'reason', 'episode_stop_proposal_already_active_or_executed'
    );
  END IF;

  SELECT p.* INTO terminal_proposal
  FROM public.n6_virtual_trade_proposal p
  WHERE p.principal_id = position_row.principal_id
    AND p.principal_type = position_row.principal_type
    AND p.virtual_account_id = position_row.virtual_account_id
    AND p.source_type = 'stop_loss'
    AND p.source_virtual_position_id = position_row.virtual_position_id
    AND p.holding_episode_no = position_row.holding_episode_no
    AND p.identity_key = position_row.identity_key
    AND p.proposal_side = 'sell'
    AND p.proposal_status IN ('expired', 'rejected', 'failed')
  ORDER BY p.updated_at DESC, p.proposal_id DESC
  LIMIT 1
  FOR UPDATE;

  SELECT q.* INTO confirm_quote
  FROM public.n6_virtual_quote_snapshot q
  WHERE q.identity_key = position_row.identity_key
  ORDER BY q.quote_minute DESC, q.virtual_quote_snapshot_id DESC
  LIMIT 1
  FOR SHARE;
  IF NOT FOUND
     OR confirm_quote.exchange <> pg_catalog.split_part(position_row.identity_key, ':', 2)
     OR confirm_quote.exchange NOT IN ('SH', 'SZ')
     OR confirm_quote.quality_status <> 'passed'
     OR confirm_quote.quality_reason <> 'ok'
     OR confirm_quote.current_price IS NULL
     OR confirm_quote.current_price <= 0
     OR confirm_quote.current_price::text IN ('NaN', 'Infinity', '-Infinity')
     OR confirm_quote.quote_minute > pg_catalog.clock_timestamp()
     OR confirm_quote.fetched_at > pg_catalog.clock_timestamp()
     OR confirm_quote.fetched_at < confirm_quote.quote_minute
     OR confirm_quote.quote_minute < pg_catalog.clock_timestamp() - interval '120 seconds'
     OR confirm_quote.fetched_at < pg_catalog.clock_timestamp() - interval '120 seconds'
     OR (confirm_quote.quote_minute AT TIME ZONE 'Asia/Shanghai')::date <> current_trade_date
     OR confirm_quote.current_price > position_row.stop_loss_price THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true, 'status', 'not_ready', 'reason', 'fresh_confirm_breach_missing'
    );
  END IF;

  SELECT q.* INTO first_quote
  FROM public.n6_virtual_quote_snapshot q
  WHERE q.identity_key = position_row.identity_key
    AND q.quote_minute = confirm_quote.quote_minute - interval '1 minute'
  LIMIT 1
  FOR SHARE;
  IF NOT FOUND
     OR first_quote.exchange <> confirm_quote.exchange
     OR first_quote.quality_status <> 'passed'
     OR first_quote.quality_reason <> 'ok'
     OR first_quote.current_price IS NULL
     OR first_quote.current_price <= 0
     OR first_quote.current_price::text IN ('NaN', 'Infinity', '-Infinity')
     OR first_quote.quote_minute > pg_catalog.clock_timestamp()
     OR first_quote.fetched_at > pg_catalog.clock_timestamp()
     OR first_quote.fetched_at < first_quote.quote_minute
     OR first_quote.quote_minute < pg_catalog.clock_timestamp() - interval '120 seconds'
     OR first_quote.fetched_at < pg_catalog.clock_timestamp() - interval '120 seconds'
     OR first_quote.current_price > position_row.stop_loss_price THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true, 'status', 'not_ready', 'reason', 'adjacent_two_minute_breach_missing'
    );
  END IF;

  IF terminal_proposal.proposal_id IS NOT NULL THEN
    SELECT EXISTS (
      SELECT 1
      FROM public.n6_virtual_quote_snapshot r1
      JOIN public.n6_virtual_quote_snapshot r2
        ON r2.identity_key = r1.identity_key
       AND r2.quote_minute = r1.quote_minute + interval '1 minute'
      WHERE r1.identity_key = position_row.identity_key
        AND r1.quote_minute > terminal_proposal.updated_at
        AND r2.quote_minute < first_quote.quote_minute
        AND r1.exchange = pg_catalog.split_part(position_row.identity_key, ':', 2)
        AND r1.exchange IN ('SH', 'SZ')
        AND r2.exchange = r1.exchange
        AND (r1.quote_minute AT TIME ZONE 'Asia/Shanghai')::date = current_trade_date
        AND (r2.quote_minute AT TIME ZONE 'Asia/Shanghai')::date = current_trade_date
        AND r1.quality_status = 'passed' AND r1.quality_reason = 'ok'
        AND r2.quality_status = 'passed' AND r2.quality_reason = 'ok'
        AND r1.current_price > position_row.stop_loss_price
        AND r2.current_price > position_row.stop_loss_price
        AND r1.current_price::text NOT IN ('NaN', 'Infinity', '-Infinity')
        AND r2.current_price::text NOT IN ('NaN', 'Infinity', '-Infinity')
        AND r1.quote_minute <= pg_catalog.clock_timestamp()
        AND r2.quote_minute <= pg_catalog.clock_timestamp()
        AND r1.fetched_at >= r1.quote_minute
        AND r2.fetched_at >= r2.quote_minute
        AND r1.fetched_at <= r1.quote_minute + interval '120 seconds'
        AND r2.fetched_at <= r2.quote_minute + interval '120 seconds'
        AND r1.fetched_at <= pg_catalog.clock_timestamp()
        AND r2.fetched_at <= pg_catalog.clock_timestamp()
    ) INTO rearmed;
    IF NOT rearmed THEN
      RETURN pg_catalog.jsonb_build_object(
        'ok', true, 'status', 'not_ready', 'reason', 'rearm_above_stop_required'
      );
    END IF;
  END IF;

  SELECT p.owner_user_id INTO owner_user_id
  FROM public.n6_principal p
  WHERE p.principal_id = position_row.principal_id
    AND p.principal_type = position_row.principal_type
    AND p.principal_status = 'active';
  IF owner_user_id IS NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true, 'status', 'not_ready', 'reason', 'principal_owner_missing'
    );
  END IF;

  source_key := position_row.virtual_position_id || ':' ||
                position_row.holding_episode_no || ':' ||
                confirm_quote.virtual_quote_snapshot_id;
  confirm_key := 'stop_loss:' || source_key;
  INSERT INTO public.n6_virtual_trade_proposal (
    principal_id, principal_type, user_id, virtual_account_id,
    source_type, source_id, source_virtual_position_id, holding_episode_no,
    asset_kind, identity_key, proposal_side, signal_reference_kind,
    signal_reference_price, proposal_status, expires_at, confirmed_at,
    confirm_idempotency_key, policy_version, policy_hash, source_lineage_json
  ) VALUES (
    position_row.principal_id, position_row.principal_type, owner_user_id,
    position_row.virtual_account_id, 'stop_loss', source_key,
    position_row.virtual_position_id, position_row.holding_episode_no,
    'stock', position_row.identity_key, 'sell', 'stop_loss',
    position_row.stop_loss_price, 'confirmed',
    pg_catalog.clock_timestamp() + interval '60 seconds',
    pg_catalog.clock_timestamp(), confirm_key,
    'n6_virtual_stop_loss_049_v1', 'n6_virtual_stop_loss_049_v1',
    pg_catalog.jsonb_build_object(
      'virtual_position_id', position_row.virtual_position_id,
      'holding_episode_no', position_row.holding_episode_no,
      'first_trigger_quote_snapshot_id', first_quote.virtual_quote_snapshot_id,
      'confirm_trigger_quote_snapshot_id', confirm_quote.virtual_quote_snapshot_id,
      'stop_loss_price', position_row.stop_loss_price,
      'trigger_price', confirm_quote.current_price,
      'stop_loss_source_quote_snapshot_id',
        position_row.stop_loss_source_quote_snapshot_id,
      'stop_loss_policy_version', position_row.stop_loss_policy_version,
      'stop_loss_policy_hash', position_row.stop_loss_policy_hash,
      'executor_run_id', p_executor_run_id,
      'rearmed_after_terminal_proposal_id', terminal_proposal.proposal_id
    )
  )
  ON CONFLICT DO NOTHING
  RETURNING proposal_id INTO new_proposal_id;
  IF new_proposal_id IS NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true, 'status', 'not_ready', 'reason', 'idempotent_duplicate'
    );
  END IF;
  RETURN pg_catalog.jsonb_build_object(
    'ok', true, 'status', 'confirmed', 'proposal_id', new_proposal_id,
    'source_id', source_key, 'confirm_idempotency_key', confirm_key,
    'expires_in_seconds', 60
  );
END
$function$;

CREATE OR REPLACE FUNCTION public.n6_executor_apply_claimed_proposal(
  p_proposal_id bigint,
  p_executor_run_id text
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
  proposal public.n6_virtual_trade_proposal%ROWTYPE;
  account public.n6_virtual_account%ROWTYPE;
  cash_before public.n6_virtual_cash_snapshot%ROWTYPE;
  quote public.n6_virtual_quote_snapshot%ROWTYPE;
  position_before public.n6_virtual_position%ROWTYPE;
  lot_row public.n6_virtual_position_lot%ROWTYPE;
  trade_date_date date;
  next_trade_date date;
  trade_date_integer integer;
  fill_quantity numeric(24,4);
  fill_price numeric(24,6);
  gross_amount numeric(24,4);
  position_cost_delta numeric(24,4);
  cash_delta numeric(24,4);
  new_available_cash numeric(24,4);
  new_quantity numeric(24,4);
  new_available_quantity numeric(24,4);
  new_locked_quantity numeric(24,4);
  new_average_cost numeric(24,6);
  position_id bigint;
  order_id bigint;
  trade_id bigint;
  ledger_id bigint;
  new_cash_snapshot_id bigint;
  new_position_event_id bigint;
  episode_no integer;
  remaining_to_sell numeric(24,4);
  old_available_lot_quantity numeric(24,4) := 0;
  old_locked_lot_quantity numeric(24,4) := 0;
  active_cash_snapshot_count integer;
  active_cash_snapshot_id bigint;
  position_pointer_update_count integer;
  lineage jsonb;
BEGIN
  IF p_proposal_id IS NULL OR p_proposal_id <= 0
     OR p_executor_run_id IS NULL OR btrim(p_executor_run_id) = ''
     OR length(p_executor_run_id) > 200 THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'invalid_request');
  END IF;

  SELECT * INTO proposal
  FROM public.n6_virtual_trade_proposal
  WHERE proposal_id = p_proposal_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'proposal_not_found');
  END IF;

  IF proposal.proposal_status = 'executed'
     AND proposal.executor_run_id = p_executor_run_id
     AND proposal.executed_virtual_order_id IS NOT NULL
     AND proposal.executed_virtual_trade_id IS NOT NULL THEN
    RETURN pg_catalog.jsonb_build_object(
      'ok', true, 'status', 'executed', 'idempotent', true,
      'proposal_id', proposal.proposal_id,
      'virtual_order_id', proposal.executed_virtual_order_id,
      'virtual_trade_id', proposal.executed_virtual_trade_id
    );
  END IF;
  IF proposal.proposal_status <> 'processing'
     OR proposal.executor_run_id IS DISTINCT FROM p_executor_run_id THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'not_claimed');
  END IF;
  IF proposal.expires_at <= pg_catalog.clock_timestamp() THEN
    IF proposal.source_type = 'stop_loss' THEN
      UPDATE public.n6_virtual_trade_proposal
      SET proposal_status = 'expired', failure_reason = 'proposal_expired',
          updated_at = pg_catalog.now()
      WHERE proposal_id = proposal.proposal_id;
      RETURN pg_catalog.jsonb_build_object('ok', true, 'status', 'expired',
        'proposal_id', proposal.proposal_id, 'account_writes', 0);
    END IF;
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'proposal_expired');
  END IF;
  IF proposal.source_type NOT IN ('signal', 'manual_position', 'stop_loss')
     OR proposal.asset_kind <> 'stock'
     OR proposal.identity_key !~ '^stock:(SH|SZ):[0-9]{6}$'
     OR proposal.proposal_side NOT IN ('buy', 'sell') THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'proposal_not_eligible');
  END IF;

  SELECT * INTO account
  FROM public.n6_virtual_account
  WHERE virtual_account_id = proposal.virtual_account_id
  FOR UPDATE;
  IF NOT FOUND
     OR account.virtual_account_status <> 'active'
     OR account.principal_id <> proposal.principal_id
     OR account.principal_type <> proposal.principal_type THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'account_scope_mismatch');
  END IF;

  SELECT * INTO cash_before
  FROM public.n6_virtual_cash_snapshot
  WHERE cash_snapshot_id = account.current_cash_snapshot_id
    AND virtual_account_id = account.virtual_account_id
    AND snapshot_status = 'active'
  FOR UPDATE;
  IF NOT FOUND THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'cash_not_ready');
  END IF;

  SELECT * INTO quote
  FROM public.n6_virtual_quote_snapshot
  WHERE identity_key = proposal.identity_key
  ORDER BY quote_minute DESC, virtual_quote_snapshot_id DESC
  LIMIT 1
  FOR SHARE;
  IF NOT FOUND
     OR quote.quality_status <> 'passed'
     OR quote.quality_reason <> 'ok'
     OR quote.exchange NOT IN ('SH', 'SZ')
     OR quote.identity_key <> proposal.identity_key
     OR quote.quote_minute > pg_catalog.clock_timestamp()
     OR quote.quote_minute < pg_catalog.clock_timestamp() - interval '2 minutes'
     OR quote.fetched_at > pg_catalog.clock_timestamp()
     OR (proposal.source_type = 'stop_loss' AND quote.fetched_at < quote.quote_minute)
     OR quote.fetched_at < pg_catalog.clock_timestamp() - interval '2 minutes'
     OR quote.current_price IS NULL
     OR quote.current_price <= 0
     OR quote.current_price::text IN ('NaN', 'Infinity', '-Infinity') THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'quote_not_ready');
  END IF;

  trade_date_date := (quote.quote_minute AT TIME ZONE 'Asia/Shanghai')::date;
  trade_date_integer := pg_catalog.to_char(trade_date_date, 'YYYYMMDD')::integer;
  fill_price := quote.current_price::numeric(24,6);
  IF trade_date_date <> (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date
     OR NOT (
       (quote.quote_minute AT TIME ZONE 'Asia/Shanghai')::time BETWEEN time '09:30' AND time '11:30'
       OR (quote.quote_minute AT TIME ZONE 'Asia/Shanghai')::time BETWEEN time '13:00' AND time '15:00'
     )
     OR NOT (
       (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::time BETWEEN time '09:30' AND time '11:30'
       OR (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::time BETWEEN time '13:00' AND time '15:00'
     )
     OR NOT EXISTS (
       SELECT 1 FROM public.common_trade_calendar
       WHERE trade_date = trade_date_integer::text AND is_open = true
     ) THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'trade_session_not_ready');
  END IF;
  IF cash_before.trade_date > trade_date_integer THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'cash_trade_date_ahead');
  END IF;
  WITH locked_cash AS (
    SELECT cash_snapshot_id
    FROM public.n6_virtual_cash_snapshot
    WHERE virtual_account_id = proposal.virtual_account_id
      AND snapshot_status = 'active'
    FOR UPDATE
  )
  SELECT count(*), min(cash_snapshot_id)
  INTO active_cash_snapshot_count, active_cash_snapshot_id
  FROM locked_cash;
  IF active_cash_snapshot_count <> 1
     OR active_cash_snapshot_id <> cash_before.cash_snapshot_id THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'cash_authority_conflict');
  END IF;

  SELECT * INTO position_before
  FROM public.n6_virtual_position
  WHERE virtual_account_id = proposal.virtual_account_id
    AND asset_kind = 'stock'
    AND identity_key = proposal.identity_key
  FOR UPDATE;
  IF FOUND AND (
       position_before.principal_id <> proposal.principal_id
       OR position_before.principal_type <> proposal.principal_type
  ) THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'position_scope_mismatch');
  END IF;
  IF position_before.virtual_position_id IS NOT NULL THEN
    WITH locked_lots AS (
      SELECT remaining_quantity, available_trade_date, lot_status
      FROM public.n6_virtual_position_lot
      WHERE virtual_position_id = position_before.virtual_position_id
        AND virtual_account_id = proposal.virtual_account_id
        AND principal_id = proposal.principal_id
        AND principal_type = proposal.principal_type
        AND identity_key = proposal.identity_key
        AND (
          proposal.source_type <> 'stop_loss'
          OR holding_episode_no = proposal.holding_episode_no
        )
        AND remaining_quantity > 0
      FOR UPDATE
    )
    SELECT
      COALESCE(sum(remaining_quantity) FILTER (
        WHERE available_trade_date <= trade_date_date
          AND lot_status IN ('locked_t1', 'available')
      ), 0),
      COALESCE(sum(remaining_quantity) FILTER (
        WHERE available_trade_date > trade_date_date
          AND lot_status = 'locked_t1'
      ), 0)
    INTO old_available_lot_quantity, old_locked_lot_quantity
    FROM locked_lots;
  END IF;

  IF proposal.source_type = 'stop_loss' THEN
    IF proposal.proposal_side <> 'sell'
       OR proposal.source_virtual_position_id IS DISTINCT FROM position_before.virtual_position_id
       OR proposal.holding_episode_no IS NULL
       OR proposal.holding_episode_no IS DISTINCT FROM position_before.holding_episode_no
       OR position_before.position_status <> 'open_virtual'
       OR position_before.quantity <= 0
       OR position_before.stop_loss_status <> 'frozen'
       OR position_before.stop_loss_effective_trade_date IS NULL
       OR position_before.stop_loss_effective_trade_date > trade_date_date
       OR position_before.stop_loss_price IS NULL
       OR position_before.stop_loss_price <= 0
       OR position_before.stop_loss_price::text IN ('NaN', 'Infinity', '-Infinity')
       OR quote.current_price > position_before.stop_loss_price
       OR old_available_lot_quantity <= 0 THEN
      UPDATE public.n6_virtual_trade_proposal
      SET proposal_status = 'failed',
          failure_reason = CASE
            WHEN quote.current_price > position_before.stop_loss_price
              THEN 'stop_loss_quote_recovered'
            WHEN old_available_lot_quantity <= 0
              THEN 'stop_loss_t1_lot_not_sellable'
            ELSE 'stop_loss_revalidation_failed'
          END,
          updated_at = pg_catalog.now()
      WHERE proposal_id = proposal.proposal_id;
      RETURN pg_catalog.jsonb_build_object(
        'ok', true, 'status', 'failed', 'proposal_id', proposal.proposal_id,
        'account_writes', 0
      );
    END IF;
  END IF;

  IF proposal.source_type <> 'stop_loss'
     AND position_before.position_status = 'open_virtual'
     AND position_before.quantity
         <> old_available_lot_quantity + old_locked_lot_quantity THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'lot_position_mismatch');
  END IF;

  IF proposal.proposal_side = 'buy' THEN
    IF proposal.source_type <> 'signal' THEN
      RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'buy_source_not_allowed');
    END IF;
    IF (
         position_before.virtual_position_id IS NULL
         OR position_before.position_status = 'closed_virtual'
         OR position_before.quantity = 0
       )
       AND (
         proposal.locked_target_price IS NULL
         OR proposal.locked_target_price <= 0
         OR proposal.source_signal_projection_id IS NULL
       ) THEN
      RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'target_price_not_ready');
    END IF;
    fill_quantity := pg_catalog.floor(
      LEAST(300000::numeric, cash_before.available_cash) / fill_price / 100
    ) * 100;
    IF fill_quantity < 100 THEN
      RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'budget_below_one_lot');
    END IF;
    gross_amount := pg_catalog.round(fill_quantity * fill_price, 4);
    IF cash_before.available_cash < gross_amount THEN
      RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'insufficient_cash');
    END IF;
    SELECT pg_catalog.to_date(min(trade_date)::text, 'YYYYMMDD') INTO next_trade_date
    FROM public.common_trade_calendar
    WHERE trade_date > trade_date_integer::text AND is_open = true;
    IF next_trade_date IS NULL THEN
      RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'next_trade_date_not_ready');
    END IF;
    episode_no := CASE
      WHEN position_before.virtual_position_id IS NULL THEN 1
      WHEN position_before.position_status = 'closed_virtual' OR position_before.quantity = 0
        THEN position_before.holding_episode_no + 1
      ELSE position_before.holding_episode_no
    END;
    new_quantity := COALESCE(position_before.quantity, 0) + fill_quantity;
    new_available_quantity := old_available_lot_quantity;
    new_locked_quantity := old_locked_lot_quantity + fill_quantity;
    new_average_cost := pg_catalog.round(
      ((COALESCE(position_before.quantity, 0) * COALESCE(position_before.average_cost, 0))
        + gross_amount) / new_quantity, 6
    );
    cash_delta := -gross_amount;
    position_cost_delta := gross_amount;
  ELSE
    IF position_before.virtual_position_id IS NULL
       OR position_before.position_status <> 'open_virtual'
       OR position_before.quantity <= 0
       OR (
         proposal.source_type IN ('manual_position', 'stop_loss')
         AND proposal.source_virtual_position_id IS DISTINCT FROM position_before.virtual_position_id
       ) THEN
      RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'position_not_sellable');
    END IF;
    IF proposal.holding_episode_no IS NULL
       OR proposal.holding_episode_no <> position_before.holding_episode_no THEN
      RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'holding_episode_mismatch');
    END IF;
    fill_quantity := old_available_lot_quantity;
    IF fill_quantity <= 0 OR fill_quantity > position_before.quantity THEN
      RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 't1_quantity_not_sellable');
    END IF;
    gross_amount := pg_catalog.round(fill_quantity * fill_price, 4);
    episode_no := position_before.holding_episode_no;
    new_quantity := position_before.quantity - fill_quantity;
    new_available_quantity := 0;
    new_locked_quantity := old_locked_lot_quantity;
    IF new_quantity <> new_available_quantity + new_locked_quantity THEN
      RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'lot_position_mismatch');
    END IF;
    new_average_cost := CASE WHEN new_quantity = 0 THEN 0 ELSE position_before.average_cost END;
    cash_delta := gross_amount;
    position_cost_delta := -pg_catalog.round(
      fill_quantity * position_before.average_cost, 4
    );
  END IF;

  new_available_cash := cash_before.available_cash + cash_delta;
  IF new_available_cash < 0 THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'status', 'insufficient_cash');
  END IF;
  lineage := pg_catalog.jsonb_build_object(
    'source_proposal_id', proposal.proposal_id,
    'confirm_idempotency_key', proposal.confirm_idempotency_key,
    'fill_quote_snapshot_id', quote.virtual_quote_snapshot_id,
    'executor_run_id', p_executor_run_id
  );

  INSERT INTO public.n6_virtual_order (
    virtual_account_id, principal_id, principal_type, asset_kind, identity_key,
    signal_type, order_side, order_type, order_status, requested_quantity,
    requested_price, estimated_fee_amount, estimated_tax_amount,
    fee_policy_version, tax_policy_version, execution_policy_version,
    execution_policy_hash, market_rule_set, run_id, policy_version, policy_hash,
    rollback_scope, source_lineage_json, quality_status, source_proposal_id,
    source_signal_projection_id, signal_reference_kind, signal_reference_price,
    fill_quote_snapshot_id
  ) VALUES (
    proposal.virtual_account_id, proposal.principal_id, proposal.principal_type,
    'stock', proposal.identity_key,
    CASE WHEN proposal.proposal_side = 'buy' THEN 'B_BUY' ELSE 'S_SELL' END,
    proposal.proposal_side, 'market_virtual', 'filled_virtual', fill_quantity,
    fill_price, 0, 0, 'n6_046_zero_fee_v1', 'n6_046_zero_tax_v1',
    'n6_046_latest_quote_fill_v1', 'n6_046_latest_quote_fill_v1',
    'a_share_t_plus_1_virtual_v1', p_executor_run_id,
    'n6_btrack_virtual_executor_046_v1', 'n6_btrack_virtual_executor_046_v1',
    p_executor_run_id, lineage, 'passed', proposal.proposal_id,
    proposal.source_signal_projection_id,
    proposal.signal_reference_kind, proposal.signal_reference_price,
    quote.virtual_quote_snapshot_id
  ) RETURNING virtual_order_id INTO order_id;

  INSERT INTO public.n6_virtual_trade (
    virtual_order_id, virtual_account_id, principal_id, principal_type,
    asset_kind, identity_key, trade_side, filled_quantity, filled_price,
    gross_amount, commission_amount, stamp_tax_amount, transfer_fee_amount,
    total_fee_amount, net_amount, fill_policy_version, fill_policy_hash,
    replay_deterministic_seed, trade_status, trade_time, source_lineage_json,
    run_id, policy_version, policy_hash, rollback_scope, quality_status,
    source_proposal_id, signal_reference_kind, signal_reference_price,
    fill_quote_snapshot_id
  ) VALUES (
    order_id, proposal.virtual_account_id, proposal.principal_id,
    proposal.principal_type, 'stock', proposal.identity_key,
    proposal.proposal_side, fill_quantity, fill_price, gross_amount,
    0, 0, 0, 0, gross_amount, 'n6_046_latest_quote_fill_v1',
    'n6_046_latest_quote_fill_v1', 'source_proposal:' || proposal.proposal_id,
    'filled_virtual', pg_catalog.clock_timestamp(), lineage, p_executor_run_id,
    'n6_btrack_virtual_executor_046_v1', 'n6_btrack_virtual_executor_046_v1',
    p_executor_run_id, 'passed', proposal.proposal_id,
    proposal.signal_reference_kind, proposal.signal_reference_price,
    quote.virtual_quote_snapshot_id
  ) RETURNING virtual_trade_id INTO trade_id;

  INSERT INTO public.n6_virtual_cash_ledger (
    virtual_account_id, ledger_type, amount, currency, trade_date, event_time,
    source_event_type, source_event_id, source_virtual_order_id,
    source_virtual_trade_id, run_id, policy_version, policy_hash,
    rollback_scope, source_lineage_json, quality_status
  ) VALUES (
    proposal.virtual_account_id,
    CASE WHEN proposal.proposal_side = 'buy' THEN 'virtual_buy' ELSE 'virtual_sell' END,
    cash_delta, 'CNY', trade_date_integer, pg_catalog.clock_timestamp(),
    'n6_virtual_executor_046', proposal.proposal_id::text, order_id, trade_id,
    p_executor_run_id, 'n6_btrack_virtual_executor_046_v1',
    'n6_btrack_virtual_executor_046_v1', p_executor_run_id, lineage, 'passed'
  ) RETURNING cash_ledger_id INTO ledger_id;

  UPDATE public.n6_virtual_cash_snapshot
  SET snapshot_status = 'superseded'
  WHERE cash_snapshot_id = cash_before.cash_snapshot_id;
  INSERT INTO public.n6_virtual_cash_snapshot (
    virtual_account_id, snapshot_time, trade_date, available_cash, frozen_cash,
    total_cash, currency, source_ledger_max_id, snapshot_status, run_id,
    policy_version, policy_hash, rollback_scope, source_lineage_json,
    quality_status
  ) VALUES (
    proposal.virtual_account_id, pg_catalog.clock_timestamp(), trade_date_integer,
    new_available_cash, cash_before.frozen_cash,
    new_available_cash + cash_before.frozen_cash, 'CNY', ledger_id, 'active',
    p_executor_run_id, 'n6_btrack_virtual_executor_046_v1',
    'n6_btrack_virtual_executor_046_v1', p_executor_run_id, lineage, 'passed'
  ) RETURNING cash_snapshot_id INTO new_cash_snapshot_id;
  UPDATE public.n6_virtual_account
  SET current_cash_snapshot_id = new_cash_snapshot_id, updated_at = pg_catalog.now()
  WHERE virtual_account_id = proposal.virtual_account_id;

  UPDATE public.n6_virtual_position_lot
  SET lot_status = 'available', updated_at = pg_catalog.now()
  WHERE virtual_position_id = position_before.virtual_position_id
    AND remaining_quantity > 0
    AND available_trade_date <= trade_date_date
    AND lot_status = 'locked_t1';

  IF position_before.virtual_position_id IS NULL THEN
    INSERT INTO public.n6_virtual_position (
      virtual_account_id, principal_id, principal_type, asset_kind, identity_key,
      position_status, quantity, available_quantity, locked_quantity,
      average_cost, last_virtual_trade_id, run_id, policy_version, policy_hash,
      rollback_scope, source_lineage_json, quality_status, holding_episode_no,
      first_open_trade_date, locked_target_price, target_price_status,
      target_price_source_signal_projection_id, stop_loss_status
    ) VALUES (
      proposal.virtual_account_id, proposal.principal_id, proposal.principal_type,
      'stock', proposal.identity_key, 'open_virtual', new_quantity,
      new_available_quantity, new_locked_quantity, new_average_cost, trade_id,
      p_executor_run_id, 'n6_btrack_virtual_executor_046_v1',
      'n6_btrack_virtual_executor_046_v1', p_executor_run_id, lineage, 'passed',
      episode_no, trade_date_date, proposal.locked_target_price, 'frozen',
      proposal.source_signal_projection_id, 'provisional_first_day'
    ) RETURNING virtual_position_id INTO position_id;
  ELSE
    position_id := position_before.virtual_position_id;
    UPDATE public.n6_virtual_position
    SET position_status = CASE WHEN new_quantity = 0 THEN 'closed_virtual' ELSE 'open_virtual' END,
        quantity = new_quantity, available_quantity = new_available_quantity,
        locked_quantity = new_locked_quantity, average_cost = new_average_cost,
        last_virtual_trade_id = trade_id, run_id = p_executor_run_id,
        policy_version = 'n6_btrack_virtual_executor_046_v1',
        policy_hash = 'n6_btrack_virtual_executor_046_v1',
        rollback_scope = p_executor_run_id, source_lineage_json = lineage,
        quality_status = 'passed', holding_episode_no = episode_no,
        first_open_trade_date = CASE
          WHEN position_before.position_status = 'closed_virtual' OR position_before.quantity = 0
            THEN trade_date_date
          ELSE position_before.first_open_trade_date
        END,
        locked_target_price = CASE
          WHEN proposal.proposal_side = 'buy'
            AND (position_before.position_status = 'closed_virtual' OR position_before.quantity = 0)
            THEN proposal.locked_target_price
          ELSE position_before.locked_target_price
        END,
        target_price_status = CASE
          WHEN proposal.proposal_side = 'buy'
            AND (position_before.position_status = 'closed_virtual' OR position_before.quantity = 0)
            THEN 'frozen'
          ELSE position_before.target_price_status
        END,
        target_price_source_signal_projection_id = CASE
          WHEN proposal.proposal_side = 'buy'
            AND (position_before.position_status = 'closed_virtual' OR position_before.quantity = 0)
            THEN proposal.source_signal_projection_id
          ELSE position_before.target_price_source_signal_projection_id
        END,
        stop_loss_status = CASE
          WHEN proposal.proposal_side = 'buy'
            AND (position_before.position_status = 'closed_virtual' OR position_before.quantity = 0)
            THEN 'provisional_first_day'
          ELSE position_before.stop_loss_status
        END,
        stop_loss_price = CASE
          WHEN proposal.proposal_side = 'buy'
            AND (position_before.position_status = 'closed_virtual' OR position_before.quantity = 0)
            THEN NULL
          ELSE position_before.stop_loss_price
        END,
        stop_loss_source_quote_snapshot_id = CASE
          WHEN proposal.proposal_side = 'buy'
            AND (position_before.position_status = 'closed_virtual' OR position_before.quantity = 0)
            THEN NULL
          ELSE position_before.stop_loss_source_quote_snapshot_id
        END,
        stop_loss_frozen_at = CASE
          WHEN proposal.proposal_side = 'buy'
            AND (position_before.position_status = 'closed_virtual' OR position_before.quantity = 0)
            THEN NULL
          ELSE position_before.stop_loss_frozen_at
        END,
        stop_loss_effective_trade_date = CASE
          WHEN proposal.proposal_side = 'buy'
            AND (position_before.position_status = 'closed_virtual' OR position_before.quantity = 0)
            THEN NULL
          ELSE position_before.stop_loss_effective_trade_date
        END,
        stop_loss_policy_version = CASE
          WHEN proposal.proposal_side = 'buy'
            AND (position_before.position_status = 'closed_virtual' OR position_before.quantity = 0)
            THEN NULL
          ELSE position_before.stop_loss_policy_version
        END,
        stop_loss_policy_hash = CASE
          WHEN proposal.proposal_side = 'buy'
            AND (position_before.position_status = 'closed_virtual' OR position_before.quantity = 0)
            THEN NULL
          ELSE position_before.stop_loss_policy_hash
        END,
        updated_at = pg_catalog.now()
    WHERE virtual_position_id = position_id;
  END IF;

  IF proposal.proposal_side = 'buy' THEN
    INSERT INTO public.n6_virtual_position_lot (
      virtual_position_id, virtual_account_id, principal_id, principal_type,
      identity_key, holding_episode_no, source_virtual_trade_id, open_trade_date,
      available_trade_date, original_quantity, remaining_quantity, cost_price,
      lot_status
    ) VALUES (
      position_id, proposal.virtual_account_id, proposal.principal_id,
      proposal.principal_type, proposal.identity_key, episode_no, trade_id,
      trade_date_date, next_trade_date, fill_quantity, fill_quantity, fill_price,
      'locked_t1'
    );
  ELSE
    remaining_to_sell := fill_quantity;
    FOR lot_row IN
      SELECT * FROM public.n6_virtual_position_lot
      WHERE virtual_position_id = position_id
        AND remaining_quantity > 0
        AND available_trade_date <= trade_date_date
      ORDER BY available_trade_date, virtual_position_lot_id
      FOR UPDATE
    LOOP
      EXIT WHEN remaining_to_sell <= 0;
      UPDATE public.n6_virtual_position_lot
      SET remaining_quantity = remaining_quantity - LEAST(remaining_quantity, remaining_to_sell),
          lot_status = CASE
            WHEN remaining_quantity - LEAST(remaining_quantity, remaining_to_sell) = 0 THEN 'closed'
            ELSE 'available'
          END,
          updated_at = pg_catalog.now()
      WHERE virtual_position_lot_id = lot_row.virtual_position_lot_id;
      remaining_to_sell := remaining_to_sell - LEAST(lot_row.remaining_quantity, remaining_to_sell);
    END LOOP;
    IF remaining_to_sell <> 0 THEN
      RAISE EXCEPTION '046 sell lot allocation mismatch';
    END IF;
  END IF;

  INSERT INTO public.n6_virtual_position_event (
    virtual_position_id, virtual_account_id, principal_id, principal_type,
    asset_kind, identity_key, event_type, quantity_delta, cost_delta,
    source_virtual_order_id, source_virtual_trade_id, event_time, run_id,
    policy_version, policy_hash, rollback_scope, source_lineage_json,
    quality_status
  ) VALUES (
    position_id, proposal.virtual_account_id, proposal.principal_id,
    proposal.principal_type, 'stock', proposal.identity_key,
    CASE WHEN proposal.proposal_side = 'buy' THEN 'virtual_buy_fill' ELSE 'virtual_sell_fill' END,
    CASE WHEN proposal.proposal_side = 'buy' THEN fill_quantity ELSE -fill_quantity END,
    position_cost_delta,
    order_id, trade_id, pg_catalog.clock_timestamp(), p_executor_run_id,
    'n6_btrack_virtual_executor_046_v1', 'n6_btrack_virtual_executor_046_v1',
    p_executor_run_id, lineage, 'passed'
  ) RETURNING position_event_id INTO new_position_event_id;

  UPDATE public.n6_virtual_position
  SET source_position_event_id = new_position_event_id,
      updated_at = pg_catalog.now()
  WHERE virtual_position_id = position_id;
  GET DIAGNOSTICS position_pointer_update_count = ROW_COUNT;
  IF position_pointer_update_count <> 1 THEN
    RAISE EXCEPTION '046 position event pointer update count: %',
      position_pointer_update_count;
  END IF;

  UPDATE public.n6_virtual_trade_proposal
  SET proposal_status = 'executed',
      executed_virtual_order_id = order_id,
      executed_virtual_trade_id = trade_id,
      failure_reason = NULL,
      updated_at = pg_catalog.now()
  WHERE proposal_id = proposal.proposal_id
    AND proposal_status = 'processing'
    AND executor_run_id = p_executor_run_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION '046 proposal lost processing ownership';
  END IF;

  RETURN pg_catalog.jsonb_build_object(
    'ok', true, 'status', 'executed', 'idempotent', false,
    'proposal_id', proposal.proposal_id, 'virtual_order_id', order_id,
    'virtual_trade_id', trade_id, 'cash_ledger_id', ledger_id,
    'cash_snapshot_id', new_cash_snapshot_id, 'virtual_position_id', position_id,
    'position_event_id', new_position_event_id, 'fill_quote_snapshot_id',
    quote.virtual_quote_snapshot_id, 'filled_quantity', fill_quantity,
    'filled_price', fill_price
  );
END
$function$;

REVOKE ALL ON FUNCTION public.n6_quote_writer_scope(timestamptz)
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_virtual_executor;
GRANT EXECUTE ON FUNCTION public.n6_quote_writer_scope(timestamptz)
  TO n6_quote_writer;

REVOKE ALL ON FUNCTION public.n6_quote_writer_save_run(
  bigint,text,timestamptz,text,integer,integer,integer,
  timestamptz,timestamptz,jsonb,jsonb
) FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_virtual_executor;
GRANT EXECUTE ON FUNCTION public.n6_quote_writer_save_run(
  bigint,text,timestamptz,text,integer,integer,integer,
  timestamptz,timestamptz,jsonb,jsonb
) TO n6_quote_writer;

REVOKE ALL ON FUNCTION public.n6_executor_evaluate_next_stop_loss(text)
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer;
GRANT EXECUTE ON FUNCTION public.n6_executor_evaluate_next_stop_loss(text)
  TO n6_virtual_executor;

REVOKE ALL ON FUNCTION public.n6_executor_apply_claimed_proposal(bigint,text)
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer;
GRANT EXECUTE ON FUNCTION public.n6_executor_apply_claimed_proposal(bigint,text)
  TO n6_virtual_executor;

COMMIT;
