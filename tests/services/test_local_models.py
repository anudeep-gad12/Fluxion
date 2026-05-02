from pathlib import Path

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
