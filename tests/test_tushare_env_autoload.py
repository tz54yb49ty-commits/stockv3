import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


class TushareEnvAutoloadTest(unittest.TestCase):
    def test_loads_token_from_secret_file_without_printing_or_returning_summary_secret(self) -> None:
        from ashare_v3.ingestion.tushare_env import load_tushare_token, tushare_token_status

        secret_token = "secret-token-from-file-123"
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / "ashare_v3_tushare.env"
            env_path.write_text(
                "\n".join(
                    [
                        "# local secret file",
                        "export TUSHARE_TOKEN='secret-token-from-file-123'",
                    ]
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch.dict(os.environ, {"ASHARE_V3_TUSHARE_ENV_PATH": str(env_path)}, clear=True):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    token = load_tushare_token()
                    status = tushare_token_status()

            self.assertEqual(token, secret_token)
            self.assertEqual(status, {"token_present": True, "token_length": len(secret_token)})
            self.assertNotIn(secret_token, stdout.getvalue())
            self.assertNotIn(secret_token, stderr.getvalue())
            self.assertNotIn(secret_token, repr(status))

    def test_environment_token_takes_precedence_over_secret_file(self) -> None:
        from ashare_v3.ingestion.tushare_env import load_tushare_token, tushare_token_status

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / "ashare_v3_tushare.env"
            env_path.write_text("TUSHARE_TOKEN=secret-file-token\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"ASHARE_V3_TUSHARE_ENV_PATH": str(env_path), "TUSHARE_TOKEN": "env-token-wins"},
                clear=True,
            ):
                self.assertEqual(load_tushare_token(), "env-token-wins")
                self.assertEqual(tushare_token_status(), {"token_present": True, "token_length": 14})

    def test_missing_secret_reports_absent_without_leaking_path_content(self) -> None:
        from ashare_v3.ingestion.tushare_env import load_tushare_token, tushare_token_status

        with patch.dict(os.environ, {"ASHARE_V3_TUSHARE_ENV_PATH": "/tmp/does-not-exist.env"}, clear=True):
            self.assertIsNone(load_tushare_token())
            self.assertEqual(tushare_token_status(), {"token_present": False, "token_length": 0})

    def test_bj_index_adapter_autoloads_secret_token(self) -> None:
        from ashare_v3.market.realtime_snapshot_execute import TushareBjIndexSnapshotAdapter

        captured: dict[str, str] = {}

        class FakeTushareModule:
            @staticmethod
            def pro_api(token: str) -> object:
                captured["token"] = token
                return object()

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / "ashare_v3_tushare.env"
            env_path.write_text("TUSHARE_TOKEN=secret-token-for-bj\n", encoding="utf-8")
            with patch.dict(os.environ, {"ASHARE_V3_TUSHARE_ENV_PATH": str(env_path)}, clear=True):
                with patch("importlib.import_module", return_value=FakeTushareModule):
                    client = TushareBjIndexSnapshotAdapter()._client_or_raise()

        self.assertIsNotNone(client)
        self.assertEqual(captured["token"], "secret-token-for-bj")

    def test_n1_n3_entrypoints_do_not_read_tushare_token_directly(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        forbidden = (
            'os.environ.get("TUSHARE_TOKEN"',
            "os.environ.get('TUSHARE_TOKEN'",
            'os.getenv("TUSHARE_TOKEN"',
            "os.getenv('TUSHARE_TOKEN'",
        )
        offenders: list[str] = []
        for root in (repo_root / "src" / "ashare_v3", repo_root / "scripts"):
            for path in root.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                if any(pattern in text for pattern in forbidden):
                    offenders.append(str(path.relative_to(repo_root)))

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
