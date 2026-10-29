"""Descriptive charts and statistics for the Bank of England sample and the ledger."""

from __future__ import annotations

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.common import (
    GOLD,
    GREEN,
    MARKET_NOTE,
    NAVY,
    RUST,
    SYNTHETIC_NOTE,
    TEAL,
    apply_style,
    save_fig,
)
from pipeline import config as cfg


def _r(value, digits):
    return round(float(value), digits)


def write_market(connection) -> dict:
    apply_style()
    rates = pd.read_sql_query(
        "SELECT date, series_code, value_pct FROM rates ORDER BY date",
        connection,
    )
    fx = pd.read_sql_query(
        "SELECT date, pair, foreign_per_gbp FROM fx ORDER BY date",
        connection,
    )
    ledger = pd.read_sql_query(
        "SELECT * FROM cash_flows ORDER BY week_ending",
        connection,
    )
    rates["date"] = pd.to_datetime(rates["date"])
    fx["date"] = pd.to_datetime(fx["date"])
    ledger["week_ending"] = pd.to_datetime(ledger["week_ending"])

    wide = rates.pivot(index="date", columns="series_code", values="value_pct").sort_index()
    spots = fx.pivot(index="date", columns="pair", values="foreign_per_gbp").sort_index()

    _plot_funding_rates(wide)
    _plot_curve(wide)
    _plot_spread(wide)
    _plot_fx(spots)
    _plot_drawdowns(spots)
    _plot_ledger(ledger)

    bank = wide["IUDBEDR"].dropna()
    sonia = wide["IUDSOIA"].dropna()
    gilt10 = wide["IUDMNPY"].dropna()
    joined = pd.concat(
        [sonia.rename("sonia"), bank.rename("bank")],
        axis=1,
    ).dropna()
    spread_bp = (joined["sonia"] - joined["bank"]) * 100.0
    recent = spread_bp[spread_bp.index >= "2022-01-01"]

    changed = bank.ne(bank.shift())
    regimes = bank.loc[changed]
    usd = spots["GBPUSD"].dropna()
    eur = spots["GBPEUR"].dropna()
    usd_dd, usd_when = _worst_drawdown(usd)
    eur_dd, eur_when = _worst_drawdown(eur)
    curve = (gilt10 - bank.reindex(gilt10.index)).dropna() * 100.0

    drawn = ledger["closing_drawn_gbp"]
    cover_num = ledger["net_operating_gbp"].tail(52).sum()
    cover_den = ledger["interest_gbp"].tail(52).sum()
    return {
        "date_min": bank.index.min().date().isoformat(),
        "date_max": bank.index.max().date().isoformat(),
        "n_bank_rate": int(bank.shape[0]),
        "n_sonia": int(sonia.shape[0]),
        "n_gilt10": int(gilt10.shape[0]),
        "bank_rate_min": _r(bank.min(), 4),
        "bank_rate_max": _r(bank.max(), 4),
        "bank_rate_last": _r(bank.iloc[-1], 4),
        "bank_rate_last_date": bank.index[-1].date().isoformat(),
        "bank_rate_mean": _r(bank.mean(), 4),
        "n_regimes": int(regimes.shape[0]),
        "current_regime_start": regimes.index[-1].date().isoformat(),
        "current_regime_rate": _r(regimes.iloc[-1], 4),
        "sonia_min": _r(sonia.min(), 4),
        "sonia_max": _r(sonia.max(), 4),
        "sonia_last": _r(sonia.iloc[-1], 4),
        "sonia_last_date": sonia.index[-1].date().isoformat(),
        "sonia_mean": _r(sonia.mean(), 4),
        "spread_bp_mean": _r(spread_bp.mean(), 2),
        "spread_bp_median": _r(spread_bp.median(), 2),
        "spread_bp_last": _r(spread_bp.iloc[-1], 2),
        "spread_bp_mean_since_2022": _r(recent.mean(), 2),
        "gilt10_min": _r(gilt10.min(), 4),
        "gilt10_max": _r(gilt10.max(), 4),
        "gilt10_last": _r(gilt10.iloc[-1], 4),
        "gilt10_last_date": gilt10.index[-1].date().isoformat(),
        "gilt10_vs_bank_rate_bp_last": _r(curve.iloc[-1], 2),
        "gilt10_vs_bank_rate_bp_min": _r(curve.min(), 2),
        "gilt10_vs_bank_rate_bp_min_date": curve.idxmin().date().isoformat(),
        "gbpusd_first": _r(usd.iloc[0], 4),
        "gbpusd_last": _r(usd.iloc[-1], 4),
        "gbpusd_min": _r(usd.min(), 4),
        "gbpusd_max": _r(usd.max(), 4),
        "gbpusd_change": _r(usd.iloc[-1] / usd.iloc[0] - 1.0, 4),
        "gbpusd_worst_drawdown": _r(usd_dd, 4),
        "gbpusd_worst_drawdown_date": usd_when,
        "gbpeur_first": _r(eur.iloc[0], 4),
        "gbpeur_last": _r(eur.iloc[-1], 4),
        "gbpeur_min": _r(eur.min(), 4),
        "gbpeur_max": _r(eur.max(), 4),
        "gbpeur_change": _r(eur.iloc[-1] / eur.iloc[0] - 1.0, 4),
        "gbpeur_worst_drawdown": _r(eur_dd, 4),
        "gbpeur_worst_drawdown_date": eur_when,
        "synthetic": _ledger_stats(ledger, drawn, cover_num, cover_den),
    }


