from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from ashare_v3.user.ai_agent import (
    AUTONOMOUS_FEATURE_FLAG,
    CONTEXT_KNOWLEDGE_BUNDLE_SHA256,
    CONTEXT_LOAD_SQL,
    DAILY_SUMMARY_RECORD_SQL,
    DECISION_RECORD_SQL,
    KNOWLEDGE_BUNDLE_SHA256,
    PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV,
    PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256,
    PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV,
    PROPOSAL_CREATE_SQL,
    SHADOW_FEATURE_FLAG,
    STRATEGY_EVALUATION_RECORD_SQL,
    ConservativeRiskPolicy,
    DISPLAY_TIMEZONE,
    DisabledModelAdapter,
    FunctionOnlyAIAgentRepository,
    evaluate_conservative_risk,
    five_minute_bucket,
    risk_adjusted_score,
    run_agent_once,
    run_daily_summary_once,
    validate_context,
    validate_model_output,
)
from ashare_v3.user.ai_investor_strategy_policy_v1 import (
    KNOWLEDGE_BUNDLE_SHA256 as STRATEGY_KNOWLEDGE_BUNDLE_SHA256,
    KNOWLEDGE_BUNDLE_VERSION as STRATEGY_KNOWLEDGE_BUNDLE_VERSION,
    POLICY_DOCUMENT_SHA256 as STRATEGY_POLICY_DOCUMENT_SHA256,
    POLICY_VERSION as STRATEGY_POLICY_VERSION,
)
from ashare_v3.user.n6_ai_deepseek_adapter import (
    DEEPSEEK_EGRESS_MODE_ENV,
    DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW,
)
from scripts.run_n6_ai_agent_once import (
    run_from_args as run_agent_from_args,
)
from scripts.run_n6_ai_daily_summary_once import (
    run_from_args as run_summary_from_args,
)
from scripts.run_n6_ai_strategy_policy_once import (
    STRATEGY_POLICY_SHADOW_FEATURE_FLAG,
    _default_connection_factory as strategy_connection_factory,
    build_parser as build_strategy_parser,
    run_from_args as run_strategy_from_args,
)


NOW = datetime(2026, 7, 20, 10, 2, 31, tzinfo=DISPLAY_TIMEZONE)
TRADE_DATE = date(2026, 7, 20)
STRATEGY_HASH = "a" * 64
ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_MANIFEST = (
    ROOT
    / "docs/N6_AI_PRODUCTION_KNOWLEDGE_BUNDLE_MANIFEST_V1.json"
)


def agent_environment() -> dict[str, str]:
    return {
        SHADOW_FEATURE_FLAG: "1",
        "PGSERVICE": "n6_ai_agent",
        "PGSERVICEFILE": "/tmp/service",
        "PGPASSFILE": "/tmp/pass",
        PRODUCTION_KNOWLEDGE_MANIFEST_FILE_ENV: str(
            PRODUCTION_MANIFEST
        ),
        PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV: (
            PRODUCTION_KNOWLEDGE_MANIFEST_FILE_SHA256
        ),
    }


def context_payload(**overrides):
    payload = {
        "ok": True,
        "status": "ready",
        "context_snapshot_id": 41,
        "decision_input_hash": "d" * 64,
        "knowledge_bundle_hash": CONTEXT_KNOWLEDGE_BUNDLE_SHA256,
        "universe_snapshot_hash": "a" * 64,
        "memory_snapshot_hash": "b" * 64,
        "workset_hash": "c" * 64,
        "for_trade_date": "20260720",
        "signals": [
            {
                "user_signal_projection_id": 101,
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "direction": "buy",
                "for_trade_date": "20260720",
                "ai_eligible": True,
                "action_state": "eligible",
                "event_time": "2026-07-20T10:00:00+08:00",
                "reason_fields": {
                    "condition_key": "BUY:Y,M,W,D",
                    "score": "80",
                },
            },
            {
                "user_signal_projection_id": 102,
                "asset_kind": "stock",
                "identity_key": "stock:SH:600001",
                "direction": "sell",
                "for_trade_date": "20260720",
                "ai_eligible": True,
                "action_state": "executed",
                "event_time": "2026-07-20T10:01:00+08:00",
                "reason_fields": {"condition_key": "SELL:D"},
            },
        ],
        "market_context": [
            {
                "user_signal_projection_id": 301,
                "asset_kind": "index",
                "identity_key": "index:SH:000300",
                "direction": "buy",
                "for_trade_date": "20260720",
                "context_only": True,
                "action_state": "eligible",
                "event_time": "2026-07-20T10:00:00+08:00",
                "reason_fields": {"condition_key": "BUY_HINT:D"},
            },
            {
                "user_signal_projection_id": 302,
                "asset_kind": "board",
                "identity_key": "board:TDX:881001",
                "direction": "sell",
                "for_trade_date": "20260720",
                "context_only": True,
                "action_state": "executed",
                "event_time": "2026-07-20T10:01:00+08:00",
                "reason_fields": {"condition_key": "SELL_HINT:D"},
            },
        ],
        "positions": [
            {
                "virtual_position_id": 201,
                "asset_kind": "stock",
                "identity_key": "stock:SH:600001",
                "quantity": "1000",
                "available_quantity": "800",
                "current_price": "100",
                "quote_minute": "2026-07-20T10:02:00+08:00",
                "quote_quality_status": "passed",
                "market_value": "100000",
                "position_status": "open_virtual",
                "stop_loss_status": "frozen",
            }
        ],
        "portfolio": {
            "cash_balance": "99000000",
            "total_equity": "100000000",
            "market_value": "100000",
            "max_drawdown_pct": "1.2",
            "daily_new_buy_count": 0,
            "autonomous_trade_day_no": 4,
        },
        "strategy": {
            "strategy_id": 7,
            "strategy_version": "ai-v1",
            "strategy_hash": STRATEGY_HASH,
        },
        "daily_metrics": {
            "net_return_pct": "1.25",
            "max_drawdown_pct": "0.50",
            "turnover_pct": "10",
            "decision_count": 4,
            "buy_trade_count": 1,
            "sell_trade_count": 1,
            "highlights": ["严格遵守当日信号"],
            "lessons": ["控制换手率"],
        },
    }
    payload.update(overrides)
    return payload


