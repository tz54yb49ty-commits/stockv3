-- N6 quote-writer least-privilege and late-scope evidence migration draft.
-- REVIEW ONLY: do not execute without a separate N6_user migration gate.
-- Role provisioning and credentials are intentionally outside this migration.

BEGIN;

DO $preflight$
DECLARE
  role_row record;
  leaked_privilege record;
BEGIN
  SELECT oid, rolcanlogin, rolinherit, rolsuper, rolcreatedb, rolcreaterole,
         rolreplication, rolbypassrls
    INTO role_row
  FROM pg_catalog.pg_roles
  WHERE rolname = 'n6_quote_writer';

  IF role_row.oid IS NULL THEN
    RAISE EXCEPTION '051 required role missing: n6_quote_writer';
  END IF;
  IF NOT role_row.rolcanlogin
     OR role_row.rolinherit
     OR role_row.rolsuper
     OR role_row.rolcreatedb
     OR role_row.rolcreaterole
     OR role_row.rolreplication
     OR role_row.rolbypassrls THEN
    RAISE EXCEPTION '051 n6_quote_writer role attributes rejected';
  END IF;

  SELECT c.relname, required.privilege_name
    INTO leaked_privilege
  FROM pg_catalog.pg_class c
  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
  CROSS JOIN (
    VALUES ('SELECT'::text), ('INSERT'::text), ('UPDATE'::text),
           ('DELETE'::text), ('TRUNCATE'::text), ('REFERENCES'::text),
           ('TRIGGER'::text)
  ) required(privilege_name)
  WHERE n.nspname = 'public'
    AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
    AND pg_catalog.has_table_privilege(
          role_row.oid, c.oid, required.privilege_name
        )
  LIMIT 1;
  IF FOUND THEN
    RAISE EXCEPTION '051 direct relation privilege rejected: %.%',
      leaked_privilege.relname, leaked_privilege.privilege_name;
  END IF;

  SELECT c.relname, required.privilege_name
    INTO leaked_privilege
  FROM pg_catalog.pg_class c
  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
  CROSS JOIN (
    VALUES ('USAGE'::text), ('SELECT'::text), ('UPDATE'::text)
  ) required(privilege_name)
  WHERE n.nspname = 'public'
    AND c.relkind = 'S'
    AND pg_catalog.has_sequence_privilege(
          role_row.oid, c.oid, required.privilege_name
        )
  LIMIT 1;
  IF FOUND THEN
    RAISE EXCEPTION '051 direct sequence privilege rejected: %.%',
      leaked_privilege.relname, leaked_privilege.privilege_name;
  END IF;
END
$preflight$;

CREATE TABLE IF NOT EXISTS public.n6_virtual_quote_run_identity (
  quote_run_identity_id BIGINT GENERATED ALWAYS AS IDENTITY,
  quote_run_id BIGINT NOT NULL
    CONSTRAINT n6_virtual_quote_run_identity_run_fk
    REFERENCES public.n6_virtual_quote_run(quote_run_id),
  virtual_quote_snapshot_id BIGINT NOT NULL
    CONSTRAINT n6_virtual_quote_run_identity_snapshot_fk
    REFERENCES public.n6_virtual_quote_snapshot(virtual_quote_snapshot_id),
  identity_key TEXT NOT NULL CONSTRAINT n6_virtual_quote_run_identity_key_ck CHECK (
    identity_key ~ '^stock:(SH|SZ|BJ):[0-9]{6}$'
  ),
  quality_status TEXT NOT NULL CONSTRAINT n6_virtual_quote_run_identity_status_ck CHECK (
    quality_status IN ('passed', 'not_ready')
  ),
  quality_reason TEXT NOT NULL CONSTRAINT n6_virtual_quote_run_identity_reason_ck CHECK (quality_reason <> ''),
  created_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
  CONSTRAINT n6_virtual_quote_run_identity_pk PRIMARY KEY (quote_run_identity_id),
  CONSTRAINT n6_virtual_quote_run_identity_run_key UNIQUE (quote_run_id, identity_key)
);

