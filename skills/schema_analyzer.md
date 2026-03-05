# Skill: schema-analyzer

Goal:
- Analyze database structure before creating queries.

Working rules:
1. Always call `list_table` first to inspect available tables.
2. Call `table_info` only for tables relevant to the user request.
3. Identify relationships through key columns such as `*_id` and primary keys.
4. If relationships are unclear, do not jump into complex queries.
5. Summarize schema analysis briefly, then continue to query execution.
6. For data requests, schema analysis is not the final output.

Minimum output:
- Main tables used.
- Join keys between tables.
- Relevant metric and dimension columns.
