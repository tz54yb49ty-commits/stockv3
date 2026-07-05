# N4 Trigger Rule Spec v4 Full-Lineage V3-V4 Diff

Result: `FULL_DIFF_PASS`

```json
{
  "v3_plan_count": 10167,
  "v4_plan_count": 5222,
  "false_positive_count": 656,
  "false_negative_count": 267,
  "changed_count": 0,
  "interpretation": "false positives/negatives are shadow comparisons between production v3 plans and shadow v4 outcomes."
}
```

## False Positive Samples

```json
[
  {
    "comparison_key": "board|board:TDX:880214|sell|SELL:Y,Q,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880220|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880501|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880516|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880549|sell|SELL:Y,Q,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880553|sell|SELL:Y,Q,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880555|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880557|sell|SELL:Y|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880567|sell|SELL:Y|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880568|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880592|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880610|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880613|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880614|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880618|sell|SELL:Y,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880642|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880644|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880645|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880649|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880667|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880668|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880717|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880718|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880724|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880747|sell|SELL:Y|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880750|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880796|sell|SELL:Y,Q,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880797|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880910|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880911|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880926|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880940|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880941|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880955|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880959|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880971|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881008|sell|SELL:Y,Q,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881019|sell|SELL:Y,Q,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881026|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881091|sell|SELL:Y|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881106|sell|SELL:Y,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881140|sell|SELL:Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881162|sell|SELL:Y|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881184|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881247|sell|SELL:Y|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881257|sell|SELL:FULL|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "quality_blocked"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": [
      "full_semantics_blocked"
    ]
  },
  {
    "comparison_key": "board|board:TDX:881344|sell|SELL:Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881384|sell|SELL:Y|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881386|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881389|sell|SELL:Y,Q,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881452|sell|SELL:Y|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881459|sell|SELL:Y,Q,M,W|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881467|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881471|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881476|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "index|index:SZ:399322|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "index|index:SZ:399328|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "index|index:SZ:399438|sell|SELL:Y,Q,M,W|S_SELL",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "stock|stock:SH:600006|buy|BUY:Y,Q,M,W,D|B_BUY",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "stock|stock:SH:600021|buy|BUY:Y,Q,W,D|B_BUY",
    "v3_event_types": [
      "TriggerMatched",
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "no_op"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  }
]
```

## False Negative Samples

```json
[
  {
    "comparison_key": "board|board:TDX:880205|buy|BUY_HINT|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880216|buy|BUY_HINT|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880221|buy|BUY_HINT|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880224|buy|BUY_HINT|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880228|buy|BUY_HINT|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880590|sell|SELL:Y,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880611|sell|SELL:Y,Q,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880628|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880634|buy|BUY_HINT|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880637|buy|BUY_HINT|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880655|buy|BUY_HINT|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880711|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880713|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880761|buy|BUY_HINT|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880761|sell|SELL:Y,Q,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880765|sell|SELL:Y,Q,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880914|sell|SELL:Y,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880949|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880968|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880974|sell|SELL:Y,Q,W,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:880975|buy|BUY_HINT|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881062|buy|BUY_HINT|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881078|buy|BUY_HINT|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881207|sell|SELL:Y,Q,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881215|sell|SELL:Y,Q,W,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881227|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881288|sell|SELL:Y|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881290|sell|SELL:Y,Q,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881293|sell|SELL:Y,Q|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881370|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881376|sell|SELL:Y,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881415|sell|SELL:Y,W,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881436|buy|BUY_HINT|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "board|board:TDX:881470|buy|BUY_HINT|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "index|index:SH:000015|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "index|index:SH:000016|sell|SELL:Y,Q,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "index|index:SH:000043|sell|SELL:Y,Q,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "index|index:SH:000044|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "index|index:SH:000122|sell|SELL:Y,W,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "index|index:SH:000300|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "index|index:SH:000687|sell|SELL:Y,Q,M,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "index|index:SH:000689|sell|SELL:Y,Q,M,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "index|index:SH:000699|sell|SELL:Y,Q,M,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "index|index:SH:000847|sell|SELL:Y,Q,M,W,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "index|index:SH:000852|sell|SELL:Y,Q,D|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "stock|stock:SH:600008|buy|BUY:Y,Q|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "stock|stock:SH:600012|buy|BUY:Y,Q,D|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "stock|stock:SH:600036|sell|SELL_HINT|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "stock|stock:SH:600060|buy|BUY:Q,D|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "stock|stock:SH:600157|buy|BUY:Q,D|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "stock|stock:SH:600162|buy|BUY:Y,D|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "stock|stock:SH:600184|buy|BUY:W,D|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "stock|stock:SH:600186|buy|BUY_HINT|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "stock|stock:SH:600219|buy|BUY:Y,Q,M,W|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "stock|stock:SH:600246|buy|BUY_HINT|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "stock|stock:SH:600267|buy|BUY:Y,Q,M,W,D|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "stock|stock:SH:600282|sell|SELL_HINT|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "stock|stock:SH:600285|sell|SELL_HINT|S_SELL",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "stock|stock:SH:600292|buy|BUY:Y,Q,M,W,D|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  },
  {
    "comparison_key": "stock|stock:SH:600330|buy|BUY:W,D|B_BUY",
    "v3_event_types": [
      "TriggerPendingMarketData"
    ],
    "v4_outcomes": [
      "matched"
    ],
    "v4_pending_reasons": [],
    "v4_blocked_reasons": []
  }
]
```
