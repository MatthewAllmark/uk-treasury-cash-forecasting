-- SYNTHETIC EXAMPLE. Northvale Components Ltd is fictional.
-- Monthly facility usage and cash interest on the example RCF.
-- The contractual limit is read from company_parameters so this file does
-- not hard-code the facility size. peak_utilisation is the worst Friday
-- closing drawing in the month, divided by that limit.

WITH limits AS (
    SELECT value AS facility_limit_gbp
    FROM company_parameters
    WHERE name = 'facility_limit_gbp'
),
ranked AS (
    SELECT
        substr(week_ending, 1, 7) AS month,
        week_ending,
        closing_drawn_gbp,
        closing_cash_gbp,
        interest_gbp,
        ROW_NUMBER() OVER (
            PARTITION BY substr(week_ending, 1, 7)
            ORDER BY week_ending DESC
        ) AS rn
    FROM cash_flows
)
SELECT
    r.month,
    SUM(r.interest_gbp) AS interest_gbp,
    AVG(r.closing_drawn_gbp) AS avg_drawn_gbp,
    MAX(r.closing_drawn_gbp) AS max_drawn_gbp,
    MAX(r.closing_drawn_gbp) / l.facility_limit_gbp AS peak_utilisation,
    l.facility_limit_gbp - MAX(r.closing_drawn_gbp) AS min_undrawn_headroom_gbp,
    MAX(CASE WHEN r.rn = 1 THEN r.closing_cash_gbp END) AS month_end_cash_gbp,
    MAX(CASE WHEN r.rn = 1 THEN r.closing_drawn_gbp END) AS month_end_drawn_gbp
FROM ranked AS r
CROSS JOIN limits AS l
GROUP BY r.month, l.facility_limit_gbp
ORDER BY r.month;
