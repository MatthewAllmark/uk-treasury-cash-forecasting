-- Annual scorecard.
-- The rate and FX block covers the full Bank of England sample.
-- The company block is the SYNTHETIC Northvale ledger and is null in years
-- before that example history starts. 2016 and the latest year are partial
-- years for the company (the ledger starts and ends on a Friday).
-- FX returns are year-end to year-end, foreign currency per GBP.

WITH rate_year AS (
    SELECT
        substr(date, 1, 4) AS year,
        AVG(CASE WHEN series_code = 'IUDBEDR' THEN value_pct END) AS bank_rate_avg,
        AVG(CASE WHEN series_code = 'IUDSOIA' THEN value_pct END) AS sonia_avg,
        AVG(CASE WHEN series_code = 'IUDSNPY' THEN value_pct END) AS gilt5_avg,
        AVG(CASE WHEN series_code = 'IUDMNPY' THEN value_pct END) AS gilt10_avg,
        AVG(CASE WHEN series_code = 'IUDLNPY' THEN value_pct END) AS gilt20_avg
    FROM rates
    GROUP BY year
),
fx_ranked AS (
    SELECT
        substr(date, 1, 4) AS year,
        pair,
        foreign_per_gbp,
        ROW_NUMBER() OVER (
            PARTITION BY substr(date, 1, 4), pair
            ORDER BY date DESC
        ) AS rn
    FROM fx
),
fx_year AS (
    SELECT
        year,
        MAX(CASE WHEN pair = 'GBPUSD' THEN foreign_per_gbp END) AS gbpusd_end,
        MAX(CASE WHEN pair = 'GBPEUR' THEN foreign_per_gbp END) AS gbpeur_end
    FROM fx_ranked
    WHERE rn = 1
    GROUP BY year
),
fx_ret AS (
    SELECT
        year,
        gbpusd_end,
        gbpeur_end,
        gbpusd_end / LAG(gbpusd_end) OVER (ORDER BY year) - 1.0 AS gbpusd_return,
        gbpeur_end / LAG(gbpeur_end) OVER (ORDER BY year) - 1.0 AS gbpeur_return
    FROM fx_year
),
cash_ranked AS (
    SELECT
        substr(week_ending, 1, 4) AS year,
        closing_cash_gbp,
        closing_drawn_gbp,
        ROW_NUMBER() OVER (
            PARTITION BY substr(week_ending, 1, 4)
            ORDER BY week_ending DESC
        ) AS rn
    FROM cash_flows
),
cash_end AS (
    SELECT
        year,
        closing_cash_gbp AS end_cash_gbp,
        closing_drawn_gbp AS end_drawn_gbp
    FROM cash_ranked
    WHERE rn = 1
),
cash_sum AS (
    SELECT
        substr(week_ending, 1, 4) AS year,
        SUM(receipts_gbp) AS receipts_gbp,
        SUM(net_operating_gbp) AS net_operating_gbp,
        SUM(interest_gbp) AS interest_gbp,
        SUM(dividend_gbp) AS dividend_gbp,
        MAX(closing_drawn_gbp) AS peak_drawn_gbp
    FROM cash_flows
    GROUP BY year
)
SELECT
    r.year,
    r.bank_rate_avg,
    r.sonia_avg,
    r.gilt5_avg,
    r.gilt10_avg,
    r.gilt20_avg,
    f.gbpusd_end,
    f.gbpeur_end,
    f.gbpusd_return,
    f.gbpeur_return,
    c.receipts_gbp AS synthetic_receipts_gbp,
    c.net_operating_gbp AS synthetic_net_operating_gbp,
    c.interest_gbp AS synthetic_interest_gbp,
    c.dividend_gbp AS synthetic_dividend_gbp,
    c.peak_drawn_gbp AS synthetic_peak_drawn_gbp,
    e.end_cash_gbp AS synthetic_end_cash_gbp,
    e.end_drawn_gbp AS synthetic_end_drawn_gbp
FROM rate_year AS r
INNER JOIN fx_ret AS f ON f.year = r.year
LEFT JOIN cash_sum AS c ON c.year = r.year
LEFT JOIN cash_end AS e ON e.year = r.year
ORDER BY r.year;
