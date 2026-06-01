"""Grok CLI OAuth credential helpers.

Fluxion treats Grok OAuth as a separate provider from xAI API keys.  The
official Grok CLI owns the browser/OIDC flow and stores short-lived session
credentials in ``~/.grok/auth.json``; this module only detects and uses those
local credentials.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from orchestrator.logging_config import get_logger

logger = get_logger(__name__)

_login_process: Optional[asyncio.subprocess.Process] = None
_last_login_error: Optional[str] = None
_last_login_message: Optional[str] = None
_cli_version_cache: Optional[str] = None


def _auth_file_path() -> Path:
    """Return the Grok auth file path, allowing tests to override it."""
    override = os.environ.get("GROK_AUTH_FILE")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".grok" / "auth.json"


def _parse_expires_at(raw: Any) -> Optional[int]:
    """Parse Grok auth.json expiry values into a Unix timestamp."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    try:
        if value.endswith("Z"):
            value = f"{value[:-1]}+00:00"
        return int(datetime.fromisoformat(value).timestamp())
    except ValueError:
        return None


def _load_auth_entries() -> list[dict[str, Any]]:
    """Load candidate Grok OAuth entries without exposing secrets."""
    path = _auth_file_path()
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        return []
    except Exception as exc:
        logger.warning("Failed to read Grok auth file", extra={"error": str(exc)})
        return []

    if not isinstance(raw, dict):
        return []

    entries: list[dict[str, Any]] = []
    for storage_key, value in raw.items():
        if not isinstance(value, dict):
            continue
        token = value.get("key") or value.get("access_token")
        if not isinstance(token, str) or not token.strip():
            continue
        issuer = str(value.get("oidc_issuer") or storage_key or "")
        if "x.ai" not in issuer and "grok" not in issuer:
            continue
        expires_at = _parse_expires_at(value.get("expires_at"))
        entries.append(
            {
                "storage_key": str(storage_key),
                "access_token": token.strip(),
                "expires_at": expires_at,
                "email": value.get("email"),
                "user_id": value.get("user_id"),
                "auth_mode": value.get("auth_mode"),
                "issuer": issuer,
            }
        )
    entries.sort(key=lambda item: item.get("expires_at") or 0, reverse=True)
    return entries


def get_grok_access_token_sync() -> Optional[str]:
    """Return a valid Grok CLI OAuth access token, if available."""
    now = int(time.time())
    for entry in _load_auth_entries():
        expires_at = entry.get("expires_at")
        if expires_at is not None and expires_at <= now + 60:
            continue
        return entry["access_token"]
    return None


