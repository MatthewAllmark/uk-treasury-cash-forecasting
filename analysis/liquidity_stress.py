"""13-week Monte Carlo liquidity stress for the synthetic company.

Each path applies a joint weekly shock to SONIA, GBPUSD and GBPEUR. The
shocks are normal, zero-mean, and correlated by the Cholesky factor of the
sample covariance of the last three years of Friday-to-Friday changes. The
historical mean drift is not added back: a three-year window that contains a
cutting cycle would otherwise keep pushing SONIA in that direction.

On top of the market shocks, contractual receipts are delayed with fixed
scenario probabilities (see pipeline.config). Delays are timing, not bad
debt. Cash still in transit at week 13 is reported separately so the horizon
cutoff is visible.

Liquidity-at-risk (95%) is the 5th percentile of the lowest closing cash on
each path. Facility-at-risk (95%) is the 95th percentile of the highest drawing.
A policy breach is a week in which the facility limit binds and cash finishes
more than £1 below the policy minimum.
"""

from __future__ import annotations

import sqlite3

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.common import GOLD, NAVY, RED, RUST, SYNTHETIC_NOTE, TEAL, apply_style, save_fig
from pipeline import config as cfg
from pipeline.cashflows import future_fridays, load_ledger_state, make_schedule, roll_ledger


def _covariance(connection) -> dict:
    frame = pd.read_sql_query(
        """
        SELECT week_ending, sonia_pct, usd_per_gbp, eur_per_gbp
        FROM cash_flows
        ORDER BY week_ending
        """,
        connection,
    )
    frame["d_sonia"] = frame["sonia_pct"].diff()
    frame["r_usd"] = np.log(frame["usd_per_gbp"]).diff()
    frame["r_eur"] = np.log(frame["eur_per_gbp"]).diff()
    changes = frame.dropna(subset=["d_sonia", "r_usd", "r_eur"]).tail(cfg.MC_COV_WEEKS)
    if len(changes) < 52:
        raise RuntimeError("Not enough weekly history to estimate a covariance")
    matrix = changes[["d_sonia", "r_usd", "r_eur"]].to_numpy(dtype=float)
    cov = np.cov(matrix, rowvar=False, ddof=1)
    jitter = 0.0
    try:
        cholesky = np.linalg.cholesky(cov)
    except np.linalg.LinAlgError:
        jitter = 1e-12
        cholesky = np.linalg.cholesky(cov + jitter * np.eye(3))
    std = np.sqrt(np.diag(cov))
    corr = cov / np.outer(std, std)
    return {
        "cholesky": cholesky,
        "cov": cov,
        "std": std,
        "corr": corr,
        "jitter": jitter,
        "mean_d_sonia": float(changes["d_sonia"].mean()),
        "start": str(changes["week_ending"].iloc[0])[:10],
        "end": str(changes["week_ending"].iloc[-1])[:10],
        "n": int(len(changes)),
    }


