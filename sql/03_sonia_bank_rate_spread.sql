-- SONIA minus Bank Rate, in basis points.
-- SONIA is an unsecured overnight fixing, so it normally prints a few basis
-- points away from the administered rate rather than on top of it. The gap
-- is the part of the coupon an RCF at SONIA + margin does not pick up from
-- Bank Rate alone. Aggregated to a month so the file stays readable.

WITH daily AS (
    SELECT
        s.date AS date,
        (s.value_pct - b.value_pct) * 100.0 AS spread_bp
    FROM rates AS s
    INNER JOIN rates AS b
        ON b.date = s.date
       AND b.series_code = 'IUDBEDR'
    WHERE s.series_code = 'IUDSOIA'
)
SELECT
    substr(date, 1, 7) AS month,
    AVG(spread_bp) AS avg_spread_bp,
    MIN(spread_bp) AS min_spread_bp,
    MAX(spread_bp) AS max_spread_bp
FROM daily
GROUP BY month
ORDER BY month;