def get_grok_cli_version_sync() -> str:
    """Return installed Grok CLI version for proxy compatibility headers."""
    global _cli_version_cache
    if _cli_version_cache:
        return _cli_version_cache

    grok_bin = shutil.which("grok")
    if not grok_bin:
        return "0.2.11"

    try:
        result = subprocess.run(
            [grok_bin, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        output = (result.stdout or result.stderr or "").strip()
        parts = output.split()
        if len(parts) >= 2 and parts[0].lower() == "grok":
            _cli_version_cache = parts[1]
            return _cli_version_cache
    except Exception as exc:
        logger.warning("Failed to read Grok CLI version", extra={"error": str(exc)})

    return "0.2.11"


async def get_grok_auth_status() -> dict[str, Any]:
    """Return Grok OAuth status without exposing token values."""
    global _login_process, _last_login_error

    login_running = False
    if _login_process is not None:
        if _login_process.returncode is None:
            login_running = True
        else:
            if _login_process.returncode != 0:
                stderr = await _login_process.stderr.read() if _login_process.stderr else b""
                _last_login_error = (
                    stderr.decode("utf-8", errors="replace")[-500:].strip()
                    or "Grok login failed"
                )
            _login_process = None

    entries = _load_auth_entries()
    now = int(time.time())
    valid_entry = next(
        (
            entry
            for entry in entries
            if entry.get("expires_at") is None or int(entry["expires_at"]) > now + 60
        ),
        None,
    )
    return {
        "enabled": shutil.which("grok") is not None,
        "authenticated": valid_entry is not None,
        "account_id": (
            valid_entry.get("email")
            or (
                str(valid_entry.get("user_id"))[:8] + "..."
                if valid_entry and valid_entry.get("user_id")
                else None
            )
        )
        if valid_entry
        else None,
        "expires_at": valid_entry.get("expires_at") if valid_entry else None,
        "auth_file": str(_auth_file_path()),
        "login_running": login_running,
        "last_error": _last_login_error,
        "last_message": _last_login_message,
    }


async def start_grok_login() -> dict[str, Any]:
    """Start ``grok login --oauth`` if it is not already running."""
    global _login_process, _last_login_error, _last_login_message

    grok_bin = shutil.which("grok")
    if not grok_bin:
        return {
            "status": "missing_cli",
            "message": "Grok CLI is not installed or not on PATH.",
        }

    if _login_process is not None and _login_process.returncode is None:
        return {"status": "already_running"}

    _last_login_error = None
    _last_login_message = None
    _login_process = await asyncio.create_subprocess_exec(
        grok_bin,
        "login",
        "--oauth",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    logger.info("Grok OAuth login started")
    return {"status": "started"}


async def submit_grok_login_code(code: str) -> dict[str, Any]:
    """Submit the browser fallback code to the running Grok CLI login."""
    global _last_login_message

    trimmed = code.strip()
    if not trimmed:
        return {"status": "error", "message": "Code cannot be empty"}

    if get_grok_access_token_sync():
        return {"status": "authenticated"}

    if _login_process is None or _login_process.returncode is not None:
        return {"status": "no_login", "message": "No active Grok login is waiting for a code."}

    if _login_process.stdin is None:
        return {"status": "error", "message": "Active Grok login cannot accept manual code input."}

    _login_process.stdin.write(f"{trimmed}\n".encode("utf-8"))
    await _login_process.stdin.drain()
    _last_login_message = "Manual fallback code submitted."
    logger.info("Grok OAuth fallback code submitted")

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if get_grok_access_token_sync():
            _last_login_message = "Grok OAuth connected."
            return {"status": "authenticated"}
        if _login_process.returncode is not None:
            break
        try:
            await asyncio.wait_for(_login_process.wait(), timeout=0.5)
        except asyncio.TimeoutError:
            continue

    if get_grok_access_token_sync():
        _last_login_message = "Grok OAuth connected."
        return {"status": "authenticated"}

    return {
        "status": "submitted",
        "message": "Code submitted. Waiting for Grok CLI to finish login.",
    }


async def cancel_grok_login() -> dict[str, Any]:
    """Cancel an in-flight Grok OAuth login process."""
    global _login_process
    cancelled = False
    if _login_process is not None and _login_process.returncode is None:
        _login_process.terminate()
        try:
            await asyncio.wait_for(_login_process.wait(), timeout=3)
        except asyncio.TimeoutError:
            _login_process.kill()
            await _login_process.wait()
        cancelled = True
    _login_process = None
    return {"status": "cancelled", "cancelled": int(cancelled)}


async def logout_grok() -> dict[str, Any]:
    """Run official Grok logout when available, clearing cached credentials."""
    await cancel_grok_login()
    grok_bin = shutil.which("grok")
    if not grok_bin:
        return {"status": "logged_out", "method": "missing_cli"}

    proc = await asyncio.create_subprocess_exec(
        grok_bin,
        "logout",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"status": "error", "message": "Grok logout timed out"}
    if proc.returncode != 0:
        message = (
            stderr.decode("utf-8", errors="replace")[-500:].strip()
            or "Grok logout failed"
        )
        logger.warning("Grok logout failed", extra={"error": message})
        return {"status": "error", "message": message}
    logger.info("Grok OAuth logout completed")
    return {"status": "logged_out", "method": "grok logout"}
