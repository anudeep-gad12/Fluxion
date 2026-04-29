"""Repository for global application settings."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from orchestrator.storage.db import Database


class AppSettingsRepo:
    """CRUD helper for global settings stored in SQLite."""

    def __init__(self, db: Database):
        self.db = db

    async def get(self, key: str) -> Optional[dict[str, Any]]:
        cursor = await self.db.conn.execute(
            "SELECT setting_key, value_json, updated_at FROM app_settings WHERE setting_key = ?",
            (key,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "key": row["setting_key"],
            "value": json.loads(row["value_json"]),
            "updated_at": row["updated_at"],
        }

    async def put(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        updated_at = datetime.now(timezone.utc).isoformat()
        value_json = json.dumps(value, ensure_ascii=False)
        await self.db.conn.execute(
            """
            INSERT INTO app_settings (setting_key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (key, value_json, updated_at),
        )
        await self.db.conn.commit()
        return {"key": key, "value": value, "updated_at": updated_at}
