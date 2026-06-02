"""Workspace-local durable artifacts for ephemeral agent outputs."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class ArtifactWrite:
    """Metadata for a saved local artifact."""

    artifact_id: str
    artifact_path: str
    absolute_path: str
    byte_count: int
    sha256: str
    content_type: str
    metadata: dict[str, Any]


class AgentArtifactManager:
    """Owns `.fluxion/runs/<run_id>` storage for one workspace run."""

    def __init__(self, workspace_path: str, run_id: str) -> None:
        self.workspace_path = Path(workspace_path).resolve()
        self.run_id = str(run_id)
        self.base_dir = (self.workspace_path / ".fluxion" / "runs" / self.run_id).resolve()
        try:
            self.base_dir.relative_to(self.workspace_path)
        except ValueError as exc:
            raise ValueError("artifact base path escapes workspace") from exc
        self.manifest_path = self.base_dir / "manifest.json"

    @property
    def base_relative_path(self) -> str:
        return self._relative_to_workspace(self.base_dir)

    def ensure_initialized(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            self._atomic_write_json(
                self.manifest_path,
                {
                    "run_id": self.run_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "artifacts": [],
                },
            )

    def write_text(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "text/plain",
        metadata: Optional[dict[str, Any]] = None,
    ) -> ArtifactWrite:
        return self.write_bytes(
            relative_path,
            text.encode("utf-8"),
            content_type=content_type,
            metadata=metadata,
        )

    def write_json(
        self,
        relative_path: str,
        payload: Any,
        *,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ArtifactWrite:
        return self.write_text(
            relative_path,
            json.dumps(payload, ensure_ascii=False, indent=2),
            content_type="application/json",
            metadata=metadata,
        )

    def write_bytes(
        self,
        relative_path: str,
        data: bytes,
        *,
        content_type: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ArtifactWrite:
        self.ensure_initialized()
        target = self._resolve_inside_base(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write_bytes(target, data)
        stat = target.stat()
        digest = hashlib.sha256(data).hexdigest()
        artifact = ArtifactWrite(
            artifact_id=str(uuid.uuid4()),
            artifact_path=self._relative_to_workspace(target),
            absolute_path=str(target),
            byte_count=stat.st_size,
            sha256=digest,
            content_type=content_type,
            metadata=metadata or {},
        )
        self._append_manifest(artifact)
        return artifact

    def list_artifacts(self) -> list[dict[str, Any]]:
        self.ensure_initialized()
        manifest = self._read_manifest()
        artifacts = manifest.get("artifacts")
        return artifacts if isinstance(artifacts, list) else []

    def read_text_artifact(
        self,
        artifact_path: str,
        *,
        offset: int = 1,
        limit: int = 200,
    ) -> dict[str, Any]:
        path = self._resolve_read_path(artifact_path)
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        offset = max(1, int(offset or 1))
        limit = min(max(1, int(limit or 200)), 1000)
        start = offset - 1
        end = min(len(lines), start + limit)
        selected = lines[start:end]
        return {
            "artifact_path": self._relative_to_workspace(path),
            "line_start": start + 1,
            "line_end": end if selected else None,
            "total_lines": len(lines),
            "next_offset": end + 1 if end < len(lines) else None,
            "content": "\n".join(f"{idx:>6}\t{line}" for idx, line in enumerate(selected, start + 1)),
        }

    def _append_manifest(self, artifact: ArtifactWrite) -> None:
        manifest = self._read_manifest()
        entries = manifest.setdefault("artifacts", [])
        entries.append(
            {
                "artifact_id": artifact.artifact_id,
                "artifact_path": artifact.artifact_path,
                "byte_count": artifact.byte_count,
                "sha256": artifact.sha256,
                "content_type": artifact.content_type,
                "metadata": artifact.metadata,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._atomic_write_json(self.manifest_path, manifest)

    def _read_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {"run_id": self.run_id, "artifacts": []}
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"run_id": self.run_id, "artifacts": []}

    def _resolve_inside_base(self, relative_path: str) -> Path:
        raw = str(relative_path or "").strip()
        if not raw:
            raise ValueError("artifact relative_path is required")
        path = (self.base_dir / raw).resolve()
        try:
            path.relative_to(self.base_dir)
        except ValueError as exc:
            raise ValueError("artifact path escapes run directory") from exc
        return path

    def _resolve_read_path(self, artifact_path: str) -> Path:
        raw = str(artifact_path or "").strip()
        if not raw:
            raise ValueError("artifact_path is required")
        path = Path(raw)
        if path.is_absolute():
            resolved = path.resolve()
        else:
            if raw.startswith(".fluxion/"):
                resolved = (self.workspace_path / raw).resolve()
            else:
                resolved = (self.base_dir / raw).resolve()
        try:
            resolved.relative_to(self.base_dir)
        except ValueError as exc:
            raise ValueError("artifact path is outside this run") from exc
        if not resolved.is_file():
            raise ValueError(f"artifact not found: {artifact_path}")
        return resolved

    def _relative_to_workspace(self, path: Path) -> str:
        return str(path.resolve().relative_to(self.workspace_path))

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
        AgentArtifactManager._atomic_write_bytes(
            path,
            json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        )

    @staticmethod
    def _atomic_write_bytes(path: Path, data: bytes) -> None:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        finally:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
