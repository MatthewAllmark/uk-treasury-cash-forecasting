"""13-week and 12-month cash forecast for the synthetic company.

The operating schedule is the expected seasonal path (noise multiplier 1).
FX is held at the latest fixing: this forecast does not embed an FX view.
Funding is the latest daily SONIA, shifted in parallel by 0, ±100 and ±200 bp,
plus an optional weekly path from the SONIA model. Interest follows the same
Actual/365 RCF rule as the historical ledger.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.common import GOLD, GREEN, NAVY, RUST, SYNTHETIC_NOTE, TEAL, apply_style, save_fig
from pipeline import config as cfg
from pipeline.cashflows import future_fridays, load_ledger_state, make_schedule, roll_ledger

SCENARIO_COLOURS = {
    "minus_200bp": TEAL,
    "minus_100bp": GREEN,
    "base": NAVY,
    "plus_100bp": GOLD,
    "plus_200bp": RUST,
    "arima": "#6B4C9A",
}


def project(connection, n_weeks: int, sonia_path: np.ndarray):
    """Post one deterministic path. `sonia_path` is percent, length n_weeks."""
    state = load_ledger_state(connection)
    weeks = future_fridays(state["last_week"], n_weeks)
    if len(sonia_path) != n_weeks:
        raise ValueError("SONIA path length does not match the forecast horizon")
    schedule = make_schedule(weeks, None)
    posted = roll_ledger(
        schedule,
        sonia=np.asarray(sonia_path, dtype=float).reshape(1, n_weeks),
        usd_per_gbp=np.full((1, n_weeks), state["usd_per_gbp"]),
        eur_per_gbp=np.full((1, n_weeks), state["eur_per_gbp"]),
        opening_cash=state["cash"],
        opening_drawn=state["drawn"],
        delay_u=None,
    )
    return state, weeks, posted


def _summarise(name: str, sonia_note: str, posted, weeks) -> dict:
    interest = posted["interest"][0]
    cash = posted["closing_cash"][0]
    drawn = posted["closing_drawn"][0]
    def pack(n):
        return {
            "interest_gbp": round(float(interest[:n].sum()), 2),
            "end_cash_gbp": round(float(cash[n - 1]), 2),
            "end_drawn_gbp": round(float(drawn[n - 1]), 2),
            "min_cash_gbp": round(float(cash[:n].min()), 2),
            "peak_drawn_gbp": round(float(drawn[:n].max()), 2),
        }
    return {
        "scenario": name,
        "sonia": sonia_note,
        "week_13_ending": weeks[12].isoformat(),
        "week_52_ending": weeks[-1].isoformat(),
        "horizon_13w": pack(13),
        "horizon_52w": pack(len(weeks)),
    }


def run_cash_forecast(connection, arima_weekly: np.ndarray | None = None) -> dict:
    apply_style()
    n_weeks = 52
    state = load_ledger_state(connection)
    weeks = future_fridays(state["last_week"], n_weeks)
    paths = {}
    summaries = []
    weekly_rows = []

    for shock in cfg.SONIA_SHOCKS_BP:
        name = cfg.shock_name(shock)
        rate = max(state["sonia"] + shock / 100.0, 0.0)
        _, _, posted = project(connection, n_weeks, np.full(n_weeks, rate))
        paths[name] = posted
        summaries.append(_summarise(name, f"{rate:.4f}% flat", posted, weeks))
        _append_weekly(weekly_rows, name, weeks, posted)

    if arima_weekly is not None:
        _, _, posted = project(connection, n_weeks, np.asarray(arima_weekly, dtype=float))
        paths["arima"] = posted
        summaries.append(_summarise("arima", "monthly ARIMA path, held flat within each month", posted, weeks))
        _append_weekly(weekly_rows, "arima", weeks, posted)

    frame = pd.DataFrame([
        {
            "scenario": item["scenario"],
            "sonia": item["sonia"],
            **{f"w13_{key}": value for key, value in item["horizon_13w"].items()},
            **{f"w52_{key}": value for key, value in item["horizon_52w"].items()},
        }
        for item in summaries
    ])
    cfg.TABLE_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(cfg.TABLE_DIR / "synthetic_cash_forecast_summary.csv", index=False)
    pd.DataFrame(weekly_rows).to_csv(
        cfg.TABLE_DIR / "synthetic_cash_forecast_weekly.csv", index=False
    )
    _plot_13w(weeks, paths)
    _plot_12m(weeks, paths, summaries)
    return {
        "origin_week": state["last_week"].isoformat(),
        "jump_off_sonia_pct": round(state["sonia"], 4),
        "fx_held_at_usd_per_gbp": round(state["usd_per_gbp"], 4),
        "fx_held_at_eur_per_gbp": round(state["eur_per_gbp"], 4),
        "opening_cash_gbp": round(state["cash"], 2),
        "opening_drawn_gbp": round(state["drawn"], 2),
        "scenarios": summaries,
    }


def _append_weekly(rows, name, weeks, posted) -> None:
    interest = posted["interest"][0]
    cumulative = np.cumsum(interest)
    for i, week in enumerate(weeks):
        rows.append({
            "example_label": cfg.SYNTHETIC_LABEL,
            "scenario": name,
            "week_ending": week.isoformat(),
            "closing_cash_gbp": round(float(posted["closing_cash"][0, i]), 2),
            "closing_drawn_gbp": round(float(posted["closing_drawn"][0, i]), 2),
            "interest_gbp": round(float(interest[i]), 2),
            "cumulative_interest_gbp": round(float(cumulative[i]), 2),
        })


def _plot_13w(weeks, paths) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(10.8, 7.2), sharex=True)
    horizon = weeks[:13]
    # At this horizon the ±200 bp cash paths sit on top of the base path, so the
    # cash panel shows the base case once. The interest panel carries the shocks.
    axes[0].plot(
        horizon,
        paths["base"]["closing_cash"][0, :13] / 1e6,
        color=NAVY,
        lw=1.8,
        label="Base case",
    )
    axes[0].axhline(cfg.MIN_CASH_POLICY_GBP / 1e6, color=GOLD, lw=0.8, ls="--", label="Policy minimum")
    for name in ("minus_200bp", "minus_100bp", "base", "plus_100bp", "plus_200bp"):
        cumulative = np.cumsum(paths[name]["interest"][0, :13])
        axes[1].plot(
            horizon,
            cumulative / 1e3,
            color=SCENARIO_COLOURS[name],
            lw=1.4,
            label=name.replace("_", " "),
        )
    axes[0].set_title("Synthetic example — 13-week cash forecast")
    axes[0].set_ylabel("Closing cash, £ million")
    axes[0].legend(loc="best", ncol=3)
    axes[1].set_title("Cumulative RCF interest under parallel SONIA shocks")
    axes[1].set_ylabel("£ thousand")
    axes[1].legend(loc="best", ncol=3)
    fig.autofmt_xdate()
    save_fig(fig, "synthetic_forecast_13w.png", SYNTHETIC_NOTE)


def _plot_12m(weeks, paths, summaries) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 5.2))
    axes[0].plot(weeks, paths["base"]["closing_cash"][0] / 1e6, color=NAVY, lw=1.5, label="Closing cash")
    axes[0].plot(weeks, paths["base"]["closing_drawn"][0] / 1e6, color=RUST, lw=1.5, label="Drawn")
    axes[0].set_title("Base case, next 52 weeks")
    axes[0].set_ylabel("£ million")
    axes[0].legend(loc="best")
    labels = [item["scenario"].replace("_", " ") for item in summaries]
    values = [item["horizon_52w"]["interest_gbp"] / 1e3 for item in summaries]
    colours = [SCENARIO_COLOURS.get(item["scenario"], NAVY) for item in summaries]
    axes[1].bar(labels, values, color=colours)
    axes[1].set_title("12-month interest by SONIA scenario")
    axes[1].set_ylabel("£ thousand")
    axes[1].tick_params(axis="x", rotation=40)
    fig.autofmt_xdate()
    save_fig(fig, "synthetic_forecast_12m.png", SYNTHETIC_NOTE)