def _worst_drawdown(series: pd.Series):
    peak = np.maximum.accumulate(series.to_numpy())
    drawdown = series.to_numpy() / peak - 1.0
    position = int(np.argmin(drawdown))
    when = series.index[position].date().isoformat()
    return float(drawdown[position]), when


def _ledger_stats(ledger, drawn, cover_num, cover_den) -> dict:
    limit = cfg.FACILITY_LIMIT_GBP
    return {
        "label": cfg.SYNTHETIC_LABEL,
        "n_weeks": int(len(ledger)),
        "start": ledger["week_ending"].iloc[0].date().isoformat(),
        "end": ledger["week_ending"].iloc[-1].date().isoformat(),
        "receipts_gbp": _r(ledger["receipts_gbp"].sum(), 2),
        "net_operating_gbp": _r(ledger["net_operating_gbp"].sum(), 2),
        "interest_gbp": _r(ledger["interest_gbp"].sum(), 2),
        "dividend_gbp": _r(ledger["dividend_gbp"].sum(), 2),
        "end_cash_gbp": _r(ledger["closing_cash_gbp"].iloc[-1], 2),
        "end_drawn_gbp": _r(drawn.iloc[-1], 2),
        "min_cash_gbp": _r(ledger["closing_cash_gbp"].min(), 2),
        "peak_drawn_gbp": _r(drawn.max(), 2),
        "peak_utilisation": _r(drawn.max() / limit, 4),
        "share_of_weeks_drawn": _r(float((drawn > 1.0).mean()), 4),
        "weeks_hard_cash_breach": int((ledger["closing_cash_gbp"] < cfg.HARD_MIN_CASH_GBP - 1.0).sum()),
        "weeks_soft_utilisation": int((drawn / limit > cfg.MAX_UTILISATION_SOFT).sum()),
        "interest_cover_last_52w": _r(cover_num / cover_den, 2) if cover_den else None,
    }


def _year_axis(axis):
    axis.xaxis.set_major_locator(mdates.YearLocator(2))
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))


def _plot_funding_rates(wide: pd.DataFrame) -> None:
    fig, axis = plt.subplots(figsize=(10.8, 5.4))
    axis.plot(wide.index, wide["IUDBEDR"], color=NAVY, lw=1.6, label="Bank Rate (IUDBEDR)")
    axis.plot(wide.index, wide["IUDSOIA"], color=RUST, lw=1.0, label="SONIA (IUDSOIA)")
    axis.plot(wide.index, wide["IUDMNPY"], color=GREEN, lw=1.0, label="10y gilt par yield (IUDMNPY)")
    axis.set_title("Bank Rate, SONIA and the 10-year gilt par yield")
    axis.set_ylabel("Percent per annum")
    axis.legend(loc="upper left")
    _year_axis(axis)
    save_fig(fig, "bank_rate_sonia_gilt10.png", MARKET_NOTE)


