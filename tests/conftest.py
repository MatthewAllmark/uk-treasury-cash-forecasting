"""Fixtures for the treasury case-study tests. Run `make load` before pytest."""

import sqlite3

import matplotlib
import pytest

matplotlib.use("Agg")

from pipeline import config as cfg


@pytest.fixture(scope="session")
def conn():
    if not cfg.DB_PATH.exists():
        pytest.fail(f"Database not found at {cfg.DB_PATH}. Run `make load` first.")
    connection = sqlite3.connect(cfg.DB_PATH)
    connection.execute("PRAGMA foreign_keys = ON")
    yield connection
    connection.close()
