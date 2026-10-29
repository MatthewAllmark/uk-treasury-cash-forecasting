"""FX VaR on the fictional company's unhedged USD and EUR payables.

The open exposure is the next four contractual weeks of foreign-currency
purchases (about 20 business days), converted at spot. It is a payable stock:
sterling weakness raises its GBP value, and that increase is the loss.

Historical VaR is the empirical quantile of revaluation losses on a constant
foreign-currency notional. Parametric VaR is delta-normal and zero-mean:
loss ≈ −V_usd × r_usd − V_eur × r_eur, with r the log return of foreign-per-GBP,
scaled by sqrt(10) for the 10-day figure. The square-root rule assumes returns
are i.i.d., which FX volatility clustering violates; the 10-day historical VaR
does not use that rule.

The backtest is an unconditional-coverage (Kupiec) test. One-day VaR is rolled
forward with a 252-day window. Ten-day VaR is tested on non-overlapping blocks
so the hits are not stacked on the same move. A 99% test with a few expected
exceptions is a weak test; the hit count is the figure to read alongside the p-value.
"""

from __future__ import annotations

import math

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import chi2, norm

from analysis.common import NAVY, RED, RUST, SYNTHETIC_NOTE, apply_style, save_fig
from pipeline import config as cfg
from pipeline.cashflows import future_fridays, load_ledger_state, make_schedule


def kupiec_pof(hits: int, n: int, tail_probability: float) -> dict:
    """Kupiec proportion-of-failures likelihood-ratio test.

    Null: the exceedance rate equals `tail_probability`. The statistic is
    compared with a chi-square distribution on 1 degree of freedom.
    """
    if n <= 0:
        raise ValueError("Kupiec test needs at least one observation")
    hits = int(hits)
    rate = hits / n

    def log_likelihood(probability: float) -> float:
        if hits == 0:
            return n * math.log(1.0 - probability) if probability < 1.0 else -math.inf
        if hits == n:
            return n * math.log(probability) if probability > 0.0 else -math.inf
        return (n - hits) * math.log(1.0 - probability) + hits * math.log(probability)

    lr = max(-2.0 * (log_likelihood(tail_probability) - log_likelihood(rate)), 0.0)
    return {
        "hits": hits,
        "n": n,
        "expected_hits": round(tail_probability * n, 2),
        "hit_rate": round(rate, 6),
        "lr": round(lr, 4),
        "pvalue": round(float(chi2.sf(lr, 1)), 8),
        "reject_5pct": bool(chi2.sf(lr, 1) < 0.05),
    }


def _exposure(connection) -> dict:
    state = load_ledger_state(connection)
    weeks = future_fridays(state["last_week"], cfg.EXPOSURE_WEEKS)
    schedule = make_schedule(weeks, None)
    usd = float(schedule["usd_fc"].sum())
    eur = float(schedule["eur_fc"].sum())
    return {
        "state": state,
        "usd_fc": usd,
        "eur_fc": eur,
        "gbp_usd": usd / state["usd_per_gbp"],
        "gbp_eur": eur / state["eur_per_gbp"],
        "weeks": weeks,
    }


def _aligned_spots(connection) -> pd.DataFrame:
    fx = pd.read_sql_query("SELECT date, pair, foreign_per_gbp FROM fx", connection)
    wide = (
        fx.pivot(index="date", columns="pair", values="foreign_per_gbp")
        .dropna()
        .sort_index()
    )
    wide.index = pd.to_datetime(wide.index)
    return wide