def run_liquidity_stress(
    connection,
    n_paths: int | None = None,
    seed: int | None = None,
    horizon_weeks: int | None = None,
    zero_shocks: bool = False,
    write_outputs: bool = False,
) -> dict:
    n_paths = cfg.MC_PATHS if n_paths is None else n_paths
    seed = cfg.MC_SEED if seed is None else seed
    horizon_weeks = cfg.MC_WEEKS if horizon_weeks is None else horizon_weeks

    state = load_ledger_state(connection)
    weeks = future_fridays(state["last_week"], horizon_weeks)
    schedule = make_schedule(weeks, None)
    market = _covariance(connection)

    rng = np.random.default_rng(seed)
    if zero_shocks:
        shocks = np.zeros((n_paths, horizon_weeks, 3))
        delay_u = np.ones((n_paths, horizon_weeks))
    else:
        draws = rng.standard_normal((n_paths, horizon_weeks, 3))
        shocks = draws @ market["cholesky"].T
        delay_u = rng.random((n_paths, horizon_weeks))

    sonia = np.empty((n_paths, horizon_weeks))
    usd = np.empty((n_paths, horizon_weeks))
    eur = np.empty((n_paths, horizon_weeks))
    level_s = np.full(n_paths, state["sonia"])
    level_u = np.full(n_paths, state["usd_per_gbp"])
    level_e = np.full(n_paths, state["eur_per_gbp"])
    for t in range(horizon_weeks):
        level_s = np.maximum(level_s + shocks[:, t, 0], 0.0)
        level_u = np.maximum(level_u * np.exp(shocks[:, t, 1]), 0.05)
        level_e = np.maximum(level_e * np.exp(shocks[:, t, 2]), 0.05)
        sonia[:, t] = level_s
        usd[:, t] = level_u
        eur[:, t] = level_e

    posted = roll_ledger(
        schedule,
        sonia=sonia,
        usd_per_gbp=usd,
        eur_per_gbp=eur,
        opening_cash=state["cash"],
        opening_drawn=state["drawn"],
        delay_u=delay_u,
    )
    min_cash = posted["closing_cash"].min(axis=1)
    peak_drawn = posted["closing_drawn"].max(axis=1)
    terminal = posted["closing_cash"][:, -1]
    terminal_drawn = posted["closing_drawn"][:, -1]
    interest = posted["interest"].sum(axis=1)
    tolerance = 1.0
    p5_min_cash = float(np.quantile(min_cash, 0.05, method="linear"))
    summary = {
        "label": cfg.SYNTHETIC_LABEL,
        "n_paths": int(n_paths),
        "seed": int(seed),
        "horizon_weeks": int(horizon_weeks),
        "horizon_end": weeks[-1].isoformat(),
        "zero_shocks": bool(zero_shocks),
        "covariance_weeks": market["n"],
        "covariance_start": market["start"],
        "covariance_end": market["end"],
        "cholesky_jitter": market["jitter"],
        "weekly_std_dsonia_pp": round(float(market["std"][0]), 4),
        "weekly_std_gbpusd_log": round(float(market["std"][1]), 6),
        "weekly_std_gbpeur_log": round(float(market["std"][2]), 6),
        "corr_dsonia_gbpusd": round(float(market["corr"][0, 1]), 4),
        "corr_dsonia_gbpeur": round(float(market["corr"][0, 2]), 4),
        "corr_gbpusd_gbpeur": round(float(market["corr"][1, 2]), 4),
        "mean_weekly_dsonia_not_applied_pp": round(market["mean_d_sonia"], 4),
        "p_policy_breach": round(float(np.mean(min_cash < cfg.MIN_CASH_POLICY_GBP - tolerance)), 6),
        "p_hard_min_breach": round(float(np.mean(min_cash < cfg.HARD_MIN_CASH_GBP - tolerance)), 6),
        "p_negative_cash": round(float(np.mean(min_cash < -tolerance)), 6),
        "p_facility_limit": round(float(np.mean(peak_drawn >= cfg.FACILITY_LIMIT_GBP - tolerance)), 6),
        "liquidity_at_risk_95_min_cash_gbp": round(p5_min_cash, 2),
        "shortfall_vs_policy_at_95_gbp": round(max(0.0, cfg.MIN_CASH_POLICY_GBP - p5_min_cash), 2),
        "p50_min_cash_gbp": round(float(np.quantile(min_cash, 0.50, method="linear")), 2),
        "p5_terminal_cash_gbp": round(float(np.quantile(terminal, 0.05, method="linear")), 2),
        "p50_terminal_cash_gbp": round(float(np.quantile(terminal, 0.50, method="linear")), 2),
        "facility_at_risk_95_peak_drawn_gbp": round(float(np.quantile(peak_drawn, 0.95, method="linear")), 2),
        "undrawn_headroom_at_95_gbp": round(
            cfg.FACILITY_LIMIT_GBP - float(np.quantile(peak_drawn, 0.95, method="linear")), 2
        ),
        "p50_peak_drawn_gbp": round(float(np.quantile(peak_drawn, 0.50, method="linear")), 2),
        "p50_terminal_drawn_gbp": round(float(np.quantile(terminal_drawn, 0.50, method="linear")), 2),
        "p95_terminal_drawn_gbp": round(float(np.quantile(terminal_drawn, 0.95, method="linear")), 2),
        "p50_interest_gbp": round(float(np.quantile(interest, 0.50, method="linear")), 2),
        "p95_interest_gbp": round(float(np.quantile(interest, 0.95, method="linear")), 2),
        "mean_receipts_in_transit_gbp": round(float(posted["in_transit"].mean()), 2),
    }
    if write_outputs:
        _write_outputs(weeks, posted, min_cash, summary)
    return {
        "min_cash": min_cash,
        "peak_drawn": peak_drawn,
        "closing_cash": posted["closing_cash"],
        "summary": summary,
    }


