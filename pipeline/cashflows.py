"""Synthetic weekly ledger for Northvale Components Ltd (fictional).

The company invoices UK customers in sterling and pays for materials in
dollars and euros. Seasonal cash troughs are funded with a sterling revolving
credit facility priced at SONIA plus a fixed margin.

Two layers stay separate on purpose:

* Operating items (receipts, payroll, materials, tax) are simulated.
* SONIA and the two spot rates are observed Bank of England fixings, or
  scenarios built from those fixings. They are never drawn from the random
  seed that builds the operating items.

Interest is simple Actual/365 on the opening drawn balance. A live facility
would more often use compounded SONIA in arrears; the simpler identity is
what the reconciliation tests rebuild.

The same `roll_ledger` function posts history, the cash forecast and the
Monte Carlo paths, so those three views cannot drift apart.

On the last Friday of June and of December, if the facility is undrawn, cash
above a surplus cap is distributed. The facility is not drawn to fund it.
"""

from __future__ import annotations

import calendar
import math
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from pipeline import config as cfg


def as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def iter_fridays(start: date, end: date) -> list[date]:
    if start.weekday() != 4:
        raise ValueError(f"{start} is not a Friday")
    weeks = []
    day = start
    while day <= end:
        weeks.append(day)
        day += timedelta(days=7)
    return weeks


def future_fridays(last_week: date, n: int) -> list[date]:
    return iter_fridays(last_week + timedelta(days=7), last_week + timedelta(days=7 * n))


def is_tax_week(day: date) -> bool:
    """Friday falling on the 14th–20th of January, April, July and October.

    Every month has exactly one such Friday, so the quarterly settlement
    cannot land twice.
    """
    return day.month in (1, 4, 7, 10) and 14 <= day.day <= 20


def is_dividend_week(day: date) -> bool:
    """Last Friday of June and of December."""
    if day.month not in (6, 12) or day.weekday() != 4:
        return False
    return day.day + 7 > calendar.monthrange(day.year, day.month)[1]


def trend_factor(day: date) -> float:
    years = (day - cfg.TREND_ANCHOR).days / 365.25
    return (1.0 + cfg.TREND_ANNUAL) ** years


def _multiplier(z: float, sigma: float) -> float:
    """Lognormal shock with mean 1. `z` is a standard normal draw."""
    if sigma == 0.0:
        return 1.0
    return math.exp(-0.5 * sigma * sigma + sigma * z)


def make_schedule(weeks: list[date], rng: np.random.Generator | None) -> dict:
    """Contractual operating items for each Friday.

    With `rng` set, each week consumes five standard normal draws in a fixed
    order (receipts, USD costs, EUR costs, payroll, other opex). With `rng`
    left as None the multipliers are 1, which is the mean of that noise, so
    the forecast is the expected schedule rather than a median path.
    """
    n = len(weeks)
    columns = {
        "receipts": np.empty(n),
        "payroll": np.empty(n),
        "opex": np.empty(n),
        "tax": np.empty(n),
        "usd_fc": np.empty(n),
        "eur_fc": np.empty(n),
    }
    is_div = np.zeros(n, dtype=bool)
    for i, week in enumerate(weeks):
        if week.weekday() != 4:
            raise ValueError(f"{week} is not a Friday")
        tr = trend_factor(week)
        receipt_season = cfg.RECEIPT_SEASON[week.month]
        cost_season = cfg.COST_SEASON[week.month]
        if rng is None:
            mr = mu = me = mp = mo = 1.0
        else:
            z = rng.normal(size=5)
            mr = _multiplier(float(z[0]), cfg.RECEIPT_SIGMA)
            mu = _multiplier(float(z[1]), cfg.COST_SIGMA)
            me = _multiplier(float(z[2]), cfg.COST_SIGMA)
            mp = _multiplier(float(z[3]), cfg.COST_SIGMA)
            mo = _multiplier(float(z[4]), cfg.COST_SIGMA)
        columns["receipts"][i] = cfg.BASE_RECEIPTS_GBP * tr * receipt_season * mr
        columns["usd_fc"][i] = cfg.BASE_USD_COSTS * tr * cost_season * mu
        columns["eur_fc"][i] = cfg.BASE_EUR_COSTS * tr * cost_season * me
        columns["payroll"][i] = cfg.BASE_PAYROLL_GBP * tr * cost_season * mp
        columns["opex"][i] = cfg.BASE_OTHER_OPEX_GBP * tr * cost_season * mo
        columns["tax"][i] = cfg.TAX_GBP * tr if is_tax_week(week) else 0.0
        is_div[i] = is_dividend_week(week)
    columns["is_dividend"] = is_div
    columns["weeks"] = list(weeks)
    return columns