def buy_decision(**overrides):
    payload = {
        "decision_type": "buy",
        "identity_key": "stock:SH:600000",
        "source_signal_projection_id": 101,
        "source_virtual_position_id": None,
        "confidence": "0.80",
        "reason_summary": "当日N6买入信号通过且组合风险可控。",
        "evidence": ["projection:101", "current_trade_date"],
        "counter_evidence": ["市场波动可能扩大"],
        "risk_assessment": {
            "trigger": "signal",
            "level": "medium",
            "summary": "等待服务端风险策略复核。",
        },
        "strategy_candidate_notes": None,
    }
    payload.update(overrides)
    return payload


def sell_decision(**overrides):
    payload = {
        "decision_type": "sell",
        "identity_key": "stock:SH:600001",
        "source_signal_projection_id": 102,
        "source_virtual_position_id": 201,
        "confidence": "0.75",
        "reason_summary": "持仓对象出现当日N6卖出信号。",
        "evidence": ["projection:102", "position:201"],
        "counter_evidence": [],
        "risk_assessment": {
            "trigger": "signal",
            "level": "high",
            "summary": "卖出仅限T+1可用数量。",
        },
        "strategy_candidate_notes": "继续观察同类卖出信号。",
    }
    payload.update(overrides)
    return payload


class FakeAdapter:
    adapter_name = "fixture"
    model_version = "fixture-v1"

    def __init__(
        self, payload=None, *, raises=False, call_metadata=None
    ):
        self.payload = payload or buy_decision()
        self.raises = raises
        self.calls = []
        self.last_call_metadata = call_metadata or {}

    def generate_decision(self, context):
        self.calls.append(context)
        if self.raises:
            raise RuntimeError("secret provider detail")
        return self.payload


class FakeRepository:
    def __init__(
        self,
        context=None,
        *,
        server_risk_allowed=True,
        server_risk_reason="passed",
    ):
        self.context = context or context_payload()
        self.server_risk_allowed = server_risk_allowed
        self.server_risk_reason = server_risk_reason
        self.calls = []
        self.decision_payload = None
        self.proposal_payload = None
        self.summary_payload = None

    def load_context(self, **kwargs):
        self.calls.append(("load_context", kwargs))
        return self.context

    def record_shadow_decision(self, payload):
        self.calls.append(("record_shadow_decision", payload))
        self.decision_payload = payload
        return {
            "ok": True,
            "decision_id": 301,
            "server_risk_allowed": self.server_risk_allowed,
            "server_risk_reason": self.server_risk_reason,
        }

    def create_confirmed_proposal(self, payload):
        self.calls.append(("create_confirmed_proposal", payload))
        self.proposal_payload = payload
        return {"ok": True, "proposal_id": 401}

    def record_daily_summary(self, payload):
        self.calls.append(("record_daily_summary", payload))
        self.summary_payload = payload
        return {"ok": True, "daily_summary_id": 501}

    def record_strategy_evaluation(self, payload):
        self.calls.append(("record_strategy_evaluation", payload))
        return {"ok": True, "strategy_evaluation_id": 601}


class FakeStrategyCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.connection.calls.append(("execute", sql, params))

    def fetchone(self):
        return (self.connection.payload,)


class FakeStrategyConnection:
    def __init__(self, payload=None):
        self.payload = payload or {
            "ok": True,
            "status": "shadow_policy_evaluated",
            "policy_version": STRATEGY_POLICY_VERSION,
            "policy_document_sha256":
                STRATEGY_POLICY_DOCUMENT_SHA256,
            "knowledge_bundle_version":
                STRATEGY_KNOWLEDGE_BUNDLE_VERSION,
            "knowledge_bundle_sha256":
                STRATEGY_KNOWLEDGE_BUNDLE_SHA256,
            "candidate_rank_audit_count": 1,
            "strategy_action_audit_count": 0,
            "completed_strategy_episode_count": 2,
            "strategy_workset_hash": "a" * 64,
            "proposal_created": False,
            "order_created": False,
            "trade_created": False,
            "position_mutated": False,
            "cash_mutated": False,
            "execution_authorized": False,
        }
        self.calls = []
        self.closed = False

    def cursor(self):
        return FakeStrategyCursor(self)

    def commit(self):
        self.calls.append(("commit",))

    def rollback(self):
        self.calls.append(("rollback",))

    def close(self):
        self.closed = True

class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.connection.calls.append(("execute", sql, params))

    def fetchone(self):
        return (self.connection.results.pop(0),)


class FakeConnection:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.calls.append(("commit",))

    def rollback(self):
        self.calls.append(("rollback",))


