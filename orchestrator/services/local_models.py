"""Local model management service.

Scans for GGUF and MLX models on disk and manages llama-server / mlx_lm.server lifecycle.
"""

import asyncio
import json
import os
import re
import signal
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from importlib.metadata import PackageNotFoundError, version
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
MLX_MODEL_TYPE_REMAPPING = {
    "mistral": "llama",
    "llava": "mistral3",
    "phi-msft": "phixtral",
    "falcon_mamba": "mamba",
    "joyai_llm_flash": "deepseek_v3",
    "kimi_k2": "deepseek_v3",
    "qwen2_5_vl": "qwen2_vl",
    "minimax_m2": "minimax",
    "iquestcoder": "llama",
}

LLAMA_PORT = 8080
LLAMA_HEALTH_URL = f"http://localhost:{LLAMA_PORT}/health"
MLX_MODELS_URL = f"http://localhost:{LLAMA_PORT}/v1/models"
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOCAL_MODEL_LOG_MAX_BYTES = 5 * 1024 * 1024
LOCAL_MODEL_LOG_SEGMENTS = 10
DEFAULT_LOCAL_CONTEXT_TOKENS = int(os.getenv("FLUXION_LOCAL_CONTEXT_TOKENS", "131072"))
DEFAULT_LLAMA_BATCH_SIZE = int(os.getenv("FLUXION_LLAMA_BATCH_SIZE", "2048"))
DEFAULT_LLAMA_UBATCH_SIZE = int(os.getenv("FLUXION_LLAMA_UBATCH_SIZE", "512"))
DEFAULT_MLX_PREFILL_STEP_SIZE = int(os.getenv("FLUXION_MLX_PREFILL_STEP_SIZE", "4096"))
DEFAULT_MLX_PROMPT_CACHE_SIZE = int(os.getenv("FLUXION_MLX_PROMPT_CACHE_SIZE", "16"))


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
    model_type_id: Optional[str] = None
    supported: bool = True
    status_message: Optional[str] = None

    @property
    def size_display(self) -> str:
        """Human-readable file size."""
        gb = self.size_bytes / (1024**3)
        if gb >= 1:
            return f"{gb:.1f} GB"
        mb = self.size_bytes / (1024**2)
        return f"{mb:.0f} MB"


@dataclass
class LocalServerStartResult:
    """Metadata for a successfully started local model server."""

    model_name: str
    model_type: ModelType
    served_model_id: str
    base_url: str
    ctx_size: int
    log_file: str
    diagnostics: dict[str, Optional[str]] = field(default_factory=dict)


class LocalModelStartError(RuntimeError):
    """Raised when a local model server cannot be started."""

    def __init__(
        self,
        message: str,
        *,
        model_type: Optional[ModelType] = None,
        log_file: Optional[str] = None,
        diagnostics: Optional[dict[str, Optional[str]]] = None,
    ) -> None:
        super().__init__(message)
        self.model_type = model_type
        self.log_file = log_file
        self.diagnostics = diagnostics or {}


@dataclass
class _ServerState:
    """Internal state for the managed server process."""

    process: Optional[subprocess.Popen] = None
    model_path: Optional[str] = None
    model_name: Optional[str] = None
    model_type: Optional[ModelType] = None
    served_model_id: Optional[str] = None
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


