"""CORE v2.0 SQLite TaskStore — persistent A2A Task storage."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

from a2a.server.context import ServerCallContext
from a2a.server.tasks.task_store import TaskStore as A2ATaskStore
from a2a.types import ListTasksRequest, ListTasksResponse, Task, TaskState

log = logging.getLogger("agentwire.task_store")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id      TEXT PRIMARY KEY,
    context_id   TEXT NOT NULL DEFAULT '',
    state        TEXT NOT NULL DEFAULT 'submitted',
    message_json TEXT NOT NULL DEFAULT '',
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL,
    data_json    TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tasks_context ON tasks(context_id);
CREATE INDEX IF NOT EXISTS idx_tasks_state   ON tasks(state);
CREATE INDEX IF NOT EXISTS idx_tasks_updated ON tasks(updated_at);
"""


def _now() -> float:
    return time.time()


class SqliteTaskStore(A2ATaskStore):
    """Persistent Task store backed by SQLite.

    Stores tasks as JSON blobs with indexed context_id and state
    for efficient querying.
    """

    def __init__(self, db_path: str = "/data/tasks.db"):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

        conn = sqlite3.connect(str(self._db_path))
        conn.executescript(SCHEMA)
        conn.commit()
        conn.close()
        log.info("task store ready: %s", self._db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    async def save(self, task: Task, context: ServerCallContext) -> None:
        """Persist task to SQLite."""
        async with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO tasks
                       (task_id, context_id, state, message_json, created_at, updated_at, data_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        task.id,
                        task.context_id,
                        TaskState.Name(task.status.state),
                        task.SerializeToString().hex() if hasattr(task, 'SerializeToString') else '',
                        _now(),
                        _now(),
                        '',
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    async def get(self, task_id: str, context: ServerCallContext) -> Task | None:
        """Retrieve task by ID."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT message_json FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if not row:
                return None
            data = bytes.fromhex(row["message_json"]) if row["message_json"] else b""
            if data:
                task = Task()
                task.ParseFromString(data)
                return task
            return None
        finally:
            conn.close()

    async def list(self, params: ListTasksRequest, context: ServerCallContext) -> ListTasksResponse:
        """List tasks with optional state/context filter and pagination."""
        conn = self._connect()
        try:
            clauses = ["1=1"]
            values: list = []
            if params.context_id:
                clauses.append("context_id = ?")
                values.append(params.context_id)
            if params.HasField("status") and params.status != TaskState.TASK_STATE_UNSPECIFIED:
                clauses.append("state = ?")
                values.append(TaskState.Name(params.status))
            where = " AND ".join(clauses)
            page_size = params.page_size if params.HasField("page_size") else 50
            offset = 0
            rows = conn.execute(
                f"SELECT message_json FROM tasks WHERE {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (*values, page_size + 1, offset),
            ).fetchall()
            tasks = []
            for row in rows[:page_size]:
                data = bytes.fromhex(row["message_json"]) if row["message_json"] else b""
                if data:
                    task = Task()
                    task.ParseFromString(data)
                    tasks.append(task)
            return ListTasksResponse(
                tasks=tasks,
                next_page_token="",
                page_size=page_size,
                total_size=len(tasks),
            )
        finally:
            conn.close()

    async def delete(self, task_id: str, context: ServerCallContext) -> None:
        """Delete a task."""
        async with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
                conn.commit()
            finally:
                conn.close()
