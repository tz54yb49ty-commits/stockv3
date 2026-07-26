#!/usr/bin/env python3
"""Run the read-only N6 AI research-room knowledge bridge over stdio."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from ashare_v3.user.ai_research_bridge import (
    MAX_RPC_LINE_BYTES,
    ReadOnlyResearchBridge,
    ResearchBridgeError,
    serve_stdio,
)


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OBSIDIAN_ROOT = Path(
    "/Users/chuanfuchen/Documents/Obsidian Vault/A股监控系统v3"
)
DEFAULT_MANIFEST = Path(
    "docs/N6_AI_KNOWLEDGE_BUNDLE_MANIFEST.json"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--expected-manifest-sha256",
        required=True,
    )
    parser.add_argument(
        "--max-line-bytes",
        type=int,
        default=MAX_RPC_LINE_BYTES,
    )
    return parser


def build_bridge(args: argparse.Namespace) -> ReadOnlyResearchBridge:
    project_root = DEFAULT_PROJECT_ROOT
    obsidian_root = DEFAULT_OBSIDIAN_ROOT
    manifest_path = project_root / DEFAULT_MANIFEST
    if (
        isinstance(args.max_line_bytes, bool)
        or not 1_024 <= args.max_line_bytes <= MAX_RPC_LINE_BYTES
    ):
        raise ResearchBridgeError("max_line_bytes_invalid")
    return ReadOnlyResearchBridge(
        manifest_path=manifest_path,
        roots={
            "git": project_root,
            "obsidian": obsidian_root,
            "notes": obsidian_root / "80-我的笔记",
        },
        expected_manifest_sha256=args.expected_manifest_sha256,
    )


def main() -> int:
    args = build_parser().parse_args()
    try:
        bridge = build_bridge(args)
    except (OSError, ResearchBridgeError):
        return 2
    serve_stdio(
        bridge,
        input_stream=sys.stdin.buffer,
        output_stream=sys.stdout.buffer,
        max_line_bytes=args.max_line_bytes,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
