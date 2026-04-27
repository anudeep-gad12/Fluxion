"""Tests for workspace browsing and file search routes."""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.app import app


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
