from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import subprocess
import tomllib
import unittest


PROJECT_ROOT = Path(
    "/Users/chuanfuchen/Documents/"
    "A股监控系统v3_n6_ai_research_room_rebind_v2"
)
CONFIG_PATH = PROJECT_ROOT / ".codex" / "config.toml"
EXPECTED_MANIFEST_SHA256 = (
    "fd99885a936dc835535bf7c4b2c7473"
    "106092f60b626421fcca5603dd2a72c82"
)
EXPECTED_TOOLS = [
    "knowledge_search",
    "knowledge_fetch",
    "ai_public_snapshot_get",
    "memory_candidate_append",
    "memory_candidate_list",
    "memory_candidate_get",
]
EXPECTED_READONLY_TOOLS = {
    "knowledge_search",
    "knowledge_fetch",
    "ai_public_snapshot_get",
    "memory_candidate_list",
    "memory_candidate_get",
}


class N6AiResearchProjectConfigTests(unittest.TestCase):
    def _config(self) -> dict:
        return tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    def test_exact_local_stdio_server_and_tool_boundary(self) -> None:
        config = self._config()
        self.assertEqual(config["model"], "gpt-5.6-sol")
        self.assertEqual(config["model_reasoning_effort"], "high")
        self.assertEqual(config["sandbox_mode"], "read-only")
        self.assertEqual(config["web_search"], "disabled")
        server = config["mcp_servers"]["n6_ai_research"]
        self.assertTrue(server["required"])
        self.assertTrue(server["enabled"])
        self.assertEqual(server["cwd"], str(PROJECT_ROOT))
        self.assertEqual(server["enabled_tools"], EXPECTED_TOOLS)
        self.assertEqual(
            server["args"],
            [
                str(
                    PROJECT_ROOT
                    / "scripts"
                    / "run_n6_ai_research_bridge.py"
                ),
                "--expected-manifest-sha256",
                EXPECTED_MANIFEST_SHA256,
            ],
        )
        self.assertEqual(
            server["default_tools_approval_mode"], "prompt"
        )
        self.assertEqual(
            server["tools"]["memory_candidate_append"][
                "approval_mode"
            ],
            "prompt",
        )
        self.assertEqual(
            {
                tool_name
                for tool_name, tool_config in server["tools"].items()
                if tool_config["approval_mode"] == "approve"
            },
            EXPECTED_READONLY_TOOLS,
        )

    def test_config_contains_no_secret_or_external_service(self) -> None:
        text = CONFIG_PATH.read_text(encoding="utf-8")
        lowered = text.lower()
        for forbidden in (
            "password",
            "pgpass",
            "api_key",
            "access_token",
            "refresh_token",
            "postgresql://",
            "http://",
            "https://",
        ):
            self.assertNotIn(forbidden, lowered)
        server = self._config()["mcp_servers"]["n6_ai_research"]
        self.assertNotIn("env_vars", server)
        self.assertEqual(
            set(server["env"]),
            {"PYTHONPATH", "PYTHONDONTWRITEBYTECODE"},
        )

    def test_manifest_hash_and_absolute_paths_are_current(self) -> None:
        import hashlib

        server = self._config()["mcp_servers"]["n6_ai_research"]
        manifest = (
            PROJECT_ROOT
            / "docs"
            / "N6_AI_KNOWLEDGE_BUNDLE_MANIFEST.json"
        )
        self.assertEqual(
            hashlib.sha256(manifest.read_bytes()).hexdigest(),
            EXPECTED_MANIFEST_SHA256,
        )
        self.assertTrue(Path(server["command"]).is_file())
        self.assertTrue(Path(server["args"][0]).is_file())
        self.assertTrue(Path(server["cwd"]).is_dir())

    def test_configured_server_initializes_and_lists_six_tools(
        self,
    ) -> None:
        server = self._config()["mcp_servers"]["n6_ai_research"]
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "project-config-test",
                        "version": "1",
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
            },
        ]
        completed = subprocess.run(
            [server["command"], *server["args"]],
            cwd=server["cwd"],
            env=server["env"],
            input=b"".join(
                json.dumps(item).encode("utf-8") + b"\n"
                for item in requests
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        responses = [
            json.loads(line)
            for line in BytesIO(completed.stdout).read().splitlines()
        ]
        self.assertEqual([item["id"] for item in responses], [1, 2])
        self.assertEqual(
            [
                item["name"]
                for item in responses[1]["result"]["tools"]
            ],
            EXPECTED_TOOLS,
        )


if __name__ == "__main__":
    unittest.main()
