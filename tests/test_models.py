"""Seed, Kupiec and the shared ledger used by the forecast and the stress test."""

import numpy as np

from analysis.cash_forecast import project
from analysis.fx_risk import kupiec_pof
from analysis.liquidity_stress import run_liquidity_stress
from pipeline import config as cfg
from pipeline.cashflows import _multiplier


def test_receipt_and_cost_seasonality_average_to_one():
    assert abs(sum(cfg.RECEIPT_SEASON.values()) - 12.0) < 1e-9
    assert abs(sum(cfg.COST_SEASON.values()) - 12.0) < 1e-9


def test_lognormal_noise_has_mean_one():
    draws = np.random.default_rng(0).normal(size=50_000)
    multiplier = np.array([_multiplier(float(z), cfg.RECEIPT_SIGMA) for z in draws])
    assert abs(multiplier.mean() - 1.0) < 0.01


def test_kupiec_is_zero_when_the_hit_rate_matches_and_rejects_a_bad_rate():
    matched = kupiec_pof(10, 200, 0.05)
    assert matched["lr"] < 1e-8
    assert abs(matched["pvalue"] - 1.0) < 1e-6
    assert matched["reject_5pct"] is False

    too_many = kupiec_pof(40, 200, 0.05)
    assert too_many["lr"] > 3.841
    assert too_many["pvalue"] < 0.05
    assert too_many["reject_5pct"] is True

    none = kupiec_pof(0, 250, 0.05)
    assert none["lr"] > 0
    assert none["hits"] == 0


def test_monte_carlo_repeats_with_the_same_seed(conn):
    first = run_liquidity_stress(conn, n_paths=10_000, seed=42, write_outputs=False)
    second = run_liquidity_stress(conn, n_paths=10_000, seed=42, write_outputs=False)
    other = run_liquidity_stress(conn, n_paths=10_000, seed=43, write_outputs=False)
    assert np.array_equal(first["peak_drawn"], second["peak_drawn"])
    assert not np.array_equal(first["peak_drawn"], other["peak_drawn"])
    assert len(np.unique(np.round(first["peak_drawn"], 2))) > 10
    assert first["summary"]["n_paths"] == 10_000
    assert first["summary"]["seed"] == 42
    for key in ("p_policy_breach", "p_hard_min_breach", "p_negative_cash", "p_facility_limit"):
        assert 0.0 <= first["summary"][key] <= 1.0


def test_zero_shock_stress_matches_the_flat_sonia_forecast(conn):
    state_rate = conn.execute(
        "SELECT sonia_pct FROM cash_flows ORDER BY week_ending DESC LIMIT 1"
    ).fetchone()[0]
    _state, _weeks, posted = project(conn, 13, np.full(13, state_rate))
    stress = run_liquidity_stress(
        conn, n_paths=4, seed=7, horizon_weeks=13, zero_shocks=True, write_outputs=False
    )
    assert np.allclose(stress["closing_cash"], posted["closing_cash"][0], atol=1e-6)
    assert np.allclose(stress["closing_cash"], stress["closing_cash"][0])
