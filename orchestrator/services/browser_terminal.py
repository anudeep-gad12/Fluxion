"""Persistent browser terminal sessions backed by PTYs."""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import os
import pty
import signal
import struct
import subprocess
import termios
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from orchestrator.logging_config import get_logger
from orchestrator.storage.db import get_db
from orchestrator.storage.repositories.terminal_repo import TerminalSessionRepo

logger = get_logger(__name__)

DEFAULT_COLS = 120
DEFAULT_ROWS = 30
MAX_REPLAY_CHARS = 120_000


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_default_shell() -> str:
    return os.environ.get("SHELL") or "/bin/zsh"


def _normalize_workspace_path(workspace_path: str | None) -> str:
    target = Path(workspace_path).expanduser() if workspace_path else Path.home()
    try:
        return str(target.resolve())
    except OSError:
        return str(Path.home())


@dataclass
class TerminalSession:
    """Live PTY session and bounded replay for one conversation."""

    session_id: str
    conversation_id: str
    workspace_path: str
    shell: str
    cols: int = DEFAULT_COLS
    rows: int = DEFAULT_ROWS
    session_owner: str | None = None
    status: str = "running"
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
    last_activity_at: str = field(default_factory=_utcnow)
    master_fd: int | None = None
    process: subprocess.Popen[bytes] | None = None
    read_task: asyncio.Task[None] | None = None
    replay_chunks: deque[str] = field(default_factory=deque)
    replay_chars: int = 0
    subscribers: set[asyncio.Queue[dict[str, Any]]] = field(default_factory=set)

    async def start(self) -> None:
        master_fd, slave_fd = pty.openpty()
        self.master_fd = master_fd
        self._set_winsize(self.cols, self.rows)
        env = os.environ.copy()
        env.setdefault("TERM", "xterm-256color")
        env["COLUMNS"] = str(self.cols)
        env["LINES"] = str(self.rows)
        def _configure_child_terminal() -> None:
            os.setsid()
            fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)

        self.process = subprocess.Popen(
            [self.shell],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=self.workspace_path,
            env=env,
            preexec_fn=_configure_child_terminal,
            close_fds=True,
        )
        os.close(slave_fd)
        self.updated_at = _utcnow()
        self.last_activity_at = self.updated_at
        self.read_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            while self.master_fd is not None:
                chunk = await asyncio.to_thread(os.read, self.master_fd, 4096)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                self._append_replay(text)
                await self._broadcast({"type": "output", "data": text})
                self.updated_at = _utcnow()
                self.last_activity_at = self.updated_at
        except OSError:
            pass
        finally:
            exit_code = None
            if self.process is not None:
                with contextlib.suppress(Exception):
                    exit_code = self.process.wait(timeout=0.2)
            self.status = "closed"
            self.updated_at = _utcnow()
            self.last_activity_at = self.updated_at
            await self._broadcast({"type": "exit", "exit_code": exit_code})

    def _append_replay(self, text: str) -> None:
        if not text:
            return
        self.replay_chunks.append(text)
        self.replay_chars += len(text)
        while self.replay_chars > MAX_REPLAY_CHARS and self.replay_chunks:
            removed = self.replay_chunks.popleft()
            self.replay_chars -= len(removed)

    async def _broadcast(self, event: dict[str, Any]) -> None:
        dead: list[asyncio.Queue[dict[str, Any]]] = []
        for queue in self.subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(queue)
        for queue in dead:
            self.subscribers.discard(queue)

    def _set_winsize(self, cols: int, rows: int) -> None:
        if self.master_fd is None:
            return
        packed = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, packed)

    async def write(self, data: str) -> None:
        if self.master_fd is None or self.status != "running":
            return
        await asyncio.to_thread(os.write, self.master_fd, data.encode("utf-8", errors="replace"))
        self.updated_at = _utcnow()
        self.last_activity_at = self.updated_at

    async def resize(self, cols: int, rows: int) -> None:
        self.cols = max(40, cols)
        self.rows = max(10, rows)
        self._set_winsize(self.cols, self.rows)
        self.updated_at = _utcnow()
        self.last_activity_at = self.updated_at

    def attach(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self.subscribers.add(queue)
        return queue

    def detach(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self.subscribers.discard(queue)

    def replay_text(self) -> str:
        return "".join(self.replay_chunks)

    async def close(self) -> None:
        if self.status == "closed":
            return
        self.status = "closed"
        self.updated_at = _utcnow()
        self.last_activity_at = self.updated_at
        if self.process is not None and self.process.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGTERM)
            await asyncio.sleep(0.05)
            if self.process.poll() is None:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(self.process.pid, signal.SIGKILL)
        if self.master_fd is not None:
            with contextlib.suppress(OSError):
                os.close(self.master_fd)
            self.master_fd = None
        if self.read_task is not None:
            self.read_task.cancel()
            self.read_task = None
        await self._broadcast({"type": "status", "status": "closed"})


class TerminalSessionManager:
    """In-memory PTY manager with persisted metadata."""

    def __init__(self) -> None:
        self._sessions_by_conversation: dict[str, TerminalSession] = {}
        self._sessions_by_id: dict[str, TerminalSession] = {}
        self._lock = asyncio.Lock()

    async def _repo(self) -> TerminalSessionRepo:
        return TerminalSessionRepo(await get_db())

    async def get_metadata(self, conversation_id: str) -> Optional[dict[str, Any]]:
        repo = await self._repo()
        row = await repo.get_by_conversation(conversation_id)
        if not row:
            return None
        row["reconnect_supported"] = conversation_id in self._sessions_by_conversation
        live = self._sessions_by_conversation.get(conversation_id)
        row["replay_buffer"] = live.replay_text() if live else ""
        if live is None and row["status"] == "running":
            row["status"] = "stale"
        return row

    async def get_or_create(
        self,
        *,
        conversation_id: str,
        workspace_path: str | None,
        session_owner: str | None,
        cols: int = DEFAULT_COLS,
        rows: int = DEFAULT_ROWS,
    ) -> dict[str, Any]:
        async with self._lock:
            existing = self._sessions_by_conversation.get(conversation_id)
            if existing and existing.status == "running":
                if cols != existing.cols or rows != existing.rows:
                    await existing.resize(cols, rows)
                    repo = await self._repo()
                    await repo.touch(conversation_id, cols=existing.cols, rows=existing.rows)
                return self._to_metadata(existing)

            workspace = _normalize_workspace_path(workspace_path)
            session = TerminalSession(
                session_id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                workspace_path=workspace,
                shell=_get_default_shell(),
                cols=cols,
                rows=rows,
                session_owner=session_owner,
            )
            await session.start()
            if session.read_task is not None:
                session.read_task.add_done_callback(
                    lambda _task, cid=conversation_id: asyncio.create_task(self.mark_closed(cid))
                )
            self._sessions_by_conversation[conversation_id] = session
            self._sessions_by_id[session.session_id] = session
            repo = await self._repo()
            await repo.upsert(
                session_id=session.session_id,
                conversation_id=conversation_id,
                workspace_path=workspace,
                shell=session.shell,
                status=session.status,
                cols=session.cols,
                rows=session.rows,
                session_owner=session_owner,
            )
            return self._to_metadata(session)

    async def restart(
        self,
        *,
        conversation_id: str,
        workspace_path: str | None,
        session_owner: str | None,
        cols: int = DEFAULT_COLS,
        rows: int = DEFAULT_ROWS,
    ) -> dict[str, Any]:
        async with self._lock:
            existing = self._sessions_by_conversation.pop(conversation_id, None)
            if existing:
                self._sessions_by_id.pop(existing.session_id, None)
                await existing.close()
            workspace = _normalize_workspace_path(workspace_path)
            session = TerminalSession(
                session_id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                workspace_path=workspace,
                shell=_get_default_shell(),
                cols=cols,
                rows=rows,
                session_owner=session_owner,
            )
            await session.start()
            if session.read_task is not None:
                session.read_task.add_done_callback(
                    lambda _task, cid=conversation_id: asyncio.create_task(self.mark_closed(cid))
                )
            self._sessions_by_conversation[conversation_id] = session
            self._sessions_by_id[session.session_id] = session
            repo = await self._repo()
            await repo.upsert(
                session_id=session.session_id,
                conversation_id=conversation_id,
                workspace_path=workspace,
                shell=session.shell,
                status=session.status,
                cols=session.cols,
                rows=session.rows,
                session_owner=session_owner,
            )
            return self._to_metadata(session)

    async def close(self, conversation_id: str) -> None:
        async with self._lock:
            session = self._sessions_by_conversation.pop(conversation_id, None)
            if not session:
                return
            self._sessions_by_id.pop(session.session_id, None)
            await session.close()
            repo = await self._repo()
            await repo.mark_status(conversation_id, status="closed")

    async def get_live(self, session_id: str) -> Optional[TerminalSession]:
        return self._sessions_by_id.get(session_id)

    async def touch_resize(self, conversation_id: str, cols: int, rows: int) -> None:
        repo = await self._repo()
        await repo.touch(conversation_id, cols=cols, rows=rows)

    async def mark_closed(self, conversation_id: str) -> None:
        repo = await self._repo()
        await repo.mark_status(conversation_id, status="closed")

    async def mark_stale(self, conversation_id: str) -> None:
        repo = await self._repo()
        await repo.mark_status(conversation_id, status="stale")

    def _to_metadata(self, session: TerminalSession) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "conversation_id": session.conversation_id,
            "workspace_path": session.workspace_path,
            "shell": session.shell,
            "status": session.status,
            "cols": session.cols,
            "rows": session.rows,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "last_activity_at": session.last_activity_at,
            "reconnect_supported": True,
            "replay_buffer": session.replay_text(),
        }


_terminal_manager: TerminalSessionManager | None = None


def get_terminal_manager() -> TerminalSessionManager:
    global _terminal_manager
    if _terminal_manager is None:
        _terminal_manager = TerminalSessionManager()
    return _terminal_manager
