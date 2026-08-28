BEGIN;

GRANT UPDATE
ON stock_n3_previous_day_context,
   index_n3_previous_day_context,
   board_n3_previous_day_context
TO ashare_v3_user;

COMMIT;
