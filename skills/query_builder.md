# Skill: query-builder

Goal:
- Build SQL from user requests accurately and safely.

Working rules:
1. Only create `SELECT` queries (read-only).
2. Use valid table and column names based on schema.
3. For aggregations, ensure all non-aggregated columns are included in `GROUP BY`.
4. For ranking, use explicit `ORDER BY` and `LIMIT`.
5. Avoid `SELECT *`; select only needed columns.
6. Validate the query, then call `execute_query`.
7. For data retrieval questions, do not return SQL-only answers.
8. Return actual query results in a readable table format.

Minimum output:
- Query results (rows/columns).
- Final SQL query.

Example:
User: "How many tracks cost more than $1?"
Steps: execute_query("SELECT COUNT(*) AS count FROM Track WHERE UnitPrice > 1.0")
Answer: 42 tracks cost more than $1.00. | SQL: SELECT COUNT(*) AS count FROM Track WHERE UnitPrice > 1.0
