# N1 Stock Financial 002831 TDX Full Line-Item Source Proof

Scope:
- layer_role=N1_ingestion
- source_trade_date=20260615
- stock_identity_key=stock:SZ:002831
- ts_code=002831.SZ
- name=裕同科技

Source proof:
- source_type=tdx_financial_package
- source_name=TDX财务包
- source_capture_method=operator_captured_target_machine_tdx_financial_package_values
- report_period=20260331
- announcement_date=20260428
- as-of pass: 20260428 <= 20260615

Line items:
- operating_revenue=3793342067.38
- operating_cost=2842927728.61
- tax_surcharges=25840844.90
- selling_expense=114217020.19
- admin_expense=280204649.99
- rd_expense=168821115.69
- interest_expense=19744658
- finance_expense=68186034.99
- finance_expense_used_as_interest=false
- operating_cashflow=657719040

Expected metrics:
- report_core_profit=341586050
- cash_realization_rate=1.9254856573
- core_profit_ttm=1940382164
- pe_core=20.2506996374
- revenue_yoy_pct=2.55
- core_profit_yoy_pct=57.1302091953
- core_gt_revenue_yoy=true
- revenue_growth_streak_q=9
- core_growth_streak_q=4
- core_gt_revenue_streak_q=2
- forecast_type=null
- score=87

TTM proof:
- 20260331=341586050
- 20251231=509246816
- 20250930=735327224
- 20250630=354222074
- sum=1940382164

PE proof:
- stock_daily_basic.total_mv=3929409.6385
- unit=ten_thousand_yuan
- total_mv_yuan=39294096385
- pe_core=20.2506996374
