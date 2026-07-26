import asyncio
import copy
import inspect
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from ashare_v3.web.n6_app_v1 import (
    app_strategy_center_change_batch_model,
    app_strategy_center_model,
)
from ashare_v3.web.n6_user_app import (
    N6UserWebConfig,
    PostgresN6UserRepository,
    build_runtime_strategy_center_repository,
    create_app,
    encode_n6_strategy_center_sse_event,
    iter_n6_strategy_center_sse,
)
from tests.test_n6_user_app import (
    FakeN6UserRepository,
    FixedPasswordHasher,
    FixedPasswordVerifier,
)


def strategy_state() -> dict[str, Any]:
    return {
        "trade_date": "2026-07-22",
        "packages": [
            {
                "package_key": "package_1",
                "package_version": "v2",
                "display_name": "策略包1",
                "rule_kind": "same_direction_index_board_stock_confluence",
                "allowed_board_types": [
                    "tdx_industry",
                    "tdx_concept",
                    "tdx_region",
                ],
                "default_selected": True,
                "policy_hash": "package-1-policy",
                "rule_json": {"requires_index_executed": True},
            },
            {
                "package_key": "package_2",
                "package_version": "v2",
                "display_name": "策略包2",
                "rule_kind": "same_direction_board_stock_confluence",
                "allowed_board_types": [
                    "tdx_industry",
                    "tdx_concept",
                    "tdx_region",
                ],
                "default_selected": False,
                "policy_hash": "package-2-policy",
                "rule_json": {"requires_index_executed": False},
            },
        ],
        "active_selection": {
            "selection_revision_id": 9007199254740993,
            "revision_no": 1,
            "selection_status": "active",
            "replay_status": "passed",
            "effective_trade_date": "2026-07-22",
            "selected_package_keys": ["package_1"],
        },
        "pending_selection": None,
        "scope": {
            "mode": "monitor_union_realtime_scope_union_virtual_position",
            "stock_count": 3,
            "monitor_count": 1,
            "realtime_scope_count": 1,
            "virtual_position_count": 1,
            "multi_source_count": 0,
        },
        "matches": [
            {
                "surface_kind": "qualified_match",
                "strategy_match_projection_id": 9007199254740995,
                "trade_date": "2026-07-22",
                "stock_identity_key": "stock:SZ:000001",
                "action_episode_key": "episode-000001-buy-1",
                "coherence_episode_key": "coherence-000001-buy-1",
                "action_state": "executed",
                "direction": "buy",
                "coherence_level": "STRONG",
                "freshness_status": "fresh",
                "evaluator_policy_hash": "a" * 64,
                "matched_packages": ["package_1", "package_2"],
                "scope_sources": ["monitor", "virtual_position"],
                "indices": [
                    {
                        "identity_key": "index:SH:000300",
                        "code": "000300",
                        "name": "沪深300",
                        "executed_today": True,
                        "selected_for_confluence": True,
                    }
                ],
                "matched_boards": [
                    {
                        "identity_key": "board:TDX:881155",
                        "code": "881155",
                        "name": "银行",
                        "board_type": "tdx_industry",
                    }
                ],
                "signal": {
                    "outbox_id": "9007199254740997",
                    "event_id": "action-executed-000001",
                    "asset_kind": "stock",
                    "identity_key": "stock:SZ:000001",
                    "code": "000001",
                    "name": "平安银行",
                    "action_state": "executed",
                    "action_price": "12.34",
                    "existing_future_field": {"kept": True},
                },
                "confluence": {
                    "strategy_version": "N6_STRATEGY_CENTER_TEMPORAL_CONFLUENCE_V2",
                    "evaluator_policy_hash": "a" * 64,
                    "direction": "buy",
                    "coherence_level": "STRONG",
                    "coherence_span_trading_minutes": 12.5,
                    "confirmation_time": "2026-07-22T10:01:00+08:00",
                    "stale_at": "2026-07-22T10:31:00+08:00",
                    "freshness_status": "fresh",
                    "package_evidence": [
                        {
                            "package_key": "package_1",
                            "coherence_level": "STRONG",
                            "coherence_span_trading_minutes": 12.5,
                            "stock_event_id": "action-executed-000001",
                            "stock_event_time": "2026-07-22T10:01:00+08:00",
                            "board_identity_key": "board:TDX:881155",
                            "board_event_id": "board-buy-1",
                            "board_event_time": "2026-07-22T09:55:00+08:00",
                            "index_identity_key": "index:SH:000300",
                            "index_event_id": "index-buy-1",
                            "index_event_time": "2026-07-22T09:48:30+08:00",
                        },
                        {
                            "package_key": "package_2",
                            "coherence_level": "STRONG",
                            "coherence_span_trading_minutes": 6,
                            "stock_event_id": "action-executed-000001",
                            "stock_event_time": "2026-07-22T10:01:00+08:00",
                            "board_identity_key": "board:TDX:881155",
                            "board_event_id": "board-buy-1",
                            "board_event_time": "2026-07-22T09:55:00+08:00",
                        },
                    ],
                    "market_heat_state": "MARKET_HEAT_SUPPORTIVE",
                    "market_heat_evidence": [
                        {
                            "index_identity_key": "index:SH:000001",
                            "event_id": "market-heat-sh-buy",
                            "event_time": "2026-07-22T09:50:00+08:00",
                            "direction": "buy",
                        },
                        {
                            "index_identity_key": "index:SZ:399001",
                            "event_id": "market-heat-sz-buy",
                            "event_time": "2026-07-22T09:52:00+08:00",
                            "direction": "buy",
                        },
                    ],
                },
                "state_timeline": [
                    {"action_state": "eligible", "event_id": "eligible-1"},
                    {"action_state": "executed", "event_id": "executed-1"},
                ],
                "mapping_quality": "passed",
                "matched_at": "2026-07-22T10:01:00+08:00",
                "updated_at": "2026-07-22T10:02:00+08:00",
            }
        ],
        "observations": [
            {
                "surface_kind": "observation",
                "strategy_observation_projection_id": 9007199254740996,
                "trade_date": "2026-07-22",
                "stock_identity_key": "stock:SZ:000002",
                "action_episode_key": "episode-000002-sell-1",
                "coherence_episode_key": "coherence-000002-sell-1",
                "action_state": "eligible",
                "direction": "sell",
                "coherence_level": "WEAK",
                "freshness_status": "weak",
                "evaluator_policy_hash": "b" * 64,
                "observation_reason": "weak_span",
                "observed_packages": ["package_2"],
                "scope_sources": ["realtime_scope"],
                "indices": [],
                "observed_boards": [
                    {
                        "identity_key": "board:TDX:881155",
                        "code": "881155",
                        "name": "银行",
                        "board_type": "tdx_industry",
                    }
                ],
                "signal": {
                    "event_id": "action-eligible-000002",
                    "asset_kind": "stock",
                    "identity_key": "stock:SZ:000002",
                    "code": "000002",
                    "name": "万科A",
                    "action_state": "eligible",
                },
                "confluence": {
                    "strategy_version": "N6_STRATEGY_CENTER_TEMPORAL_CONFLUENCE_V2",
                    "evaluator_policy_hash": "b" * 64,
                    "direction": "sell",
                    "coherence_level": "WEAK",
                    "coherence_span_trading_minutes": 42,
                    "confirmation_time": "2026-07-22T10:42:00+08:00",
                    "stale_at": "2026-07-22T11:12:00+08:00",
                    "freshness_status": "weak",
                    "package_evidence": [
                        {
                            "package_key": "package_2",
                            "coherence_level": "WEAK",
                            "coherence_span_trading_minutes": 42,
                            "stock_event_id": "action-eligible-000002",
                            "stock_event_time": "2026-07-22T10:42:00+08:00",
                            "board_identity_key": "board:TDX:881155",
                            "board_event_id": "board-sell-1",
                            "board_event_time": "2026-07-22T10:00:00+08:00",
                        }
                    ],
                    "market_heat_state": "MARKET_HEAT_MIXED",
                    "market_heat_evidence": [],
                },
                "state_timeline": [
                    {"action_state": "eligible", "event_id": "action-eligible-000002"}
                ],
                "mapping_quality": "missing_index",
                "observed_at": "2026-07-22T10:42:00+08:00",
                "updated_at": "2026-07-22T10:42:00+08:00",
            }
        ],
        "watermark": 9007199254741000,
        "watermarks": {
            "qualified_match": 9007199254740999,
            "observation": 9007199254741000,
        },
        "quality": {
            "qualified_match": {"status": "ready", "missing_count": 0},
            "observation": {"status": "ready", "missing_count": 0},
        },
    }


