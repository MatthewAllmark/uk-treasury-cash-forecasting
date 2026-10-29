"""Market-data checks against the cached Bank of England file and the database.

The business-day calendar is built here from the England and Wales holiday
list. It does not import a calendar helper from the pipeline, so a download
that dropped a Tuesday would fail this file rather than a shared function.
"""

import hashlib
import json
from datetime import datetime, timedelta

import holidays

from pipeline import config as cfg

EXPECTED_NAMES = {
    "IUDBEDR": "Official Bank Rate",
    "IUDSOIA": "SONIA (Sterling Overnight Index Average)",
    "IUDSNPY": "Yield from British Government Securities, 5 year Nominal Par Yield",
    "IUDMNPY": "Yield from British Government Securities, 10 year Nominal Par Yield",
    "IUDLNPY": "Yield from British Government Securities, 20 year Nominal Par Yield",
    "XUDLUSS": "Spot exchange rate, US dollar into sterling",
    "XUDLERS": "Spot exchange rate, euro into sterling",
}

RATE_RANGES = {
    "IUDBEDR": (0.0, 15.0),
    "IUDSOIA": (-2.0, 15.0),
    "IUDSNPY": (-2.0, 20.0),
    "IUDMNPY": (-2.0, 20.0),
    "IUDLNPY": (-2.0, 20.0),
}

FX_RANGES = {
    "GBPUSD": (0.8, 2.5),
    "GBPEUR": (0.8, 2.0),
}


def _dates(connection, sql, params=()):
    rows = connection.execute(sql, params).fetchall()
    return [datetime.strptime(row[0], "%Y-%m-%d").date() for row in rows]


def _business_days(start, end):
    uk = holidays.country_holidays("GB", subdiv="ENG", years=range(start.year, end.year + 1))
    days = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5 and cursor not in uk:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def test_source_note_and_checksum():
    meta = json.loads(cfg.DOWNLOAD_META.read_text(encoding="utf-8"))
    digest = hashlib.sha256(cfg.RAW_CSV.read_bytes()).hexdigest()
    note = cfg.SOURCE_NOTE.read_text(encoding="utf-8")
    assert digest == meta["sha256"]
    assert meta["n_rows"] > 1000
    assert "Open Government Licence" in note
    assert cfg.LICENCE_URL in note
    assert "bankofengland.co.uk" in meta["source_url"]
    for code in EXPECTED_NAMES:
        assert code in note
        assert code in meta["series_codes"]


def test_catalog_matches_the_series_we_claim_to_use(conn):
    rows = conn.execute(
        "SELECT series_code, series_name, category FROM series_catalog ORDER BY series_code"
    ).fetchall()
    found = {code: name for code, name, _category in rows}
    assert found == EXPECTED_NAMES
    categories = {code: category for code, _name, category in rows}
    assert categories["XUDLUSS"] == "fx"
    assert categories["IUDBEDR"] == "rate"


def test_bank_rate_calendar_is_weekdays_minus_england_holidays(conn):
    published = _dates(
        conn,
        "SELECT date FROM rates WHERE series_code = 'IUDBEDR' ORDER BY date",
    )
    assert published == _business_days(published[0], published[-1])
    assert published[0].weekday() < 5
    assert all(day.weekday() < 5 for day in published)


def test_no_interior_gaps_and_only_a_short_publication_lag(conn):
    calendar = _dates(
        conn,
        "SELECT date FROM rates WHERE series_code = 'IUDBEDR' ORDER BY date",
    )
    for code in RATE_RANGES:
        valid = _dates(
            conn,
            "SELECT date FROM rates WHERE series_code = ? ORDER BY date",
            (code,),
        )
        expected = [day for day in calendar if valid[0] <= day <= valid[-1]]
        assert valid == expected, code
        tail = [day for day in calendar if day > valid[-1]]
        assert len(tail) <= 3, code
    for pair in FX_RANGES:
        valid = _dates(
            conn,
            "SELECT date FROM fx WHERE pair = ? ORDER BY date",
            (pair,),
        )
        expected = [day for day in calendar if valid[0] <= day <= valid[-1]]
        assert valid == expected, pair
        tail = [day for day in calendar if day > valid[-1]]
        assert len(tail) <= 3, pair


def test_rates_and_fx_sit_in_plausible_ranges(conn):
    for code, (low, high) in RATE_RANGES.items():
        lo, hi, n = conn.execute(
            "SELECT MIN(value_pct), MAX(value_pct), COUNT(*) FROM rates WHERE series_code = ?",
            (code,),
        ).fetchone()
        assert n > 1000
        assert low <= lo <= hi <= high
    for pair, (low, high) in FX_RANGES.items():
        lo, hi = conn.execute(
            "SELECT MIN(foreign_per_gbp), MAX(foreign_per_gbp) FROM fx WHERE pair = ?",
            (pair,),
        ).fetchone()
        assert low <= lo <= hi <= high
        assert lo > 0


def test_primary_keys_are_unique(conn):
    for sql in (
        "SELECT COUNT(*) - COUNT(DISTINCT date || series_code) FROM rates",
        "SELECT COUNT(*) - COUNT(DISTINCT date || pair) FROM fx",
        "SELECT COUNT(*) - COUNT(DISTINCT week_ending) FROM cash_flows",
    ):
        assert conn.execute(sql).fetchone()[0] == 0
