-- Month-end gilt nominal par curve and how it moved.
-- slope_10s5s_bp is the 10-year par yield minus the 5-year.
-- slope_20s10s_bp is the 20-year minus the 10-year.
-- gilt10_vs_bank_rate_bp is a two-point floating-versus-fixed gap: it is not
-- a fitted term premium, because it still contains expected future Bank Rate.
-- y10_change_bp is the month-to-month move in the 10-year par yield.

WITH month_end AS (
    SELECT
        series_code,
        substr(date, 1, 7) AS month,
        value_pct,
        ROW_NUMBER() OVER (
            PARTITION BY series_code, substr(date, 1, 7)
            ORDER BY date DESC
        ) AS rn
    FROM rates
    WHERE series_code IN ('IUDSNPY', 'IUDMNPY', 'IUDLNPY', 'IUDBEDR')
),
levels AS (
    SELECT
        month,
        MAX(CASE WHEN series_code = 'IUDSNPY' THEN value_pct END) AS gilt_5y,
        MAX(CASE WHEN series_code = 'IUDMNPY' THEN value_pct END) AS gilt_10y,
        MAX(CASE WHEN series_code = 'IUDLNPY' THEN value_pct END) AS gilt_20y,
        MAX(CASE WHEN series_code = 'IUDBEDR' THEN value_pct END) AS bank_rate
    FROM month_end
    WHERE rn = 1
    GROUP BY month
)
SELECT
    month,
    gilt_5y,
    gilt_10y,
    gilt_20y,
    bank_rate,
    (gilt_10y - gilt_5y) * 100.0 AS slope_10s5s_bp,
    (gilt_20y - gilt_10y) * 100.0 AS slope_20s10s_bp,
    (gilt_10y - bank_rate) * 100.0 AS gilt10_vs_bank_rate_bp,
    (gilt_10y - LAG(gilt_10y) OVER (ORDER BY month)) * 100.0 AS y10_change_bp
FROM levels
ORDER BY month;
