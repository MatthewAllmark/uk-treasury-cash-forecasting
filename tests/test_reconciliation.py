"""The synthetic ledger has to rebuild from its own inputs, to the penny of float error."""

import json

import numpy as np
import pandas as pd

from pipeline import config as cfg
from pipeline.cashflows import apply_facility, build_synthetic_history
from tests.test_data_quality import EXPECTED_NAMES


def test_parameters_match_config(conn):
    stored = dict(conn.execute("SELECT name, value FROM company_parameters"))
    assert stored["facility_limit_gbp"] == cfg.FACILITY_LIMIT_GBP
    assert stored["margin"] == cfg.MARGIN
    assert stored["min_cash_policy_gbp"] == cfg.MIN_CASH_POLICY_GBP
    assert stored["hard_min_cash_gbp"] == cfg.HARD_MIN_CASH_GBP
    assert stored["surplus_cap_gbp"] == cfg.SURPLUS_CAP_GBP
    assert stored["week_year_fraction"] == cfg.WEEK_YEAR_FRACTION


def test_components_sum_and_the_facility_rule_holds(conn):
    ledger = pd.read_sql_query("SELECT * FROM cash_flows ORDER BY week_ending", conn)
    params = dict(conn.execute("SELECT name, value FROM company_parameters"))
    assert (ledger["is_synthetic"] == 1).all()
    assert ledger["example_label"].str.contains("SYNTHETIC").all()
    assert (ledger["fixing_date"] <= ledger["week_ending"]).all()

    usd_gbp = ledger["usd_costs_fc"] / ledger["usd_per_gbp"]
    eur_gbp = ledger["eur_costs_fc"] / ledger["eur_per_gbp"]
    outflow = (
        ledger["payroll_gbp"]
        + ledger["other_opex_gbp"]
        + ledger["tax_gbp"]
        + ledger["usd_costs_gbp"]
        + ledger["eur_costs_gbp"]
    )
    interest = (
        ledger["opening_drawn_gbp"]
        * (ledger["sonia_pct"] / 100.0 + params["margin"])
        * params["week_year_fraction"]
    )
    closing_cash = (
        ledger["opening_cash_gbp"]
        + ledger["net_operating_gbp"]
        - ledger["dividend_gbp"]
        - interest
        + ledger["drawdown_gbp"]
        - ledger["repayment_gbp"]
    )
    closing_drawn = ledger["opening_drawn_gbp"] + ledger["drawdown_gbp"] - ledger["repayment_gbp"]

    assert np.allclose(usd_gbp, ledger["usd_costs_gbp"], atol=1e-6)
    assert np.allclose(eur_gbp, ledger["eur_costs_gbp"], atol=1e-6)
    assert np.allclose(outflow, ledger["total_operating_outflow_gbp"], atol=1e-6)
    assert np.allclose(
        ledger["receipts_gbp"] - outflow, ledger["net_operating_gbp"], atol=1e-6
    )
    assert np.allclose(interest, ledger["interest_gbp"], atol=1e-6)
    assert np.allclose(closing_cash, ledger["closing_cash_gbp"], atol=1e-6)
    assert np.allclose(closing_drawn, ledger["closing_drawn_gbp"], atol=1e-6)
    assert np.allclose(
        ledger["closing_cash_gbp"].iloc[:-1], ledger["opening_cash_gbp"].iloc[1:], atol=1e-6
    )
    assert np.allclose(
        ledger["closing_drawn_gbp"].iloc[:-1], ledger["opening_drawn_gbp"].iloc[1:], atol=1e-6
    )
    both = (ledger["drawdown_gbp"] > 1e-6) & (ledger["repayment_gbp"] > 1e-6)
    assert int(both.sum()) == 0
    assert ledger["closing_drawn_gbp"].min() >= -1e-6
    assert ledger["closing_drawn_gbp"].max() <= params["facility_limit_gbp"] + 1e-4
    paid = ledger["dividend_gbp"] > 1e-6
    assert (ledger.loc[paid, "opening_drawn_gbp"] <= 1e-6).all()
    cash_before_sweep = (
        ledger["opening_cash_gbp"] + ledger["net_operating_gbp"] - ledger["interest_gbp"]
    )
    assert np.allclose(
        (cash_before_sweep - ledger["dividend_gbp"])[paid],
        params["surplus_cap_gbp"],
        atol=1e-4,
    )
    assert (ledger["receipts_gbp"] > 0).all()
    assert (ledger["usd_costs_fc"] > 0).all()
    assert (ledger["eur_costs_fc"] > 0).all()

    limit = params["facility_limit_gbp"]
    minimum = params["min_cash_policy_gbp"]
    cash_before = (
        ledger["opening_cash_gbp"]
        + ledger["net_operating_gbp"]
        - ledger["dividend_gbp"]
        - ledger["interest_gbp"]
    )
    shortfall = minimum - cash_before
    headroom = limit - ledger["opening_drawn_gbp"]
    expected_draw = np.where(shortfall > 0, np.minimum(shortfall, np.maximum(headroom, 0)), 0.0)
    expected_repay = np.where(
        shortfall > 0, 0.0, np.minimum(-shortfall, np.maximum(ledger["opening_drawn_gbp"], 0))
    )
    assert np.allclose(expected_draw, ledger["drawdown_gbp"], atol=1e-4)
    assert np.allclose(expected_repay, ledger["repayment_gbp"], atol=1e-4)


