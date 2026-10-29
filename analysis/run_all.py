"""Run every analytical step and write key_findings.json.

Figures in the README are taken from that file, which this command produces.
"""

from __future__ import annotations

import json
import sqlite3

import numpy as np
import pandas as pd

from analysis.cash_forecast import run_cash_forecast
from analysis.fx_risk import run_fx_risk
from analysis.liquidity_stress import run_liquidity_stress
from analysis.market import write_market
from analysis.rate_forecast import run_rate_forecast
from pipeline import config as cfg


def _clean(value):
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, np.ndarray):
        raise TypeError("A numpy array was passed into the findings file")
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.integer):
        return int(value)
    return value


def _assumptions() -> dict:
    return {
        "company": cfg.COMPANY_NAME,
        "label": cfg.SYNTHETIC_LABEL,
        "seed": cfg.SEED,
        "history_start": cfg.HISTORY_START.isoformat(),
        "base_weekly_receipts_gbp": cfg.BASE_RECEIPTS_GBP,
        "base_weekly_usd_costs": cfg.BASE_USD_COSTS,
        "base_weekly_eur_costs": cfg.BASE_EUR_COSTS,
        "facility_limit_gbp": cfg.FACILITY_LIMIT_GBP,
        "margin_bp": round(cfg.MARGIN * 10_000, 2),
        "min_cash_policy_gbp": cfg.MIN_CASH_POLICY_GBP,
        "hard_min_cash_gbp": cfg.HARD_MIN_CASH_GBP,
        "opening_cash_gbp": cfg.OPENING_CASH_GBP,
        "opening_drawn_gbp": cfg.OPENING_DRAWN_GBP,
        "surplus_cap_gbp": cfg.SURPLUS_CAP_GBP,
        "day_count": "simple Actual/365 on the opening drawn balance, 7/365",
        "interest_cover_example": cfg.MIN_INTEREST_COVER,
        "soft_utilisation_example": cfg.MAX_UTILISATION_SOFT,
    }


def _headline(findings: dict) -> list[dict]:
    market = findings["market"]
    company = market["synthetic"]
    rates = findings["rate_forecast"]
    var = findings["fx_var"]["current_var_gbp"]
    mc = findings["monte_carlo"]
    rows = [
        ("bank_rate_last_pct", market["bank_rate_last"], "percent"),
        ("bank_rate_min_pct", market["bank_rate_min"], "percent"),
        ("bank_rate_max_pct", market["bank_rate_max"], "percent"),
        ("n_bank_rate_regimes", market["n_regimes"], "count"),
        ("sonia_last_pct", market["sonia_last"], "percent"),
        ("sonia_mean_pct", market["sonia_mean"], "percent"),
        ("sonia_bank_rate_spread_mean_bp", market["spread_bp_mean"], "bp"),
        ("gilt10_last_pct", market["gilt10_last"], "percent"),
        ("gilt10_vs_bank_rate_last_bp", market["gilt10_vs_bank_rate_bp_last"], "bp"),
        ("gbpusd_last", market["gbpusd_last"], "USD per GBP"),
        ("gbpeur_last", market["gbpeur_last"], "EUR per GBP"),
        ("gbpusd_worst_drawdown", market["gbpusd_worst_drawdown"], "fraction"),
        ("synthetic_interest_gbp", company["interest_gbp"], "GBP"),
        ("synthetic_peak_drawn_gbp", company["peak_drawn_gbp"], "GBP"),
        ("synthetic_share_weeks_drawn", company["share_of_weeks_drawn"], "fraction"),
        ("arima_order", str(rates["order"]), "p,d,q"),
        ("arima_multistep_mae_bp", rates["multistep_12m"]["mae_bp"], "bp"),
        ("arima_multistep_rmse_bp", rates["multistep_12m"]["rmse_bp"], "bp"),
        ("arima_onestep_mae_bp", rates["onestep_24m"]["mae_bp"], "bp"),
        ("arima_onestep_rmse_bp", rates["onestep_24m"]["rmse_bp"], "bp"),
        ("arima_2022_episode_mae_bp", rates["hiking_cycle_episode"]["mae_bp"], "bp"),
        ("arima_2022_episode_rmse_bp", rates["hiking_cycle_episode"]["rmse_bp"], "bp"),
        ("var_hist_1d_95_gbp", var["hist_1d_95"], "GBP"),
        ("var_hist_1d_99_gbp", var["hist_1d_99"], "GBP"),
        ("var_hist_10d_95_gbp", var["hist_10d_95"], "GBP"),
        ("var_hist_10d_99_gbp", var["hist_10d_99"], "GBP"),
        ("var_param_1d_95_gbp", var["param_1d_95"], "GBP"),
        ("var_param_1d_99_gbp", var["param_1d_99"], "GBP"),
        ("var_param_10d_95_gbp", var["param_10d_95"], "GBP"),
        ("var_param_10d_99_gbp", var["param_10d_99"], "GBP"),
        ("mc_p_policy_breach", mc["p_policy_breach"], "probability"),
        ("mc_p_hard_min_breach", mc["p_hard_min_breach"], "probability"),
        ("mc_p_negative_cash", mc["p_negative_cash"], "probability"),
        ("mc_liquidity_at_risk_95_min_cash_gbp", mc["liquidity_at_risk_95_min_cash_gbp"], "GBP"),
        ("mc_facility_at_risk_95_peak_drawn_gbp", mc["facility_at_risk_95_peak_drawn_gbp"], "GBP"),
        ("mc_undrawn_headroom_at_95_gbp", mc["undrawn_headroom_at_95_gbp"], "GBP"),
    ]
    return [{"metric": name, "value": value, "unit": unit} for name, value, unit in rows]


def main() -> None:
    if not cfg.DB_PATH.exists():
        raise SystemExit(f"Missing {cfg.DB_PATH}. Run: python -m pipeline.load")
    cfg.FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    cfg.TABLE_DIR.mkdir(parents=True, exist_ok=True)
    download = json.loads(cfg.DOWNLOAD_META.read_text(encoding="utf-8"))
    connection = sqlite3.connect(cfg.DB_PATH)
    try:
        market = write_market(connection)
        rate = run_rate_forecast(connection)
        forecast = run_cash_forecast(connection, rate["weekly_sonia"])
        fx = run_fx_risk(connection)
        stress = run_liquidity_stress(connection, write_outputs=True)
    finally:
        connection.close()

    findings = _clean({
        "download": {
            "downloaded_at": download["downloaded_at"],
            "source_url": download["source_url"],
            "sha256": download["sha256"],
            "user_agent": download["user_agent"],
            "fallback_user_agent_used": download["fallback_user_agent_used"],
            "attempts": download["attempts"],
            "n_rows": download["n_rows"],
            "date_min_raw": download["date_min_raw"],
            "date_max_raw": download["date_max_raw"],
            "series_codes": list(cfg.SERIES),
            "licence": cfg.LICENCE_NAME,
        },
        "assumptions": _assumptions(),
        "market": market,
        "rate_forecast": rate["findings"],
        "cash_forecast": forecast,
        "fx_var": fx,
        "monte_carlo": stress["summary"],
    })
    cfg.FINDINGS_PATH.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")
    headline = _headline(findings)
    pd.DataFrame(headline).to_csv(cfg.TABLE_DIR / "headline_numbers.csv", index=False)
    print(f"Wrote {cfg.FINDINGS_PATH}")
    for row in headline:
        print(f"  {row['metric']}: {row['value']} {row['unit']}")


if __name__ == "__main__":
    main()
