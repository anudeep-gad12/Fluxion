"""macOS app launcher and service manager for packaged Fluxion builds."""

from __future__ import annotations

import json
import os
import platform
import plistlib
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "Fluxion"
APP_LABEL = "io.fluxion.local"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = "9000"
DEFAULT_VERSION = "0.1.1"
DEFAULT_BUILD_ID = "source"


@dataclass(frozen=True)
class ServicePaths:
    """Resolved paths used by the packaged app service."""

    app_bundle: Path | None
    launcher: Path
    data_dir: Path
    var_dir: Path
    log_dir: Path
    db_path: Path
    launch_agent_dir: Path
    launch_agent: Path
    static_dir: Path | None


def _log(message: str) -> None:
    print(f"[fluxion] {message}")


def _host() -> str:
    return os.environ.get("FLUXION_HOST", DEFAULT_HOST)


def _port() -> str:
    return os.environ.get("FLUXION_PORT", DEFAULT_PORT)


def _url() -> str:
    return f"http://{_host()}:{_port()}"


def _app_version() -> str:
    return os.environ.get("FLUXION_APP_VERSION", DEFAULT_VERSION)


def _build_id() -> str:
    return os.environ.get("FLUXION_BUILD_ID", DEFAULT_BUILD_ID)


def _is_macos() -> bool:
    return platform.system() == "Darwin"


