-- A Bank Rate regime is a spell at one administered rate.
-- LAG finds the dates the rate actually changes. The current regime has no
-- successor, so its end date is the last published observation and its length
-- runs up to the sample end rather than up to a further change.

WITH ordered AS (
    SELECT
        date,
        value_pct AS bank_rate_pct,
        LAG(value_pct) OVER (ORDER BY date) AS previous_rate
    FROM rates
    WHERE series_code = 'IUDBEDR'
),
changes AS (
    SELECT date AS regime_start, bank_rate_pct
    FROM ordered
    WHERE previous_rate IS NULL OR bank_rate_pct <> previous_rate
),
bounded AS (
    SELECT
        regime_start,
        bank_rate_pct,
        LEAD(regime_start) OVER (ORDER BY regime_start) AS next_regime_start
    FROM changes
)
SELECT
    regime_start,
    bank_rate_pct,
    COALESCE(
        next_regime_start,
        (SELECT MAX(date) FROM rates WHERE series_code = 'IUDBEDR')
    ) AS regime_end,
    CAST(
        julianday(
            COALESCE(
                next_regime_start,
                (SELECT MAX(date) FROM rates WHERE series_code = 'IUDBEDR')
            )
        ) - julianday(regime_start) AS INTEGER
    ) AS regime_length_days,
    CASE WHEN next_regime_start IS NULL THEN 1 ELSE 0 END AS is_current_regime
FROM bounded
ORDER BY regime_start;
