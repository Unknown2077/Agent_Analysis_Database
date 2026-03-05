# Skill: query-builder

Goal:
- Build SQL from user requests accurately and safely.

Working rules:
1. Only create `SELECT` queries (read-only).
2. Use valid table and column names based on schema.
3. For aggregations, ensure all non-aggregated columns are included in `GROUP BY`.
4. For ranking, use explicit `ORDER BY` and `LIMIT`.
5. Avoid `SELECT *`; select only needed columns.
6. Validate the query before calling `execute_query`.

Minimum output:
- Final SQL query.
- Short reason why the query satisfies the request.