CREATE INDEX IF NOT EXISTS idx_051_n6_virtual_quote_run_identity_snapshot
ON public.n6_virtual_quote_run_identity(virtual_quote_snapshot_id);

DO $evidence_schema_preflight$
DECLARE
  relation_oid oid;
  relation_owner text;
  actual_columns text;
  constraints_exact boolean;
  constraint_count integer;
  actual_index text;
  index_owner text;
  index_kind "char";
  index_valid boolean;
  index_ready boolean;
BEGIN
  SELECT c.oid, owner.rolname
    INTO relation_oid, relation_owner
  FROM pg_catalog.pg_class c
  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_catalog.pg_roles owner ON owner.oid = c.relowner
  WHERE n.nspname = 'public'
    AND c.relname = 'n6_virtual_quote_run_identity'
    AND c.relkind = 'r';
  IF relation_oid IS NULL OR relation_owner <> current_user THEN
    RAISE EXCEPTION '051 evidence table owner/kind drift';
  END IF;

  SELECT pg_catalog.string_agg(
           a.attname || ':' || pg_catalog.format_type(a.atttypid, a.atttypmod)
           || ':' || a.attnotnull::text || ':' || a.attidentity::text
           || ':' || COALESCE(pg_catalog.pg_get_expr(d.adbin, d.adrelid), ''),
           '|' ORDER BY a.attnum
         )
    INTO actual_columns
  FROM pg_catalog.pg_attribute a
  LEFT JOIN pg_catalog.pg_attrdef d
    ON d.adrelid = a.attrelid AND d.adnum = a.attnum
  WHERE a.attrelid = relation_oid
    AND a.attnum > 0
    AND NOT a.attisdropped;
  IF actual_columns <> (
    'quote_run_identity_id:bigint:true:a:|'
    'quote_run_id:bigint:true::|'
    'virtual_quote_snapshot_id:bigint:true::|'
    'identity_key:text:true::|quality_status:text:true::|'
    'quality_reason:text:true::|'
    'created_at:timestamp with time zone:true::now()'
  ) THEN
    RAISE EXCEPTION '051 evidence table column drift';
  END IF;

  SELECT pg_catalog.bool_and(
           NOT con.condeferrable
           AND NOT con.condeferred
           AND con.convalidated
           AND CASE con.conname
             WHEN 'n6_virtual_quote_run_identity_pk' THEN
               con.contype = 'p'
               AND pg_catalog.pg_get_constraintdef(con.oid, false) =
                     'PRIMARY KEY (quote_run_identity_id)'
             WHEN 'n6_virtual_quote_run_identity_run_key' THEN
               con.contype = 'u'
               AND pg_catalog.pg_get_constraintdef(con.oid, false) =
                     'UNIQUE (quote_run_id, identity_key)'
             WHEN 'n6_virtual_quote_run_identity_run_fk' THEN
               con.contype = 'f'
               AND pg_catalog.pg_get_constraintdef(con.oid, false) =
                     'FOREIGN KEY (quote_run_id) REFERENCES n6_virtual_quote_run(quote_run_id)'
             WHEN 'n6_virtual_quote_run_identity_snapshot_fk' THEN
               con.contype = 'f'
               AND pg_catalog.pg_get_constraintdef(con.oid, false) =
                     'FOREIGN KEY (virtual_quote_snapshot_id) REFERENCES n6_virtual_quote_snapshot(virtual_quote_snapshot_id)'
             WHEN 'n6_virtual_quote_run_identity_key_ck' THEN
               con.contype = 'c'
               AND pg_catalog.pg_get_constraintdef(con.oid, false) =
                     'CHECK ((identity_key ~ ''^stock:(SH|SZ|BJ):[0-9]{6}$''::text))'
             WHEN 'n6_virtual_quote_run_identity_status_ck' THEN
               con.contype = 'c'
               AND pg_catalog.pg_get_constraintdef(con.oid, false) =
                     'CHECK ((quality_status = ANY (ARRAY[''passed''::text, ''not_ready''::text])))'
             WHEN 'n6_virtual_quote_run_identity_reason_ck' THEN
               con.contype = 'c'
               AND pg_catalog.pg_get_constraintdef(con.oid, false) =
                     'CHECK ((quality_reason <> ''''::text))'
             ELSE false
           END
         ),
         count(*)::integer
    INTO constraints_exact, constraint_count
  FROM pg_catalog.pg_constraint con
  WHERE con.conrelid = relation_oid;
  IF constraints_exact IS DISTINCT FROM true OR constraint_count <> 7 THEN
    RAISE EXCEPTION '051 evidence table constraint drift';
  END IF;

  SELECT pg_catalog.pg_get_indexdef(index_class.oid),
         owner.rolname, index_class.relkind,
         index_row.indisvalid, index_row.indisready
    INTO actual_index, index_owner, index_kind, index_valid, index_ready
  FROM pg_catalog.pg_class index_class
  JOIN pg_catalog.pg_namespace n ON n.oid = index_class.relnamespace
  JOIN pg_catalog.pg_roles owner ON owner.oid = index_class.relowner
  JOIN pg_catalog.pg_index index_row ON index_row.indexrelid = index_class.oid
  WHERE n.nspname = 'public'
    AND index_class.relname =
          'idx_051_n6_virtual_quote_run_identity_snapshot';
  IF index_owner <> current_user
     OR index_kind <> 'i'
     OR index_valid IS DISTINCT FROM true
     OR index_ready IS DISTINCT FROM true
     OR actual_index <>
       'CREATE INDEX idx_051_n6_virtual_quote_run_identity_snapshot ON public.n6_virtual_quote_run_identity USING btree (virtual_quote_snapshot_id)' THEN
    RAISE EXCEPTION '051 evidence index drift';
  END IF;
END
$evidence_schema_preflight$;

CREATE OR REPLACE FUNCTION public.n6_quote_writer_is_open_trade_date(
  p_trade_date text
)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
  SELECT CASE
    WHEN p_trade_date !~ '^[0-9]{8}$' THEN false
    ELSE EXISTS (
      SELECT 1
      FROM public.common_trade_calendar c
      WHERE c.trade_date = p_trade_date
        AND c.is_open = true
    )
  END
$function$;

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

CREATE OR REPLACE FUNCTION public.n6_quote_writer_pending_scope(
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
  SELECT scope.principal_id, scope.principal_type,
         scope.virtual_account_id, scope.identity_key
  FROM public.n6_quote_writer_scope(p_quote_minute) scope
  WHERE NOT EXISTS (
      SELECT 1
      FROM public.n6_virtual_quote_snapshot existing
      WHERE existing.identity_key = scope.identity_key
        AND existing.quote_minute = p_quote_minute
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

REVOKE EXECUTE ON FUNCTION
  public.n6_quote_writer_is_open_trade_date(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION
  public.n6_quote_writer_scope(timestamptz) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION
  public.n6_quote_writer_pending_scope(timestamptz) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION
  public.n6_quote_writer_save_run(
    bigint,text,timestamptz,text,integer,integer,integer,
    timestamptz,timestamptz,jsonb,jsonb
  ) FROM PUBLIC;

GRANT USAGE ON SCHEMA public TO n6_quote_writer;
GRANT EXECUTE ON FUNCTION
  public.n6_quote_writer_is_open_trade_date(text) TO n6_quote_writer;
GRANT EXECUTE ON FUNCTION
  public.n6_quote_writer_scope(timestamptz) TO n6_quote_writer;
GRANT EXECUTE ON FUNCTION
  public.n6_quote_writer_pending_scope(timestamptz) TO n6_quote_writer;
GRANT EXECUTE ON FUNCTION
  public.n6_quote_writer_save_run(
    bigint,text,timestamptz,text,integer,integer,integer,
    timestamptz,timestamptz,jsonb,jsonb
  ) TO n6_quote_writer;

COMMIT;