def _plot_curve(wide: pd.DataFrame) -> None:
    month_end = wide.resample("ME").last()
    slope_5s10s = (month_end["IUDMNPY"] - month_end["IUDSNPY"]) * 100.0
    long_gap = (month_end["IUDMNPY"] - month_end["IUDBEDR"]) * 100.0
    fig, axis = plt.subplots(figsize=(10.8, 5.4))
    axis.plot(slope_5s10s.index, slope_5s10s, color=TEAL, lw=1.3, label="10y − 5y par yield")
    axis.plot(long_gap.index, long_gap, color=NAVY, lw=1.3, label="10y par yield − Bank Rate")
    axis.axhline(0.0, color="#888888", lw=0.8)
    axis.set_title("Gilt curve slope and the gap to Bank Rate")
    axis.set_ylabel("Basis points")
    axis.legend(loc="best")
    _year_axis(axis)
    save_fig(fig, "yield_curve_slopes.png", MARKET_NOTE)


def _plot_spread(wide: pd.DataFrame) -> None:
    spread = (wide["IUDSOIA"] - wide["IUDBEDR"]) * 100.0
    monthly = spread.resample("MS").mean()
    fig, axis = plt.subplots(figsize=(10.8, 5.4))
    axis.plot(monthly.index, monthly, color=RUST, lw=1.4)
    axis.axhline(0.0, color="#888888", lw=0.8)
    axis.set_title("SONIA minus Bank Rate, monthly average")
    axis.set_ylabel("Basis points")
    _year_axis(axis)
    save_fig(fig, "sonia_bank_rate_spread.png", MARKET_NOTE)


def _plot_fx(spots: pd.DataFrame) -> None:
    fig, axis = plt.subplots(figsize=(10.8, 5.4))
    axis.plot(spots.index, spots["GBPUSD"], color=NAVY, lw=1.1, label="GBPUSD, USD per GBP (XUDLUSS)")
    axis.plot(spots.index, spots["GBPEUR"], color=RUST, lw=1.1, label="GBPEUR, EUR per GBP (XUDLERS)")
    axis.set_title("Sterling spot rates")
    axis.set_ylabel("Foreign currency per GBP")
    axis.legend(loc="best")
    _year_axis(axis)
    save_fig(fig, "fx_spot_rates.png", MARKET_NOTE)


def _plot_drawdowns(spots: pd.DataFrame) -> None:
    fig, axis = plt.subplots(figsize=(10.8, 5.4))
    for pair, color, label in (
        ("GBPUSD", NAVY, "GBPUSD"),
        ("GBPEUR", RUST, "GBPEUR"),
    ):
        series = spots[pair].dropna()
        peak = np.maximum.accumulate(series.to_numpy())
        drawdown = series.to_numpy() / peak - 1.0
        axis.plot(series.index, drawdown * 100.0, color=color, lw=1.1, label=label)
    axis.set_title("Drawdown of sterling from its running peak")
    axis.set_ylabel("Percent")
    axis.legend(loc="best")
    _year_axis(axis)
    save_fig(fig, "fx_drawdowns.png", MARKET_NOTE)


def _plot_ledger(ledger: pd.DataFrame) -> None:
    fig, axis = plt.subplots(figsize=(10.8, 5.4))
    axis.plot(
        ledger["week_ending"],
        ledger["closing_cash_gbp"] / 1e6,
        color=NAVY,
        lw=1.2,
        label="Closing cash",
    )
    axis.plot(
        ledger["week_ending"],
        ledger["closing_drawn_gbp"] / 1e6,
        color=RUST,
        lw=1.2,
        label="Facility drawn",
    )
    axis.axhline(cfg.MIN_CASH_POLICY_GBP / 1e6, color=GOLD, lw=0.8, ls="--", label="Policy minimum cash")
    axis.set_title("Synthetic example — Northvale cash and revolving credit facility")
    axis.set_ylabel("£ million")
    axis.legend(loc="best")
    _year_axis(axis)
    save_fig(fig, "synthetic_cash_and_facility.png", SYNTHETIC_NOTE)