def apply_facility(opening_cash, opening_drawn, net_operating, dividend, interest):
    """Sweep cash back to the policy minimum, subject to the facility limit.

    Arrays are shape (n_paths,). A shortfall is drawn, capped by undrawn
    headroom. A surplus repays the facility down towards a zero balance and
    is not drawn again in the same week.
    """
    cash_before = opening_cash + net_operating - dividend - interest
    shortfall = cfg.MIN_CASH_POLICY_GBP - cash_before
    headroom = cfg.FACILITY_LIMIT_GBP - opening_drawn
    draw = np.where(shortfall > 0.0, np.minimum(shortfall, np.maximum(headroom, 0.0)), 0.0)
    repay = np.where(
        shortfall > 0.0,
        0.0,
        np.minimum(-shortfall, np.maximum(opening_drawn, 0.0)),
    )
    closing_cash = cash_before + draw - repay
    closing_drawn = opening_drawn + draw - repay
    return draw, repay, closing_cash, closing_drawn


def _dividend(is_div, opening_cash, opening_drawn, net_operating, interest) -> np.ndarray:
    """Sweep cash above the surplus cap. Never draw the facility to do it."""
    n_paths = opening_cash.shape[0]
    if not is_div:
        return np.zeros(n_paths)
    cash_before = opening_cash + net_operating - interest
    desired = cash_before - cfg.SURPLUS_CAP_GBP
    available = cash_before - cfg.MIN_CASH_POLICY_GBP
    pay = np.maximum(np.minimum(desired, available), 0.0)
    return np.where(opening_drawn <= 1e-8, pay, 0.0)