def _package_path_in_python(python_path: str, package_name: str) -> Optional[str]:
    """Find a package directory in another Python env without importing the package."""
    try:
        result = subprocess.run(
            [
                python_path,
                "-c",
                (
                    "import importlib.util\n"
                    f"spec=importlib.util.find_spec({package_name!r})\n"
                    "locs=getattr(spec, 'submodule_search_locations', None) if spec else None\n"
                    "print(next(iter(locs), '') if locs else '')\n"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _supported_mlx_model_types(executable: Optional[str]) -> Optional[set[str]]:
    """Return model_type ids supported by the installed mlx-lm package.

    This is a filesystem check, not an MLX import, so it is safe in desktop and
    headless test contexts where importing MLX may initialize Metal.
    """
    python_path = _python_from_script_shebang(executable) if executable else None
    package_path = _package_path_in_python(python_path, "mlx_lm") if python_path else None
    if not package_path:
        return None

    models_dir = Path(package_path) / "models"
    if not models_dir.is_dir():
        return None

    supported = {
        path.stem
        for path in models_dir.iterdir()
        if path.name != "__init__.py"
        and not path.name.startswith("__")
        and (path.suffix == ".py" or (path.is_dir() and (path / "__init__.py").exists()))
    }
    supported.update(MLX_MODEL_TYPE_REMAPPING.keys())
    return supported


def _read_mlx_model_type(model_dir: Path) -> Optional[str]:
    """Read the Hugging Face config model_type for an MLX model directory."""
    try:
        config = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    model_type = config.get("model_type")
    return str(model_type) if model_type else None


def _mlx_support_status(
    *,
    model_dir: Path,
    supported_types: Optional[set[str]],
    mlx_lm_version: Optional[str],
) -> tuple[bool, Optional[str], Optional[str]]:
    """Return (supported, model_type_id, status_message) for an MLX model."""
    model_type = _read_mlx_model_type(model_dir)
    if not model_type or supported_types is None:
        return True, model_type, None

    resolved_type = MLX_MODEL_TYPE_REMAPPING.get(model_type, model_type)
    if resolved_type in supported_types:
        return True, model_type, None

    version_text = f" {mlx_lm_version}" if mlx_lm_version else ""
    return (
        False,
        model_type,
        (
            f"MLX model type '{model_type}' is not supported by installed mlx-lm{version_text}. "
            "Update mlx-lm or use a supported MLX/GGUF model."
        ),
    )


def _scan_mlx_models() -> list[LocalModel]:
    """Scan standard directories for MLX models (dirs with config.json + safetensors)."""
    models: list[LocalModel] = []
    seen_paths: set[str] = set()
    executable: Optional[str] = None
    diagnostics: dict[str, Optional[str]] = {}
    supported_types: Optional[set[str]] = None
    try:
        executable = _resolve_server_executable(ModelType.MLX)
        diagnostics = _local_server_diagnostics(ModelType.MLX, executable)
        supported_types = _supported_mlx_model_types(executable)
    except LocalModelStartError:
        supported_types = None

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
            supported, model_type_id, status_message = _mlx_support_status(
                model_dir=parent,
                supported_types=supported_types,
                mlx_lm_version=diagnostics.get("mlx_lm_version"),
            )

            models.append(
                LocalModel(
                    path=parent_str,
                    name=display_name,
                    size_bytes=size,
                    model_type=ModelType.MLX,
                    model_type_id=model_type_id,
                    supported=supported,
                    status_message=status_message,
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


def _server_binary_name(model_type: ModelType) -> str:
    """Return the executable name for the local server type."""
    return "mlx_lm.server" if model_type == ModelType.MLX else "llama-server"


def _candidate_executable_paths(binary_name: str) -> list[Path]:
    """Return desktop-safe executable candidates, including user tool dirs."""
    candidates: list[Path] = []
    found = shutil.which(binary_name)
    if found:
        candidates.append(Path(found))

    candidates.extend(
        [
            Path.home() / ".local" / "bin" / binary_name,
            Path("/opt/homebrew/bin") / binary_name,
            Path("/usr/local/bin") / binary_name,
            Path("/usr/bin") / binary_name,
        ]
    )

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            deduped.append(candidate)
            seen.add(key)
    return deduped


def _resolve_server_executable(model_type: ModelType) -> str:
    """Resolve the server executable without relying only on packaged-app PATH."""
    binary_name = _server_binary_name(model_type)
    for candidate in _candidate_executable_paths(binary_name):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    install_hint = (
        "Install or update with: uv tool install -U mlx-lm"
        if model_type == ModelType.MLX
        else "Install llama.cpp so llama-server is on PATH."
    )
    raise LocalModelStartError(
        f"{binary_name} was not found. {install_hint}",
        model_type=model_type,
        log_file=str(_log_file_path(model_type)),
    )


def _python_from_script_shebang(executable: str) -> Optional[str]:
    """Read a console script shebang without importing the tool package."""
    try:
        first_line = Path(executable).read_text(encoding="utf-8", errors="ignore").splitlines()[0]
    except (OSError, IndexError):
        return None
    if not first_line.startswith("#!"):
        return None
    python_path = first_line[2:].strip().split(" ", 1)[0]
    return python_path if python_path else None


def _package_version_in_python(python_path: str, package_name: str) -> Optional[str]:
    """Read package metadata in another Python env without importing MLX/Metal."""
    try:
        result = subprocess.run(
            [
                python_path,
                "-c",
                (
                    "from importlib.metadata import version, PackageNotFoundError\n"
                    f"pkg={package_name!r}\n"
                    "try:\n"
                    " print(version(pkg))\n"
                    "except PackageNotFoundError:\n"
                    " print('')\n"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _current_env_package_version(package_name: str) -> Optional[str]:
    """Read package metadata from Fluxion's own Python env."""
    try:
        return version(package_name)
    except PackageNotFoundError:
        return None


def _local_server_diagnostics(
    model_type: ModelType,
    executable: Optional[str],
) -> dict[str, Optional[str]]:
    """Return non-invasive diagnostics for local server startup."""
    diagnostics: dict[str, Optional[str]] = {
        "executable": executable,
    }
    if model_type != ModelType.MLX:
        return diagnostics

    python_path = _python_from_script_shebang(executable) if executable else None
    diagnostics["python"] = python_path
    diagnostics["mlx_lm_version"] = (
        _package_version_in_python(python_path, "mlx-lm")
        if python_path
        else _current_env_package_version("mlx-lm")
    )
    diagnostics["mlx_version"] = (
        _package_version_in_python(python_path, "mlx")
        if python_path
        else _current_env_package_version("mlx")
    )
    return diagnostics


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


def _served_model_id(model_type: ModelType, resolved_model_path: str, model_name: str) -> str:
    """Return the model id Fluxion should send to the local OpenAI-compatible API."""
    if model_type == ModelType.MLX:
        return str(Path(resolved_model_path).resolve())
    return model_name


def _tail_log_file(model_type: ModelType, max_chars: int = 1600) -> str:
    """Return a short log tail for startup errors."""
    log_file = _log_file_path(model_type)
    try:
        content = log_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return content[-max_chars:].strip()


async def start(
    model_path: str,
    ctx_size: Optional[int] = None,
) -> LocalServerStartResult:
    """Start a local model server.

    Detects model type (GGUF or MLX) and launches the appropriate server.

    Args:
        model_path: Path to GGUF file or MLX model directory.
        ctx_size: Context window size. If omitted, uses the local-only
            high-context workstation default.

    Returns:
        Metadata for the healthy server.
    """
    resolved = os.path.expanduser(model_path)
    model_type = _detect_model_type(resolved)
    if ctx_size is None:
        ctx_size = DEFAULT_LOCAL_CONTEXT_TOKENS

    if model_type == ModelType.GGUF and not os.path.isfile(resolved):
        raise FileNotFoundError(f"Model file not found: {resolved}")
    if model_type == ModelType.MLX and not os.path.isdir(resolved):
        raise FileNotFoundError(f"Model directory not found: {resolved}")

    executable = _resolve_server_executable(model_type)
    diagnostics = _local_server_diagnostics(model_type, executable)
    if model_type == ModelType.MLX:
        supported_types = _supported_mlx_model_types(executable)
        supported, model_type_id, status_message = _mlx_support_status(
            model_dir=Path(resolved),
            supported_types=supported_types,
            mlx_lm_version=diagnostics.get("mlx_lm_version"),
        )
        diagnostics["model_type_id"] = model_type_id
        if not supported:
            raise LocalModelStartError(
                status_message or "Selected MLX model is not supported by installed mlx-lm.",
                model_type=model_type,
                log_file=str(_log_file_path(model_type)),
                diagnostics=diagnostics,
            )

    # Stop any existing server
    await stop()

    # Kill anything on the port
    _kill_port(LLAMA_PORT)
    await asyncio.sleep(0.5)

    model_name = Path(resolved).stem if model_type == ModelType.GGUF else Path(resolved).name
    served_model_id = _served_model_id(model_type, resolved, model_name)

    server_name = _server_binary_name(model_type)
    logger.info(
        f"Starting {server_name} with {model_name}",
        extra={
            "model_path": resolved,
            "model_type": model_type.value,
            "ctx_size": ctx_size,
            "executable": executable,
            "served_model_id": served_model_id,
            "mlx_lm_version": diagnostics.get("mlx_lm_version"),
            "mlx_version": diagnostics.get("mlx_version"),
        },
    )

    if model_type == ModelType.MLX:
        cmd = [
            executable,
            "--model", resolved,
            "--host", "127.0.0.1",
            "--port", str(LLAMA_PORT),
            "--prefill-step-size", str(DEFAULT_MLX_PREFILL_STEP_SIZE),
            "--prompt-cache-size", str(DEFAULT_MLX_PROMPT_CACHE_SIZE),
        ]
    else:
        cmd = [
            executable,
            "-m", resolved,
            "--port", str(LLAMA_PORT),
            "--jinja",
            "--ctx-size", str(ctx_size),
            "-ngl", "all",
            "-fa", "auto",
            "--cache-type-k", "f16",
            "--cache-type-v", "f16",
            "--mlock",
            "-b", str(DEFAULT_LLAMA_BATCH_SIZE),
            "-ub", str(DEFAULT_LLAMA_UBATCH_SIZE),
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
    _state.served_model_id = served_model_id
    _state.ctx_size = ctx_size

    # Wait for health
    healthy = await _wait_for_health(model_type, timeout=60.0)
    if not healthy:
        logger.error(f"{server_name} failed to become healthy")
        log_tail = _tail_log_file(model_type)
        await stop()
        message = f"{server_name} failed to become healthy. Check {log_file}."
        if log_tail:
            message = f"{message}\n\nRecent log:\n{log_tail}"
        raise LocalModelStartError(
            message,
            model_type=model_type,
            log_file=str(log_file),
            diagnostics=diagnostics,
        )

    logger.info(f"Server ready: {model_name} ({model_type.value})")
    return LocalServerStartResult(
        model_name=model_name,
        model_type=model_type,
        served_model_id=served_model_id,
        base_url=f"http://localhost:{LLAMA_PORT}/v1",
        ctx_size=ctx_size,
        log_file=str(log_file),
        diagnostics=diagnostics,
    )


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
        _state.served_model_id = None


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
        "served_model_id": _state.served_model_id,
        "ctx_size": _state.ctx_size if managed else None,
        "port": LLAMA_PORT,
    }
