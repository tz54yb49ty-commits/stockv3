-- Roll back the 051 quote-writer executable authority only.
-- REVIEW ONLY: do not execute without a separate rollback gate.
-- Quote snapshots, runs, and run-identity history are intentionally preserved.

BEGIN;

REVOKE EXECUTE ON FUNCTION
  public.n6_quote_writer_is_open_trade_date(text) FROM n6_quote_writer;
REVOKE EXECUTE ON FUNCTION
  public.n6_quote_writer_scope(timestamptz) FROM n6_quote_writer;
REVOKE EXECUTE ON FUNCTION
  public.n6_quote_writer_pending_scope(timestamptz) FROM n6_quote_writer;
REVOKE EXECUTE ON FUNCTION
  public.n6_quote_writer_save_run(
    bigint,text,timestamptz,text,integer,integer,integer,
    timestamptz,timestamptz,jsonb,jsonb
  ) FROM n6_quote_writer;
REVOKE USAGE ON SCHEMA public FROM n6_quote_writer;

DROP FUNCTION IF EXISTS public.n6_quote_writer_save_run(
  bigint,text,timestamptz,text,integer,integer,integer,
  timestamptz,timestamptz,jsonb,jsonb
);
DROP FUNCTION IF EXISTS public.n6_quote_writer_pending_scope(timestamptz);
DROP FUNCTION IF EXISTS public.n6_quote_writer_scope(timestamptz);
DROP FUNCTION IF EXISTS public.n6_quote_writer_is_open_trade_date(text);

-- Deliberately do not drop public.n6_virtual_quote_run_identity.
-- It is append-only quote evidence and rollback must preserve quote history.

COMMIT;