def _use_launch_agent() -> bool:
    """Return True when the legacy KeepAlive LaunchAgent install path is enabled."""
    return os.environ.get("FLUXION_USE_LAUNCH_AGENT", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _detect_app_bundle() -> Path | None:
    override = os.environ.get("FLUXION_APP_BUNDLE")
    if override:
        return Path(override).expanduser().resolve()

    current = Path(sys.argv[0]).expanduser().resolve()
    for parent in [current, *current.parents]:
        if parent.name.endswith(".app"):
            return parent
    return None


def _launcher_path(app_bundle: Path | None) -> Path:
    override = os.environ.get("FLUXION_LAUNCHER_PATH")
    if override:
        return Path(override).expanduser().resolve()
    if app_bundle:
        return app_bundle / "Contents" / "MacOS" / APP_NAME
    return Path(sys.argv[0]).expanduser().resolve()


def _default_data_dir() -> Path:
    override = os.environ.get("FLUXION_DATA_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / APP_NAME / "data"


def _static_dir(app_bundle: Path | None) -> Path | None:
    override = os.environ.get("FLUXION_STATIC_DIR")
    if override:
        return Path(override).expanduser()
    if app_bundle:
        return app_bundle / "Contents" / "Resources" / "ui" / "dist"
    source_static = Path(__file__).parent.parent / "ui" / "dist"
    return source_static if source_static.exists() else None


def get_service_paths() -> ServicePaths:
    """Resolve service paths without mutating the filesystem."""
    app_bundle = _detect_app_bundle()
    data_dir = _default_data_dir()
    var_dir = data_dir / "var"
    log_dir = data_dir / "logs"
    return ServicePaths(
        app_bundle=app_bundle,
        launcher=_launcher_path(app_bundle),
        data_dir=data_dir,
        var_dir=var_dir,
        log_dir=log_dir,
        db_path=var_dir / "traces.sqlite",
        launch_agent_dir=Path.home() / "Library" / "LaunchAgents",
        launch_agent=Path.home() / "Library" / "LaunchAgents" / f"{APP_LABEL}.plist",
        static_dir=_static_dir(app_bundle),
    )


def ensure_dirs(paths: ServicePaths) -> None:
    """Create persistent user-data and service directories."""
    paths.var_dir.mkdir(parents=True, exist_ok=True)
    paths.log_dir.mkdir(parents=True, exist_ok=True)
    paths.launch_agent_dir.mkdir(parents=True, exist_ok=True)


def _service_environment(paths: ServicePaths) -> dict[str, str]:
    env = {
        "SERVE_STATIC": "true",
        "DATABASE_PATH": str(paths.db_path),
        "LOG_DIR": str(paths.log_dir),
        "LOG_TO_FILE": "true",
        "FLUXION_PACKAGED": "true",
        "FLUXION_APP_VERSION": _app_version(),
        "FLUXION_BUILD_ID": _build_id(),
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
    }
    if paths.static_dir:
        env["FLUXION_STATIC_DIR"] = str(paths.static_dir)
    if paths.app_bundle:
        env["FLUXION_APP_BUNDLE"] = str(paths.app_bundle)
        env["FLUXION_LAUNCHER_PATH"] = str(paths.launcher)
    return env


def _launch_agent_plist(paths: ServicePaths) -> dict[str, object]:
    """Build the LaunchAgent plist payload."""
    return {
        "Label": APP_LABEL,
        "ProgramArguments": [str(paths.launcher), "serve"],
        "EnvironmentVariables": _service_environment(paths),
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(paths.log_dir / "service.stdout.log"),
        "StandardErrorPath": str(paths.log_dir / "service.stderr.log"),
    }


def launch_agent_matches(paths: ServicePaths) -> bool:
    """Return True when the installed LaunchAgent already matches this app."""
    if not paths.launch_agent.exists():
        return False
    try:
        with paths.launch_agent.open("rb") as handle:
            existing = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException):
        return False
    desired = _launch_agent_plist(paths)
    return (
        existing.get("ProgramArguments") == desired["ProgramArguments"]
        and existing.get("EnvironmentVariables") == desired["EnvironmentVariables"]
    )


def write_launch_agent(paths: ServicePaths) -> None:
    """Write the per-user LaunchAgent that runs the packaged backend."""
    ensure_dirs(paths)
    with paths.launch_agent.open("wb") as handle:
        plistlib.dump(_launch_agent_plist(paths), handle)


def _run_launchctl(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _bootout(paths: ServicePaths) -> None:
    _run_launchctl(["bootout", f"gui/{os.getuid()}", str(paths.launch_agent)], check=False)


def start_service(paths: ServicePaths, *, force: bool = False) -> None:
    """Install/update and start the LaunchAgent."""
    if not _use_launch_agent():
        raise RuntimeError(
            "LaunchAgent mode is disabled. Use the Fluxion desktop app (Tauri) or "
            "`fluxion-server serve` for the local API."
        )
    if not _is_macos():
        raise RuntimeError("Packaged service management is only supported on macOS")
    if not force and service_status() and health_ok(paths) and launch_agent_matches(paths):
        return
    write_launch_agent(paths)
    _bootout(paths)
    result = _run_launchctl(["bootstrap", f"gui/{os.getuid()}", str(paths.launch_agent)])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "launchctl bootstrap failed")
    _run_launchctl(["enable", f"gui/{os.getuid()}/{APP_LABEL}"], check=False)


def stop_service(paths: ServicePaths) -> None:
    """Stop the LaunchAgent if it is loaded."""
    if not _is_macos():
        raise RuntimeError("Packaged service management is only supported on macOS")
    _bootout(paths)


def service_status() -> bool:
    """Return True when the LaunchAgent is loaded."""
    if not _is_macos():
        return False
    result = _run_launchctl(["print", f"gui/{os.getuid()}/{APP_LABEL}"])
    return result.returncode == 0


def _read_health_metadata() -> dict[str, object] | None:
    """Read the local API health payload."""
    try:
        with urllib.request.urlopen(f"{_url()}/api/health", timeout=1.0) as response:
            if not 200 <= response.status < 300:
                return None
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _health_matches(payload: dict[str, object] | None, paths: ServicePaths | None = None) -> bool:
    """Return True when a health payload belongs to the expected Fluxion build."""
    if not payload:
        return False
    if payload.get("status") != "ok" or payload.get("app") != APP_NAME:
        return False
    if paths and paths.app_bundle:
        return (
            payload.get("packaged") is True
            and payload.get("version") == _app_version()
            and payload.get("build_id") == _build_id()
        )
    return True


def health_ok(paths: ServicePaths | None = None) -> bool:
    """Return True when the local API health endpoint is this Fluxion build."""
    return _health_matches(_read_health_metadata(), paths)


def _health_mismatch_message(payload: dict[str, object] | None) -> str | None:
    """Return a clear message for a reachable but unexpected service."""
    if not payload:
        return None
    if payload.get("app") != APP_NAME:
        return (
            f"Port {_port()} is already serving something else at {_url()}. "
            "Stop that process, then open Fluxion again."
        )
    return (
        f"Port {_port()} is serving a different Fluxion build "
        f"(version={payload.get('version')}, build={payload.get('build_id')}). "
        f"Run `{APP_NAME} restart` after replacing the app."
    )


def _port_has_http_service() -> bool:
    """Return True when something answers the health URL but is not this build."""
    try:
        with urllib.request.urlopen(f"{_url()}/api/health", timeout=1.0) as response:
            return 200 <= response.status < 500
    except (OSError, urllib.error.URLError):
        return False


def wait_for_health(timeout_seconds: float = 40.0, paths: ServicePaths | None = None) -> None:
    """Wait until the local service is healthy."""
    expected_paths = paths or get_service_paths()
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        payload = _read_health_metadata()
        if _health_matches(payload, expected_paths):
            return
        mismatch = _health_mismatch_message(payload)
        if mismatch and payload and payload.get("app") != APP_NAME:
            raise RuntimeError(mismatch)
        time.sleep(0.5)
    payload = _read_health_metadata()
    mismatch = _health_mismatch_message(payload)
    if mismatch:
        raise RuntimeError(mismatch)
    if _port_has_http_service():
        raise RuntimeError(
            f"Fluxion service did not become healthy because port {_port()} is occupied at {_url()}"
        )
    raise RuntimeError(f"Fluxion service did not become healthy at {_url()}")


def open_browser() -> None:
    """Open the browser to the local Fluxion UI."""
    if _is_macos():
        subprocess.run(["open", _url()], check=False)
    else:
        _log(f"Open {_url()}")


def serve(paths: ServicePaths) -> None:
    """Run the FastAPI backend in the current process."""
    ensure_dirs(paths)
    os.environ.setdefault("SERVE_STATIC", "true")
    os.environ.setdefault("DATABASE_PATH", str(paths.db_path))
    os.environ.setdefault("LOG_DIR", str(paths.log_dir))
    os.environ.setdefault("LOG_TO_FILE", "true")
    os.environ.setdefault("FLUXION_PACKAGED", "true")
    os.environ.setdefault("FLUXION_APP_VERSION", _app_version())
    os.environ.setdefault("FLUXION_BUILD_ID", _build_id())
    if paths.static_dir:
        os.environ.setdefault("FLUXION_STATIC_DIR", str(paths.static_dir))

    import uvicorn

    uvicorn.run(
        "orchestrator.app:app",
        host=_host(),
        port=int(_port()),
        log_level=os.environ.get("UVICORN_LOG_LEVEL", "warning"),
    )


def open_app(paths: ServicePaths) -> None:
    """Start the legacy LaunchAgent service and open the browser (pre-Tauri installs)."""
    if not _use_launch_agent():
        _log(
            "LaunchAgent mode is disabled. Open the Fluxion.app desktop client instead."
        )
        if health_ok(paths):
            open_browser()
        return
    start_service(paths)
    wait_for_health(paths=paths)
    open_browser()


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for packaged app commands."""
    args = list(argv if argv is not None else sys.argv[1:])
    command = args[0] if args else "open"
    paths = get_service_paths()

    try:
        if command == "serve":
            serve(paths)
            return 0
        if command == "open":
            open_app(paths)
            return 0
        if command == "start":
            start_service(paths)
            wait_for_health(paths=paths)
            _log("running")
            return 0
        if command == "stop":
            stop_service(paths)
            _log("stopped")
            return 0
        if command == "restart":
            stop_service(paths)
            start_service(paths, force=True)
            wait_for_health(paths=paths)
            _log("running")
            return 0
        if command == "status":
            if service_status():
                print("running")
                return 0
            print("stopped")
            return 1
        print(f"usage: {APP_NAME} [open|start|stop|restart|status|serve]", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"[fluxion] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
