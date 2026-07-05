-- N4 trigger context localization after N2 trigger baseline repair.
-- BLOCKED no-op rollback artifact.
--
-- No N4 context localization rows were written in this gate because the N4
-- preflight blocked before execute. This SQL intentionally hard-fails so it
-- cannot be mistaken for a scoped delete rollback.

DO $$
BEGIN
  RAISE EXCEPTION 'N4 context localization rollback is not applicable: gate blocked before N4 context rows were written.';
END $$;
