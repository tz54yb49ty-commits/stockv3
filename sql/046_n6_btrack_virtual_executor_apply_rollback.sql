-- Roll back only the 046 interface and grant. Business history and 041-045 remain.
-- Do not execute without a separate rollback gate.

BEGIN;

REVOKE EXECUTE ON FUNCTION public.n6_executor_apply_claimed_proposal(bigint,text)
FROM n6_virtual_executor;
DROP FUNCTION IF EXISTS public.n6_executor_apply_claimed_proposal(bigint,text);

COMMIT;
