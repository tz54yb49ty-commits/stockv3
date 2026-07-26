from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import re
import unittest

from scripts.check_n6_ai_shadow_observation_acceptance import (
    CONTRACT_VERSION,
    NOT_READY_EXIT_CODE,
    READY_EXIT_CODE,
    SIDE_EFFECT_FIELDS,
    build_acceptance_report,
    build_report_from_repository,
    main,
    serialize_report,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT / "docs/N6_AI_SHADOW_OBSERVATION_ACCEPTANCE_CONTRACT.json"
)
SCRIPT_PATH = (
    ROOT / "scripts/check_n6_ai_shadow_observation_acceptance.py"
)
PHASE_AB_PATHS = [
    ROOT / "sql/062_n6_ai_shadow_observation_run_audit.sql",
    ROOT / "sql/062_n6_ai_shadow_observation_run_audit_rollback.sql",
    ROOT / "tests/test_n6_ai_shadow_observation_run_audit_schema.py",
    ROOT / "src/ashare_v3/user/ai_agent.py",
    ROOT / "scripts/run_n6_ai_agent_once.py",
    ROOT / "tests/test_n6_ai_deepseek_adapter.py",
]
PHASE_AB_COMBINED_SHA256 = (
    "d54a7e8e088d305b2f845865cc8964135984cd9af3e095d843d8c10e7ae734c8"
)


def make_rows(
    *,
    attempts: int = 50,
    open_day_count: int = 10,
    valid_count: int | None = None,
    fingerprint: str = "fp_current",
    start_date: date = date(2026, 7, 1),
    audit_id_offset: int = 0,
) -> tuple[list[dict[str, object]], list[str]]:
    if valid_count is None:
        valid_count = attempts
    trade_dates = [
        (start_date + timedelta(days=offset)).isoformat()
        for offset in range(open_day_count)
    ]
    rows: list[dict[str, object]] = []
    for index in range(attempts):
        day_index = min(
            index * open_day_count // max(attempts, 1),
            open_day_count - 1,
        )
        row_date = date.fromisoformat(trade_dates[day_index])
        started_at = datetime.combine(
            row_date,
            time(10, index % 60),
            tzinfo=timezone(timedelta(hours=8)),
        )
        structure_valid = index < valid_count
        accepted = structure_valid
        audit_id = audit_id_offset + index + 1
        rows.append(
            {
                "audit_id": audit_id,
                "dedup_key": sha256(
                    f"dedup-{audit_id}".encode("ascii")
                ).hexdigest(),
                "trade_date": row_date.isoformat(),
                "system_fingerprint": fingerprint,
                "one_shot_status": (
                    "shadow_decision_recorded"
                    if accepted
                    else "decision_structure_invalid"
                ),
                "identity_probe_succeeded": True,
                "decision_call_attempted": True,
                "structure_valid": structure_valid,
                "decision_run_id": (
                    200000 + audit_id if accepted else None
                ),
                "decision_id": (
                    100000 + audit_id if accepted else None
                ),
                "server_risk_allowed": (
                    False if accepted else None
                ),
                "server_risk_reason": (
                    "hold_no_trade" if accepted else None
                ),
                "proposal_created": False,
                "proposal_created_count": 0,
                "order_created_count": 0,
                "trade_created_count": 0,
                "position_mutation_count": 0,
                "lot_mutation_count": 0,
                "cash_mutation_count": 0,
                "started_at": started_at.isoformat(),
            }
        )
    return rows, trade_dates


def evidence_for(
    rows: list[dict[str, object]],
    open_trade_dates: list[str],
) -> dict[str, object]:
    return {
        "source_complete": True,
        "source_order_proven": True,
        "expected_enabled_one_shot_count": len(rows),
        "authority_conflict_count": 0,
        "unexplained_state_count": 0,
        "open_trade_dates": list(open_trade_dates),
        "audit_rows": rows,
    }


