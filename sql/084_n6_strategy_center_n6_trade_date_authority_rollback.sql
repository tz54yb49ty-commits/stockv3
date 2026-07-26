-- Fail-closed rollback for 084.
--
-- Rollback is permitted only before a current-authority pending revision or
-- any current-authority Strategy Center projection/change depends on 084.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

SELECT pg_catalog.pg_advisory_xact_lock(
  pg_catalog.hashtextextended(
    'n6_strategy_center_n6_trade_date_authority_084_v1', 0
  )
);

DO $preflight$
DECLARE
  authority jsonb;
  authority_trade_date date;
  function_signature text;
  installation jsonb;
BEGIN
  IF pg_catalog.current_database() IS DISTINCT FROM 'ashare_v3'
     OR CURRENT_USER IS DISTINCT FROM 'ashare_v3_user'
     OR SESSION_USER IS DISTINCT FROM 'ashare_v3_user' THEN
    RAISE EXCEPTION '084 rollback owner migration identity rejected';
  END IF;
  IF pg_catalog.to_regprocedure(
       'public.n6_strategy_center_trade_date_authority_v1()'
     ) IS NULL THEN
    RAISE EXCEPTION '084 rollback authority helper missing';
  END IF;
  installation := pg_catalog.obj_description(
    'public.n6_strategy_center_trade_date_authority_v1()'
      ::pg_catalog.regprocedure,
    'pg_proc'
  )::jsonb;
  IF installation->>'migration_id' IS DISTINCT FROM
       '084_n6_strategy_center_n6_trade_date_authority_v1'
     OR pg_catalog.jsonb_typeof(
          installation->'installed_authority'
        ) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION '084 rollback installation authority invalid';
  END IF;
  authority := installation->'installed_authority';
  authority_trade_date := pg_catalog.to_date(
    authority->>'for_trade_date', 'YYYYMMDD'
  );
  IF authority_trade_date IS NULL
     OR authority->>'for_trade_date' !~ '^[0-9]{8}$'
     OR pg_catalog.to_char(
          authority_trade_date, 'YYYYMMDD'
        ) IS DISTINCT FROM authority->>'for_trade_date' THEN
    RAISE EXCEPTION '084 rollback authority date invalid';
  END IF;
  IF EXISTS (
       SELECT 1
       FROM public.n6_user_strategy_selection_revision revision
       WHERE revision.effective_trade_date >= authority_trade_date
     )
     OR EXISTS (
       SELECT 1
       FROM public.n6_strategy_match_projection projection
       WHERE projection.trade_date >= authority_trade_date
     )
     OR EXISTS (
       SELECT 1
       FROM public.n6_strategy_observation_projection observation
       WHERE observation.trade_date >= authority_trade_date
     )
     OR EXISTS (
       SELECT 1
       FROM public.n6_strategy_match_change change_row
       WHERE change_row.trade_date >= authority_trade_date
     ) THEN
    RAISE EXCEPTION '084 rollback blocked by N6 authority dependencies';
  END IF;
  FOREACH function_signature IN ARRAY ARRAY[
    'public.n6_strategy_default_selection_on_principal_insert()',
    'public.n6_btrack_strategy_center_state(text)',
    'public.n6_btrack_strategy_selection_put(text,text[],bigint,text)',
    'public.n6_strategy_center_compensate_revision_v1('
      'bigint,text,bigint,bigint,bigint,text,bigint,date,text)',
    'public.n6_strategy_center_abandon_pending_v2('
      'bigint,text,bigint,bigint,bigint,date,text)'
  ] LOOP
    IF pg_catalog.to_regprocedure(function_signature) IS NULL
       OR pg_catalog.strpos(
            pg_catalog.pg_get_functiondef(
              pg_catalog.to_regprocedure(function_signature)
            ),
            'n6_strategy_center_trade_date_authority_v1'
          ) = 0
       OR pg_catalog.strpos(
            pg_catalog.pg_get_functiondef(
              pg_catalog.to_regprocedure(function_signature)
            ),
            'common_trade_calendar'
          ) > 0 THEN
      RAISE EXCEPTION '084 rollback active function drift: %',
        function_signature;
    END IF;
  END LOOP;
  IF pg_catalog.has_table_privilege(
       'n6_strategy_worker',
       'public.common_trade_calendar',
       'SELECT'
     ) THEN
    RAISE EXCEPTION '084 rollback worker ACL baseline drift';
  END IF;
END
$preflight$;

DO $rewrite$
DECLARE
  function_signature text;
  function_definition text;
  rewritten_definition text;
  old_fragment text;
  new_fragment text;