class StrategyRepository(FakeN6UserRepository):
    def __init__(self) -> None:
        super().__init__()
        self.strategy_state = strategy_state()
        self.strategy_states_by_user_id: dict[int, dict[str, Any]] = {}
        self.strategy_state_session_hashes: list[str] = []
        self.strategy_change_calls: list[dict[str, Any]] = []
        self.strategy_selection_calls: list[dict[str, Any]] = []
        self.strategy_selection_error = ""

    def fetch_strategy_center_state(
        self, session_token_hash: str
    ) -> dict[str, Any] | None:
        self.strategy_state_session_hashes.append(session_token_hash)
        session = self.sessions_by_hash.get(session_token_hash)
        if session is None:
            return None
        return copy.deepcopy(
            self.strategy_states_by_user_id.get(session.user_id, self.strategy_state)
        )

    def fetch_strategy_center_changes(
        self, session_token_hash: str, *, after_id: int, limit: int
    ) -> dict[str, Any] | None:
        self.strategy_change_calls.append(
            {
                "session_token_hash": session_token_hash,
                "after_id": after_id,
                "limit": limit,
            }
        )
        if session_token_hash not in self.sessions_by_hash:
            return None
        return {"events": [], "watermark": after_id, "has_more": False}

    def put_strategy_center_selection(
        self,
        session_token_hash: str,
        *,
        selected_package_keys: list[str],
        expected_revision: int,
        request_id: str,
    ) -> dict[str, Any] | None:
        if self.strategy_selection_error:
            raise ValueError(self.strategy_selection_error)
        self.strategy_selection_calls.append(
            {
                "session_token_hash": session_token_hash,
                "selected_package_keys": list(selected_package_keys),
                "expected_revision": expected_revision,
                "request_id": request_id,
            }
        )
        if session_token_hash not in self.sessions_by_hash:
            return None
        return {
            "selection_revision_id": 9007199254741001,
            "revision_no": expected_revision + 1,
            "selection_status": "pending",
            "replay_status": "pending",
            "effective_trade_date": "2026-07-22",
            "selected_package_keys": sorted(selected_package_keys),
        }