class AIAgentContractTest(unittest.TestCase):
    def test_knowledge_bundle_hash_is_frozen(self):
        self.assertEqual(
            KNOWLEDGE_BUNDLE_SHA256,
            "062c8f65f9f666e2872c7c7311389ee112d56574631f1271735ba91cd9cfbe06",
        )
        self.assertEqual(
            CONTEXT_KNOWLEDGE_BUNDLE_SHA256,
            "1a873d69ef8f14e329b744460d549bcb3c35d99bb6af5fd10c16fc1a9dda15bc",
        )

    def test_five_minute_bucket_is_timezone_stable_and_idempotent(self):
        self.assertEqual(five_minute_bucket(NOW), "20260720T1000+0800")
        self.assertEqual(
            five_minute_bucket(NOW + timedelta(minutes=2)),
            "20260720T1000+0800",
        )
        self.assertEqual(
            five_minute_bucket(NOW + timedelta(minutes=3)),
            "20260720T1005+0800",
        )
        with self.assertRaisesRegex(ValueError, "timezone_aware"):
            five_minute_bucket(datetime(2026, 7, 20, 10, 0))

    def test_context_accepts_only_current_approved_stock_sources(self):
        context = validate_context(
            context_payload(), current_trade_date=TRADE_DATE
        )
        self.assertEqual(context.for_trade_date, "20260720")
        self.assertEqual(len(context.signals), 2)
        self.assertEqual(len(context.market_context), 2)
        self.assertTrue(
            all(
                item["context_only"]
                for item in context.model_payload()["market_context"]
            )
        )
        self.assertEqual(
            context.model_payload()["knowledge_bundle_hash"],
            CONTEXT_KNOWLEDGE_BUNDLE_SHA256,
        )
        self.assertNotIn("principal_id", context.model_payload())
        self.assertNotIn("virtual_account_id", context.model_payload())
        for drift in (
            context_payload(for_trade_date="20260719"),
            context_payload(knowledge_bundle_hash="0" * 64),
            context_payload(universe_snapshot_hash="invalid"),
            context_payload(memory_snapshot_hash=None),
            context_payload(workset_hash="g" * 64),
            context_payload(
                signals=[
                    {
                        **context_payload()["signals"][0],
                        "asset_kind": "index",
                        "identity_key": "index:SH:000001",
                    }
                ]
            ),
            context_payload(
                signals=[
                    {
                        **context_payload()["signals"][0],
                        "ai_eligible": False,
                    }
                ]
            ),
            context_payload(
                market_context=[
                    {
                        **context_payload()["market_context"][0],
                        "context_only": False,
                    }
                ]
            ),
        ):
            with self.assertRaises(ValueError):
                validate_context(drift, current_trade_date=TRADE_DATE)

    def test_model_output_rejects_price_quantity_account_date_and_principal(self):
        context = validate_context(
            context_payload(), current_trade_date=TRADE_DATE
        )
        for forbidden in (
            "price",
            "quantity",
            "virtual_account_id",
            "trade_date",
            "principal_id",
            "user_id",
        ):
            payload = buy_decision()
            payload[forbidden] = "forged"
            with self.assertRaisesRegex(
                ValueError, "server_owned_field"
            ):
                validate_model_output(payload, context=context)
        nested = buy_decision(
            risk_assessment={
                "trigger": "signal",
                "level": "low",
                "summary": "x",
                "price": "10",
            }
        )
        with self.assertRaises(ValueError):
            validate_model_output(nested, context=context)
        with self.assertRaisesRegex(ValueError, "invalid_stock_identity"):
            validate_model_output(
                buy_decision(identity_key="index:SH:000300"),
                context=context,
            )

    def test_buy_requires_exact_current_buy_projection(self):
        context = validate_context(
            context_payload(), current_trade_date=TRADE_DATE
        )
        self.assertEqual(
            validate_model_output(buy_decision(), context=context).decision_type,
            "buy",
        )
        for bad in (
            buy_decision(source_signal_projection_id=102),
            buy_decision(source_signal_projection_id=None),
            buy_decision(identity_key="stock:SH:600001"),
            buy_decision(source_virtual_position_id=201),
        ):
            with self.assertRaisesRegex(ValueError, "buy_requires"):
                validate_model_output(bad, context=context)
        with self.assertRaisesRegex(ValueError, "signal_evidence_reference"):
            validate_model_output(
                buy_decision(evidence=["current_trade_date"]),
                context=context,
            )

    def test_sell_requires_owned_position_and_signal_or_risk_reason(self):
        context = validate_context(
            context_payload(), current_trade_date=TRADE_DATE
        )
        self.assertEqual(
            validate_model_output(sell_decision(), context=context).decision_type,
            "sell",
        )
        risk_sell = sell_decision(
            source_signal_projection_id=None,
            risk_assessment={
                "trigger": "portfolio_risk",
                "level": "critical",
                "summary": "组合风险达到确定性阈值。",
            },
        )
        self.assertEqual(
            validate_model_output(
                risk_sell, context=context
            ).risk_assessment["trigger"],
            "portfolio_risk",
        )
        stop_sell = sell_decision(
            source_signal_projection_id=None,
            risk_assessment={
                "trigger": "stop_loss",
                "level": "critical",
                "summary": "止损策略要求卖出。",
            },
        )
        self.assertEqual(
            validate_model_output(
                stop_sell, context=context
            ).risk_assessment["trigger"],
            "stop_loss",
        )
        with self.assertRaisesRegex(ValueError, "position_evidence_reference"):
            validate_model_output(
                sell_decision(evidence=["projection:102"]),
                context=context,
            )
        for bad in (
            sell_decision(source_virtual_position_id=None),
            sell_decision(source_signal_projection_id=101),
        ):
            with self.assertRaises(ValueError):
                validate_model_output(bad, context=context)

    def test_hold_cannot_select_trade_scope(self):
        context = validate_context(
            context_payload(), current_trade_date=TRADE_DATE
        )
        hold = {
            **buy_decision(),
            "decision_type": "hold",
            "identity_key": None,
            "source_signal_projection_id": None,
            "source_virtual_position_id": None,
            "risk_assessment": {
                "trigger": "none",
                "level": "low",
                "summary": "当前不产生交易申请。",
            },
        }
        self.assertEqual(
            validate_model_output(hold, context=context).decision_type,
            "hold",
        )
        with self.assertRaisesRegex(ValueError, "hold_must_not"):
            validate_model_output(
                {**hold, "identity_key": "stock:SH:600000"},
                context=context,
            )


