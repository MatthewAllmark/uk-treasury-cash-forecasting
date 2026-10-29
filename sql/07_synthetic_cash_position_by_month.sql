-- SYNTHETIC EXAMPLE. Northvale Components Ltd is fictional.
-- Monthly operating result and the cash and facility balances on the last
-- Friday of each month. Interest and the dividend are financing items, so
-- they are reported beside net operating cash flow rather than inside it.

WITH ranked AS (
    SELECT
        substr(week_ending, 1, 7) AS month,
        week_ending,
        receipts_gbp,
        net_operating_gbp,
        interest_gbp,
        dividend_gbp,
        closing_cash_gbp,
        closing_drawn_gbp,
        ROW_NUMBER() OVER (
            PARTITION BY substr(week_ending, 1, 7)
            ORDER BY week_ending DESC
        ) AS rn
    FROM cash_flows
)
SELECT
    month,
    SUM(receipts_gbp) AS receipts_gbp,
    SUM(net_operating_gbp) AS net_operating_gbp,
    SUM(interest_gbp) AS interest_gbp,
    SUM(dividend_gbp) AS dividend_gbp,
    MAX(CASE WHEN rn = 1 THEN closing_cash_gbp END) AS month_end_cash_gbp,
    MAX(CASE WHEN rn = 1 THEN closing_drawn_gbp END) AS month_end_drawn_gbp
FROM ranked
GROUP BY month
ORDER BY month;
