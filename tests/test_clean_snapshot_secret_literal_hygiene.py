import re
import subprocess
import unittest
from pathlib import Path
from urllib.parse import urlsplit


class CleanSnapshotSecretLiteralHygieneTest(unittest.TestCase):
    def test_tracked_files_do_not_contain_password_bearing_postgres_dsn_literals(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        tracked = subprocess.check_output(["git", "ls-files"], cwd=repo, text=True).splitlines()
        dsn_pattern = re.compile(r"postgres(?:ql)?://[^\s\"']+", re.IGNORECASE)
        offenders: list[str] = []

        for rel_path in tracked:
            path = repo / rel_path
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for line_no, line in enumerate(text.splitlines(), 1):
                for match in dsn_pattern.finditer(line):
                    value = match.group(0).rstrip("),.;]}`")
                    parsed = urlsplit(value)
                    if parsed.password:
                        offenders.append(f"{rel_path}:{line_no}")

        self.assertEqual([], offenders)
