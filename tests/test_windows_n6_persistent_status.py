from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ashare_v3.web.n6_user_app import (  # noqa: E402
    AuthSession,
    COOKIE_NAME,
    N6UserWebConfig,
    PostgresN6UserRepository,
    create_app,
    hash_session_token,
)
from ashare_v3.web.windows_n6_runtime import OfflineWindowsRuntimeBridge  # noqa: E402


SOURCE_DATE = "20260831"
FOR_DATE = "20260901"
N2_RUN = "condition_layer_20260831_to_20260901_20260901020202_execute"
N3_RUN = "windows_n3_previous_day_context_6ca6e4baf19d6842d07e92eb"
CONTEXT_VERSION = "pretrade_c2f55d9_v1"


def _n3_row(
    *, expected_stock: int = 5553, context_version: str = CONTEXT_VERSION,
) -> dict[str, object]:
    return {
        "context_run_id": N3_RUN,
        "source_condition_run_id": N2_RUN,
        "context_version": context_version,
        "source_trade_date": SOURCE_DATE,
        "for_trade_date": FOR_DATE,
        "status": "completed",
        "expected_stock_count": expected_stock,
        "expected_index_count": 100,
        "expected_board_count": 429,
        "terminal_stock_count": 5553,
        "terminal_index_count": 100,
        "terminal_board_count": 429,
        "result_summary": {
            "_coverage": {
                "expected_total": 6082,
                "ready_total": 6074,
                "missing_total": 8,
                "missing_ratio": 0.0013153567905294311,
                "coverage_gate": "passed",
            }
        },
        "updated_at": "2026-09-01T02:08:00+08:00",
    }


class _FakeCursor:
    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        self.current: list[dict[str, object]] = []
        self.statements: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, statement: str, _params=()) -> None:
        normalized = " ".join(statement.split())
        self.statements.append(normalized)
        if not normalized.upper().startswith("SELECT"):
            raise AssertionError(f"non-read-only SQL: {normalized}")
        if "FROM common_ingest_batch" in normalized and "status='passed'" in normalized:
            self.current = [] if self.scenario == "no_n1" else [{
                "trade_date": SOURCE_DATE,
                "batch_id": "windows_n1_fastlane_complete_20260831_v1",
                "finished_at": "2026-09-01T01:58:00+08:00",
                "created_at": "2026-09-01T01:58:00+08:00",
            }]
        elif "count(*) AS attempt_count" in normalized:
            self.current = [{"attempt_count": 2, "failed_attempt_count": 1}]
        elif "FROM common_condition_run" in normalized:
            if self.scenario == "waiting_n2":
                self.current = []
            elif self.scenario == "multiple_n2":
                row = self._n2_row()
                self.current = [row, {**row, "run_id": "conflicting_active_run"}]
            else:
                self.current = [self._n2_row()]
        elif "FROM stock_condition_basis" in normalized:
            self.current = [{"row_count": 5553}]
        elif "FROM index_condition_basis" in normalized:
            self.current = [{"row_count": 100}]
        elif "FROM board_condition_basis" in normalized:
            self.current = [{"row_count": 429}]
        elif "FROM common_n3_previous_day_context_run" in normalized:
            if self.scenario == "waiting_n3":
                self.current = []
            elif self.scenario == "multiple_n3":
                self.current = [_n3_row(), {**_n3_row(), "context_run_id": "conflict"}]
            else:
                self.current = [
                    _n3_row(expected_stock=5552)
                    if self.scenario == "n3_mismatch"
                    else _n3_row(
                        context_version="unexpected_v2"
                        if self.scenario == "context_version_mismatch"
                        else CONTEXT_VERSION
                    )
                ]
        else:
            raise AssertionError(f"unexpected SQL: {normalized}")

    def fetchone(self):
        return self.current[0] if self.current else None

    def fetchall(self):
        return list(self.current)

    @staticmethod
    def _n2_row() -> dict[str, object]:
        return {
            "run_id": N2_RUN,
            "source_trade_date": SOURCE_DATE,
            "for_trade_date": FOR_DATE,
            "status": "passed_active",
            "updated_at": "2026-09-01T02:02:02+08:00",
        }


class _FakeConnection:
    def __init__(self, scenario: str) -> None:
        self.cursor_value = _FakeCursor(scenario)
        self.write_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        return self.cursor_value


def _repository(scenario: str):
    connection = _FakeConnection(scenario)
    repository = PostgresN6UserRepository("fake://readonly")
    repository._readonly_connection = lambda: connection
    return repository, connection