def run_fx_risk(connection) -> dict:
    apply_style()
    exposure = _exposure(connection)
    spots = _aligned_spots(connection)
    usd = spots["GBPUSD"].to_numpy(dtype=float)
    eur = spots["GBPEUR"].to_numpy(dtype=float)
    dates = spots.index
    value = exposure["usd_fc"] / usd + exposure["eur_fc"] / eur
    loss_1d = np.diff(value)
    horizon = cfg.VAR_HORIZON_DAYS
    loss_10d = value[horizon:] - value[:-horizon]
    window = cfg.VAR_WINDOW

    r_usd = np.diff(np.log(usd))
    r_eur = np.diff(np.log(eur))
    v_usd = exposure["gbp_usd"]
    v_eur = exposure["gbp_eur"]
    linear = -v_usd * r_usd[-window:] - v_eur * r_eur[-window:]
    sigma = float(linear.std(ddof=1))
    z95 = float(norm.ppf(0.95))
    z99 = float(norm.ppf(0.99))

    current = {
        "hist_1d_95": float(np.quantile(loss_1d[-window:], 0.95, method="linear")),
        "hist_1d_99": float(np.quantile(loss_1d[-window:], 0.99, method="linear")),
        "hist_10d_95": float(np.quantile(loss_10d[-window:], 0.95, method="linear")),
        "hist_10d_99": float(np.quantile(loss_10d[-window:], 0.99, method="linear")),
        "param_1d_95": z95 * sigma,
        "param_1d_99": z99 * sigma,
        "param_10d_95": z95 * sigma * math.sqrt(horizon),
        "param_10d_99": z99 * sigma * math.sqrt(horizon),
    }

    backtest_1d = _backtest_1d(loss_1d, r_usd, r_eur, usd, eur, exposure, window)
    backtest_10d = _backtest_10d(value, loss_10d, r_usd, r_eur, usd, eur, exposure, window, horizon)
    _plot_backtest(dates, loss_1d, backtest_1d["hist_95_var"], window)
    _plot_vol(dates, r_usd, r_eur)

    current_rows = [
        {"measure": name, "var_gbp": round(amount, 2)}
        for name, amount in current.items()
    ]
    backtest_rows = []
    for horizon_name, block in (("1d", backtest_1d["tests"]), ("10d", backtest_10d)):
        for key, result in block.items():
            backtest_rows.append({"horizon": horizon_name, "test": key, **result})
    cfg.TABLE_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(current_rows).to_csv(cfg.TABLE_DIR / "var_current.csv", index=False)
    pd.DataFrame(backtest_rows).to_csv(cfg.TABLE_DIR / "var_backtest.csv", index=False)

    return {
        "exposure_definition": (
            f"Next {cfg.EXPOSURE_WEEKS} contractual weeks of unhedged USD and EUR purchases"
        ),
        "exposure_weeks": [week.isoformat() for week in exposure["weeks"]],
        "usd_notional": round(exposure["usd_fc"], 2),
        "eur_notional": round(exposure["eur_fc"], 2),
        "gbp_value_usd_payables": round(exposure["gbp_usd"], 2),
        "gbp_value_eur_payables": round(exposure["gbp_eur"], 2),
        "gbp_value_total": round(exposure["gbp_usd"] + exposure["gbp_eur"], 2),
        "spot_usd_per_gbp": round(exposure["state"]["usd_per_gbp"], 4),
        "spot_eur_per_gbp": round(exposure["state"]["eur_per_gbp"], 4),
        "window_losses": window,
        "window_end": dates[-1].date().isoformat(),
        "window_first_loss_end": dates[-window].date().isoformat(),
        "daily_sigma_gbp": round(sigma, 2),
        "current_var_gbp": {key: round(value, 2) for key, value in current.items()},
        "backtest_1d": backtest_1d["tests"],
        "backtest_10d_nonoverlapping": backtest_10d,
    }


def _backtest_1d(loss, r_usd, r_eur, usd, eur, exposure, window) -> dict:
    n = len(loss) - window
    hist_var = {0.95: np.empty(n), 0.99: np.empty(n)}
    param_var = {0.95: np.empty(n), 0.99: np.empty(n)}
    hits = {("hist", 0.95): 0, ("hist", 0.99): 0, ("param", 0.95): 0, ("param", 0.99): 0}
    z = {0.95: float(norm.ppf(0.95)), 0.99: float(norm.ppf(0.99))}
    for i, t in enumerate(range(window, len(loss))):
        sample = loss[t - window:t]
        v_usd = exposure["usd_fc"] / usd[t]
        v_eur = exposure["eur_fc"] / eur[t]
        sigma = np.std(
            -v_usd * r_usd[t - window:t] - v_eur * r_eur[t - window:t],
            ddof=1,
        )
        for probability in (0.95, 0.99):
            hv = float(np.quantile(sample, probability, method="linear"))
            pv = z[probability] * float(sigma)
            hist_var[probability][i] = hv
            param_var[probability][i] = pv
            if loss[t] > hv:
                hits[("hist", probability)] += 1
            if loss[t] > pv:
                hits[("param", probability)] += 1
    tests = {
        "historical_95": kupiec_pof(hits[("hist", 0.95)], n, 0.05),
        "historical_99": kupiec_pof(hits[("hist", 0.99)], n, 0.01),
        "parametric_95": kupiec_pof(hits[("param", 0.95)], n, 0.05),
        "parametric_99": kupiec_pof(hits[("param", 0.99)], n, 0.01),
    }
    return {"hist_95_var": hist_var[0.95], "param_95_var": param_var[0.95], "tests": tests}


