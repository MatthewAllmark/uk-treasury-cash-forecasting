-- SYNTHETIC EXAMPLE. Northvale Components Ltd is fictional.
-- Average week by calendar month. Receipts are seasonal by construction
-- (stronger into year-end, softer in late summer). Costs move less, which is
-- why the facility is a summer tool rather than a permanent drawing.
-- The month factor is the average receipts in that month divided by the
-- average receipts across every week in the ledger.

WITH by_month AS (
    SELECT
        CAST(substr(week_ending, 6, 2) AS INTEGER) AS calendar_month,
        AVG(receipts_gbp) AS avg_weekly_receipts_gbp,
        AVG(usd_costs_fc) AS avg_weekly_usd_costs,
        AVG(eur_costs_fc) AS avg_weekly_eur_costs,
        AVG(payroll_gbp + other_opex_gbp) AS avg_weekly_gbp_opex,
        AVG(net_operating_gbp) AS avg_weekly_net_operating_gbp,
        COUNT(*) AS n_weeks
    FROM cash_flows
    GROUP BY calendar_month
)
SELECT
    calendar_month,
    avg_weekly_receipts_gbp,
    avg_weekly_receipts_gbp / (SELECT AVG(receipts_gbp) FROM cash_flows)
        AS receipt_index_vs_all_weeks,
    avg_weekly_usd_costs,
    avg_weekly_eur_costs,
    avg_weekly_gbp_opex,
    avg_weekly_net_operating_gbp,
    n_weeks
FROM by_month
ORDER BY calendar_month;
