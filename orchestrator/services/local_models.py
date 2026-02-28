"""Local model management service.

Scans for GGUF models on disk and manages llama-server lifecycle.
Ports the CLI logic from scripts/install-cli.sh lines 62-169.
"""

import asyncio
import os
import re
import signal
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

from orchestrator.logging_config import get_logger

logger = get_logger(__name__)

# Same directories the CLI scans
MODEL_DIRS = [
    Path.home() / ".lmstudio" / "models",
    Path.home() / "models",
    Path.home() / ".cache" / "huggingface",
    Path.home() / ".cache" / "lm-studio" / "models",
]

LLAMA_PORT = 8080
LLAMA_HEALTH_URL = f"http://localhost:{LLAMA_PORT}/health"


@dataclass
class LocalModel:
    """A GGUF model found on disk."""

    path: str
    name: str
    size_bytes: int

    @property
    def size_display(self) -> str:
        """Human-readable file size."""
        gb = self.size_bytes / (1024**3)
        if gb >= 1:
            return f"{gb:.1f} GB"
        mb = self.size_bytes / (1024**2)
        return f"{mb:.0f} MB"


@dataclass
class _ServerState:
    """Internal state for the managed llama-server process."""

    process: Optional[subprocess.Popen] = None
    model_path: Optional[str] = None
    model_name: Optional[str] = None
    ctx_size: int = 4096


# Module-level singleton
_state = _ServerState()


def scan_models() -> list[LocalModel]:
    """Scan standard directories for GGUF files.

    Same filters as the CLI: exclude mmproj vision files and split shards
    (keep only the first shard -00001-of-).
    """
    models: list[LocalModel] = []
    seen_paths: set[str] = set()

    for model_dir in MODEL_DIRS:
        if not model_dir.is_dir():
            continue
        for gguf_path in sorted(model_dir.rglob("*.gguf")):
            if not gguf_path.is_file():
                continue
            name = gguf_path.name
            # Exclude mmproj vision adapter files
            if "mmproj" in name.lower():
                continue
            # Exclude split shards except the first one
            if re.search(r"-0000[2-9]-of-", name) or re.search(r"-000[1-9]\d-of-", name):
                continue

            path_str = str(gguf_path)
            if path_str in seen_paths:
                continue
            seen_paths.add(path_str)

            # Friendly display name: parent_dir/filename
            display_name = f"{gguf_path.parent.name}/{gguf_path.name}"

            models.append(
                LocalModel(
                    path=path_str,
                    name=display_name,
                    size_bytes=gguf_path.stat().st_size,
                )
            )

    return models


def _kill_port(port: int) -> None:
    """Kill any process listening on the given port."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pids = result.stdout.strip()
        if pids:
            for pid in pids.split("\n"):
                pid = pid.strip()
                if pid:
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                    except (ProcessLookupError, ValueError):
                        pass
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


async def _wait_for_health(timeout: float = 60.0) -> bool:
    """Poll llama-server health endpoint until ready."""
    interval = 0.5
    elapsed = 0.0
    async with httpx.AsyncClient() as client:
        while elapsed < timeout:
            try:
                resp = await client.get(LLAMA_HEALTH_URL, timeout=2.0)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "ok":
                        return True
            except (httpx.HTTPError, Exception):
                pass

            # Check if process died
            if _state.process and _state.process.poll() is not None:
                return False

            await asyncio.sleep(interval)
            elapsed += interval

    return False


async def start(model_path: str, ctx_size: int = 100000) -> bool:
    """Start llama-server with the given model.

    Kills any existing process on the llama port first.

    Args:
        model_path: Absolute path to the GGUF file.
        ctx_size: Context window size (default matches config context.max_tokens).

    Returns:
        True if server started and is healthy.
    """
    # Resolve ~ in path
    resolved = os.path.expanduser(model_path)
    if not os.path.isfile(resolved):
        raise FileNotFoundError(f"Model file not found: {resolved}")

    # Stop any existing server
    await stop()

    # Kill anything on the port
    _kill_port(LLAMA_PORT)
    await asyncio.sleep(0.5)

    # Ensure logs directory exists
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "llama.log"

    model_name = Path(resolved).stem

    logger.info(
        f"Starting llama-server with {model_name}",
        extra={"model_path": resolved, "ctx_size": ctx_size},
    )

    with open(log_file, "w") as lf:
        proc = subprocess.Popen(
            [
                "llama-server",
                "-m", resolved,
                "--port", str(LLAMA_PORT),
                "--jinja",
                "--ctx-size", str(ctx_size),
                "-ub", "512",
                "-b", "512",
            ],
            stdout=lf,
            stderr=subprocess.STDOUT,
        )

    _state.process = proc
    _state.model_path = resolved
    _state.model_name = model_name
    _state.ctx_size = ctx_size

    # Wait for health
    healthy = await _wait_for_health(timeout=60.0)
    if not healthy:
        logger.error("llama-server failed to become healthy")
        await stop()
        return False

    logger.info(f"llama-server ready: {model_name}")
    return True


async def stop() -> None:
    """Stop the managed llama-server process."""
    if _state.process is not None:
        logger.info("Stopping llama-server")
        try:
            _state.process.terminate()
            try:
                _state.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _state.process.kill()
                _state.process.wait(timeout=3)
        except Exception as e:
            logger.warning(f"Error stopping llama-server: {e}")
        _state.process = None
        _state.model_path = None
        _state.model_name = None


async def is_running() -> bool:
    """Check if llama-server is healthy."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(LLAMA_HEALTH_URL, timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("status") == "ok"
    except (httpx.HTTPError, Exception):
        pass
    return False


def status() -> dict:
    """Get current local model status."""
    managed = _state.process is not None and _state.process.poll() is None
    return {
        "managed_process": managed,
        "model_path": _state.model_path,
        "model_name": _state.model_name,
        "ctx_size": _state.ctx_size if managed else None,
        "port": LLAMA_PORT,
    }
