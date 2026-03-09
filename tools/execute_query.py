from __future__ import annotations

import sqlite3
from pathlib import Path

SQLiteValue = str | int | float | None

QueryResult = dict[
    str,
    list[str]
    | list[dict[str, SQLiteValue]]
    | bool
    | int,
]


def _clip_cell(value: SQLiteValue, max_cell_chars: int) -> SQLiteValue:
    if value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, str) and len(value) > max_cell_chars:
        return value[: max_cell_chars - 3].rstrip() + "..."
    return value


def execute_readonly_query(
    database_path: str,
    query: str,
    max_rows: int = 50,
    max_cell_chars: int = 200,
) -> QueryResult:
    if max_rows <= 0:
        raise ValueError("max_rows must be greater than 0.")
    if max_cell_chars <= 0:
        raise ValueError("max_cell_chars must be greater than 0.")

    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query must not be empty.")
    if not normalized_query.lower().startswith("select"):
        raise ValueError("Only SELECT queries are allowed.")

    db_file = Path(database_path)
    if not db_file.exists():
        raise FileNotFoundError(f"Database file not found: {database_path}")

    with sqlite3.connect(str(db_file)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(normalized_query).fetchall()
        if not rows:
            return {
                "columns": [],
                "rows": [],
                "truncated": False,
                "returned_rows": 0,
                "row_limit": max_rows,
            }

        columns = [str(column_name) for column_name in rows[0].keys()]
        result_rows: list[dict[str, SQLiteValue]] = []
        truncated = False
        for idx, row in enumerate(rows):
            if idx >= max_rows:
                truncated = True
                break
            mapped_row: dict[str, SQLiteValue] = {}
            for column_name in columns:
                value = row[column_name]
                if isinstance(value, bytes):
                    raise TypeError(
                        f"Column '{column_name}' returned bytes; convert it to text or number in SQL."
                    )
                if isinstance(value, (str, int, float)) or value is None:
                    mapped_row[column_name] = _clip_cell(value, max_cell_chars)
                else:
                    raise TypeError(
                        f"Unsupported value type for column '{column_name}': {type(value).__name__}"
                    )
            result_rows.append(mapped_row)

        return {
            "columns": columns,
            "rows": result_rows,
            "truncated": truncated,
            "returned_rows": len(result_rows),
            "row_limit": max_rows,
        }