def no_new_row(
    *,
    audit_id: int,
    trade_date: str,
    fingerprint: str = "fp_current",
    minute: int = 59,
) -> dict[str, object]:
    started_at = datetime.combine(
        date.fromisoformat(trade_date),
        time(11, minute),
        tzinfo=timezone(timedelta(hours=8)),
    )
    return {
        "audit_id": audit_id,
        "dedup_key": sha256(
            f"dedup-{audit_id}".encode("ascii")
        ).hexdigest(),
        "trade_date": trade_date,
        "system_fingerprint": fingerprint,
        "one_shot_status": "no_new_input",
        "identity_probe_succeeded": True,
        "decision_call_attempted": False,
        "structure_valid": None,
        "decision_run_id": None,
        "decision_id": None,
        "server_risk_allowed": None,
        "server_risk_reason": None,
        "proposal_created": False,
        "proposal_created_count": 0,
        "order_created_count": 0,
        "trade_created_count": 0,
        "position_mutation_count": 0,
        "lot_mutation_count": 0,
        "cash_mutation_count": 0,
        "started_at": started_at.isoformat(),
    }


class ShadowObservationAcceptanceTest(unittest.TestCase):
    def test_ready_positive(self):
        rows, dates = make_rows()
        report = build_acceptance_report(evidence_for(rows, dates))

        self.assertTrue(report["ready"])
        self.assertEqual(report["contract_version"], CONTRACT_VERSION)
        self.assertEqual(
            report["current_system_fingerprint"], "fp_current"
        )
        self.assertEqual(report["open_trade_date_count"], 10)
        self.assertEqual(report["decision_call_attempt_count"], 50)
        self.assertEqual(report["structure_valid_count"], 50)
        self.assertEqual(report["structure_valid_rate"], 1.0)
        self.assertEqual(report["gaps"], [])
        self.assertEqual(
            report["side_effects"],
            {name: 0 for name in SIDE_EFFECT_FIELDS},
        )

    def test_zero_over_zero_is_null_and_not_ready(self):
        dates = [
            (date(2026, 7, 1) + timedelta(days=index)).isoformat()
            for index in range(10)
        ]
        rows = [
            no_new_row(
                audit_id=index + 1,
                trade_date=trade_date,
                minute=index,
            )
            for index, trade_date in enumerate(dates)
        ]
        report = build_acceptance_report(evidence_for(rows, dates))

        self.assertFalse(report["ready"])
        self.assertEqual(report["decision_call_attempt_count"], 0)
        self.assertIsNone(report["structure_valid_rate"])
        self.assertIn("structure_valid_rate_unavailable", report["gaps"])

    def test_nine_days_and_forty_nine_attempts_are_independent_gaps(self):
        nine_day_rows, nine_dates = make_rows(open_day_count=9)
        nine_day = build_acceptance_report(
            evidence_for(nine_day_rows, nine_dates)
        )
        self.assertIn(
            "insufficient_open_trade_dates", nine_day["gaps"]
        )
        self.assertNotIn(
            "insufficient_decision_call_attempts", nine_day["gaps"]
        )

        rows_49, dates_10 = make_rows(attempts=49)
        forty_nine = build_acceptance_report(
            evidence_for(rows_49, dates_10)
        )
        self.assertIn(
            "insufficient_decision_call_attempts",
            forty_nine["gaps"],
        )

    def test_ninety_eight_percent_is_not_ready(self):
        rows, dates = make_rows(valid_count=49)
        report = build_acceptance_report(evidence_for(rows, dates))

        self.assertFalse(report["ready"])
        self.assertEqual(report["structure_valid_rate"], 0.98)
        self.assertIn(
            "structure_valid_rate_below_threshold", report["gaps"]
        )

    def test_exact_ninety_nine_percent_is_ready(self):
        rows, dates = make_rows(attempts=100, valid_count=99)
        report = build_acceptance_report(evidence_for(rows, dates))

        self.assertTrue(report["ready"])
        self.assertEqual(report["structure_valid_rate"], 0.99)

    def test_missing_risk_and_invalid_structure_accepted_fail_closed(self):
        rows, dates = make_rows()
        rows[0]["server_risk_allowed"] = None
        rows[0]["server_risk_reason"] = None
        missing_risk = build_acceptance_report(
            evidence_for(rows, dates)
        )
        self.assertEqual(
            missing_risk[
                "accepted_decision_missing_risk_count"
            ],
            1,
        )
        self.assertIn(
            "accepted_decision_missing_server_risk",
            missing_risk["gaps"],
        )

        rows, dates = make_rows()
        rows[0]["structure_valid"] = False
        invalid_accepted = build_acceptance_report(
            evidence_for(rows, dates)
        )
        self.assertEqual(
            invalid_accepted["invalid_structure_accepted_count"], 1
        )
        self.assertIn(
            "invalid_structure_accepted", invalid_accepted["gaps"]
        )

    def test_each_side_effect_nonzero_is_an_explicit_gap(self):
        for name, field in SIDE_EFFECT_FIELDS.items():
            with self.subTest(side_effect=name):
                rows, dates = make_rows()
                rows[0][field] = 1
                if name == "proposal":
                    rows[0]["proposal_created"] = True
                report = build_acceptance_report(
                    evidence_for(rows, dates)
                )
                self.assertFalse(report["ready"])
                self.assertEqual(report["side_effects"][name], 1)
                self.assertIn(
                    f"side_effect_nonzero:{name}", report["gaps"]
                )

    def test_latest_fingerprint_switch_resets_the_window(self):
        old_rows, old_dates = make_rows(fingerprint="fp_old")
        new_rows, new_dates = make_rows(
            attempts=5,
            open_day_count=2,
            fingerprint="fp_new",
            start_date=date(2026, 7, 11),
            audit_id_offset=50,
        )
        report = build_acceptance_report(
            evidence_for(
                old_rows + new_rows, old_dates + new_dates
            )
        )

        self.assertFalse(report["ready"])
        self.assertEqual(
            report["current_system_fingerprint"], "fp_new"
        )
        self.assertEqual(report["audit_row_count"], 5)
        self.assertEqual(report["historical_audit_row_count"], 50)
        self.assertEqual(report["decision_call_attempt_count"], 5)
        self.assertEqual(report["open_trade_date_count"], 2)

    def test_no_new_input_rows_do_not_enter_denominator(self):
        rows, dates = make_rows()
        rows.append(
            no_new_row(
                audit_id=51,
                trade_date=dates[-1],
                minute=59,
            )
        )
        report = build_acceptance_report(evidence_for(rows, dates))

        self.assertTrue(report["ready"])
        self.assertEqual(report["audit_row_count"], 51)
        self.assertEqual(report["decision_call_attempt_count"], 50)
        self.assertEqual(report["structure_valid_count"], 50)

    def test_non_open_trade_date_fails_closed(self):
        rows, dates = make_rows()
        report = build_acceptance_report(
            evidence_for(rows, dates[1:])
        )
        self.assertFalse(report["ready"])
        self.assertIn(
            "audit_row_0_trade_date_not_open", report["gaps"]
        )

    def test_abnormal_types_negative_counts_duplicates_and_order_fail(self):
        mutations = {}

        rows, dates = make_rows()
        rows[0]["decision_call_attempted"] = "true"
        mutations["invalid_type"] = evidence_for(rows, dates)

        rows, dates = make_rows()
        rows[0]["cash_mutation_count"] = -1
        mutations["negative_count"] = evidence_for(rows, dates)

        rows, dates = make_rows()
        rows[1]["dedup_key"] = rows[0]["dedup_key"]
        mutations["duplicate"] = evidence_for(rows, dates)

        rows, dates = make_rows()
        rows[1]["audit_id"] = rows[0]["audit_id"]
        mutations["duplicate_audit_id"] = evidence_for(rows, dates)

        rows, dates = make_rows()
        rows[0], rows[1] = rows[1], rows[0]
        mutations["unordered"] = evidence_for(rows, dates)

        rows, dates = make_rows()
        rows[0]["decision_call_attempted"] = False
        mutations["structure_without_attempt"] = evidence_for(
            rows, dates
        )

        rows, dates = make_rows()
        rows[-1]["system_fingerprint"] = ""
        mutations["empty_fingerprint"] = evidence_for(rows, dates)

        for name, evidence in mutations.items():
            with self.subTest(mutation=name):
                report = build_acceptance_report(evidence)
                self.assertFalse(report["ready"])
                self.assertTrue(report["gaps"])

    def test_audit_gap_and_authority_conflict_are_explicit(self):
        rows, dates = make_rows()
        evidence = evidence_for(rows, dates)
        evidence["expected_enabled_one_shot_count"] = 51
        evidence["authority_conflict_count"] = 1
        evidence["unexplained_state_count"] = 2
        report = build_acceptance_report(evidence)

        self.assertFalse(report["ready"])
        self.assertIn("audit_row_count_mismatch", report["gaps"])
        self.assertIn("authority_conflict_count_nonzero", report["gaps"])
        self.assertIn(
            "unexplained_state_count_nonzero", report["gaps"]
        )

    def test_same_input_has_byte_stable_json(self):
        rows, dates = make_rows()
        evidence = evidence_for(rows, dates)
        first = serialize_report(build_acceptance_report(evidence))
        second = serialize_report(build_acceptance_report(evidence))

        self.assertEqual(first, second)
        self.assertNotIn("generated_at", first)
        self.assertRegex(
            json.loads(first)["evidence_sha256"], r"^[0-9a-f]{64}$"
        )

    def test_sensitive_extra_fields_never_reach_report(self):
        rows, dates = make_rows()
        rows[0].update(
            {
                "prompt": "private-prompt-value",
                "content": "private-content-value",
                "reasoning": "private-reasoning-value",
                "response_id": "private-response-id",
                "credential": "private-credential-value",
                "session": "private-session-value",
                "identity_key": "stock:private",
                "stock_code": "600000",
                "person_name": "private-person",
            }
        )
        serialized = serialize_report(
            build_acceptance_report(evidence_for(rows, dates))
        )
        for forbidden in (
            "private-prompt-value",
            "private-content-value",
            "private-reasoning-value",
            "private-response-id",
            "private-credential-value",
            "private-session-value",
            "stock:private",
            "600000",
            "private-person",
            "response_id",
            "identity_key",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_repository_is_injected_once_and_exit_codes_are_stable(self):
        rows, dates = make_rows()

        class Repository:
            def __init__(self):
                self.calls = 0

            def load_shadow_observation_acceptance_evidence(self):
                self.calls += 1
                return evidence_for(rows, dates)

        repository = Repository()
        report = build_report_from_repository(repository)
        self.assertTrue(report["ready"])
        self.assertEqual(repository.calls, 1)

        stdout = StringIO()
        self.assertEqual(
            main(repository, stdout=stdout), READY_EXIT_CODE
        )
        self.assertTrue(json.loads(stdout.getvalue())["ready"])

        stdout = StringIO()
        self.assertEqual(
            main(None, stdout=stdout), NOT_READY_EXIT_CODE
        )
        unavailable = json.loads(stdout.getvalue())
        self.assertFalse(unavailable["ready"])
        self.assertEqual(
            unavailable["gaps"],
            ["acceptance_repository_not_configured"],
        )

        class FailingRepository:
            def load_shadow_observation_acceptance_evidence(self):
                raise RuntimeError("private-response-id")

        failed = build_report_from_repository(FailingRepository())
        serialized = serialize_report(failed)
        self.assertEqual(
            failed["gaps"], ["acceptance_repository_read_failed"]
        )
        self.assertNotIn("private-response-id", serialized)

    def test_script_contains_no_database_driver_sql_or_dml(self):
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("psycopg", source)
        self.assertNotRegex(
            source,
            re.compile(
                r"(?i)\b(?:select|insert|update|delete|truncate|alter|drop)"
                r"\s+(?:from\s+|into\s+)?public\."
            ),
        )
        self.assertNotIn("connect(", source)
        self.assertIn(
            "load_shadow_observation_acceptance_evidence", source
        )

    def test_contract_freezes_thresholds_sources_and_runtime_boundaries(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(contract["contract_version"], CONTRACT_VERSION)
        self.assertEqual(
            contract["thresholds"]["minimum_open_trade_date_count"],
            10,
        )
        self.assertEqual(
            contract["thresholds"][
                "minimum_decision_call_attempt_count"
            ],
            50,
        )
        self.assertEqual(
            contract["thresholds"]["minimum_structure_valid_rate"],
            0.99,
        )
        self.assertIsNone(
            contract["denominator"]["zero_denominator_rate"]
        )
        self.assertFalse(contract["evidence_input"]["direct_sql"])
        self.assertFalse(contract["evidence_input"]["dml"])
        boundaries = contract["safety_boundaries"]
        self.assertTrue(boundaries["read_only"])
        self.assertFalse(boundaries["autonomous_trading"])
        self.assertFalse(boundaries["real_trading"])
        self.assertFalse(boundaries["production_agent_usable"])

    def test_phase_a_and_b_payload_is_preserved(self):
        combined = sha256(
            b"".join(path.read_bytes() for path in PHASE_AB_PATHS)
        ).hexdigest()
        self.assertEqual(combined, PHASE_AB_COMBINED_SHA256)


if __name__ == "__main__":
    unittest.main()