def roll_ledger(
    schedule: dict,
    sonia: np.ndarray,
    usd_per_gbp: np.ndarray,
    eur_per_gbp: np.ndarray,
    opening_cash: float,
    opening_drawn: float,
    delay_u: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """Post the weekly ledger.

    `sonia`, `usd_per_gbp` and `eur_per_gbp` have shape (n_paths, n_weeks).
    SONIA is a percent per annum. FX is foreign currency per pound.

    `delay_u` is an optional uniform(0, 1) array of the same shape. Values
    below DELAY_P_2W defer a fraction of this week's contractual receipts by
    two weeks; the next band defers a smaller fraction by one week. Money
    already in transit is not delayed again. None means receipts are on time.
    """
    sonia = np.asarray(sonia, dtype=float)
    usd_per_gbp = np.asarray(usd_per_gbp, dtype=float)
    eur_per_gbp = np.asarray(eur_per_gbp, dtype=float)
    n_paths, n_weeks = sonia.shape
    if usd_per_gbp.shape != sonia.shape or eur_per_gbp.shape != sonia.shape:
        raise ValueError("SONIA and FX paths must share shape (n_paths, n_weeks)")
    if len(schedule["weeks"]) != n_weeks:
        raise ValueError("schedule length does not match the rate paths")
    if delay_u is not None and delay_u.shape != sonia.shape:
        raise ValueError("delay draws must have shape (n_paths, n_weeks)")

    cash = np.full(n_paths, opening_cash, dtype=float)
    drawn = np.full(n_paths, opening_drawn, dtype=float)

    fields = [
        "receipts", "payroll", "opex", "tax", "usd_fc", "eur_fc",
        "usd_gbp", "eur_gbp", "operating_out", "net_operating",
        "interest", "dividend", "opening_cash", "opening_drawn",
        "draw", "repay", "closing_cash", "closing_drawn", "sonia",
        "usd_per_gbp", "eur_per_gbp",
    ]
    out = {name: np.zeros((n_paths, n_weeks)) for name in fields}
    queue1 = np.zeros(n_paths)
    queue2 = np.zeros(n_paths)

    for t in range(n_weeks):
        scheduled = float(schedule["receipts"][t])
        arriving = queue1.copy()
        if delay_u is None:
            hold1 = np.zeros(n_paths)
            hold2 = np.zeros(n_paths)
        else:
            u = delay_u[:, t]
            hold2 = np.where(u < cfg.DELAY_P_2W, cfg.DELAY_FRAC_2W * scheduled, 0.0)
            hold1 = np.where(
                (u >= cfg.DELAY_P_2W) & (u < cfg.DELAY_P_2W + cfg.DELAY_P_1W),
                cfg.DELAY_FRAC_1W * scheduled,
                0.0,
            )
        receipts = scheduled - hold1 - hold2 + arriving
        queue1 = queue2 + hold1
        queue2 = hold2

        usd_gbp = float(schedule["usd_fc"][t]) / usd_per_gbp[:, t]
        eur_gbp = float(schedule["eur_fc"][t]) / eur_per_gbp[:, t]
        payroll = float(schedule["payroll"][t])
        opex = float(schedule["opex"][t])
        tax = float(schedule["tax"][t])
        operating_out = payroll + opex + tax + usd_gbp + eur_gbp
        net_operating = receipts - operating_out
        interest = drawn * (sonia[:, t] / 100.0 + cfg.MARGIN) * cfg.WEEK_YEAR_FRACTION
        dividend = _dividend(
            bool(schedule["is_dividend"][t]), cash, drawn, net_operating, interest
        )
        draw, repay, closing_cash, closing_drawn = apply_facility(
            cash, drawn, net_operating, dividend, interest
        )

        out["receipts"][:, t] = receipts
        out["payroll"][:, t] = payroll
        out["opex"][:, t] = opex
        out["tax"][:, t] = tax
        out["usd_fc"][:, t] = float(schedule["usd_fc"][t])
        out["eur_fc"][:, t] = float(schedule["eur_fc"][t])
        out["usd_gbp"][:, t] = usd_gbp
        out["eur_gbp"][:, t] = eur_gbp
        out["operating_out"][:, t] = operating_out
        out["net_operating"][:, t] = net_operating
        out["interest"][:, t] = interest
        out["dividend"][:, t] = dividend
        out["opening_cash"][:, t] = cash
        out["opening_drawn"][:, t] = drawn
        out["draw"][:, t] = draw
        out["repay"][:, t] = repay
        out["closing_cash"][:, t] = closing_cash
        out["closing_drawn"][:, t] = closing_drawn
        out["sonia"][:, t] = sonia[:, t]
        out["usd_per_gbp"][:, t] = usd_per_gbp[:, t]
        out["eur_per_gbp"][:, t] = eur_per_gbp[:, t]

        cash = closing_cash
        drawn = closing_drawn

    out["in_transit"] = queue1 + queue2
    return out


def _fixing_maps(rates: pd.DataFrame, fx: pd.DataFrame):
    def mapping(frame, key, value):
        return {as_date(d): float(v) for d, v in zip(frame[key], frame[value])}

    sonia = mapping(rates.loc[rates["series_code"] == "IUDSOIA"], "date", "value_pct")
    usd = mapping(fx.loc[fx["pair"] == "GBPUSD"], "date", "foreign_per_gbp")
    eur = mapping(fx.loc[fx["pair"] == "GBPEUR"], "date", "foreign_per_gbp")
    common = sorted(set(sonia) & set(usd) & set(eur))
    if not common:
        raise RuntimeError("SONIA, GBPUSD and GBPEUR have no dates in common")
    return sonia, usd, eur, common


def _asof(common: list[date], week: date) -> date:
    """Last common fixing on or before this Friday."""
    lo, hi = 0, len(common)
    while lo < hi:
        mid = (lo + hi) // 2
        if common[mid] <= week:
            lo = mid + 1
        else:
            hi = mid
    if lo == 0:
        raise RuntimeError(f"No Bank of England fixing on or before {week}")
    return common[lo - 1]


def build_synthetic_history(rates: pd.DataFrame, fx: pd.DataFrame) -> pd.DataFrame:
    """Seeded weekly ledger using observed Friday-as-of SONIA and FX.

    The fixing for a Friday is the latest date on which SONIA and both spot
    rates had all been published. A Friday bank holiday therefore uses the
    previous business day's fixings, and the week is still posted.
    """
    sonia_map, usd_map, eur_map, common = _fixing_maps(rates, fx)
    last = common[-1]
    if cfg.HISTORY_START < common[0]:
        raise RuntimeError("Example history starts before the market data")
    weeks = iter_fridays(cfg.HISTORY_START, last)
    if not weeks:
        raise RuntimeError("No Friday weeks in the example history")

    fixings = [_asof(common, week) for week in weeks]
    schedule = make_schedule(weeks, np.random.default_rng(cfg.SEED))
    posted = roll_ledger(
        schedule,
        sonia=np.array([[sonia_map[day] for day in fixings]]),
        usd_per_gbp=np.array([[usd_map[day] for day in fixings]]),
        eur_per_gbp=np.array([[eur_map[day] for day in fixings]]),
        opening_cash=cfg.OPENING_CASH_GBP,
        opening_drawn=cfg.OPENING_DRAWN_GBP,
        delay_u=None,
    )
    frame = pd.DataFrame({
        "week_ending": [week.isoformat() for week in weeks],
        "fixing_date": [day.isoformat() for day in fixings],
        "receipts_gbp": posted["receipts"][0],
        "payroll_gbp": posted["payroll"][0],
        "other_opex_gbp": posted["opex"][0],
        "tax_gbp": posted["tax"][0],
        "dividend_gbp": posted["dividend"][0],
        "usd_costs_fc": posted["usd_fc"][0],
        "eur_costs_fc": posted["eur_fc"][0],
        "usd_per_gbp": posted["usd_per_gbp"][0],
        "eur_per_gbp": posted["eur_per_gbp"][0],
        "usd_costs_gbp": posted["usd_gbp"][0],
        "eur_costs_gbp": posted["eur_gbp"][0],
        "sonia_pct": posted["sonia"][0],
        "interest_gbp": posted["interest"][0],
        "total_operating_outflow_gbp": posted["operating_out"][0],
        "net_operating_gbp": posted["net_operating"][0],
        "opening_cash_gbp": posted["opening_cash"][0],
        "opening_drawn_gbp": posted["opening_drawn"][0],
        "drawdown_gbp": posted["draw"][0],
        "repayment_gbp": posted["repay"][0],
        "closing_cash_gbp": posted["closing_cash"][0],
        "closing_drawn_gbp": posted["closing_drawn"][0],
        "is_synthetic": 1,
        "example_label": cfg.SYNTHETIC_LABEL,
    })
    return frame


def load_ledger_state(connection) -> dict:
    """Last posted week, as the starting point for a forecast or a stress."""
    frame = pd.read_sql_query(
        """
        SELECT week_ending, closing_cash_gbp, closing_drawn_gbp,
               sonia_pct, usd_per_gbp, eur_per_gbp
        FROM cash_flows
        ORDER BY week_ending
        """,
        connection,
    )
    if len(frame) < 52:
        raise RuntimeError("Need at least 52 synthetic weeks before a forecast")
    last = frame.iloc[-1]
    return {
        "last_week": as_date(last["week_ending"]),
        "cash": float(last["closing_cash_gbp"]),
        "drawn": float(last["closing_drawn_gbp"]),
        "sonia": float(last["sonia_pct"]),
        "usd_per_gbp": float(last["usd_per_gbp"]),
        "eur_per_gbp": float(last["eur_per_gbp"]),
        "n_weeks": int(len(frame)),
    }
