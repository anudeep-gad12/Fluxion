"""Local model management service.

Scans for GGUF and MLX models on disk and manages llama-server / mlx_lm.server lifecycle.
"""

import asyncio
import os
import re
import signal
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import httpx

from orchestrator.logging_config import get_logger

logger = get_logger(__name__)

# Fluxion should prefer LM Studio-managed model folders only.
MODEL_DIRS = [
    Path.home() / ".lmstudio" / "models",
    Path.home() / ".cache" / "lm-studio" / "models",
]
EXCLUDED_MODEL_PATH_PARTS = {"ollama"}

LLAMA_PORT = 8080
LLAMA_HEALTH_URL = f"http://localhost:{LLAMA_PORT}/health"
MLX_MODELS_URL = f"http://localhost:{LLAMA_PORT}/v1/models"
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOCAL_MODEL_LOG_MAX_BYTES = 5 * 1024 * 1024
LOCAL_MODEL_LOG_SEGMENTS = 10


class ModelType(str, Enum):
    GGUF = "gguf"
    MLX = "mlx"


@dataclass
class LocalModel:
    """A local model found on disk (GGUF or MLX)."""

    path: str
    name: str
    size_bytes: int
    model_type: ModelType = ModelType.GGUF

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
    """Internal state for the managed server process."""

    process: Optional[subprocess.Popen] = None
    model_path: Optional[str] = None
    model_name: Optional[str] = None
    model_type: Optional[ModelType] = None
    ctx_size: int = 4096


# Module-level singleton
_state = _ServerState()


def _scan_gguf_models() -> list[LocalModel]:
    """Scan standard directories for GGUF files."""
    models: list[LocalModel] = []
    seen_paths: set[str] = set()

    for model_dir in MODEL_DIRS:
        if not model_dir.is_dir():
            continue
        for gguf_path in sorted(model_dir.rglob("*.gguf")):
            if not gguf_path.is_file():
                continue
            if any(part.lower() in EXCLUDED_MODEL_PATH_PARTS for part in gguf_path.parts):
                continue
            name = gguf_path.name
            if "mmproj" in name.lower():
                continue
            if re.search(r"-0000[2-9]-of-", name) or re.search(r"-000[1-9]\d-of-", name):
                continue

            path_str = str(gguf_path)
            if path_str in seen_paths:
                continue
            seen_paths.add(path_str)

            display_name = f"{gguf_path.parent.name}/{gguf_path.name}"
            models.append(
                LocalModel(
                    path=path_str,
                    name=display_name,
                    size_bytes=gguf_path.stat().st_size,
                    model_type=ModelType.GGUF,
                )
            )

    return models


def _scan_mlx_models() -> list[LocalModel]:
    """Scan standard directories for MLX models (dirs with config.json + safetensors)."""
    models: list[LocalModel] = []
    seen_paths: set[str] = set()

    for model_dir in MODEL_DIRS:
        if not model_dir.is_dir():
            continue
        for config_path in model_dir.rglob("config.json"):
            parent = config_path.parent
            parent_str = str(parent)
            if any(part.lower() in EXCLUDED_MODEL_PATH_PARTS for part in parent.parts):
                continue

            # Skip HF cache directories
            if "snapshots" in parent_str or "models--" in parent_str:
                continue
            if parent_str in seen_paths:
                continue

            # Must have safetensors files
            safetensors = list(parent.glob("*.safetensors"))
            if not safetensors:
                continue

            seen_paths.add(parent_str)
            size = sum(f.stat().st_size for f in safetensors)
            display_name = f"{parent.parent.name}/{parent.name}"

            models.append(
                LocalModel(
                    path=parent_str,
                    name=display_name,
                    size_bytes=size,
                    model_type=ModelType.MLX,
                )
            )

    return models


def scan_models() -> list[LocalModel]:
    """Scan standard directories for all local models (GGUF + MLX)."""
    return _scan_gguf_models() + _scan_mlx_models()


def _detect_model_type(path: str) -> ModelType:
    """Detect model type from path."""
    p = Path(path)
    if p.is_file() and p.suffix == ".gguf":
        return ModelType.GGUF
    if p.is_dir() and (p / "config.json").exists():
        return ModelType.MLX
    raise ValueError(f"Cannot detect model type for: {path}")


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


def _log_file_path(model_type: ModelType) -> Path:
    """Return the active log file path for the given local model server type."""
    return LOG_DIR / ("mlx.log" if model_type == ModelType.MLX else "llama.log")


def _wal_segment_path(log_file: Path, timestamp: str, suffix: int) -> Path:
    """Build a rotated append-only WAL segment path for a local model log file."""
    candidate = log_file.with_name(f"{log_file.name}.wal.{timestamp}")
    if suffix == 0:
        return candidate
    return log_file.with_name(f"{log_file.name}.wal.{timestamp}.{suffix}")


