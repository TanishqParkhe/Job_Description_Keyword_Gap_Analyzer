"""Small SQLite persistence layer for analyses saved by the user."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from config import SQLITE_PATH, ensure_directories
from database.queries import (
    CREATE_TABLE,
    DELETE_ALL,
    INSERT_ANALYSIS,
    SELECT_RECENT,
)


class DatabaseManager:
    """Save, list and delete analyses in one local SQLite file."""

    def __init__(self, database_path: str | Path = SQLITE_PATH):
        ensure_directories()
        self.database_path = Path(database_path)
        self.last_error = ""
        try:
            self.initialize()
        except Exception as error:  # The main app must still work without history.
            self.last_error = str(error)

    @property
    def enabled(self) -> bool:
        return not self.last_error

    def _connection(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with closing(self._connection()) as connection:
            connection.execute(CREATE_TABLE)
            connection.commit()
        self.last_error = ""

    @staticmethod
    def _record_values(record: dict[str, Any]) -> tuple[Any, ...]:
        analysis = record.get("analysis", {})
        return (
            str(record.get("candidate_name", "Unknown candidate")),
            str(record.get("job_title", "Unspecified role")),
            float(record.get("ats_score", 0) or 0),
            str(record.get("rating", "")),
            json.dumps(record.get("matched_skills", []), ensure_ascii=False),
            json.dumps(record.get("missing_skills", []), ensure_ascii=False),
            json.dumps(analysis, ensure_ascii=False, default=str),
        )

    def save_analysis(self, record: dict[str, Any]) -> int | None:
        try:
            with closing(self._connection()) as connection:
                cursor = connection.execute(INSERT_ANALYSIS, self._record_values(record))
                connection.commit()
                self.last_error = ""
                return int(cursor.lastrowid)
        except Exception as error:
            self.last_error = str(error)
            return None

    def list_analyses(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        try:
            with closing(self._connection()) as connection:
                rows = connection.execute(SELECT_RECENT, (limit,)).fetchall()
            self.last_error = ""
            return [dict(row) for row in rows]
        except Exception as error:
            self.last_error = str(error)
            return []

    def delete_all(self) -> bool:
        try:
            with closing(self._connection()) as connection:
                connection.execute(DELETE_ALL)
                connection.commit()
            return True
        except Exception as error:
            self.last_error = str(error)
            return False