class AIAgentRiskTest(unittest.TestCase):
    def _validated(self, *, payload=None, context=None):
        context = context or validate_context(
            context_payload(), current_trade_date=TRADE_DATE
        )
        return (
            validate_model_output(payload or buy_decision(), context=context),
            context,
        )

    def test_conservative_buy_risk_allows_base_case(self):
        decision, context = self._validated()
        result = evaluate_conservative_risk(
            decision, context=context
        )
        self.assertTrue(result.allowed)
        self.assertEqual(result.reason, "buy_scope_ready")

    def test_drawdown_daily_total_and_identity_limits_block(self):
        variants = [
            (
                {"max_drawdown_pct": "5"},
                "max_drawdown_pause",
                context_payload()["positions"],
            ),
            (
                {"daily_new_buy_count": 10},
                "daily_buy_limit_reached",
                context_payload()["positions"],
            ),
            (
                {
                    "total_equity": "1000000",
                    "market_value": "100000",
                },
                "total_exposure_limit",
                context_payload()["positions"],
            ),
            (
                {},
                "identity_exposure_limit",
                [
                    {
                        **context_payload()["positions"][0],
                        "virtual_position_id": 202,
                        "identity_key": "stock:SH:600000",
                        "quantity": "3001",
                        "market_value": "300100",
                    }
                ],
            ),
        ]
        for portfolio_changes, expected, positions in variants:
            raw = context_payload(
                portfolio={
                    **context_payload()["portfolio"],
                    **portfolio_changes,
                },
                positions=positions,
            )
            context = validate_context(
                raw, current_trade_date=TRADE_DATE
            )
            decision = validate_model_output(
                buy_decision(), context=context
            )
            self.assertEqual(
                evaluate_conservative_risk(
                    decision, context=context
                ).reason,
                expected,
            )

    def test_first_three_autonomous_days_limit_to_one_buy(self):
        raw = context_payload(
            portfolio={
                **context_payload()["portfolio"],
                "autonomous_trade_day_no": 2,
                "daily_new_buy_count": 1,
            }
        )
        context = validate_context(raw, current_trade_date=TRADE_DATE)
        decision = validate_model_output(buy_decision(), context=context)
        self.assertEqual(
            evaluate_conservative_risk(
                decision, context=context
            ).reason,
            "daily_buy_limit_reached",
        )

    def test_after_three_autonomous_days_uses_standard_daily_limit(self):
        raw = context_payload(
            portfolio={
                **context_payload()["portfolio"],
                "autonomous_trade_day_no": 3,
                "daily_new_buy_count": 1,
            }
        )
        context = validate_context(raw, current_trade_date=TRADE_DATE)
        decision = validate_model_output(buy_decision(), context=context)
        result = evaluate_conservative_risk(decision, context=context)
        self.assertTrue(result.allowed)
        self.assertEqual(result.reason, "buy_scope_ready")

    def test_unknown_autonomous_trade_day_is_canary_limited(self):
        raw = context_payload(
            portfolio={
                **context_payload()["portfolio"],
                "autonomous_trade_day_no": 0,
                "daily_new_buy_count": 1,
            }
        )
        context = validate_context(raw, current_trade_date=TRADE_DATE)
        decision = validate_model_output(buy_decision(), context=context)
        self.assertEqual(
            evaluate_conservative_risk(
                decision, context=context
            ).reason,
            "daily_buy_limit_reached",
        )

    def test_sell_requires_t1_available_quantity(self):
        raw = context_payload(
            positions=[
                {
                    **context_payload()["positions"][0],
                    "available_quantity": "0",
                }
            ]
        )
        context = validate_context(raw, current_trade_date=TRADE_DATE)
        decision = validate_model_output(sell_decision(), context=context)
        self.assertEqual(
            evaluate_conservative_risk(
                decision, context=context
            ).reason,
            "t1_available_quantity_not_sellable",
        )


