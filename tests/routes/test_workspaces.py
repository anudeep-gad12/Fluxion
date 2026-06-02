"""Tests for workspace browsing and file search routes."""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.app import app
from orchestrator.routes import workspaces as workspace_routes


def test_ensure_fluxion_gitignore_creates_entry_for_git_workspace(tmp_path: Path):
    (tmp_path / ".git").mkdir()

    changed = workspace_routes.ensure_fluxion_gitignore(tmp_path)

    assert changed is True
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == ".fluxion/\n"


def test_ensure_fluxion_gitignore_appends_entry_idempotently(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("dist\n", encoding="utf-8")

    first_changed = workspace_routes.ensure_fluxion_gitignore(tmp_path)
    second_changed = workspace_routes.ensure_fluxion_gitignore(tmp_path)

    content = gitignore.read_text(encoding="utf-8")
    assert first_changed is True
    assert second_changed is False
    assert content == "dist\n.fluxion/\n"
    assert content.count(".fluxion") == 1


def test_ensure_fluxion_gitignore_skips_non_git_workspace(tmp_path: Path):
    changed = workspace_routes.ensure_fluxion_gitignore(tmp_path)

    assert changed is False
    assert not (tmp_path / ".gitignore").exists()


@pytest.mark.asyncio
async def test_ensure_fluxion_gitignore_endpoint_updates_git_workspace(tmp_path: Path):
    (tmp_path / ".git").mkdir()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/workspaces/ensure-fluxion-gitignore",
            json={"workspace_path": str(tmp_path)},
        )

    assert response.status_code == 200
    assert response.json()["changed"] is True
    assert response.json()["ignored"] is True
    assert ".fluxion/" in (tmp_path / ".gitignore").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_browse_workspace_directories_lists_only_directories(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("hi")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/workspaces/browse", params={"path": str(tmp_path)})

    assert response.status_code == 200
    data = response.json()
    assert data["path"] == str(tmp_path.resolve())
    assert [entry["name"] for entry in data["entries"]] == ["src"]


@pytest.mark.asyncio
async def test_search_workspace_files_matches_relative_paths(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.tsx").write_text("export {}")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "AppGuide.md").write_text("# hi")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/workspaces/search-files",
            params={"workspace_path": str(tmp_path), "q": "app"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["workspace_path"] == str(tmp_path.resolve())
    assert [entry["path"] for entry in data["entries"]] == [
        "src/App.tsx",
        "docs/AppGuide.md",
    ]


@pytest.mark.asyncio
async def test_search_workspace_files_excludes_hidden_and_ignored_dirs(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("x")
    (tmp_path / ".env").write_text("SECRET=1")
    (tmp_path / "visible.py").write_text("print('ok')")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/workspaces/search-files",
            params={"workspace_path": str(tmp_path), "q": ""},
        )

    assert response.status_code == 200
    paths = [entry["path"] for entry in response.json()["entries"]]
    assert "visible.py" in paths
    assert ".env" not in paths
    assert ".git/config" not in paths
    assert "node_modules/pkg.js" not in paths


@pytest.mark.asyncio
async def test_search_workspace_files_excludes_fluxion_dir(tmp_path: Path):
    (tmp_path / ".fluxion" / "runs" / "run-1").mkdir(parents=True)
    (tmp_path / ".fluxion" / "runs" / "run-1" / "stdout.txt").write_text("output")
    (tmp_path / "visible.py").write_text("print('ok')")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/workspaces/search-files",
            params={"workspace_path": str(tmp_path), "q": ""},
        )

    assert response.status_code == 200
    paths = [entry["path"] for entry in response.json()["entries"]]
    assert "visible.py" in paths
    assert ".fluxion/runs/run-1/stdout.txt" not in paths


@pytest.mark.asyncio
async def test_search_workspace_files_requires_valid_workspace():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/workspaces/search-files",
            params={"workspace_path": "/definitely/missing/path", "q": "app"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_search_workspace_files_caps_results(tmp_path: Path):
    for idx in range(5):
        (tmp_path / f"file-{idx}.ts").write_text("x")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/workspaces/search-files",
            params={"workspace_path": str(tmp_path), "limit": 3},
        )

    assert response.status_code == 200
    assert len(response.json()["entries"]) == 3


@pytest.mark.asyncio
async def test_search_workspace_files_skips_problematic_file_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "good.py").write_text("print('ok')")
    (tmp_path / "bad.py").write_text("print('bad')")
    original_is_file = Path.is_file

    def flaky_is_file(path: Path) -> bool:
        if path.name == "bad.py":
            raise OSError("iCloud placeholder unavailable")
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", flaky_is_file)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/workspaces/search-files",
            params={"workspace_path": str(tmp_path), "q": ".py"},
        )

    assert response.status_code == 200
    assert [entry["path"] for entry in response.json()["entries"]] == ["good.py"]


@pytest.mark.asyncio
async def test_search_workspace_files_returns_best_effort_when_walk_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def failing_walk(*args, **kwargs):
        raise OSError("directory unavailable")

    monkeypatch.setattr(workspace_routes.os, "walk", failing_walk)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/workspaces/search-files",
            params={"workspace_path": str(tmp_path), "q": ""},
        )

    assert response.status_code == 200
    assert response.json()["entries"] == []
