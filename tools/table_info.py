from __future__ import annotations

import sqlite3
from pathlib import Path


def get_table_info(database_path: str, table_name: str) -> list[dict[str, str | int | None]]:
    normalized_table_name = table_name.strip()
    if not normalized_table_name:
        raise ValueError("table_name must not be empty.")

    db_file = Path(database_path)
    if not db_file.exists():
        raise FileNotFoundError(f"Database file not found: {database_path}")

    with sqlite3.connect(str(db_file)) as connection:
        connection.row_factory = sqlite3.Row
        table_exists_query = "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1;"
        exists_row = connection.execute(table_exists_query, (normalized_table_name,)).fetchone()
        if exists_row is None:
            raise ValueError(f"Table not found: {normalized_table_name}")

        pragma_query = f"PRAGMA table_info('{normalized_table_name}')"
        rows = connection.execute(pragma_query).fetchall()
        return [
            {
                "cid": int(row["cid"]),
                "name": str(row["name"]),
                "type": str(row["type"]),
                "notnull": int(row["notnull"]),
                "dflt_value": None if row["dflt_value"] is None else str(row["dflt_value"]),
                "pk": int(row["pk"]),
            }
            for row in rows
        ]
