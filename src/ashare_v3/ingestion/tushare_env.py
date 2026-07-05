"""Local Tushare token autoload helpers.

The helper intentionally exposes only presence and length metadata. It never
prints or returns a loggable structure containing the token value.
"""

from __future__ import annotations

from collections.abc import MutableMapping
import os
from pathlib import Path
import shlex


TOKEN_ENV_VAR = "TUSHARE_TOKEN"
SECRET_PATH_ENV_VAR = "ASHARE_V3_TUSHARE_ENV_PATH"
DEFAULT_TUSHARE_ENV_PATH = Path("/Users/chuanfuchen/.secrets/ashare_v3_tushare.env")


def load_tushare_token(
    *,
    token_env: str = TOKEN_ENV_VAR,
    secret_path: str | Path | None = None,
    set_env: bool = True,
    environ: MutableMapping[str, str] | None = None,
) -> str | None:
    """Return a Tushare token from env or the local secret file.

    Environment variables take precedence. If the token is loaded from the
    secret file, it is copied into ``environ`` by default so downstream code
    that still checks ``TUSHARE_TOKEN`` sees a consistent process environment.
    """

    env = environ if environ is not None else os.environ
    token = str(env.get(token_env) or "").strip()
    if token:
        return token

    resolved_path = _resolve_secret_path(env, secret_path)
    token = _read_token_from_secret_file(resolved_path, token_env=token_env)
    if token and set_env:
        env[token_env] = token
    return token


def tushare_token_status(
    *,
    token_env: str = TOKEN_ENV_VAR,
    secret_path: str | Path | None = None,
    environ: MutableMapping[str, str] | None = None,
) -> dict[str, int | bool]:
    """Return redacted token readiness metadata."""

    token = load_tushare_token(token_env=token_env, secret_path=secret_path, environ=environ)
    return {"token_present": bool(token), "token_length": len(token or "")}


def _resolve_secret_path(env: MutableMapping[str, str], secret_path: str | Path | None) -> Path:
    if secret_path is not None:
        return Path(secret_path).expanduser()
    configured = str(env.get(SECRET_PATH_ENV_VAR) or "").strip()
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_TUSHARE_ENV_PATH


def _read_token_from_secret_file(path: Path, *, token_env: str) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return None

    for raw_line in text.splitlines():
        parsed = _parse_env_assignment(raw_line)
        if not parsed:
            continue
        key, value = parsed
        if key == token_env and value:
            return value
    return None


def _parse_env_assignment(raw_line: str) -> tuple[str, str] | None:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[len("export ") :].strip()
    if "=" not in line:
        return None
    key, raw_value = line.split("=", 1)
    key = key.strip()
    if not key:
        return None
    try:
        parts = shlex.split(raw_value, comments=True, posix=True)
        value = parts[0] if parts else ""
    except ValueError:
        value = raw_value.strip().strip("'\"")
    return key, value.strip()
