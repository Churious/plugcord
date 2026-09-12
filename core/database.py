"""Asynchronous SQLite database interface for Plugcord."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from core.exceptions import DatabaseError

logger = logging.getLogger("plugcord.database")


class Database:
    """Manages asynchronous SQLite connections and module state persistence."""

    def __init__(self, db_path: str | Path = "data/plugcord.db") -> None:
        self.db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Establishes connection to the SQLite database and runs initial migrations."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL;")
            await self._conn.execute("PRAGMA foreign_keys=ON;")
            await self._init_tables()
            logger.info(f"Connected to SQLite database at {self.db_path}")
        except Exception as e:
            logger.error(f"Database connection failed: {e}", exc_info=True)
            raise DatabaseError(f"Failed to connect to database at {self.db_path}: {e}") from e

    async def close(self) -> None:
        """Closes the active database connection."""
        if self._conn is not None:
            try:
                await self._conn.close()
                logger.info("Closed database connection.")
            except Exception as e:
                logger.error(f"Error closing database: {e}")
            finally:
                self._conn = None

    async def _init_tables(self) -> None:
        """Initializes tables and schema migrations."""
        if self._conn is None:
            raise DatabaseError("Database is not connected.")

        query = """
        CREATE TABLE IF NOT EXISTS modules (
            id TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0,
            last_status TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
        await self._conn.execute(query)
        await self._conn.commit()

    async def get_module_state(self, module_id: str) -> dict[str, Any] | None:
        """Fetches stored state for a specific module."""
        if self._conn is None:
            raise DatabaseError("Database is not connected.")

        try:
            async with self._conn.execute(
                "SELECT id, enabled, last_status, updated_at FROM modules WHERE id = ?",
                (module_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return None
                return {
                    "id": row["id"],
                    "enabled": bool(row["enabled"]),
                    "last_status": row["last_status"],
                    "updated_at": row["updated_at"],
                }
        except Exception as e:
            logger.error(f"Database error querying module '{module_id}': {e}")
            raise DatabaseError(f"Failed to get module state: {e}") from e

    async def set_module_state(self, module_id: str, enabled: bool, last_status: str) -> None:
        """Inserts or updates the module state in SQLite."""
        if self._conn is None:
            raise DatabaseError("Database is not connected.")

        now = datetime.now(UTC).isoformat()
        query = """
        INSERT INTO modules (id, enabled, last_status, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            enabled = excluded.enabled,
            last_status = excluded.last_status,
            updated_at = excluded.updated_at;
        """
        try:
            await self._conn.execute(query, (module_id, int(enabled), last_status, now))
            await self._conn.commit()
            logger.debug(f"Updated database state for '{module_id}': enabled={enabled}, status={last_status}")
        except Exception as e:
            logger.error(f"Database error saving module '{module_id}': {e}")
            raise DatabaseError(f"Failed to set module state for '{module_id}': {e}") from e

    async def get_all_modules(self) -> dict[str, dict[str, Any]]:
        """Retrieves all stored module states."""
        if self._conn is None:
            raise DatabaseError("Database is not connected.")

        try:
            async with self._conn.execute("SELECT id, enabled, last_status, updated_at FROM modules") as cursor:
                rows = await cursor.fetchall()
                result: dict[str, dict[str, Any]] = {}
                for row in rows:
                    result[row["id"]] = {
                        "id": row["id"],
                        "enabled": bool(row["enabled"]),
                        "last_status": row["last_status"],
                        "updated_at": row["updated_at"],
                    }
                return result
        except Exception as e:
            logger.error(f"Database error querying all modules: {e}")
            raise DatabaseError(f"Failed to get all module states: {e}") from e

    async def delete_module_record(self, module_id: str) -> bool:
        """Deletes a module record from the database."""
        if self._conn is None:
            raise DatabaseError("Database is not connected.")

        try:
            cursor = await self._conn.execute("DELETE FROM modules WHERE id = ?", (module_id,))
            await self._conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Database error deleting module record '{module_id}': {e}")
            raise DatabaseError(f"Failed to delete module '{module_id}': {e}") from e