def test_fixings_match_the_market_tables(conn):
    ledger = pd.read_sql_query(
        "SELECT fixing_date, usd_per_gbp, eur_per_gbp, sonia_pct FROM cash_flows",
        conn,
    )
    fx = pd.read_sql_query("SELECT date, pair, foreign_per_gbp FROM fx", conn)
    rates = pd.read_sql_query(
        "SELECT date, value_pct FROM rates WHERE series_code = 'IUDSOIA'",
        conn,
    )
    usd = fx.loc[fx["pair"] == "GBPUSD", ["date", "foreign_per_gbp"]]
    eur = fx.loc[fx["pair"] == "GBPEUR", ["date", "foreign_per_gbp"]]
    usd_check = ledger.merge(usd, left_on="fixing_date", right_on="date")
    eur_check = ledger.merge(eur, left_on="fixing_date", right_on="date")
    sonia_check = ledger.merge(rates, left_on="fixing_date", right_on="date")
    assert len(usd_check) == len(ledger)
    assert np.allclose(usd_check["usd_per_gbp"], usd_check["foreign_per_gbp"])
    assert np.allclose(eur_check["eur_per_gbp"], eur_check["foreign_per_gbp"])
    assert np.allclose(sonia_check["sonia_pct"], sonia_check["value_pct"])


def test_history_rebuilds_from_the_seed(conn):
    rates = pd.read_sql_query("SELECT date, series_code, value_pct FROM rates", conn)
    fx = pd.read_sql_query("SELECT date, pair, series_code, foreign_per_gbp FROM fx", conn)
    first = build_synthetic_history(rates, fx)
    second = build_synthetic_history(rates, fx)
    stored = pd.read_sql_query("SELECT * FROM cash_flows ORDER BY week_ending", conn)
    assert np.allclose(first["receipts_gbp"], second["receipts_gbp"])
    assert np.allclose(first["closing_cash_gbp"], second["closing_cash_gbp"])
    assert list(first["week_ending"]) == list(stored["week_ending"])
    assert np.allclose(first["receipts_gbp"], stored["receipts_gbp"])
    assert np.allclose(first["closing_cash_gbp"], stored["closing_cash_gbp"])
    assert np.allclose(first["interest_gbp"], stored["interest_gbp"])
    assert np.allclose(first["dividend_gbp"], stored["dividend_gbp"])


def test_facility_sweep_respects_the_limit_and_the_minimum():
    draw, repay, cash, drawn = apply_facility(
        np.array([1_000.0]),
        np.array([cfg.FACILITY_LIMIT_GBP - 100.0]),
        np.array([-5_000.0]),
        np.array([0.0]),
        np.array([0.0]),
    )
    assert draw[0] == 100.0
    assert repay[0] == 0.0
    assert drawn[0] == cfg.FACILITY_LIMIT_GBP
    assert cash[0] == -3_900.0

    draw, repay, cash, drawn = apply_facility(
        np.array([2_000_000.0]),
        np.array([500_000.0]),
        np.array([0.0]),
        np.array([0.0]),
        np.array([0.0]),
    )
    assert repay[0] == 500_000.0
    assert draw[0] == 0.0
    assert cash[0] == cfg.MIN_CASH_POLICY_GBP
    assert drawn[0] == 0.0


def test_outputs_written_by_make_all():
    figures = [
        "bank_rate_sonia_gilt10.png",
        "yield_curve_slopes.png",
        "sonia_bank_rate_spread.png",
        "fx_spot_rates.png",
        "fx_drawdowns.png",
        "synthetic_cash_and_facility.png",
        "synthetic_forecast_13w.png",
        "synthetic_forecast_12m.png",
        "sonia_forecast_backtest.png",
        "fx_rolling_volatility.png",
        "synthetic_var_backtest.png",
        "synthetic_mc_liquidity_fan.png",
        "synthetic_mc_min_cash.png",
    ]
    for name in figures:
        path = cfg.FIGURE_DIR / name
        assert path.exists(), name
        assert path.stat().st_size > 5_000, name
    findings = json.loads(cfg.FINDINGS_PATH.read_text(encoding="utf-8"))
    assert findings["monte_carlo"]["n_paths"] == 10_000
    assert findings["monte_carlo"]["seed"] == 42
    assert findings["download"]["series_codes"] == list(EXPECTED_NAMES)
    assert "SYNTHETIC" in findings["assumptions"]["label"]