class AIAgentOrchestrationTest(unittest.TestCase):
    def test_default_disabled_makes_zero_repository_or_model_calls(self):
        repository = FakeRepository()
        adapter = FakeAdapter()
        result = run_agent_once(
            repository=repository,
            model_adapter=adapter,
            now=NOW,
        )
        self.assertEqual(result["status"], "feature_disabled")
        self.assertEqual(repository.calls, [])
        self.assertEqual(adapter.calls, [])

    def test_shadow_records_decision_but_never_creates_proposal(self):
        repository = FakeRepository()
        adapter = FakeAdapter(
            call_metadata={
                "provider": "openai",
                "model": "gpt-5.6-sol",
                "provider_request_id": "req_test",
                "response_id": "resp_test",
                "input_tokens": 120,
                "output_tokens": 30,
                "total_tokens": 150,
                "latency_ms": 321,
                "secret": "must-not-leak",
            }
        )
        result = run_agent_once(
            repository=repository,
            model_adapter=adapter,
            now=NOW,
            shadow_enabled=True,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "shadow_decision_recorded")
        self.assertFalse(result["proposal_created"])
        self.assertIsNotNone(repository.decision_payload)
        self.assertIsNone(repository.proposal_payload)
        self.assertEqual(
            repository.decision_payload["knowledge_bundle_hash"],
            KNOWLEDGE_BUNDLE_SHA256,
        )
        self.assertEqual(
            repository.decision_payload["input_payload_hash"], "d" * 64
        )
        self.assertNotIn("output_payload_hash", repository.decision_payload)
        self.assertNotIn(
            "server_policy",
            repository.decision_payload["risk_assessment"],
        )
        self.assertEqual(
            result["model_call"],
            {
                "provider": "openai",
                "model": "gpt-5.6-sol",
                "provider_request_id": "req_test",
                "response_id": "resp_test",
                "input_tokens": 120,
                "output_tokens": 30,
                "total_tokens": 150,
                "latency_ms": 321,
            },
        )
        self.assertNotIn("secret", json.dumps(result))

    def test_autonomous_requires_two_flags_and_creates_only_server_proposal(self):
        repository = FakeRepository()
        adapter = FakeAdapter()
        disabled = run_agent_once(
            repository=repository,
            model_adapter=adapter,
            now=NOW,
            requested_mode="autonomous",
            shadow_enabled=True,
            autonomous_enabled=False,
        )
        self.assertEqual(disabled["status"], "feature_disabled")
        self.assertEqual(repository.calls, [])

        result = run_agent_once(
            repository=repository,
            model_adapter=adapter,
            now=NOW,
            requested_mode="autonomous",
            shadow_enabled=True,
            autonomous_enabled=True,
        )
        self.assertEqual(
            result["status"], "autonomous_proposal_confirmed"
        )
        self.assertTrue(result["server_risk_allowed"])
        self.assertEqual(result["server_risk_reason"], "passed")
        self.assertEqual(
            repository.proposal_payload,
            {
                "decision_id": 301,
                "idempotency_key":
                    repository.decision_payload["idempotency_key"],
            },
        )
        for key in (
            "price",
            "quantity",
            "account_id",
            "trade_date",
            "principal_id",
        ):
            self.assertNotIn(key, repository.proposal_payload)

    def test_risk_block_is_recorded_but_never_proposed(self):
        repository = FakeRepository(
            context_payload(
                portfolio={
                    **context_payload()["portfolio"],
                    "max_drawdown_pct": "5",
                }
            ),
            server_risk_allowed=False,
            server_risk_reason="max_drawdown_pause",
        )
        result = run_agent_once(
            repository=repository,
            model_adapter=FakeAdapter(),
            now=NOW,
            requested_mode="autonomous",
            shadow_enabled=True,
            autonomous_enabled=True,
        )
        self.assertTrue(result["decision_recorded"])
        self.assertFalse(result["proposal_created"])
        self.assertEqual(result["risk_reason"], "max_drawdown_pause")
        self.assertIsNone(repository.proposal_payload)

    def test_server_risk_result_is_required_and_cannot_be_overridden(self):
        repository = FakeRepository(
            server_risk_allowed=False,
            server_risk_reason="server_policy_rejected",
        )
        result = run_agent_once(
            repository=repository,
            model_adapter=FakeAdapter(),
            now=NOW,
            requested_mode="autonomous",
            shadow_enabled=True,
            autonomous_enabled=True,
        )
        self.assertTrue(result["decision_recorded"])
        self.assertFalse(result["risk_allowed"])
        self.assertEqual(result["risk_reason"], "server_policy_rejected")
        self.assertIsNone(repository.proposal_payload)

        for invalid in (None, 1, "true"):
            repository = FakeRepository(server_risk_allowed=invalid)
            result = run_agent_once(
                repository=repository,
                model_adapter=FakeAdapter(),
                now=NOW,
                shadow_enabled=True,
            )
            self.assertFalse(result["ok"])
            self.assertEqual(
                result["reason"], "decision_record_risk_invalid"
            )
            self.assertIsNone(repository.proposal_payload)

    def test_model_exception_and_invalid_output_fail_closed(self):
        for adapter in (
            FakeAdapter(raises=True),
            FakeAdapter({**buy_decision(), "quantity": 100}),
        ):
            repository = FakeRepository()
            result = run_agent_once(
                repository=repository,
                model_adapter=adapter,
                now=NOW,
                shadow_enabled=True,
            )
            self.assertFalse(result["ok"])
            self.assertEqual(
                result["reason"], "model_or_decision_validation_failed"
            )
            self.assertIsNone(repository.decision_payload)
            self.assertIsNone(repository.proposal_payload)
            self.assertNotIn("secret provider detail", json.dumps(result))

    def test_already_processed_bucket_does_not_call_model(self):
        repository = FakeRepository(
            {"ok": False, "status": "already_processed"}
        )
        adapter = FakeAdapter()
        result = run_agent_once(
            repository=repository,
            model_adapter=adapter,
            now=NOW,
            shadow_enabled=True,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "already_processed")
        self.assertEqual(adapter.calls, [])

    def test_expected_context_noops_do_not_call_model(self):
        for status in (
            "not_open_trade_date",
            "position_quote_not_ready",
        ):
            with self.subTest(status=status):
                repository = FakeRepository(
                    {"ok": True, "status": status}
                )
                adapter = FakeAdapter()
                result = run_agent_once(
                    repository=repository,
                    model_adapter=adapter,
                    now=NOW,
                    shadow_enabled=True,
                )
                self.assertTrue(result["ok"])
                self.assertEqual(result["status"], status)
                self.assertFalse(result["model_called"])
                self.assertFalse(result["decision_recorded"])
                self.assertFalse(result["proposal_created"])
                self.assertEqual(adapter.calls, [])
                self.assertEqual(
                    [call[0] for call in repository.calls],
                    ["load_context"],
                )
                self.assertIsNone(repository.decision_payload)
                self.assertIsNone(repository.proposal_payload)

    def test_signal_universe_too_large_fails_before_model(self):
        repository = FakeRepository(
            {
                "ok": True,
                "status": "signal_universe_too_large",
                "eligible_signal_count": 1001,
                "market_context_count": 0,
            }
        )
        adapter = FakeAdapter()
        result = run_agent_once(
            repository=repository,
            model_adapter=adapter,
            now=NOW,
            shadow_enabled=True,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed_closed")
        self.assertEqual(result["reason"], "signal_universe_too_large")
        self.assertFalse(result["model_called"])
        self.assertFalse(result["decision_recorded"])
        self.assertFalse(result["proposal_created"])
        self.assertEqual(adapter.calls, [])
        self.assertEqual(
            [call[0] for call in repository.calls], ["load_context"]
        )
        self.assertIsNone(repository.decision_payload)
        self.assertIsNone(repository.proposal_payload)

    def test_unknown_ready_context_status_fails_before_model(self):
        repository = FakeRepository(
            {"ok": True, "status": "unexpected_ready_status"}
        )
        adapter = FakeAdapter()
        result = run_agent_once(
            repository=repository,
            model_adapter=adapter,
            now=NOW,
            shadow_enabled=True,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed_closed")
        self.assertEqual(result["reason"], "context_status_unrecognized")
        self.assertFalse(result["model_called"])
        self.assertFalse(result["decision_recorded"])
        self.assertFalse(result["proposal_created"])
        self.assertEqual(adapter.calls, [])
        self.assertEqual(
            [call[0] for call in repository.calls], ["load_context"]
        )
        self.assertIsNone(repository.decision_payload)
        self.assertIsNone(repository.proposal_payload)

    def test_same_bucket_builds_same_idempotency_key(self):
        keys = []
        for run_time in (NOW, NOW + timedelta(minutes=2)):
            repository = FakeRepository()
            run_agent_once(
                repository=repository,
                model_adapter=FakeAdapter(),
                now=run_time,
                shadow_enabled=True,
            )
            keys.append(repository.decision_payload["idempotency_key"])
        self.assertEqual(keys[0], keys[1])


class FunctionOnlyRepositoryTest(unittest.TestCase):
    def test_repository_uses_only_fixed_security_definer_functions(self):
        connection = FakeConnection(
            [
                {"ok": True, "status": "ready"},
                {"ok": True, "decision_id": 1},
                {"ok": True, "proposal_id": 2},
                {"ok": True, "daily_summary_id": 3},
                {"ok": True, "strategy_evaluation_id": 4},
            ]
        )
        repository = FunctionOnlyAIAgentRepository(connection)
        repository.load_context(
            run_bucket="bucket",
            for_trade_date=TRADE_DATE,
            max_signals=1000,
        )
        repository.record_shadow_decision({"a": 1})
        repository.create_confirmed_proposal({"decision_id": 1})
        repository.record_daily_summary({"a": 2})
        repository.record_strategy_evaluation({"a": 3})
        sql_calls = [
            call[1] for call in connection.calls if call[0] == "execute"
        ]
        self.assertEqual(
            sql_calls,
            [
                CONTEXT_LOAD_SQL,
                DECISION_RECORD_SQL,
                PROPOSAL_CREATE_SQL,
                DAILY_SUMMARY_RECORD_SQL,
                STRATEGY_EVALUATION_RECORD_SQL,
            ],
        )
        for sql in sql_calls:
            upper = sql.upper()
            self.assertNotIn(" INSERT ", f" {upper} ")
            self.assertNotIn(" UPDATE ", f" {upper} ")
            self.assertNotIn(" DELETE ", f" {upper} ")
            self.assertNotIn(" FROM N6_", upper)
        context_call = next(
            call
            for call in connection.calls
            if call[0] == "execute" and call[1] == CONTEXT_LOAD_SQL
        )
        self.assertEqual(
            context_call[2],
            (
                "bucket",
                TRADE_DATE,
                1000,
                CONTEXT_KNOWLEDGE_BUNDLE_SHA256,
            ),
        )


class DailySummaryTest(unittest.TestCase):
    def test_score_formula_is_exact(self):
        self.assertEqual(
            risk_adjusted_score(
                net_return_pct="1.25",
                max_drawdown_pct="0.50",
                turnover_pct="10",
            ),
            Decimal("0.300000"),
        )

    def test_summary_is_deterministic_and_current_day_only(self):
        repository = FakeRepository()
        result = run_daily_summary_once(
            repository=repository,
            now=NOW.replace(hour=15, minute=16),
            enabled=True,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["risk_adjusted_score"], "0.300000")
        self.assertEqual(
            repository.summary_payload["risk_adjusted_score"],
            "0.300000",
        )
        self.assertIn("模拟账户", repository.summary_payload["summary_text"])
        self.assertTrue(repository.summary_payload["highlights"])
        self.assertTrue(repository.summary_payload["lessons"])
        self.assertTrue(repository.summary_payload["next_day_watch"])

        historical_repository = FakeRepository()
        blocked = run_daily_summary_once(
            repository=historical_repository,
            now=NOW,
            for_trade_date=date(2026, 7, 19),
            enabled=True,
        )
        self.assertFalse(blocked["ok"])
        self.assertEqual(historical_repository.calls, [])

        early_repository = FakeRepository()
        early = run_daily_summary_once(
            repository=early_repository,
            now=NOW.replace(hour=15, minute=14),
            enabled=True,
        )
        self.assertFalse(early["ok"])
        self.assertEqual(early["status"], "failed_closed")
        self.assertEqual(early["reason"], "daily_summary_before_1515")
        self.assertEqual(early_repository.calls, [])


class RunnerGateTest(unittest.TestCase):
    def test_agent_runner_dry_and_default_disabled_never_build_dependencies(self):
        calls = []
        dry = run_agent_from_args(
            argparse.Namespace(
                run_at=None,
                max_signals=1000,
                autonomous=False,
                execute=False,
            ),
            environment={},
            repository_factory=lambda: calls.append("repo"),
            model_adapter_factory=lambda: calls.append("model"),
        )
        self.assertEqual(dry["status"], "dry_run_preflight")
        self.assertEqual(calls, [])

        disabled = run_agent_from_args(
            argparse.Namespace(
                run_at=None,
                max_signals=1000,
                autonomous=False,
                execute=True,
            ),
            environment={},
            repository_factory=lambda: calls.append("repo"),
            model_adapter_factory=lambda: calls.append("model"),
        )
        self.assertEqual(disabled["status"], "feature_disabled")
        self.assertEqual(calls, [])

    def test_agent_runner_no_model_adapter_stops_after_schedule_preflight(self):
        calls = []
        env = agent_environment()
        env[DEEPSEEK_EGRESS_MODE_ENV] = (
            DEEPSEEK_EGRESS_PSEUDONYMOUS_SHADOW
        )

        class Repository:
            def shadow_schedule_preflight(self, **kwargs):
                del kwargs
                return {"ok": True, "status": "open_slot_ready"}

        result = run_agent_from_args(
            argparse.Namespace(
                run_at=NOW.replace(
                    minute=30, second=0, microsecond=0
                ).isoformat(),
                max_signals=1000,
                autonomous=False,
                execute=True,
            ),
            environment=env,
            repository_factory=lambda: (
                calls.append("repo") or Repository(),
                lambda: None,
            ),
            model_adapter_factory=DisabledModelAdapter,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "model_adapter_not_configured")
        self.assertEqual(calls, ["repo"])

    def test_agent_runner_rejects_manifest_before_model_or_database(self):
        calls = []
        env = agent_environment()
        env[PRODUCTION_KNOWLEDGE_MANIFEST_SHA256_ENV] = "0" * 64
        result = run_agent_from_args(
            argparse.Namespace(
                run_at=NOW.replace(
                    minute=30, second=0, microsecond=0
                ).isoformat(),
                max_signals=1000,
                autonomous=False,
                execute=True,
            ),
            environment=env,
            repository_factory=lambda: calls.append("repo"),
            model_adapter_factory=lambda: calls.append("model"),
        )
        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"], "production_knowledge_manifest_invalid"
        )
        self.assertEqual(calls, [])

    def test_agent_runner_manifest_disables_autonomous_mode(self):
        calls = []
        env = agent_environment()
        env[AUTONOMOUS_FEATURE_FLAG] = "1"
        result = run_agent_from_args(
            argparse.Namespace(
                run_at=NOW.replace(
                    minute=30, second=0, microsecond=0
                ).isoformat(),
                max_signals=1000,
                autonomous=True,
                execute=True,
            ),
            environment=env,
            repository_factory=lambda: calls.append("repo"),
            model_adapter_factory=lambda: calls.append("model"),
        )
        self.assertEqual(result["status"], "feature_disabled")
        self.assertEqual(
            result["reason"],
            "knowledge_manifest_autonomous_disabled",
        )
        self.assertEqual(calls, [])

    def test_daily_runner_defaults_disabled_and_zero_connection(self):
        calls = []
        result = run_summary_from_args(
            argparse.Namespace(
                for_trade_date=None, run_at=None, execute=True
            ),
            environment={},
            repository_factory=lambda: calls.append("repo"),
        )
        self.assertEqual(result["status"], "feature_disabled")
        self.assertEqual(calls, [])


class N6AIStrategyPolicyRunnerTest(unittest.TestCase):
    @patch("scripts.run_n6_ai_strategy_policy_once.psycopg.connect")
    def test_default_connection_has_bounded_statement_and_lock_timeouts(
        self, connect
    ):
        strategy_connection_factory()

        options = connect.call_args.kwargs["options"]
        self.assertIn("-c statement_timeout=30000", options)
        self.assertIn("-c lock_timeout=1000", options)

    def test_parser_has_only_shadow_mode_and_rejects_autonomous(self):
        parser = build_strategy_parser()
        args = parser.parse_args([])
        self.assertEqual(args.mode, "shadow")
        self.assertFalse(args.execute)
        with self.assertRaises(SystemExit):
            parser.parse_args(["--autonomous"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["--mode", "autonomous"])

    def test_dry_run_is_zero_connection_and_zero_business_write(self):
        calls = []
        result = run_strategy_from_args(
            argparse.Namespace(
                run_at=NOW.isoformat(), mode="shadow", execute=False
            ),
            environment={},
            connection_factory=lambda: calls.append("connect"),
        )
        self.assertEqual(result["status"], "dry_run_preflight")
        self.assertEqual(calls, [])
        for key in (
            "proposal_created",
            "order_created",
            "trade_created",
            "position_mutated",
            "cash_mutated",
            "model_called",
        ):
            self.assertFalse(result[key])

    def test_disabled_feature_is_zero_connection(self):
        calls = []
        result = run_strategy_from_args(
            argparse.Namespace(
                run_at=NOW.isoformat(), mode="shadow", execute=True
            ),
            environment={},
            connection_factory=lambda: calls.append("connect"),
        )
        self.assertEqual(result["status"], "feature_disabled")
        self.assertEqual(calls, [])

    def test_outside_trading_session_is_safe_noop(self):
        calls = []
        environment = {
            STRATEGY_POLICY_SHADOW_FEATURE_FLAG: "1",
            "PGSERVICE": "n6_ai_agent",
            "PGSERVICEFILE": "/tmp/service",
            "PGPASSFILE": "/tmp/pass",
        }
        result = run_strategy_from_args(
            argparse.Namespace(
                run_at="2026-07-20T15:30:00+08:00",
                mode="shadow",
                execute=True,
            ),
            environment=environment,
            connection_factory=lambda: calls.append("connect"),
        )
        self.assertEqual(result["status"], "outside_trading_session")
        self.assertEqual(calls, [])

    def test_closed_weekday_from_server_calendar_is_safe_noop(self):
        connection = FakeStrategyConnection(
            {
                **FakeStrategyConnection().payload,
                "status": "not_open_trade_date",
                "candidate_rank_audit_count": 0,
                "strategy_action_audit_count": 0,
                "completed_strategy_episode_count": 0,
            }
        )
        environment = {
            STRATEGY_POLICY_SHADOW_FEATURE_FLAG: "1",
            "PGSERVICE": "n6_ai_agent",
            "PGSERVICEFILE": "/tmp/service",
            "PGPASSFILE": "/tmp/pass",
        }
        result = run_strategy_from_args(
            argparse.Namespace(
                run_at=NOW.isoformat(), mode="shadow", execute=True
            ),
            environment=environment,
            connection_factory=lambda: connection,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "not_open_trade_date")
        self.assertTrue(result["db_connected"])
        self.assertEqual(connection.calls[-1], ("rollback",))

    def test_execute_calls_only_hardened_shadow_function_and_commits(self):
        connection = FakeStrategyConnection()
        environment = {
            STRATEGY_POLICY_SHADOW_FEATURE_FLAG: "1",
            "PGSERVICE": "n6_ai_agent",
            "PGSERVICEFILE": "/tmp/service",
            "PGPASSFILE": "/tmp/pass",
        }
        result = run_strategy_from_args(
            argparse.Namespace(
                run_at=NOW.isoformat(), mode="shadow", execute=True
            ),
            environment=environment,
            connection_factory=lambda: connection,
        )
        self.assertEqual(result["status"], "shadow_policy_evaluated")
        self.assertEqual(connection.calls[-1], ("commit",))
        sql = connection.calls[0][1]
        self.assertIn(
            "public.n6_ai_strategy_shadow_evaluate", sql
        )
        for token in (
            "INSERT",
            "UPDATE",
            "DELETE",
            "proposal",
            "order",
            "trade",
            "position",
            "cash",
        ):
            self.assertNotIn(token.lower(), sql.lower())
        self.assertFalse(result["proposal_created"])
        self.assertFalse(result["order_created"])
        self.assertFalse(result["trade_created"])
        self.assertFalse(result["position_mutated"])
        self.assertEqual(
            result["completed_strategy_episode_count"],
            2,
        )
        self.assertEqual(result["strategy_workset_hash"], "a" * 64)
        self.assertEqual(
            result["policy_version"],
            STRATEGY_POLICY_VERSION,
        )
        self.assertEqual(
            result["policy_document_sha256"],
            STRATEGY_POLICY_DOCUMENT_SHA256,
        )
        self.assertEqual(
            result["knowledge_bundle_version"],
            STRATEGY_KNOWLEDGE_BUNDLE_VERSION,
        )
        self.assertEqual(
            result["knowledge_bundle_sha256"],
            STRATEGY_KNOWLEDGE_BUNDLE_SHA256,
        )

    def test_execute_rejects_missing_or_invalid_strategy_workset_hash(self):
        environment = {
            STRATEGY_POLICY_SHADOW_FEATURE_FLAG: "1",
            "PGSERVICE": "n6_ai_agent",
            "PGSERVICEFILE": "/tmp/service",
            "PGPASSFILE": "/tmp/pass",
        }
        for invalid_hash in (None, "", "A" * 64, "g" * 64, "a" * 63):
            with self.subTest(invalid_hash=invalid_hash):
                payload = {
                    **FakeStrategyConnection().payload,
                    "strategy_workset_hash": invalid_hash,
                }
                connection = FakeStrategyConnection(payload)
                result = run_strategy_from_args(
                    argparse.Namespace(
                        run_at=NOW.isoformat(),
                        mode="shadow",
                        execute=True,
                    ),
                    environment=environment,
                    connection_factory=lambda: connection,
                )
                self.assertFalse(result["ok"])
                self.assertEqual(
                    result["reason"],
                    "strategy_workset_hash_invalid",
                )
                self.assertEqual(connection.calls[-1], ("rollback",))

    def test_claimed_business_mutation_from_function_fails_closed(self):
        connection = FakeStrategyConnection(
            {
                "ok": True,
                "status": "shadow_policy_evaluated",
                "proposal_created": True,
            }
        )
        environment = {
            STRATEGY_POLICY_SHADOW_FEATURE_FLAG: "1",
            "PGSERVICE": "n6_ai_agent",
            "PGSERVICEFILE": "/tmp/service",
            "PGPASSFILE": "/tmp/pass",
        }
        result = run_strategy_from_args(
            argparse.Namespace(
                run_at=NOW.isoformat(), mode="shadow", execute=True
            ),
            environment=environment,
            connection_factory=lambda: connection,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "shadow_mutation_contract_breach")
        self.assertEqual(connection.calls[-1], ("rollback",))

    def test_execution_authority_or_unexpected_success_status_fails_closed(self):
        environment = {
            STRATEGY_POLICY_SHADOW_FEATURE_FLAG: "1",
            "PGSERVICE": "n6_ai_agent",
            "PGSERVICEFILE": "/tmp/service",
            "PGPASSFILE": "/tmp/pass",
        }
        for mutation in (
            {"execution_authorized": True},
            {"execution_authorized": None},
            {"status": "autonomous_executed"},
        ):
            with self.subTest(mutation=mutation):
                payload = {
                    **FakeStrategyConnection().payload,
                    **mutation,
                }
                connection = FakeStrategyConnection(payload)
                result = run_strategy_from_args(
                    argparse.Namespace(
                        run_at=NOW.isoformat(),
                        mode="shadow",
                        execute=True,
                    ),
                    environment=environment,
                    connection_factory=lambda: connection,
                )
                self.assertFalse(result["ok"])
                self.assertEqual(connection.calls[-1], ("rollback",))
                self.assertNotIn(("commit",), connection.calls)

    def test_missing_or_drifted_policy_bundle_identity_rolls_back(self):
        expected = {
            "policy_version": STRATEGY_POLICY_VERSION,
            "policy_document_sha256":
                STRATEGY_POLICY_DOCUMENT_SHA256,
            "knowledge_bundle_version":
                STRATEGY_KNOWLEDGE_BUNDLE_VERSION,
            "knowledge_bundle_sha256":
                STRATEGY_KNOWLEDGE_BUNDLE_SHA256,
        }
        environment = {
            STRATEGY_POLICY_SHADOW_FEATURE_FLAG: "1",
            "PGSERVICE": "n6_ai_agent",
            "PGSERVICEFILE": "/tmp/service",
            "PGPASSFILE": "/tmp/pass",
        }
        for field in expected:
            for mutation in ("missing", "wrong"):
                with self.subTest(field=field, mutation=mutation):
                    payload = dict(FakeStrategyConnection().payload)
                    if mutation == "missing":
                        payload.pop(field)
                    else:
                        payload[field] = "wrong"
                    connection = FakeStrategyConnection(payload)

                    result = run_strategy_from_args(
                        argparse.Namespace(
                            run_at=NOW.isoformat(),
                            mode="shadow",
                            execute=True,
                        ),
                        environment=environment,
                        connection_factory=lambda: connection,
                    )

                    self.assertFalse(result["ok"])
                    self.assertEqual(
                        result["reason"],
                        "strategy_policy_identity_mismatch",
                    )
                    self.assertEqual(
                        connection.calls[-1], ("rollback",)
                    )
                    self.assertNotIn(("commit",), connection.calls)

if __name__ == "__main__":
    unittest.main()
