-- Monthly average of the daily Bank Rate, SONIA and gilt par yields.
-- Bank Rate is an administered step, so the monthly mean sits on the steps.
-- SONIA is the overnight fixing an RCF actually prices from, and it moves
-- inside a Bank Rate regime. Averages are unweighted across published days.

SELECT
    substr(date, 1, 7) AS month,
    AVG(CASE WHEN series_code = 'IUDBEDR' THEN value_pct END) AS bank_rate_avg,
    AVG(CASE WHEN series_code = 'IUDSOIA' THEN value_pct END) AS sonia_avg,
    AVG(CASE WHEN series_code = 'IUDSNPY' THEN value_pct END) AS gilt_5y_avg,
    AVG(CASE WHEN series_code = 'IUDMNPY' THEN value_pct END) AS gilt_10y_avg,
    AVG(CASE WHEN series_code = 'IUDLNPY' THEN value_pct END) AS gilt_20y_avg,
    COUNT(DISTINCT date) AS n_days
FROM rates
GROUP BY month
ORDER BY month;
