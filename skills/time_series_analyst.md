# Skill: time-series-analyst

Goal:
- Analyze metric movement over time with clear trend direction.

Working rules:
1. Build time-bucketed `SELECT` queries (`day`, `month`, `quarter`, `year`) based on user request.
2. Use stable sorting by time in ascending order for trend computation.
3. For growth, compute both absolute change and percentage change when possible.
4. Handle divide-by-zero safely in SQL when calculating percentage change.
5. Keep trend commentary short and based on returned rows only.
6. Call `execute_query` and present real data before interpretation.

Minimum output:
- Time-bucketed result table.
- Short trend interpretation (increasing, decreasing, or mixed).
- Final SQL query.

Example:
User: "Show yearly revenue trend"
Steps: execute_query("SELECT strftime('%Y',InvoiceDate) AS year, SUM(Total) AS revenue FROM Invoice GROUP BY year ORDER BY year")
Answer: [year|revenue table] Revenue grew steadily from 2009 to 2013.