def _write_outputs(weeks, posted, min_cash, summary) -> None:
    apply_style()
    cash = posted["closing_cash"]
    drawn = posted["closing_drawn"]
    percentiles = (5, 25, 50, 75, 95)
    rows = []
    cash_q = {}
    drawn_q = {}
    for p in percentiles:
        cash_q[p] = np.quantile(cash, p / 100.0, axis=0, method="linear")
        drawn_q[p] = np.quantile(drawn, p / 100.0, axis=0, method="linear")
        for i, week in enumerate(weeks):
            rows.append({
                "week_ending": week.isoformat(),
                "percentile": p,
                "closing_cash_gbp": round(float(cash_q[p][i]), 2),
                "closing_drawn_gbp": round(float(drawn_q[p][i]), 2),
            })
    cfg.TABLE_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(cfg.TABLE_DIR / "synthetic_mc_weekly_percentiles.csv", index=False)
    pd.DataFrame([summary]).to_csv(cfg.TABLE_DIR / "synthetic_mc_summary.csv", index=False)

    fig, axes = plt.subplots(2, 1, figsize=(10.8, 7.2), sharex=True)
    _fan(axes[0], weeks, cash_q, "Closing cash, £ million", 1e6)
    axes[0].axhline(cfg.MIN_CASH_POLICY_GBP / 1e6, color=GOLD, lw=0.8, ls="--", label="Policy minimum")
    axes[0].set_title("Synthetic example — 13-week cash fan, 10,000 paths")
    axes[0].legend(loc="best")
    _fan(axes[1], weeks, drawn_q, "Facility drawn, £ million", 1e6)
    axes[1].axhline(cfg.FACILITY_LIMIT_GBP / 1e6, color=RED, lw=0.8, ls="--", label="Facility limit")
    axes[1].set_title("Synthetic example — facility drawing under the same paths")
    axes[1].legend(loc="best")
    fig.autofmt_xdate()
    save_fig(fig, "synthetic_mc_liquidity_fan.png", SYNTHETIC_NOTE)

    fig, axis = plt.subplots(figsize=(10.8, 5.4))
    axis.hist(min_cash / 1e6, bins=40, color=NAVY, alpha=0.9)
    axis.axvline(summary["liquidity_at_risk_95_min_cash_gbp"] / 1e6, color=RUST, lw=1.4, label="95% liquidity-at-risk")
    axis.axvline(cfg.MIN_CASH_POLICY_GBP / 1e6, color=GOLD, lw=1.0, ls="--", label="Policy minimum")
    axis.axvline(cfg.HARD_MIN_CASH_GBP / 1e6, color=RED, lw=1.0, ls=":", label="Hard minimum")
    axis.set_title("Synthetic example — distribution of the lowest cash balance over 13 weeks")
    axis.set_xlabel("Minimum closing cash, £ million")
    axis.set_ylabel("Paths")
    axis.legend(loc="best")
    save_fig(fig, "synthetic_mc_min_cash.png", SYNTHETIC_NOTE)


def _fan(axis, weeks, quantiles, ylabel, scale) -> None:
    axis.fill_between(weeks, quantiles[5] / scale, quantiles[95] / scale, color=TEAL, alpha=0.25, label="5th–95th")
    axis.fill_between(weeks, quantiles[25] / scale, quantiles[75] / scale, color=NAVY, alpha=0.35, label="25th–75th")
    axis.plot(weeks, quantiles[50] / scale, color=NAVY, lw=1.6, label="Median")
    axis.set_ylabel(ylabel)


def main() -> None:
    connection = sqlite3.connect(cfg.DB_PATH)
    try:
        result = run_liquidity_stress(connection, write_outputs=True)
    finally:
        connection.close()
    print(result["summary"])


if __name__ == "__main__":
    main()
