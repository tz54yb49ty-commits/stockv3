BEGIN;

DO $gate$
BEGIN
  IF SESSION_USER <> 'ashare_v3_user'
     OR CURRENT_USER <> 'ashare_v3_user' THEN
    RAISE EXCEPTION '058_rollback_identity_mismatch';
  END IF;
  IF pg_catalog.to_regprocedure(
       'public.n6_ai_agent_context_load_v2(text,date,integer,text)'
     ) IS NULL THEN
    RAISE EXCEPTION '058_not_applied';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.n6_ai_context_snapshot snapshot
    WHERE snapshot.knowledge_bundle_hash IS NOT NULL
       OR snapshot.universe_snapshot_hash IS NOT NULL
       OR snapshot.memory_snapshot_hash IS NOT NULL
       OR snapshot.workset_hash IS NOT NULL
  ) THEN
    RAISE EXCEPTION '058_rollback_blocked_by_frozen_context_history';
  END IF;
END
$gate$;

REVOKE EXECUTE ON FUNCTION public.n6_ai_agent_context_load_v2(
  text,date,integer,text
) FROM n6_ai_agent;
DROP FUNCTION public.n6_ai_agent_context_load_v2(
  text,date,integer,text
);
GRANT EXECUTE ON FUNCTION public.n6_ai_agent_context_load(
  text,date,integer
) TO n6_ai_agent;

ALTER TABLE public.n6_ai_context_snapshot
  DROP CONSTRAINT n6_ai_context_snapshot_058_hashes_ck,
  DROP COLUMN workset_hash,
  DROP COLUMN memory_snapshot_hash,
  DROP COLUMN universe_snapshot_hash,
  DROP COLUMN knowledge_bundle_hash;

COMMIT;
