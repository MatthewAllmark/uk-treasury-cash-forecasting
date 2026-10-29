"""SONIA forecast: a small ARIMA grid, a 12-month backtest, and parallel shocks.

The model is fit to the monthly average of daily SONIA. Order (p, d, q) is
chosen by AIC on the sample that excludes the last 12 months, with p and q
in 0..2 and d in 0..1. A differenced model is fit with no constant, so the
2010–2024 hiking cycle does not become a permanent drift. A model in levels
keeps a constant so it can have a mean away from zero.

Parallel ±100 bp and ±200 bp scenarios are applied to the latest daily fixing
and held flat. They are decision scenarios, not confidence intervals of the ARIMA.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA

from analysis.common import GOLD, GREEN, MARKET_NOTE, NAVY, RED, RUST, TEAL, apply_style, save_fig
from pipeline import config as cfg
from pipeline.cashflows import future_fridays, load_ledger_state


def _monthly_sonia(connection) -> tuple[pd.Series, int]:
    frame = pd.read_sql_query(
        "SELECT date, value_pct FROM rates WHERE series_code = 'IUDSOIA' ORDER BY date",
        connection,
    )
    frame["date"] = pd.to_datetime(frame["date"])
    series = frame.set_index("date")["value_pct"].astype(float).sort_index()
    means = series.resample("MS").mean()
    counts = series.resample("MS").count()
    if means.isna().any():
        raise RuntimeError("Monthly SONIA has a gap; refusing to interpolate it")
    kept = means[counts >= 15]
    dropped = int((counts < 15).sum())
    return kept, dropped


def _fit(sample: np.ndarray, order: tuple[int, int, int]):
    trend = "n" if order[1] > 0 else "c"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ARIMA(sample, order=order, trend=trend).fit(method_kwargs={"maxiter": 300})


def _select_order(train: np.ndarray) -> tuple[tuple[int, int, int], float, int, int]:
    best_order = None
    best_aic = np.inf
    failed = 0
    tried = 0
    for p in range(3):
        for d in range(2):
            for q in range(3):
                if p == 0 and d == 0 and q == 0:
                    continue
                tried += 1
                order = (p, d, q)
                try:
                    result = _fit(train, order)
                    aic = float(result.aic)
                except Exception:
                    failed += 1
                    continue
                if not np.isfinite(aic):
                    failed += 1
                    continue
                rank = (aic, p + d + q, p, q, d)
                best_rank = (
                    (best_aic, sum(best_order), best_order[0], best_order[2], best_order[1])
                    if best_order is not None else None
                )
                if best_rank is None or rank < best_rank:
                    best_order = order
                    best_aic = aic
    if best_order is None:
        raise RuntimeError("Every ARIMA specification failed on the SONIA training sample")
    return best_order, best_aic, tried, failed


def _errors(actual: np.ndarray, predicted: np.ndarray) -> dict:
    error = predicted - actual
    mae = float(np.mean(np.abs(error)))
    rmse = float(np.sqrt(np.mean(error ** 2)))
    mask = np.abs(actual) >= 0.05
    mape = float(np.mean(np.abs(error[mask] / actual[mask])) * 100.0) if mask.any() else None
    return {
        "n": int(len(actual)),
        "mae_pp": round(mae, 4),
        "rmse_pp": round(rmse, 4),
        "mae_bp": round(mae * 100.0, 2),
        "rmse_bp": round(rmse * 100.0, 2),
        "mape_pct": None if mape is None else round(mape, 2),
        "actual_mean": round(float(np.mean(actual)), 4),
        "predicted_mean": round(float(np.mean(predicted)), 4),
        "actual_end": round(float(actual[-1]), 4),
        "predicted_end": round(float(predicted[-1]), 4),
    }


def _one_step(values: np.ndarray, order, n_steps: int = 24) -> np.ndarray:
    predicted = np.empty(n_steps)
    start = len(values) - n_steps
    for i in range(n_steps):
        result = _fit(values[: start + i], order)
        predicted[i] = float(np.asarray(result.forecast(1), dtype=float).ravel()[0])
    return predicted


def weekly_arima_path(weeks, last_month: pd.Timestamp, last_daily: float, monthly_forecast: pd.Series):
    """Map the monthly ARIMA path onto Friday weeks.

    Weeks inside the last observed month use the latest daily fixing, because
    the model is only asked for months after that observation. Later weeks
    take the forecast for their calendar month.
    """
    lookup = {idx.strftime("%Y-%m"): float(value) for idx, value in monthly_forecast.items()}
    last_key = last_month.strftime("%Y-%m")
    last_forecast = float(monthly_forecast.iloc[-1])
    path = []
    for week in weeks:
        key = week.strftime("%Y-%m")
        if key <= last_key:
            path.append(last_daily)
        else:
            path.append(lookup.get(key, last_forecast))
    return np.asarray(path, dtype=float)


def run_rate_forecast(connection) -> dict:
    apply_style()
    monthly, dropped_months = _monthly_sonia(connection)
    values = monthly.to_numpy(dtype=float)
    if len(values) <= 36:
        raise RuntimeError("Not enough monthly SONIA observations to backtest")

    train = values[:-12]
    holdout = values[-12:]
    order, aic, tried, failed = _select_order(train)
    print(f"SONIA ARIMA{order} selected on training AIC {aic:.1f} ({failed} of {tried} orders failed)")

    holdout_fit = _fit(train, order)
    multi_step = np.asarray(holdout_fit.forecast(12), dtype=float).ravel()
    one_step = _one_step(values, order, 24)
    forward_fit = _fit(values, order)
    forward = np.asarray(forward_fit.forecast(13), dtype=float).ravel()
    forward_index = pd.date_range(
        monthly.index[-1] + pd.DateOffset(months=1), periods=13, freq="MS"
    )
    forward_series = pd.Series(forward, index=forward_index)

    state = load_ledger_state(connection)
    weeks = future_fridays(state["last_week"], 52)
    weekly = weekly_arima_path(weeks, monthly.index[-1], state["sonia"], forward_series)

    multi_errors = _errors(holdout, multi_step)
    one_errors = _errors(values[-24:], one_step)
    holdout_index = monthly.index[-12:]
    episode_origin = pd.Timestamp("2021-12-01")
    episode_pos = int(monthly.index.get_loc(episode_origin))
    episode_actual = values[episode_pos + 1: episode_pos + 13]
    episode_index = monthly.index[episode_pos + 1: episode_pos + 13]
    episode_fit = _fit(values[: episode_pos + 1], order)
    episode_forecast = np.asarray(episode_fit.forecast(12), dtype=float).ravel()
    episode_errors = _errors(episode_actual, episode_forecast)

    holdout_frame = pd.DataFrame({
        "month": holdout_index.strftime("%Y-%m"),
        "actual_sonia": np.round(holdout, 4),
        "multistep_forecast": np.round(multi_step, 4),
    })
    forward_frame = pd.DataFrame({
        "month": forward_index.strftime("%Y-%m"),
        "arima_sonia": np.round(forward, 4),
    })
    cfg.TABLE_DIR.mkdir(parents=True, exist_ok=True)
    holdout_frame.to_csv(cfg.TABLE_DIR / "sonia_forecast_holdout.csv", index=False)
    forward_frame.to_csv(cfg.TABLE_DIR / "sonia_forecast_forward.csv", index=False)
    pd.DataFrame({
        "week_ending": [week.isoformat() for week in weeks],
        "arima_sonia_pct": np.round(weekly, 4),
    }).to_csv(cfg.TABLE_DIR / "sonia_forecast_weekly.csv", index=False)

    episode_frame = pd.DataFrame({
        "month": episode_index.strftime("%Y-%m"),
        "actual_sonia": np.round(episode_actual, 4),
        "forecast_from_2021_12": np.round(episode_forecast, 4),
    })
    episode_frame.to_csv(cfg.TABLE_DIR / "sonia_forecast_2022_episode.csv", index=False)
    _plot(
        monthly, holdout_index, multi_step, forward_series, state["sonia"],
        episode_index, episode_forecast, order,
    )

    shocks = {}
    for shock in cfg.SONIA_SHOCKS_BP:
        shocks[cfg.shock_name(shock)] = round(max(state["sonia"] + shock / 100.0, 0.0), 4)

    return {
        "weekly_sonia": weekly,
        "findings": {
            "frequency": "monthly average of daily SONIA",
            "n_months": int(len(monthly)),
            "months_dropped_under_15_days": dropped_months,
            "sample_start": monthly.index[0].strftime("%Y-%m"),
            "sample_end": monthly.index[-1].strftime("%Y-%m"),
            "order": list(order),
            "trend": "n" if order[1] > 0 else "c",
            "selection_aic": round(float(aic), 2),
            "refit_aic": round(float(forward_fit.aic), 2),
            "orders_tried": tried,
            "orders_failed": failed,
            "holdout_start": holdout_index[0].strftime("%Y-%m"),
            "holdout_end": holdout_index[-1].strftime("%Y-%m"),
            "multistep_12m": multi_errors,
            "onestep_24m": one_errors,
            "hiking_cycle_episode": {
                "train_end": "2021-12",
                "forecast_start": episode_index[0].strftime("%Y-%m"),
                "forecast_end": episode_index[-1].strftime("%Y-%m"),
                "order_note": (
                    "Coefficients are fit on data through December 2021. "
                    "The order is the one selected on the later training sample, "
                    "so this episode illustrates the path and is not a pure real-time selection."
                ),
                **episode_errors,
            },
            "forward_month_end": forward_index[-1].strftime("%Y-%m"),
            "forward_end_sonia": round(float(forward[-1]), 4),
            "parallel_shocks_pct": shocks,
            "jump_off_daily_sonia": round(state["sonia"], 4),
        },
    }


def _plot(monthly, holdout_index, multi_step, forward_series, last_daily: float,
          episode_index, episode_forecast, order) -> None:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, figsize=(10.8, 7.4))
    recent = monthly[monthly.index >= "2016-01-01"]
    axes[0].plot(recent.index, recent, color=NAVY, lw=1.4, label="Monthly average SONIA")
    axes[0].plot(holdout_index, multi_step, color=RUST, lw=1.6, label="12-month forecast from a year earlier")
    axes[0].plot(
        episode_index, episode_forecast, color=TEAL, lw=1.6, ls="--",
        label=f"ARIMA{order} projected from Dec 2021",
    )
    axes[0].axvline(holdout_index[0], color="#888888", lw=0.8, ls="--")
    axes[0].set_title("SONIA backtest: multi-step ARIMA versus the following year")
    axes[0].set_ylabel("Percent")
    axes[0].legend(loc="best")

    tail = monthly[monthly.index >= "2022-01-01"]
    axes[1].plot(tail.index, tail, color=NAVY, lw=1.4, label="Monthly average SONIA")
    axes[1].plot(forward_series.index, forward_series, color=RUST, lw=1.6, label="ARIMA, next 13 months")
    for shock, color, text in (
        (-200, TEAL, "−200 bp"),
        (-100, GREEN, "−100 bp"),
        (100, GOLD, "+100 bp"),
        (200, RED, "+200 bp"),
    ):
        level = max(last_daily + shock / 100.0, 0.0)
        axes[1].axhline(level, color=color, lw=0.8, ls=":", label=f"Latest daily {text}")
    axes[1].set_title("Forward ARIMA path and parallel shocks to the latest daily fixing")
    axes[1].set_ylabel("Percent")
    axes[1].legend(loc="best", fontsize=8, ncol=2)
    save_fig(fig, "sonia_forecast_backtest.png", MARKET_NOTE)
