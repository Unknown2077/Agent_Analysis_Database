# Skill: data-quality-checker

Goal:
- Validate data quality before or during analysis.

Working rules:
1. Build focused `SELECT` checks for nulls in key columns.
2. Check duplicates using grouped counts on natural or business keys.
3. Check outliers or invalid values only when user asks or metric suggests risk.
4. Keep checks scoped to relevant tables and columns.
5. If issues are found, quantify them with counts and percentages.
6. Call `execute_query` for each check and report actual results.

Minimum output:
- Quality check summary table(s).
- Clear issue list with counts (or confirm no issue found).
- Final SQL query per check.
