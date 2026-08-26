#!/usr/bin/env python3
"""Write a non-secret, native-Windows N1 dependency authority manifest."""

from __future__ import annotations

from importlib import metadata, util
import json
from pathlib import Path
import platform
import subprocess
import sys


FORBIDDEN = ("tushare", "mootdx")


def build_manifest() -> dict[str, object]:
    freeze = subprocess.run(
        [sys.executable, "-m", "pip", "freeze", "--all"],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    direct_url_path = Path(metadata.distribution("eltdx").locate_file("eltdx-1.2.0.dist-info/direct_url.json"))
    direct_url = json.loads(direct_url_path.read_text(encoding="utf-8"))
    forbidden = {
        name: {
            "module_present": util.find_spec(name) is not None,
            "distribution_present": any(line.lower().startswith(name + "==") for line in freeze),
        }
        for name in FORBIDDEN
    }
    if any(item["module_present"] or item["distribution_present"] for item in forbidden.values()):
        raise RuntimeError(f"forbidden Windows N1 packages detected: {forbidden}")
    return {
        "schema_version": "WindowsN1RuntimeManifest.v1",
        "python": {
            "executable": sys.executable,
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "architecture": platform.architecture()[0],
            "platform": platform.platform(),
        },
        "pip_freeze": freeze,
        "eltdx": {"version": metadata.version("eltdx"), "direct_url": direct_url},
        "forbidden_packages": forbidden,
    }


def main() -> int:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\AshareV3\artifacts\n1\windows_n1_runtime_manifest.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_manifest(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
