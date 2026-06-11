import subprocess
from pathlib import Path

import pytest

from orchestrator.services import local_models


def test_rotate_log_if_needed_renames_large_log(monkeypatch, tmp_path):
    monkeypatch.setattr(local_models, "LOCAL_MODEL_LOG_MAX_BYTES", 10)
    monkeypatch.setattr(local_models, "LOCAL_MODEL_LOG_SEGMENTS", 10)

    log_file = tmp_path / "llama.log"
    log_file.write_text("x" * 32, encoding="utf-8")

    rotated = local_models._rotate_log_if_needed(log_file)

    assert rotated is not None
    assert rotated.exists()
    assert rotated.name.startswith("llama.log.wal.")
    assert rotated.read_text(encoding="utf-8") == "x" * 32
    assert not log_file.exists()


def test_rotate_log_if_needed_skips_small_log(monkeypatch, tmp_path):
    monkeypatch.setattr(local_models, "LOCAL_MODEL_LOG_MAX_BYTES", 100)

    log_file = tmp_path / "llama.log"
    log_file.write_text("small", encoding="utf-8")

    rotated = local_models._rotate_log_if_needed(log_file)

    assert rotated is None
    assert log_file.exists()
    assert log_file.read_text(encoding="utf-8") == "small"


def test_open_log_file_appends_header(monkeypatch, tmp_path):
    monkeypatch.setattr(local_models, "LOG_DIR", tmp_path)
    monkeypatch.setattr(local_models, "LOCAL_MODEL_LOG_MAX_BYTES", 10_000)

    handle, log_file = local_models._open_log_file(
        local_models.ModelType.GGUF,
        model_name="gemma",
        model_path="/models/gemma.gguf",
        ctx_size=4096,
        command=["llama-server", "-m", "/models/gemma.gguf"],
    )
    handle.close()

    content = log_file.read_text(encoding="utf-8")
    assert "MODEL_NAME: gemma" in content
    assert "MODEL_PATH: /models/gemma.gguf" in content
    assert "CTX_SIZE: 4096" in content
    assert "COMMAND: llama-server -m /models/gemma.gguf" in content


def test_scan_gguf_models_excludes_ollama_paths(monkeypatch, tmp_path):
    lmstudio_dir = tmp_path / ".lmstudio" / "models"
    good_dir = lmstudio_dir / "lmstudio-community" / "gemma"
    bad_dir = lmstudio_dir / "ollama" / "gemma"
    good_dir.mkdir(parents=True)
    bad_dir.mkdir(parents=True)
    (good_dir / "good.gguf").write_text("ok", encoding="utf-8")
    (bad_dir / "bad.gguf").write_text("bad", encoding="utf-8")

    monkeypatch.setattr(local_models, "MODEL_DIRS", [lmstudio_dir])

    models = local_models._scan_gguf_models()

    assert len(models) == 1
    assert models[0].path.endswith("good.gguf")


def test_scan_mlx_models_excludes_ollama_paths(monkeypatch, tmp_path):
    cache_dir = tmp_path / ".cache" / "lm-studio" / "models"
    good_dir = cache_dir / "mlx-community" / "good-mlx"
    bad_dir = cache_dir / "ollama" / "bad-mlx"
    good_dir.mkdir(parents=True)
    bad_dir.mkdir(parents=True)
    (good_dir / "config.json").write_text("{}", encoding="utf-8")
    (good_dir / "weights.safetensors").write_text("ok", encoding="utf-8")
    (bad_dir / "config.json").write_text("{}", encoding="utf-8")
    (bad_dir / "weights.safetensors").write_text("bad", encoding="utf-8")

    monkeypatch.setattr(local_models, "MODEL_DIRS", [cache_dir])

    models = local_models._scan_mlx_models()

    assert len(models) == 1
    assert models[0].path.endswith("good-mlx")


def test_resolve_server_executable_uses_desktop_safe_user_path(monkeypatch, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "mlx_lm.server"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)

    monkeypatch.setenv("PATH", str(bin_dir))

    assert local_models._resolve_server_executable(local_models.ModelType.MLX) == str(executable)


def test_local_server_diagnostics_reads_mlx_versions_without_importing_mlx(
    monkeypatch,
    tmp_path,
):
    python_path = tmp_path / "python"
    python_path.write_text("#!/bin/sh\n", encoding="utf-8")
    python_path.chmod(0o755)
    executable = tmp_path / "mlx_lm.server"
    executable.write_text(f"#!{python_path}\n", encoding="utf-8")

    def fake_version_reader(path: str, package_name: str):
        assert path == str(python_path)
        return {"mlx-lm": "0.31.3", "mlx": "0.31.2"}[package_name]

    monkeypatch.setattr(local_models, "_package_version_in_python", fake_version_reader)

    diagnostics = local_models._local_server_diagnostics(
        local_models.ModelType.MLX,
        str(executable),
    )

    assert diagnostics["executable"] == str(executable)
    assert diagnostics["python"] == str(python_path)
    assert diagnostics["mlx_lm_version"] == "0.31.3"
    assert diagnostics["mlx_version"] == "0.31.2"


@pytest.mark.asyncio
async def test_start_mlx_uses_absolute_served_model_id(monkeypatch, tmp_path):
    model_dir = tmp_path / "lmstudio-community" / "Qwen-MLX-4bit"
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "weights.safetensors").write_text("ok", encoding="utf-8")

    commands: list[list[str]] = []

    class FakeProcess:
        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    def fake_popen(command, stdout=None, stderr=None):
        commands.append(command)
        return FakeProcess()

    async def fake_wait_for_health(model_type, timeout=60.0):
        return True

    monkeypatch.setattr(
        local_models,
        "_resolve_server_executable",
        lambda model_type: "/usr/bin/mlx_lm.server",
    )
    monkeypatch.setattr(
        local_models,
        "_local_server_diagnostics",
        lambda model_type, executable: {"executable": executable},
    )
    monkeypatch.setattr(local_models, "_kill_port", lambda port: None)
    monkeypatch.setattr(local_models, "_wait_for_health", fake_wait_for_health)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(local_models, "LOG_DIR", tmp_path / "logs")
    local_models._state = local_models._ServerState()

    try:
        result = await local_models.start(str(model_dir), ctx_size=4096)
    finally:
        local_models._state = local_models._ServerState()

    assert result.model_type == local_models.ModelType.MLX
    assert result.model_name == "Qwen-MLX-4bit"
    assert result.served_model_id == str(model_dir.resolve())
    assert result.base_url.endswith("/v1")
    assert commands[0][:6] == [
        "/usr/bin/mlx_lm.server",
        "--model",
        str(model_dir),
        "--host",
        "127.0.0.1",
        "--port",
    ]
