# Skill: segment-analyzer

Goal:
- Compare metrics across business segments clearly.

Working rules:
1. Identify the requested segment dimension (for example: country, genre, customer).
2. Aggregate the requested metric per segment with explicit `GROUP BY`.
3. Rank segments with deterministic ordering (`ORDER BY` metric, then segment key).
4. Return top/bottom N when user requests ranking.
5. Use concise comparisons and avoid unsupported causal claims.
6. Call `execute_query` and return real rows before explanation.

Minimum output:
- Segment comparison table.
- Short insight on top and bottom segments.
- Final SQL query.

Example:
User: "Revenue by country, top 5"
Steps: execute_query("SELECT BillingCountry, SUM(Total) AS revenue FROM Invoice GROUP BY BillingCountry ORDER BY revenue DESC LIMIT 5")
Answer: [country|revenue table] USA leads with the highest revenue.
