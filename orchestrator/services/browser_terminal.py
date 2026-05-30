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

from orchestrator.config import get_chat_config
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


def _shell_label(shell: str) -> str:
    return Path(shell).name or "shell"


class TerminalSessionLimitError(Exception):
    """Raised when a conversation already has the maximum number of running terminals."""

    def __init__(self, *, limit: int, conversation_id: str) -> None:
        self.limit = limit
        self.conversation_id = conversation_id
        super().__init__(
            f"Maximum {limit} running terminals for conversation {conversation_id}"
        )


def _normalize_workspace_path(workspace_path: str | None) -> str:
    target = Path(workspace_path).expanduser() if workspace_path else Path.home()
    try:
        return str(target.resolve())
    except OSError:
        return str(Path.home())


def build_pty_shell_environment(
    base: dict[str, str] | None,
    *,
    cols: int,
    rows: int,
) -> dict[str, str]:
    """Build environment for an interactive PTY shell.

    Parent processes (IDE, CI, uvicorn) often set ``TERM=dumb``; shells and
    prompts such as Starship require a real terminal type.
    """
    env = dict(base or os.environ)
    env["TERM"] = "xterm-256color"
    env["COLORTERM"] = "truecolor"
    env.setdefault("TERM_PROGRAM", "fluxion")
    env.pop("STARSHIP_SHELL", None)
    env["COLUMNS"] = str(cols)
    env["LINES"] = str(rows)
    return env


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
        env = build_pty_shell_environment(os.environ, cols=self.cols, rows=self.rows)
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
        self._sessions_by_id: dict[str, TerminalSession] = {}
        self._session_ids_by_conversation: dict[str, list[str]] = {}
        self._lock = asyncio.Lock()

    async def _repo(self) -> TerminalSessionRepo:
        return TerminalSessionRepo(await get_db())

    def _max_sessions(self) -> int:
        return max(1, get_chat_config().terminal.max_sessions_per_conversation)

    def _register_session(self, session: TerminalSession) -> None:
        self._sessions_by_id[session.session_id] = session
        ids = self._session_ids_by_conversation.setdefault(session.conversation_id, [])
        if session.session_id not in ids:
            ids.append(session.session_id)

    def _unregister_session(self, session: TerminalSession) -> None:
        self._sessions_by_id.pop(session.session_id, None)
        ids = self._session_ids_by_conversation.get(session.conversation_id, [])
        if session.session_id in ids:
            ids.remove(session.session_id)
        if not ids:
            self._session_ids_by_conversation.pop(session.conversation_id, None)

    async def _spawn_session(
        self,
        *,
        conversation_id: str,
        workspace_path: str | None,
        session_owner: str | None,
        cols: int,
        rows: int,
    ) -> TerminalSession:
        workspace = _normalize_workspace_path(workspace_path)
        shell = _get_default_shell()
        session = TerminalSession(
            session_id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            workspace_path=workspace,
            shell=shell,
            cols=cols,
            rows=rows,
            session_owner=session_owner,
        )
        await session.start()
        if session.read_task is not None:
            session.read_task.add_done_callback(
                lambda _task, sid=session.session_id: asyncio.create_task(self.mark_closed(sid))
            )
        self._register_session(session)
        repo = await self._repo()
        await repo.insert(
            session_id=session.session_id,
            conversation_id=conversation_id,
            workspace_path=workspace,
            shell=session.shell,
            status=session.status,
            cols=session.cols,
            rows=session.rows,
            session_owner=session_owner,
            title=_shell_label(shell),
        )
        return session

    async def list_sessions(self, conversation_id: str) -> list[dict[str, Any]]:
        repo = await self._repo()
        rows = await repo.list_by_conversation(conversation_id, status="running")
        return [self._row_to_metadata(row) for row in rows]

    async def get_metadata(self, conversation_id: str) -> Optional[dict[str, Any]]:
        """Legacy: first running session for a conversation."""
        sessions = await self.list_sessions(conversation_id)
        return sessions[0] if sessions else None

    async def get_metadata_by_session_id(self, session_id: str) -> Optional[dict[str, Any]]:
        repo = await self._repo()
        row = await repo.get_by_session_id(session_id)
        if not row:
            return None
        return self._row_to_metadata(row)

    def _row_to_metadata(self, row: dict[str, Any]) -> dict[str, Any]:
        live = self._sessions_by_id.get(row["session_id"])
        metadata = dict(row)
        metadata.setdefault("title", _shell_label(str(row.get("shell", ""))))
        metadata["reconnect_supported"] = live is not None and live.status == "running"
        metadata["replay_buffer"] = live.replay_text() if live else ""
        if live is None and metadata.get("status") == "running":
            metadata["status"] = "stale"
        return metadata

    async def get_or_create(
        self,
        *,
        conversation_id: str,
        workspace_path: str | None,
        session_owner: str | None,
        cols: int = DEFAULT_COLS,
        rows: int = DEFAULT_ROWS,
    ) -> dict[str, Any]:
        """Legacy: return first running session or create one."""
        async with self._lock:
            for session_id in self._session_ids_by_conversation.get(conversation_id, []):
                existing = self._sessions_by_id.get(session_id)
                if existing and existing.status == "running":
                    if cols != existing.cols or rows != existing.rows:
                        await existing.resize(cols, rows)
                        repo = await self._repo()
                        await repo.touch(session_id, cols=existing.cols, rows=existing.rows)
                    return self._to_metadata(existing)
        return await self.create(
            conversation_id=conversation_id,
            workspace_path=workspace_path,
            session_owner=session_owner,
            cols=cols,
            rows=rows,
        )

    async def create(
        self,
        *,
        conversation_id: str,
        workspace_path: str | None,
        session_owner: str | None,
        cols: int = DEFAULT_COLS,
        rows: int = DEFAULT_ROWS,
    ) -> dict[str, Any]:
        async with self._lock:
            repo = await self._repo()
            running = await repo.count_running(conversation_id)
            limit = self._max_sessions()
            if running >= limit:
                raise TerminalSessionLimitError(limit=limit, conversation_id=conversation_id)
            session = await self._spawn_session(
                conversation_id=conversation_id,
                workspace_path=workspace_path,
                session_owner=session_owner,
                cols=cols,
                rows=rows,
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
        """Legacy: restart the first running session for a conversation."""
        target_session_id: str | None = None
        async with self._lock:
            for session_id in self._session_ids_by_conversation.get(conversation_id, []):
                existing = self._sessions_by_id.get(session_id)
                if existing and existing.status == "running":
                    target_session_id = session_id
                    break
        if target_session_id:
            return await self.restart_session(
                session_id=target_session_id,
                workspace_path=workspace_path,
                session_owner=session_owner,
                cols=cols,
                rows=rows,
            )
        return await self.create(
            conversation_id=conversation_id,
            workspace_path=workspace_path,
            session_owner=session_owner,
            cols=cols,
            rows=rows,
        )

    async def restart_session(
        self,
        *,
        session_id: str,
        workspace_path: str | None,
        session_owner: str | None,
        cols: int = DEFAULT_COLS,
        rows: int = DEFAULT_ROWS,
    ) -> dict[str, Any]:
        async with self._lock:
            existing = self._sessions_by_id.get(session_id)
            repo = await self._repo()
            if not existing:
                row = await repo.get_by_session_id(session_id)
                if not row:
                    raise KeyError(session_id)
                conversation_id = row["conversation_id"]
                workspace = workspace_path or row.get("workspace_path")
                await repo.mark_status(session_id, status="closed")
            else:
                conversation_id = existing.conversation_id
                workspace = workspace_path or existing.workspace_path
                await self._close_session_locked(existing)
            session = await self._spawn_session(
                conversation_id=conversation_id,
                workspace_path=workspace,
                session_owner=session_owner,
                cols=cols,
                rows=rows,
            )
            return self._to_metadata(session)

    async def _close_session_locked(self, session: TerminalSession) -> None:
        self._unregister_session(session)
        await session.close()
        repo = await self._repo()
        await repo.mark_status(session.session_id, status="closed")

    async def close(self, conversation_id: str) -> None:
        """Legacy: close all running sessions for a conversation."""
        async with self._lock:
            session_ids = list(self._session_ids_by_conversation.get(conversation_id, []))
            for session_id in session_ids:
                session = self._sessions_by_id.get(session_id)
                if session:
                    await self._close_session_locked(session)

    async def close_session(self, session_id: str) -> None:
        async with self._lock:
            session = self._sessions_by_id.get(session_id)
            if session:
                await self._close_session_locked(session)
                return
            repo = await self._repo()
            await repo.mark_status(session_id, status="closed")

    async def get_live(self, session_id: str) -> Optional[TerminalSession]:
        return self._sessions_by_id.get(session_id)

    async def touch_resize(self, session_id: str, cols: int, rows: int) -> None:
        repo = await self._repo()
        await repo.touch(session_id, cols=cols, rows=rows)

    async def mark_closed(self, session_id: str) -> None:
        session = self._sessions_by_id.get(session_id)
        if session:
            self._unregister_session(session)
        repo = await self._repo()
        await repo.mark_status(session_id, status="closed")

    async def mark_stale(self, session_id: str) -> None:
        repo = await self._repo()
        await repo.mark_status(session_id, status="stale")

    async def shutdown_all(self) -> None:
        """Close every live PTY (used by tests and app shutdown)."""
        async with self._lock:
            session_ids = list(self._sessions_by_id.keys())
            for session_id in session_ids:
                session = self._sessions_by_id.get(session_id)
                if session:
                    await self._close_session_locked(session)

    def _to_metadata(self, session: TerminalSession) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "conversation_id": session.conversation_id,
            "workspace_path": session.workspace_path,
            "shell": session.shell,
            "title": _shell_label(session.shell),
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
