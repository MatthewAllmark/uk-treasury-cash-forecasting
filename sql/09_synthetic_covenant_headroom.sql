-- SYNTHETIC EXAMPLE. Northvale Components Ltd is fictional.
-- Weekly covenant monitor for the example facility. Thresholds come from
-- company_parameters. They illustrate headroom; they are not a real loan
-- agreement.
--
-- interest_cover_52w uses a trailing 52-week window (ROWS BETWEEN 51 PRECEDING
-- AND CURRENT ROW) and is only reported once that window is full. The numerator
-- is net operating cash flow, a cash proxy, not accounting EBITDA.
-- hard_cash_breach is 1 when closing cash is under the example hard minimum.
-- soft_utilisation_flag is 1 when drawings exceed the example soft trigger.
-- interest_cover_flag is 1 when the full-window cover is below the example minimum.

WITH params AS (
    SELECT
        MAX(CASE WHEN name = 'facility_limit_gbp' THEN value END) AS facility_limit,
        MAX(CASE WHEN name = 'hard_min_cash_gbp' THEN value END) AS hard_min_cash,
        MAX(CASE WHEN name = 'max_utilisation_soft' THEN value END) AS max_util_soft,
        MAX(CASE WHEN name = 'min_interest_cover' THEN value END) AS min_cover
    FROM company_parameters
),
base AS (
    SELECT
        c.week_ending,
        c.closing_cash_gbp,
        c.closing_drawn_gbp,
        c.net_operating_gbp,
        c.interest_gbp,
        SUM(c.net_operating_gbp) OVER (
            ORDER BY c.week_ending
            ROWS BETWEEN 51 PRECEDING AND CURRENT ROW
        ) AS net_operating_52w,
        SUM(c.interest_gbp) OVER (
            ORDER BY c.week_ending
            ROWS BETWEEN 51 PRECEDING AND CURRENT ROW
        ) AS interest_52w,
        ROW_NUMBER() OVER (ORDER BY c.week_ending) AS week_no
    FROM cash_flows AS c
)
SELECT
    b.week_ending,
    b.closing_cash_gbp,
    b.closing_drawn_gbp,
    p.facility_limit - b.closing_drawn_gbp AS undrawn_gbp,
    b.closing_cash_gbp - p.hard_min_cash AS cash_headroom_vs_hard_min_gbp,
    b.closing_drawn_gbp / p.facility_limit AS utilisation,
    CASE
        WHEN b.week_no >= 52 THEN b.net_operating_52w / NULLIF(b.interest_52w, 0)
    END AS interest_cover_52w,
    CASE WHEN b.closing_cash_gbp < p.hard_min_cash THEN 1 ELSE 0 END AS hard_cash_breach,
    CASE
        WHEN b.closing_drawn_gbp / p.facility_limit > p.max_util_soft THEN 1
        ELSE 0
    END AS soft_utilisation_flag,
    CASE
        WHEN b.week_no >= 52
         AND b.interest_52w > 0
         AND b.net_operating_52w / b.interest_52w < p.min_cover
        THEN 1
        ELSE 0
    END AS interest_cover_flag
FROM base AS b
CROSS JOIN params AS p
ORDER BY b.week_ending;
