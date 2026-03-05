from __future__ import annotations

import sqlite3
from pathlib import Path


def list_tables(database_path: str) -> list[str]:
    db_file = Path(database_path)
    if not db_file.exists():
        raise FileNotFoundError(f"Database file not found: {database_path}")

    query = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
    with sqlite3.connect(str(db_file)) as connection:
        rows = connection.execute(query).fetchall()
        return [str(row[0]) for row in rows]
