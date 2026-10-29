"""Parse the cached Bank of England CSV and build the SQLite database.

Market rows are inserted only where the Bank published a number. The company
ledger is generated afterwards by pipeline.cashflows and written to a CSV
whose name says SYNTHETIC as well as to the database.
"""

from __future__ import annotations

import io
import json
import sqlite3
from datetime import date

import pandas as pd

from pipeline import config as cfg
from pipeline.cashflows import build_synthetic_history
from pipeline.download import MONTHS

RATE_CODES = [code for code, info in cfg.SERIES.items() if info["category"] == "rate"]
FX_CODES = [code for code, info in cfg.SERIES.items() if info["category"] == "fx"]


def parse_boe_date(text: str) -> date:
    """Parse '04 Jan 2010' without depending on the machine locale."""
    day, month, year = text.split()
    return date(int(year), MONTHS[month], int(day))


def read_raw_csv(path=cfg.RAW_CSV) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"Missing {path}. Run: python -m pipeline.download")
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("DATE"))
    frame = pd.read_csv(
        io.StringIO("\n".join(lines[start:])),
        dtype=str,
        keep_default_na=False,
    )
    frame.columns = [column.strip() for column in frame.columns]
    missing = [code for code in cfg.SERIES if code not in frame.columns]
    if missing:
        raise SystemExit(f"Cached CSV is missing {missing}. Re-run the download.")
    return frame


def _long_tables(frame: pd.DataFrame):
    rates = []
    fx = []
    for row in frame.itertuples(index=False):
        raw_date = getattr(row, "DATE").strip()
        if not raw_date:
            continue
        iso = parse_boe_date(raw_date).isoformat()
        for code in RATE_CODES:
            raw = getattr(row, code).strip()
            if raw == "":
                continue
            rates.append((iso, code, float(raw)))
        for code in FX_CODES:
            raw = getattr(row, code).strip()
            if raw == "":
                continue
            fx.append((iso, cfg.SERIES[code]["pair"], code, float(raw)))
    return rates, fx


def _parameters() -> list[tuple[str, float, str]]:
    return [
        ("facility_limit_gbp", cfg.FACILITY_LIMIT_GBP, "Synthetic RCF limit, GBP"),
        ("margin", cfg.MARGIN, "Synthetic margin over SONIA, decimal (0.0175 = 175 bp)"),
        ("min_cash_policy_gbp", cfg.MIN_CASH_POLICY_GBP, "Synthetic cash balance the sweep targets, GBP"),
        ("hard_min_cash_gbp", cfg.HARD_MIN_CASH_GBP, "Example hard minimum-cash level, GBP"),
        ("min_interest_cover", cfg.MIN_INTEREST_COVER, "Example minimum 52-week cash interest cover"),
        ("max_utilisation_soft", cfg.MAX_UTILISATION_SOFT, "Example soft utilisation trigger, fraction of the limit"),
        ("surplus_cap_gbp", cfg.SURPLUS_CAP_GBP, "Synthetic cash cap on dividend dates; surplus above this is distributed if the facility is undrawn"),
        ("week_year_fraction", cfg.WEEK_YEAR_FRACTION, "Simple Actual/365 day-count fraction for a 7-day week"),
    ]


def main() -> None:
    if not cfg.DOWNLOAD_META.exists():
        raise SystemExit(f"Missing {cfg.DOWNLOAD_META}. Run: python -m pipeline.download")
    meta = json.loads(cfg.DOWNLOAD_META.read_text(encoding="utf-8"))
    wide = read_raw_csv()
    rate_rows, fx_rows = _long_tables(wide)
    rates = pd.DataFrame(rate_rows, columns=["date", "series_code", "value_pct"])
    fx = pd.DataFrame(fx_rows, columns=["date", "pair", "series_code", "foreign_per_gbp"])

    ledger = build_synthetic_history(rates, fx)
    hard_weeks = int((ledger["closing_cash_gbp"] < cfg.HARD_MIN_CASH_GBP - 1.0).sum())
    drawn_weeks = int((ledger["closing_drawn_gbp"] > 1.0).sum())
    print(
        "Synthetic ledger: "
        f"{len(ledger)} weeks, {ledger['week_ending'].iloc[0]} to {ledger['week_ending'].iloc[-1]}, "
        f"end cash £{ledger['closing_cash_gbp'].iloc[-1]:,.0f}, "
        f"end drawn £{ledger['closing_drawn_gbp'].iloc[-1]:,.0f}, "
        f"peak drawn £{ledger['closing_drawn_gbp'].max():,.0f}, "
        f"weeks drawn {drawn_weeks}, hard-min breaches {hard_weeks}, "
        f"interest £{ledger['interest_gbp'].sum():,.0f}, "
        f"dividends £{ledger['dividend_gbp'].sum():,.0f}"
    )

    cfg.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if cfg.DB_PATH.exists():
        cfg.DB_PATH.unlink()
    connection = sqlite3.connect(cfg.DB_PATH)
    try:
        connection.executescript(cfg.SCHEMA_PATH.read_text(encoding="utf-8"))
        connection.executemany(
            """
            INSERT INTO series_catalog (
                series_code, series_name, category, unit, pair,
                source_url, licence, downloaded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    code,
                    info["name"],
                    info["category"],
                    info["unit"],
                    info["pair"],
                    meta["source_url"],
                    cfg.LICENCE_NAME,
                    meta["downloaded_at"],
                )
                for code, info in cfg.SERIES.items()
            ],
        )
        connection.executemany(
            "INSERT INTO rates (date, series_code, value_pct) VALUES (?, ?, ?)",
            rate_rows,
        )
        connection.executemany(
            "INSERT INTO fx (date, pair, series_code, foreign_per_gbp) VALUES (?, ?, ?, ?)",
            fx_rows,
        )
        connection.executemany(
            "INSERT INTO company_parameters (name, value, description) VALUES (?, ?, ?)",
            _parameters(),
        )
        ledger.to_sql("cash_flows", connection, if_exists="append", index=False)
        connection.commit()
    finally:
        connection.close()

    cfg.SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(cfg.SYNTHETIC_CSV, index=False)
    print(
        f"SQLite {cfg.DB_PATH.name}: {len(rate_rows)} rate rows, {len(fx_rows)} fx rows, "
        f"{len(ledger)} synthetic weeks. CSV {cfg.SYNTHETIC_CSV.name}."
    )


if __name__ == "__main__":
    main()
