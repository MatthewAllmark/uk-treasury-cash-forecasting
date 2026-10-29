-- Peak-to-current drawdown of sterling's spot value (foreign per GBP).
-- The running peak is the highest fixing from the start of the sample up to
-- each day. drawdown is zero at a new high and negative when sterling has
-- fallen from that high. For a UK importer, a deeper (more negative) drawdown
-- is a higher sterling cost of foreign payables than at the recent peak.

WITH peaks AS (
    SELECT
        date,
        pair,
        foreign_per_gbp,
        MAX(foreign_per_gbp) OVER (
            PARTITION BY pair
            ORDER BY date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS peak_foreign_per_gbp
    FROM fx
)
SELECT
    date,
    pair,
    foreign_per_gbp,
    peak_foreign_per_gbp,
    foreign_per_gbp / peak_foreign_per_gbp - 1.0 AS drawdown
FROM peaks
ORDER BY pair, date;
