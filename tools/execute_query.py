from __future__ import annotations

import sqlite3
from pathlib import Path

SQLiteValue = str | int | float | None


def execute_readonly_query(database_path: str, query: str) -> dict[str, list[str] | list[dict[str, SQLiteValue]]]:
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
            return {"columns": [], "rows": []}

        columns = [str(column_name) for column_name in rows[0].keys()]
        result_rows: list[dict[str, SQLiteValue]] = []
        for row in rows:
            mapped_row: dict[str, SQLiteValue] = {}
            for column_name in columns:
                value = row[column_name]
                if isinstance(value, bytes):
                    raise TypeError(
                        f"Column '{column_name}' returned bytes; convert it to text or number in SQL."
                    )
                if isinstance(value, (str, int, float)) or value is None:
                    mapped_row[column_name] = value
                else:
                    raise TypeError(
                        f"Unsupported value type for column '{column_name}': {type(value).__name__}"
                    )
            result_rows.append(mapped_row)
        return {"columns": columns, "rows": result_rows}
