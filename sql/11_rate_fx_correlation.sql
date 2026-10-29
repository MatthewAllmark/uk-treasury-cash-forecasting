-- Pearson correlation of daily SONIA changes with sterling log returns.
-- SQLite has no CORR(), so the correlation is the standard one-pass formula
-- (the n versus n-1 terms cancel and this matches the sample correlation).
--
-- d_sonia is the daily change in SONIA, in percentage points.
-- r_usd and r_eur are daily log returns of foreign-per-GBP spot.
-- A negative correlation with r_usd means SONIA tended to rise on days when
-- the pound bought fewer dollars. Most SONIA changes are zero inside a regime,
-- so this full-sample correlation can be weak even when a stress week is not.
-- The Monte Carlo uses a separate, shorter weekly covariance, saved with the
-- model outputs rather than estimated here.

WITH sonia AS (
    SELECT
        date,
        value_pct - LAG(value_pct) OVER (ORDER BY date) AS d_sonia
    FROM rates
    WHERE series_code = 'IUDSOIA'
),
usd AS (
    SELECT
        date,
        foreign_per_gbp,
        LAG(foreign_per_gbp) OVER (ORDER BY date) AS previous_rate
    FROM fx
    WHERE pair = 'GBPUSD'
),
eur AS (
    SELECT
        date,
        foreign_per_gbp,
        LAG(foreign_per_gbp) OVER (ORDER BY date) AS previous_rate
    FROM fx
    WHERE pair = 'GBPEUR'
),
joined AS (
    SELECT
        s.d_sonia AS d_sonia,
        LN(u.foreign_per_gbp / u.previous_rate) AS r_usd,
        LN(e.foreign_per_gbp / e.previous_rate) AS r_eur
    FROM sonia AS s
    INNER JOIN usd AS u ON u.date = s.date
    INNER JOIN eur AS e ON e.date = s.date
    WHERE s.d_sonia IS NOT NULL
      AND u.previous_rate IS NOT NULL
      AND e.previous_rate IS NOT NULL
),
stats AS (
    SELECT
        COUNT(*) AS n,
        SUM(d_sonia) AS sx,
        SUM(r_usd) AS sy,
        SUM(r_eur) AS sz,
        SUM(d_sonia * d_sonia) AS sxx,
        SUM(r_usd * r_usd) AS syy,
        SUM(r_eur * r_eur) AS szz,
        SUM(d_sonia * r_usd) AS sxy,
        SUM(d_sonia * r_eur) AS sxz,
        SUM(r_usd * r_eur) AS syz
    FROM joined
)
SELECT
    n AS n_days,
    (n * sxy - sx * sy) / SQRT((n * sxx - sx * sx) * (n * syy - sy * sy))
        AS corr_dsonia_gbpusd,
    (n * sxz - sx * sz) / SQRT((n * sxx - sx * sx) * (n * szz - sz * sz))
        AS corr_dsonia_gbpeur,
    (n * syz - sy * sz) / SQRT((n * syy - sy * sy) * (n * szz - sz * sz))
        AS corr_gbpusd_gbpeur
FROM stats;