class WindowsPersistentStatusRepositoryTest(unittest.TestCase):
    def test_20260831_complete_lineage_is_rendered_from_one_readonly_snapshot(self):
        repository, connection = _repository("passed")

        status = repository.fetch_windows_fastlane_persistent_status()

        self.assertEqual("passed", status["pipeline_status"])
        self.assertEqual((SOURCE_DATE, FOR_DATE), (status["source_trade_date"], status["for_trade_date"]))
        self.assertEqual("passed", status["n1_status"])
        self.assertEqual((2, 1), (status["n1_attempt_count"], status["n1_failed_attempt_count"]))
        self.assertEqual(N2_RUN, status["n2_run_id"])
        self.assertEqual({"stock": 5553, "index": 100, "board": 429}, status["n2_basis_counts"])
        self.assertEqual(N3_RUN, status["n3_context_run_id"])
        self.assertEqual(CONTEXT_VERSION, status["context_version"])
        self.assertEqual((6082, 6074, 8), (status["expected"], status["ready"], status["missing"]))
        self.assertEqual(0.0013153567905294311, status["missing_ratio"])
        self.assertEqual("passed", status["coverage_gate"])
        self.assertTrue(all(sql.startswith("SELECT") for sql in connection.cursor_value.statements))
        self.assertEqual(0, connection.write_count)
        self.assertFalse(any("outbox" in sql.lower() for sql in connection.cursor_value.statements))

    def test_missing_stages_and_lineage_mismatch_are_fail_closed(self):
        expected = {
            "no_n1": "no_persisted_status",
            "waiting_n2": "waiting_n2",
            "waiting_n3": "waiting_n3",
            "multiple_n2": "blocked_lineage_mismatch",
            "multiple_n3": "blocked_lineage_mismatch",
            "n3_mismatch": "blocked_lineage_mismatch",
            "context_version_mismatch": "blocked_lineage_mismatch",
        }
        for scenario, pipeline_status in expected.items():
            with self.subTest(scenario=scenario):
                repository, connection = _repository(scenario)
                status = repository.fetch_windows_fastlane_persistent_status()
                self.assertEqual(pipeline_status, status["pipeline_status"])
                self.assertTrue(all(sql.startswith("SELECT") for sql in connection.cursor_value.statements))


class _PageRepository:
    def __init__(self) -> None:
        self.database_write_count = 0
        self.market_request_count = 0
        self.outbox_write_count = 0
        self.session = AuthSession(
            user_session_id=1,
            user_id=1,
            login_name="admin",
            display_name="Admin",
            role="admin",
            status="active",
            session_token_hash=hash_session_token("offline-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            revoked_at=None,
        )

    def fetch_session(self, token_hash: str):
        return self.session if token_hash == self.session.session_token_hash else None

    def fetch_windows_fastlane_persistent_status(self):
        repository, _connection = _repository("passed")
        return repository.fetch_windows_fastlane_persistent_status()


class WindowsPersistentStatusHttpTest(unittest.TestCase):
    def test_intraday_offline_keeps_persisted_page_and_api_http_200(self):
        repository = _PageRepository()
        app = create_app(
            repository=repository,
            buy_execution_repository=object(),
            config=N6UserWebConfig(
                dsn="fake://readonly",
                windows_mode=True,
                virtual_executor_enabled=False,
            ),
            runtime_bridge=OfflineWindowsRuntimeBridge(),
        )
        client = TestClient(app)
        client.cookies.set(COOKIE_NAME, "offline-token")

        page = client.get("/n6/post-close-fastlane-status")
        api = client.get("/api/n6/ui/v1/post-close-fastlane-status")

        self.assertEqual(200, page.status_code)
        self.assertEqual(200, api.status_code)
        payload = api.json()
        self.assertEqual("passed", payload["pipeline_status"])
        self.assertEqual("offline", payload["intraday_runtime"])
        self.assertEqual(N2_RUN, payload["n2_run_id"])
        self.assertEqual(N3_RUN, payload["n3_context_run_id"])
        self.assertIn("盘中runtime已退出", page.text)
        self.assertIn(SOURCE_DATE, page.text)
        self.assertIn(FOR_DATE, page.text)
        self.assertIn("6082 / 6074 / 8", page.text)
        self.assertEqual(0, repository.database_write_count)
        self.assertEqual(0, repository.market_request_count)
        self.assertEqual(0, repository.outbox_write_count)


if __name__ == "__main__":
    unittest.main()