class StrategyClient:
    def __init__(self, *, write_enabled: bool) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.repository = StrategyRepository()
        secret_path = Path(self.directory.name) / "csrf"
        secret_path.write_text("strategy-center-test-secret")
        secret_path.chmod(0o600)
        app = create_app(
            repository=self.repository,
            config=N6UserWebConfig(
                cookie_secure=False,
                session_ttl_seconds=3600,
                strategy_center_write_enabled=write_enabled,
                csrf_secret_file=str(secret_path),
            ),
            password_verifier=FixedPasswordVerifier(True),
            password_hasher=FixedPasswordHasher(),
        )
        self.client = TestClient(app, follow_redirects=False)

    def close(self) -> None:
        self.client.close()
        self.directory.cleanup()

    def login(self) -> str:
        response = self.client.post(
            "/api/n6/auth/login",
            json={"login_name": "admin", "password": "password"},
        )
        if response.status_code != 302:
            raise AssertionError(response.text)
        page = self.client.get("/n6/app/account")
        match = re.search(r'data-n6-csrf-token="([^"]*)"', page.text)
        if match is None:
            raise AssertionError("csrf token not rendered")
        return match.group(1)


class StrategyCenterApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = StrategyClient(write_enabled=True)

    def tearDown(self) -> None:
        self.fixture.close()

    def test_model_preserves_signal_dto_and_stringifies_bigint_ids(self) -> None:
        state = strategy_state()
        payload = app_strategy_center_model(
            {"principal_id": 1, "principal_type": "admin", "owner_user_id": 1},
            user={"user_id": 1, "login_name": "admin", "display_name": "Admin"},
            state=state,
            write_enabled=True,
        )
        self.assertEqual(payload["active_selection"]["selection_revision_id"], "9007199254740993")
        self.assertEqual(payload["matches"][0]["strategy_match_projection_id"], "9007199254740995")
        self.assertEqual(payload["observations"][0]["strategy_observation_projection_id"], "9007199254740996")
        self.assertEqual(payload["watermark"], "9007199254741000")
        self.assertEqual(payload["watermarks"]["qualified_match"], "9007199254740999")
        self.assertEqual(payload["watermarks"]["observation"], "9007199254741000")
        self.assertEqual(
            payload["matches"][0]["confluence"]["evaluator_policy_hash"],
            "a" * 64,
        )
        self.assertEqual(
            payload["observations"][0]["confluence"]["evaluator_policy_hash"],
            "b" * 64,
        )
        self.assertEqual(payload["matches"][0]["signal"], state["matches"][0]["signal"])
        self.assertEqual(payload["matches"][0]["confluence"], state["matches"][0]["confluence"])
        self.assertEqual(payload["matches"][0]["surface_kind"], "qualified_match")
        self.assertEqual(payload["observations"][0]["surface_kind"], "observation")
        self.assertEqual(payload["observations"][0]["observation_reason"], "weak_span")
        self.assertEqual(payload["counts"], {"qualified_match": 1, "observation": 1, "total": 2})
        self.assertEqual(
            payload["active_selection"]["selected_packages"],
            [{"package_key": "package_1", "package_version": "v2"}],
        )
        self.assertTrue(payload["quality"]["canonical_signal_dto"])
        self.assertTrue(payload["quality"]["confluence_separate"])
        self.assertTrue(payload["quality"]["display_only"])
        self.assertFalse(payload["quality"]["auto_buy_enabled"])

    def test_model_extracts_legacy_confluence_without_polluting_signal_dto(self) -> None:
        state = strategy_state()
        row = state["matches"][0]
        canonical_signal = copy.deepcopy(row["signal"])
        legacy_confluence = row.pop("confluence")
        row["signal"]["strategy_center_temporal_confluence"] = legacy_confluence
        payload = app_strategy_center_model(
            {"principal_id": 1, "principal_type": "admin", "owner_user_id": 1},
            user={"user_id": 1, "login_name": "admin", "display_name": "Admin"},
            state=state,
            write_enabled=True,
        )
        self.assertEqual(payload["matches"][0]["signal"], canonical_signal)
        self.assertEqual(payload["matches"][0]["confluence"], legacy_confluence)
        self.assertNotIn(
            "strategy_center_temporal_confluence", payload["matches"][0]["signal"]
        )

    def test_model_rejects_conflicting_top_level_and_legacy_confluence(self) -> None:
        state = strategy_state()
        row = state["matches"][0]
        polluted = copy.deepcopy(row["confluence"])
        polluted["direction"] = "sell"
        row["signal"]["strategy_center_temporal_confluence"] = polluted
        with self.assertRaisesRegex(ValueError, "conflicting_strategy_confluence"):
            app_strategy_center_model(
                {"principal_id": 1, "principal_type": "admin", "owner_user_id": 1},
                user={"user_id": 1, "login_name": "admin", "display_name": "Admin"},
                state=state,
                write_enabled=True,
            )

    def test_model_suppresses_grandfathered_v1_results_fail_closed(self) -> None:
        state = strategy_state()
        state["active_selection"]["selected_packages"] = [
            {"package_key": "package_1", "package_version": "v1"}
        ]
        state["matches"][0]["confluence"][
            "strategy_version"
        ] = "N6_STRATEGY_CENTER_V1"
        state["observations"][0]["confluence"][
            "strategy_version"
        ] = "N6_STRATEGY_CENTER_V1"
        payload = app_strategy_center_model(
            {"principal_id": 1, "principal_type": "admin", "owner_user_id": 1},
            user={"user_id": 1, "login_name": "admin", "display_name": "Admin"},
            state=state,
            write_enabled=True,
        )
        self.assertEqual(
            payload["active_selection"]["selected_packages"],
            [{"package_key": "package_1", "package_version": "v1"}],
        )
        self.assertEqual(payload["packages"][0]["package_version"], "v2")
        self.assertTrue(payload["migration_required"])
        self.assertEqual(payload["legacy_v1_suppressed_count"], 2)
        self.assertEqual(payload["matches"], [])
        self.assertEqual(payload["observations"], [])
        self.assertEqual(
            payload["counts"],
            {"qualified_match": 0, "observation": 0, "total": 0},
        )
        self.assertEqual(payload["quality"]["status"], "migration_required")

    def test_model_keeps_v2_surfaces_and_signal_dto_isomorphic(self) -> None:
        state = strategy_state()
        payload = app_strategy_center_model(
            {"principal_id": 1, "principal_type": "admin", "owner_user_id": 1},
            user={"user_id": 1, "login_name": "admin", "display_name": "Admin"},
            state=state,
            write_enabled=True,
        )
        self.assertFalse(payload["migration_required"])
        self.assertEqual(payload["legacy_v1_suppressed_count"], 0)
        self.assertEqual(payload["matches"][0]["signal"], state["matches"][0]["signal"])
        self.assertEqual(
            payload["observations"][0]["signal"], state["observations"][0]["signal"]
        )

    def test_model_exposes_stale_candidate_on_observation_surface(self) -> None:
        state = strategy_state()
        observation = state["observations"][0]
        observation["coherence_level"] = "STRONG"
        observation["freshness_status"] = "stale"
        observation["observation_reason"] = "stale_after_confirmation"
        observation["confluence"]["coherence_level"] = "STRONG"
        observation["confluence"]["freshness_status"] = "stale"
        payload = app_strategy_center_model(
            {"principal_id": 1, "principal_type": "admin", "owner_user_id": 1},
            user={"user_id": 1, "login_name": "admin", "display_name": "Admin"},
            state=state,
            write_enabled=True,
        )
        self.assertEqual(
            payload["observations"][0]["observation_reason"],
            "stale_after_confirmation",
        )
        self.assertEqual(
            payload["observations"][0]["confluence"]["freshness_status"],
            "stale",
        )

    def test_get_requires_session_and_uses_only_session_authority(self) -> None:
        unauthorized = self.fixture.client.get("/api/n6/app/v3/strategy-center")
        self.assertEqual(unauthorized.status_code, 401)

        self.fixture.login()
        response = self.fixture.client.get("/api/n6/app/v3/strategy-center")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["scope"]["stock_count"], 3)
        self.assertEqual(payload["match_count"], 1)
        self.assertEqual(payload["observation_count"], 1)
        self.assertEqual(payload["contract_version"], "n6-strategy-center-api-v2")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(len(self.fixture.repository.strategy_state_session_hashes), 1)
        self.assertIn(
            self.fixture.repository.strategy_state_session_hashes[0],
            self.fixture.repository.sessions_by_hash,
        )

    def test_get_keeps_v1_suppression_isolated_per_authenticated_user(self) -> None:
        v1_state = strategy_state()
        v1_state["active_selection"]["selected_packages"] = [
            {"package_key": "package_1", "package_version": "v1"}
        ]
        self.fixture.repository.strategy_states_by_user_id[1] = v1_state
        self.fixture.repository.create_user_with_defaults(
            login_name="strategy-user",
            display_name="Strategy User",
            role="user",
            password_hash="stored-password-hash",
            password_hash_algo="argon2id",
            created_by_user_id=1,
        )
        strategy_user = self.fixture.repository.users_by_login["strategy-user"]
        self.fixture.repository.strategy_states_by_user_id[
            strategy_user.user_id
        ] = strategy_state()

        self.fixture.login()
        admin_payload = self.fixture.client.get(
            "/api/n6/app/v3/strategy-center"
        ).json()
        self.fixture.client.post(
            "/api/n6/auth/login",
            json={"login_name": "strategy-user", "password": "password"},
        )
        user_payload = self.fixture.client.get(
            "/api/n6/app/v3/strategy-center"
        ).json()

        self.assertTrue(admin_payload["migration_required"])
        self.assertEqual(admin_payload["matches"], [])
        self.assertFalse(user_payload["migration_required"])
        self.assertEqual(user_payload["match_count"], 1)
        self.assertEqual(user_payload["principal"]["display_name"], "Strategy User")
        self.assertNotEqual(
            user_payload["principal"]["principal_id"],
            admin_payload["principal"]["principal_id"],
        )

    def test_strategy_center_page_has_navigation_display_only_ui_and_refresh_contract(self) -> None:
        self.fixture.login()
        response = self.fixture.client.get("/n6/app/strategy-center")
        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/n6/app/strategy-center"', response.text)
        self.assertIn("data-n6-strategy-center", response.text)
        self.assertIn("策略包选择", response.text)
        self.assertIn("纯展示", response.text)
        self.assertIn("合格候选", response.text)
        self.assertIn("观察区", response.text)
        self.assertIn("STRONG / MEDIUM", response.text)
        self.assertIn("WEAK / stale", response.text)
        self.assertIn("data-strategy-qualified-results", response.text)
        self.assertIn("data-strategy-observation-results", response.text)
        self.assertIn("各层事件时间与冻结 lineage", response.text)
        self.assertIn("市场热度指数证据（000001 / 399001）", response.text)
        self.assertIn("版本 ${escapeHtml(item.package_version)}", response.text)
        self.assertIn("data-strategy-migration-required", response.text)
        self.assertIn("V1 历史结果已 fail-closed 隔离", response.text)
        self.assertIn("activeSelection.revision_no", response.text)
        self.assertIn("item.package_version", response.text)
        self.assertIn("/api/n6/app/v3/strategy-center/stream", response.text)
        self.assertIn("45000", response.text)
        template = (
            Path(__file__).parents[1]
            / "src/ashare_v3/web/templates/n6_app_shell.html"
        ).read_text()
        strategy_section = template.split(
            '{% elif page.page_key == "strategy-center" %}', 1
        )[1].split('{% elif page.page_key == "trade-log" %}', 1)[0]
        self.assertNotIn("data-n6-create-proposal", strategy_section)
        self.assertNotIn("自动买入", strategy_section)

    def test_strategy_center_refresh_is_coalesced_and_single_flight(self) -> None:
        template = (
            Path(__file__).parents[1]
            / "src/ashare_v3/web/templates/n6_app_shell.html"
        ).read_text()
        script = template.split("const n6StrategyCenter = (() => {", 1)[1].split(
            "n6StrategyCenter.init();", 1
        )[0]
        refresh_state = script[script.index("let refreshPromise = null;") :]
        refresh_state = refresh_state[: refresh_state.index("const status =")]
        scheduler = script[script.index("const performRefresh = async () => {") :]
        scheduler = scheduler[: scheduler.index("const save = async () => {")]
        harness = r"""
const timers = new Map();
const intervals = new Map();
const pendingFetches = [];
let nextTimerId = 1;
let fetchCalls = 0;
let activeFetches = 0;
let maxActiveFetches = 0;
let renderCalls = 0;
let source = {
  closed: false,
  close() { this.closed = true; },
};
const window = {
  setTimeout(callback, delay) {
    const id = nextTimerId++;
    timers.set(id, { callback, delay });
    return id;
  },
  clearTimeout(id) { timers.delete(id); },
  setInterval(callback, delay) {
    const id = nextTimerId++;
    intervals.set(id, { callback, delay });
    return id;
  },
  clearInterval(id) { intervals.delete(id); },
};
const refreshButton = { disabled: false };
const status = () => {};
const render = () => { renderCalls += 1; };
const fetch = () => {
  fetchCalls += 1;
  activeFetches += 1;
  maxActiveFetches = Math.max(maxActiveFetches, activeFetches);
  return new Promise((resolve) => {
    pendingFetches.push({
      resolve(value) {
        activeFetches -= 1;
        resolve(value);
      },
    });
  });
};
""" + refresh_state + scheduler + r"""
const fireOnlyTimer = () => {
  if (timers.size !== 1) throw new Error(`expected_one_timer:${timers.size}`);
  const entry = Array.from(timers.values())[0];
  timers.clear();
  entry.callback();
};
const response = { ok: true, json: async () => ({ ok: true }) };
(async () => {
  for (let index = 0; index < 100; index += 1) scheduleStreamRefresh();
  if (timers.size !== 1) throw new Error(`first_burst_timer_count:${timers.size}`);
  if (Array.from(timers.values())[0].delay !== 250) throw new Error("bad_debounce_delay");
  fireOnlyTimer();
  const firstFlight = refreshPromise;
  if (fetchCalls !== 1) throw new Error(`first_fetch_count:${fetchCalls}`);

  for (let index = 0; index < 100; index += 1) scheduleStreamRefresh();
  if (timers.size !== 1) throw new Error(`inflight_burst_timer_count:${timers.size}`);
  fireOnlyTimer();
  if (!refreshAfterFlight) throw new Error("trailing_refresh_not_queued");
  if (fetchCalls !== 1) throw new Error(`overlapping_fetch_started:${fetchCalls}`);

  pendingFetches.shift().resolve(response);
  await firstFlight;
  await Promise.resolve();
  if (fetchCalls !== 2) throw new Error(`trailing_fetch_count:${fetchCalls}`);
  const secondFlight = refreshPromise;
  pendingFetches.shift().resolve(response);
  await secondFlight;
  if (refreshPromise !== null) throw new Error("refresh_promise_not_cleared");
  if (maxActiveFetches !== 1) throw new Error(`max_active_fetches:${maxActiveFetches}`);
  if (renderCalls !== 2) throw new Error(`render_count:${renderCalls}`);

  scheduleStreamRefresh();
  fullRefreshTimer = window.setInterval(() => {}, 45000);
  dispose();
  if (!disposed || !source.closed) throw new Error("dispose_did_not_close");
  if (timers.size !== 0 || intervals.size !== 0) throw new Error("dispose_did_not_clear_timers");
  scheduleStreamRefresh();
  if (timers.size !== 0) throw new Error("refresh_scheduled_after_dispose");
  console.log(JSON.stringify({ fetchCalls, maxActiveFetches, renderCalls }));
})().catch((error) => {
  console.error(error.stack || String(error));
  process.exitCode = 1;
});
"""
        completed = subprocess.run(
            ["node", "-e", harness],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            json.loads(completed.stdout),
            {"fetchCalls": 2, "maxActiveFetches": 1, "renderCalls": 2},
        )
        self.assertIn("}, 45000);", script)
        self.assertIn(
            "source.addEventListener(eventType, scheduleStreamRefresh)", script
        )
        self.assertIn(
            'const streamEventTypes = ["upsert", "remove", "reset"]', script
        )
        self.assertIn('window.addEventListener("beforeunload", dispose)', script)

    def test_selection_requires_csrf_and_rejects_client_authority(self) -> None:
        csrf = self.fixture.login()
        body = {
            "selected_package_keys": ["package_1", "package_2"],
            "expected_revision": 1,
            "request_id": "selection-request-0001",
        }
        missing = self.fixture.client.put(
            "/api/n6/app/v3/strategy-center/selection", json=body
        )
        self.assertEqual(missing.status_code, 403)
        polluted = self.fixture.client.put(
            "/api/n6/app/v3/strategy-center/selection",
            json={**body, "principal_id": 999},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(polluted.status_code, 400)
        self.assertEqual(polluted.json()["error"], "client_scope_not_allowed")
        self.assertEqual(self.fixture.repository.strategy_selection_calls, [])

    def test_selection_accepts_multi_select_and_passes_no_client_user_id(self) -> None:
        csrf = self.fixture.login()
        response = self.fixture.client.put(
            "/api/n6/app/v3/strategy-center/selection",
            json={
                "selected_package_keys": ["package_2", "package_1"],
                "expected_revision": 1,
                "request_id": "selection-request-0002",
            },
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["selection"]["revision_no"], 2)
        self.assertTrue(response.json()["replay_required"])
        call = self.fixture.repository.strategy_selection_calls[0]
        self.assertEqual(call["selected_package_keys"], ["package_2", "package_1"])
        self.assertNotIn("principal_id", call)
        self.assertNotIn("user_id", call)

    def test_selection_rejects_zero_duplicate_unknown_and_revision_conflict(self) -> None:
        csrf = self.fixture.login()
        base = {"expected_revision": 1, "request_id": "selection-request-0003"}
        for selected in ([], ["package_1", "package_1"], ["package_3"]):
            with self.subTest(selected=selected):
                response = self.fixture.client.put(
                    "/api/n6/app/v3/strategy-center/selection",
                    json={**base, "selected_package_keys": selected},
                    headers={"X-CSRF-Token": csrf},
                )
                self.assertEqual(response.status_code, 400)
        self.fixture.repository.strategy_selection_error = "strategy_selection_revision_conflict"
        conflict = self.fixture.client.put(
            "/api/n6/app/v3/strategy-center/selection",
            json={**base, "selected_package_keys": ["package_1"]},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(conflict.status_code, 409)

    def test_write_flag_is_fail_closed(self) -> None:
        self.fixture.close()
        self.fixture = StrategyClient(write_enabled=False)
        self.fixture.login()
        response = self.fixture.client.put(
            "/api/n6/app/v3/strategy-center/selection",
            json={
                "selected_package_keys": ["package_1"],
                "expected_revision": 1,
                "request_id": "selection-request-0004",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "strategy_center_write_disabled")

    def test_stream_rejects_client_scope_and_invalid_cursor(self) -> None:
        self.fixture.login()
        polluted = self.fixture.client.get(
            "/api/n6/app/v3/strategy-center/stream?principal_id=999"
        )
        self.assertEqual(polluted.status_code, 400)
        invalid = self.fixture.client.get(
            "/api/n6/app/v3/strategy-center/stream?after_id=-1"
        )
        self.assertEqual(invalid.status_code, 400)

    def test_sse_iterator_emits_monotonic_typed_event(self) -> None:
        calls = 0

        async def run() -> list[str]:
            nonlocal calls

            async def read_batch(after_id: int, limit: int) -> dict[str, Any]:
                nonlocal calls
                calls += 1
                if calls == 1:
                    return app_strategy_center_change_batch_model(
                        {
                            "events": [
                                {
                                    "change_id": 8,
                                    "event": "upsert",
                                    "surface_kind": "observation",
                                    "trade_date": "2026-07-22",
                                    "selection_revision_id": 3,
                                    "strategy_observation_projection_id": 5,
                                    "source_event_id": "executed-1",
                                    "data": {
                                        "strategy_observation_projection_id": 5,
                                        "signal": {
                                            "event_id": "executed-1",
                                            "strategy_center_temporal_confluence": {
                                                "strategy_version": "N6_STRATEGY_CENTER_TEMPORAL_CONFLUENCE_V2",
                                                "evaluator_policy_hash": "c" * 64,
                                                "direction": "buy",
                                                "coherence_level": "WEAK",
                                            },
                                        },
                                    },
                                    "payload_hash": "hash",
                                    "created_at": "2026-07-22T10:00:00+08:00",
                                }
                            ],
                            "watermark": 8,
                            "has_more": False,
                        }
                    )
                return {"events": [], "watermark": after_id, "has_more": False}

            disconnected_checks = 0

            async def disconnected() -> bool:
                nonlocal disconnected_checks
                disconnected_checks += 1
                return disconnected_checks > 1

            async def no_sleep(_: float) -> None:
                return None

            output = []
            async for chunk in iter_n6_strategy_center_sse(
                after_id=7,
                read_batch=read_batch,
                is_disconnected=disconnected,
                sleep=no_sleep,
            ):
                output.append(chunk)
            return output

        output = asyncio.run(run())
        self.assertEqual(output[0], "retry: 5000\n\n")
        self.assertIn("event: upsert\nid: 8\n", output[1])
        self.assertIn('"surface_kind":"observation"', output[1])
        self.assertIn('"strategy_observation_projection_id":"5"', output[1])
        self.assertNotIn("strategy_center_temporal_confluence", output[1])
        self.assertIn('"confluence":{', output[1])
        self.assertIn('"coherence_level":"WEAK"', output[1])
        self.assertIn('"evaluator_policy_hash":"' + "c" * 64 + '"', output[1])

    def test_sse_encoder_requires_exact_surface_kind(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_strategy_center_sse_event"):
            encode_n6_strategy_center_sse_event(
                {"change_id": "1", "event": "upsert"}
            )
        encoded = encode_n6_strategy_center_sse_event(
            {
                "change_id": "2",
                "event": "reset",
                "surface_kind": "qualified_match",
            }
        )
        self.assertIn("event: reset\nid: 2\n", encoded)

    def test_postgres_repository_is_function_only_for_strategy_contract(self) -> None:
        source = inspect.getsource(PostgresN6UserRepository)
        self.assertIn("n6_btrack_strategy_center_state", source)
        self.assertIn("n6_btrack_strategy_center_changes", source)
        self.assertIn("n6_btrack_strategy_selection_put", source)
        strategy_methods = "\n".join(
            inspect.getsource(getattr(PostgresN6UserRepository, name))
            for name in (
                "fetch_strategy_center_state",
                "fetch_strategy_center_changes",
                "put_strategy_center_selection",
            )
        )
        self.assertNotIn("FROM public.n6_strategy_", strategy_methods)
        self.assertNotIn("INSERT INTO public.n6_strategy_", strategy_methods)

    def test_runtime_strategy_repository_requires_exact_limited_service(self) -> None:
        accepted = {
            "PGSERVICE": "n6_btrack_web",
            "PGSERVICEFILE": "/nonsecret/pg_service.conf",
            "PGPASSFILE": "/nonsecret/n6_btrack_web.pgpass",
        }
        repository = build_runtime_strategy_center_repository(accepted)
        self.assertIsInstance(repository, PostgresN6UserRepository)
        self.assertEqual(repository.dsn, "service=n6_btrack_web")
        for polluted in (
            {},
            {**accepted, "PGSERVICE": "ashare_v3_user"},
            {**accepted, "PGPASSWORD": "secret"},
            {**accepted, "ASHARE_V3_POSTGRES_DSN": "owner"},
            {**accepted, "PGSERVICEFILE": "relative"},
            {**accepted, "PGPASSFILE": ""},
        ):
            with self.subTest(polluted=polluted):
                self.assertIsNone(build_runtime_strategy_center_repository(polluted))

    def test_required_strategy_repository_fails_closed_without_runtime_binding(self) -> None:
        app = create_app(
            repository=StrategyRepository(),
            strategy_center_repository_required=True,
            config=N6UserWebConfig(cookie_secure=False),
            password_verifier=FixedPasswordVerifier(True),
            password_hasher=FixedPasswordHasher(),
        )
        client = TestClient(app, follow_redirects=False)
        try:
            client.post(
                "/api/n6/auth/login",
                json={"login_name": "admin", "password": "password"},
            )
            response = client.get("/api/n6/app/v3/strategy-center")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(
                response.json()["error"], "strategy_center_service_unavailable"
            )
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
