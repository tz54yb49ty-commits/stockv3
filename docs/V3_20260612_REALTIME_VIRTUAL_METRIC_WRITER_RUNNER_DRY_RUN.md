# V3 20260612 Realtime Virtual Metric Writer Runner Dry Run

Result: DRY_RUN_PASS

Planned rows:

```text
total=100
metric_ready=100
metric_not_ready=0
B_BUY=76
S_SELL=24
```

Source fact proof:

```text
stock_minute_bar_1m=705120
index_minute_bar_1m=90144
board_minute_bar_1m=56832
subscription rows=2676
subscription objects=2082
source condition status=passed_active
```

This dry-run did not write DB rows, did not execute wrapper/N4/N5, and did not
consume or update outbox/inbox/checkpoint.