def _rotate_log_if_needed(log_file: Path) -> Optional[Path]:
    """Rotate the active log into an append-only WAL segment when it grows too large."""
    if not log_file.exists() or log_file.stat().st_size < LOCAL_MODEL_LOG_MAX_BYTES:
        return None

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = 0
    archive = _wal_segment_path(log_file, timestamp, suffix)
    while archive.exists():
        suffix += 1
        archive = _wal_segment_path(log_file, timestamp, suffix)

    log_file.rename(archive)

    segments = sorted(
        log_file.parent.glob(f"{log_file.name}.wal.*"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for stale in segments[LOCAL_MODEL_LOG_SEGMENTS:]:
        try:
            stale.unlink()
        except OSError:
            logger.warning("Failed to prune local model log segment", extra={"path": str(stale)})

    return archive


def _open_log_file(
    model_type: ModelType,
    *,
    model_name: str,
    model_path: str,
    ctx_size: int,
    command: list[str],
):
    """Open the active local-model log file in append mode with WAL-style rotation."""
    LOG_DIR.mkdir(exist_ok=True)
    log_file = _log_file_path(model_type)
    rotated = _rotate_log_if_needed(log_file)

    if rotated:
        logger.info(
            "Rotated local model log file",
            extra={"active_log": str(log_file), "archive_log": str(rotated)},
        )

    handle = open(log_file, "a", encoding="utf-8")
    started_at = datetime.now(timezone.utc).isoformat()
    header = (
        "\n"
        "============================================================\n"
        f"START {started_at}\n"
        f"MODEL_TYPE: {model_type.value}\n"
        f"MODEL_NAME: {model_name}\n"
        f"MODEL_PATH: {model_path}\n"
        f"CTX_SIZE: {ctx_size}\n"
        f"COMMAND: {' '.join(command)}\n"
        "============================================================\n"
    )
    handle.write(header)
    handle.flush()
    return handle, log_file


async def _wait_for_health(model_type: ModelType, timeout: float = 60.0) -> bool:
    """Poll server health endpoint until ready."""
    interval = 0.5
    elapsed = 0.0

    if model_type == ModelType.MLX:
        health_url = MLX_MODELS_URL
    else:
        health_url = LLAMA_HEALTH_URL

    async with httpx.AsyncClient() as client:
        while elapsed < timeout:
            try:
                resp = await client.get(health_url, timeout=2.0)
                if resp.status_code == 200:
                    if model_type == ModelType.MLX:
                        return True
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
    """Start a local model server.

    Detects model type (GGUF or MLX) and launches the appropriate server.

    Args:
        model_path: Path to GGUF file or MLX model directory.
        ctx_size: Context window size (used for GGUF/llama-server only).

    Returns:
        True if server started and is healthy.
    """
    resolved = os.path.expanduser(model_path)
    model_type = _detect_model_type(resolved)

    if model_type == ModelType.GGUF and not os.path.isfile(resolved):
        raise FileNotFoundError(f"Model file not found: {resolved}")
    if model_type == ModelType.MLX and not os.path.isdir(resolved):
        raise FileNotFoundError(f"Model directory not found: {resolved}")

    # Stop any existing server
    await stop()

    # Kill anything on the port
    _kill_port(LLAMA_PORT)
    await asyncio.sleep(0.5)

    model_name = Path(resolved).stem if model_type == ModelType.GGUF else Path(resolved).name

    logger.info(
        f"Starting {'mlx_lm.server' if model_type == ModelType.MLX else 'llama-server'} with {model_name}",
        extra={"model_path": resolved, "model_type": model_type.value, "ctx_size": ctx_size},
    )

    if model_type == ModelType.MLX:
        cmd = [
            "mlx_lm.server",
            "--model", resolved,
            "--port", str(LLAMA_PORT),
        ]
    else:
        cmd = [
            "llama-server",
            "-m", resolved,
            "--port", str(LLAMA_PORT),
            "--jinja",
            "--ctx-size", str(ctx_size),
            "-ub", "512",
            "-b", "512",
        ]

    lf, log_file = _open_log_file(
        model_type,
        model_name=model_name,
        model_path=resolved,
        ctx_size=ctx_size,
        command=cmd,
    )
    with lf:
        proc = subprocess.Popen(
            cmd,
            stdout=lf,
            stderr=subprocess.STDOUT,
        )

    _state.process = proc
    _state.model_path = resolved
    _state.model_name = model_name
    _state.model_type = model_type
    _state.ctx_size = ctx_size

    # Wait for health
    healthy = await _wait_for_health(model_type, timeout=60.0)
    if not healthy:
        logger.error(f"{'mlx_lm.server' if model_type == ModelType.MLX else 'llama-server'} failed to become healthy")
        await stop()
        return False

    logger.info(f"Server ready: {model_name} ({model_type.value})")
    return True


async def stop() -> None:
    """Stop the managed server process."""
    if _state.process is not None:
        logger.info("Stopping local model server")
        try:
            _state.process.terminate()
            try:
                _state.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _state.process.kill()
                _state.process.wait(timeout=3)
        except Exception as e:
            logger.warning(f"Error stopping server: {e}")
        _state.process = None
        _state.model_path = None
        _state.model_name = None
        _state.model_type = None


async def is_running() -> bool:
    """Check if the local model server is healthy."""
    model_type = _state.model_type or ModelType.GGUF
    try:
        async with httpx.AsyncClient() as client:
            if model_type == ModelType.MLX:
                resp = await client.get(MLX_MODELS_URL, timeout=2.0)
                return resp.status_code == 200
            else:
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
        "model_type": _state.model_type.value if _state.model_type else None,
        "ctx_size": _state.ctx_size if managed else None,
        "port": LLAMA_PORT,
    }