def _backtest_10d(value, loss_10d, r_usd, r_eur, usd, eur, exposure, window, horizon) -> dict:
    """Non-overlapping 10-day blocks, each VaR estimated only on earlier moves."""
    hits = {("hist", 0.95): 0, ("hist", 0.99): 0, ("param", 0.95): 0, ("param", 0.99): 0}
    z = {0.95: float(norm.ppf(0.95)), 0.99: float(norm.ppf(0.99))}
    first = window + horizon - 1
    starts = range(first, len(value) - horizon, horizon)
    n = 0
    for start in starts:
        actual = value[start + horizon] - value[start]
        j0 = start - horizon - window + 1
        j1 = start - horizon + 1
        sample = loss_10d[j0:j1]
        if len(sample) != window:
            continue
        v_usd = exposure["usd_fc"] / usd[start]
        v_eur = exposure["eur_fc"] / eur[start]
        sigma = np.std(
            -v_usd * r_usd[start - window:start] - v_eur * r_eur[start - window:start],
            ddof=1,
        )
        n += 1
        for probability in (0.95, 0.99):
            hv = float(np.quantile(sample, probability, method="linear"))
            pv = z[probability] * float(sigma) * math.sqrt(horizon)
            if actual > hv:
                hits[("hist", probability)] += 1
            if actual > pv:
                hits[("param", probability)] += 1
    return {
        "historical_95": kupiec_pof(hits[("hist", 0.95)], n, 0.05),
        "historical_99": kupiec_pof(hits[("hist", 0.99)], n, 0.01),
        "parametric_95": kupiec_pof(hits[("param", 0.95)], n, 0.05),
        "parametric_99": kupiec_pof(hits[("param", 0.99)], n, 0.01),
    }


def _plot_backtest(dates, loss, hist_var_95, window) -> None:
    # Show the last two years of the 1-day historical 95% VaR. The Kupiec
    # counts in the tables use the full backtest, not this window.
    show = 504
    end_losses = loss[-show:]
    var_line = hist_var_95[-show:]
    loss_dates = dates[1:][-show:]
    exceed = end_losses > var_line
    fig, axis = plt.subplots(figsize=(10.8, 5.4))
    axis.plot(loss_dates, end_losses / 1e3, color="#8AA0B8", lw=0.7, label="Daily revaluation loss")
    axis.plot(loss_dates, var_line / 1e3, color=NAVY, lw=1.2, label="Rolling 252-day historical 95% VaR")
    axis.scatter(
        loss_dates[exceed],
        end_losses[exceed] / 1e3,
        color=RED,
        s=12,
        zorder=3,
        label="Exceedance",
    )
    axis.set_title("Synthetic example — 1-day FX VaR backtest, last two years shown")
    axis.set_ylabel("£ thousand")
    axis.legend(loc="best")
    save_fig(fig, "synthetic_var_backtest.png", SYNTHETIC_NOTE)


def _plot_vol(dates, r_usd, r_eur) -> None:
    index = dates[1:]
    usd_vol = pd.Series(r_usd, index=index).rolling(cfg.VOL_WINDOW).std(ddof=1) * math.sqrt(252)
    eur_vol = pd.Series(r_eur, index=index).rolling(cfg.VOL_WINDOW).std(ddof=1) * math.sqrt(252)
    fig, axis = plt.subplots(figsize=(10.8, 5.4))
    axis.plot(usd_vol.index, usd_vol * 100.0, color=NAVY, lw=1.1, label="GBPUSD")
    axis.plot(eur_vol.index, eur_vol * 100.0, color=RUST, lw=1.1, label="GBPEUR")
    axis.set_title(f"{cfg.VOL_WINDOW}-day realised volatility of sterling, annualised")
    axis.set_ylabel("Percent")
    axis.legend(loc="best")
    save_fig(
        fig,
        "fx_rolling_volatility.png",
        "Source: Bank of England spot rates. Volatility is the 63-day standard deviation, annualised with sqrt(252).",
    )