BEGIN
  FOREACH function_signature IN ARRAY ARRAY[
    'public.n6_strategy_default_selection_on_principal_insert()',
    'public.n6_btrack_strategy_center_state(text)',
    'public.n6_btrack_strategy_selection_put(text,text[],bigint,text)',
    'public.n6_strategy_center_compensate_revision_v1('
      'bigint,text,bigint,bigint,bigint,text,bigint,date,text)',
    'public.n6_strategy_center_abandon_pending_v2('
      'bigint,text,bigint,bigint,bigint,date,text)'
  ] LOOP
    SELECT pg_catalog.pg_get_functiondef(
             pg_catalog.to_regprocedure(function_signature)
           )
      INTO function_definition;
    IF function_signature =
       'public.n6_btrack_strategy_center_state(text)' THEN
      old_fragment := $old$
  ), n6_trade_date_authority AS MATERIALIZED (
    SELECT public.n6_strategy_center_trade_date_authority_v1() AS value
  ), resolved_trade_date AS (
    SELECT pg_catalog.to_date(
             authority.value->>'for_trade_date', 'YYYYMMDD'
           ) AS value
    FROM n6_trade_date_authority authority
$old$;
      new_fragment := $new$
  ), resolved_trade_date AS (
    SELECT max(pg_catalog.to_date(calendar.trade_date, 'YYYYMMDD')) AS value
    FROM public.common_trade_calendar calendar
    WHERE calendar.is_open = true
      AND calendar.trade_date ~ '^[0-9]{8}$'
      AND calendar.trade_date <= pg_catalog.to_char(
            pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai',
            'YYYYMMDD'
          )
$new$;
    ELSIF function_signature IN (
      'public.n6_strategy_default_selection_on_principal_insert()',
      'public.n6_btrack_strategy_selection_put(text,text[],bigint,text)'
    ) THEN
      old_fragment := $old$
  effective_trade_date := pg_catalog.to_date(
    public.n6_strategy_center_trade_date_authority_v1()
      ->>'for_trade_date',
    'YYYYMMDD'
  );
$old$;
      new_fragment := $new$
  SELECT min(pg_catalog.to_date(calendar.trade_date, 'YYYYMMDD'))
    INTO effective_trade_date
  FROM public.common_trade_calendar calendar
  WHERE calendar.is_open = true
    AND calendar.trade_date ~ '^[0-9]{8}$'
    AND calendar.trade_date >= pg_catalog.to_char(
          pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai',
          'YYYYMMDD'
        );
$new$;
    ELSIF function_signature IN (
      'public.n6_strategy_center_compensate_revision_v1('
        'bigint,text,bigint,bigint,bigint,text,bigint,date,text)',
      'public.n6_strategy_center_abandon_pending_v2('
        'bigint,text,bigint,bigint,bigint,date,text)'
    ) THEN
      old_fragment := $old$
  IF p_trade_date IS NULL
     OR p_trade_date IS DISTINCT FROM pg_catalog.to_date(
          public.n6_strategy_center_trade_date_authority_v1()
            ->>'for_trade_date',
          'YYYYMMDD'
        ) THEN
$old$;
      new_fragment := $new$
  IF p_trade_date IS NULL
     OR p_trade_date IS DISTINCT FROM (
       pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai'
     )::date
     OR NOT EXISTS (
       SELECT 1
       FROM public.common_trade_calendar calendar
       WHERE calendar.trade_date = pg_catalog.to_char(
               p_trade_date, 'YYYYMMDD'
             )
         AND calendar.is_open = true
     ) THEN
$new$;
    ELSE
      RAISE EXCEPTION '084 rollback unsupported function: %',
        function_signature;
    END IF;
    rewritten_definition := pg_catalog.replace(
      function_definition, old_fragment, new_fragment
    );
    IF rewritten_definition IS NOT DISTINCT FROM function_definition
       OR pg_catalog.strpos(
            rewritten_definition, 'common_trade_calendar'
          ) = 0
       OR pg_catalog.strpos(
            rewritten_definition,
            'n6_strategy_center_trade_date_authority_v1'
          ) > 0 THEN
      RAISE EXCEPTION '084 rollback function rewrite failed: %',
        function_signature;
    END IF;
    EXECUTE rewritten_definition;
  END LOOP;
END
$rewrite$;

GRANT SELECT ON TABLE public.common_trade_calendar
TO n6_strategy_worker;

DROP FUNCTION public.n6_strategy_center_trade_date_authority_v1();

DO $postflight$
DECLARE
  function_signature text;
  function_definition text;
BEGIN
  IF pg_catalog.to_regprocedure(
       'public.n6_strategy_center_trade_date_authority_v1()'
     ) IS NOT NULL
     OR NOT pg_catalog.has_table_privilege(
          'n6_strategy_worker',
          'public.common_trade_calendar',
          'SELECT'
        ) THEN
    RAISE EXCEPTION '084 rollback helper or ACL postflight failed';
  END IF;
  FOREACH function_signature IN ARRAY ARRAY[
    'public.n6_strategy_default_selection_on_principal_insert()',
    'public.n6_btrack_strategy_center_state(text)',
    'public.n6_btrack_strategy_selection_put(text,text[],bigint,text)',
    'public.n6_strategy_center_compensate_revision_v1('
      'bigint,text,bigint,bigint,bigint,text,bigint,date,text)',
    'public.n6_strategy_center_abandon_pending_v2('
      'bigint,text,bigint,bigint,bigint,date,text)'
  ] LOOP
    function_definition := pg_catalog.pg_get_functiondef(
      pg_catalog.to_regprocedure(function_signature)
    );
    IF pg_catalog.strpos(
         function_definition, 'common_trade_calendar'
       ) = 0
       OR pg_catalog.strpos(
            function_definition,
            'n6_strategy_center_trade_date_authority_v1'
          ) > 0 THEN
      RAISE EXCEPTION '084 rollback active function postflight failed: %',
        function_signature;
    END IF;
  END LOOP;
END
$postflight$;

COMMIT;
