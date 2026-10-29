-- Month-end sterling spot (foreign currency per GBP) and the monthly return.
-- A negative log return means one pound bought fewer units of foreign currency
-- than a month earlier, so the sterling cost of a foreign-currency payable rose.
-- log_return is ln(S_t / S_t-1). simple_return is S_t / S_t-1 - 1.

WITH month_end AS (
    SELECT
        pair,
        substr(date, 1, 7) AS month,
        foreign_per_gbp,
        ROW_NUMBER() OVER (
            PARTITION BY pair, substr(date, 1, 7)
            ORDER BY date DESC
        ) AS rn
    FROM fx
),
levels AS (
    SELECT pair, month, foreign_per_gbp
    FROM month_end
    WHERE rn = 1
)
SELECT
    pair,
    month,
    foreign_per_gbp,
    LN(foreign_per_gbp / LAG(foreign_per_gbp) OVER (PARTITION BY pair ORDER BY month))
        AS log_return,
    foreign_per_gbp / LAG(foreign_per_gbp) OVER (PARTITION BY pair ORDER BY month) - 1.0
        AS simple_return
FROM levels
ORDER BY pair, month;
