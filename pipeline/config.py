"""Shared paths, Bank of England series, and fictional-company assumptions.

Cash-flow assumptions describe Northvale Components Ltd, a made-up UK
manufacturer. They are inputs to a deterministic simulation (fixed seed),
not the books of a real firm.
"""

from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RAW_DIR = ROOT / "data" / "raw"
RAW_CSV = RAW_DIR / "boe_iadb.csv"
SOURCE_NOTE = RAW_DIR / "SOURCE.md"
DOWNLOAD_META = RAW_DIR / "download_meta.json"

SYNTHETIC_DIR = ROOT / "data" / "synthetic"
SYNTHETIC_CSV = SYNTHETIC_DIR / "northvale_components_SYNTHETIC_weekly_cash_flows.csv"

DB_PATH = ROOT / "data" / "processed" / "treasury.db"
SCHEMA_PATH = ROOT / "schema.sql"
SQL_DIR = ROOT / "sql"

FIGURE_DIR = ROOT / "outputs" / "figures"
TABLE_DIR = ROOT / "outputs" / "tables"
FINDINGS_PATH = TABLE_DIR / "key_findings.json"

DATE_FROM = "01/Jan/2010"

# Official IADB names. Gilt wording follows the Bank's series catalogue
# ("Yield from British Government Securities, N year Nominal Par Yield").
SERIES = {
    "IUDBEDR": {
        "name": "Official Bank Rate",
        "category": "rate",
        "unit": "percent per annum",
        "pair": None,
    },
    "IUDSOIA": {
        "name": "SONIA (Sterling Overnight Index Average)",
        "category": "rate",
        "unit": "percent per annum",
        "pair": None,
    },
    "IUDSNPY": {
        "name": "Yield from British Government Securities, 5 year Nominal Par Yield",
        "category": "rate",
        "unit": "percent per annum",
        "pair": None,
    },
    "IUDMNPY": {
        "name": "Yield from British Government Securities, 10 year Nominal Par Yield",
        "category": "rate",
        "unit": "percent per annum",
        "pair": None,
    },
    "IUDLNPY": {
        "name": "Yield from British Government Securities, 20 year Nominal Par Yield",
        "category": "rate",
        "unit": "percent per annum",
        "pair": None,
    },
    "XUDLUSS": {
        "name": "Spot exchange rate, US dollar into sterling",
        "category": "fx",
        "unit": "USD per GBP",
        "pair": "GBPUSD",
    },
    "XUDLERS": {
        "name": "Spot exchange rate, euro into sterling",
        "category": "fx",
        "unit": "EUR per GBP",
        "pair": "GBPEUR",
    },
}

LICENCE_NAME = "Open Government Licence v3.0"
LICENCE_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
BOE_TERMS_URL = "https://www.bankofengland.co.uk/legal/terms-and-conditions"
IADB_HOME = "https://www.bankofengland.co.uk/boeapps/database/"

# urllib's default User-Agent is often refused. The downloader tries these
# in order and records which one actually returned the CSV.
USER_AGENTS = (
    "treasury-analytics-portfolio/1.0 (educational; +https://github.com/MatthewAllmark)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
)

# --- Fictional company -------------------------------------------------------
COMPANY_NAME = "Northvale Components Ltd"
SYNTHETIC_LABEL = (
    "SYNTHETIC EXAMPLE — Northvale Components Ltd (fictional), seed 42"
)
SEED = 42

# First Friday of the example ledger. Market history itself starts in 2010.
HISTORY_START = date(2016, 1, 8)

# Weekly baselines before seasonality, trend and noise.
BASE_RECEIPTS_GBP = 1_480_000.0
BASE_USD_COSTS = 780_000.0       # US dollars
BASE_EUR_COSTS = 210_000.0       # euros
BASE_PAYROLL_GBP = 340_000.0
BASE_OTHER_OPEX_GBP = 247_000.0
TAX_GBP = 1_000_000.0            # quarterly settlement, before trend
TREND_ANNUAL = 0.012
TREND_ANCHOR = date(2016, 1, 8)
RECEIPT_SIGMA = 0.04             # weekly lognormal noise
COST_SIGMA = 0.02

# Calendar-month factors. Each set averages to 1.00 across the twelve months
# so the baselines above are the mean week, not a January week.
RECEIPT_SEASON = {
    1: 0.88, 2: 0.92, 3: 1.02, 4: 1.00,
    5: 1.04, 6: 0.98, 7: 0.84, 8: 0.76,
    9: 1.05, 10: 1.12, 11: 1.20, 12: 1.19,
}
COST_SEASON = {
    1: 0.99, 2: 0.98, 3: 1.00, 4: 1.01,
    5: 1.02, 6: 1.02, 7: 0.99, 8: 0.97,
    9: 1.01, 10: 1.02, 11: 1.01, 12: 0.98,
}

# Revolving credit facility priced off SONIA. Simple Actual/365, not
# compounded-in-arrears: see the limitations in the README.
FACILITY_LIMIT_GBP = 6_000_000.0
MARGIN = 0.0175                  # 175 bp
MIN_CASH_POLICY_GBP = 1_500_000.0
HARD_MIN_CASH_GBP = 500_000.0
OPENING_CASH_GBP = 1_500_000.0
OPENING_DRAWN_GBP = 2_000_000.0
# On the June and December dividend dates, distribute cash above this cap
# when the facility is undrawn. Keeps the seasonal RCF in use instead of
# letting surplus cash accumulate for a decade.
SURPLUS_CAP_GBP = 2_000_000.0
MIN_INTEREST_COVER = 2.0         # example covenant, cash-flow proxy
MAX_UTILISATION_SOFT = 0.80      # example soft trigger
WEEK_YEAR_FRACTION = 7.0 / 365.0

# Receipt-delay stress. These are scenario settings, not estimated default rates.
# A draw is applied to that week's contractual receipts only (aged receipts
# already in transit are not delayed again).
DELAY_P_2W = 0.05
DELAY_FRAC_2W = 0.40
DELAY_P_1W = 0.15                # on top of the 2-week event, so P(any delay) = 0.20
DELAY_FRAC_1W = 0.25

MC_PATHS = 10_000
MC_WEEKS = 13
MC_SEED = 42
MC_COV_WEEKS = 156               # three years of Friday-to-Friday changes

VAR_WINDOW = 252
VAR_HORIZON_DAYS = 10
VOL_WINDOW = 63
EXPOSURE_WEEKS = 4               # about 20 business days of expected purchases

# Parallel shocks applied to the latest daily SONIA fixing, in basis points.
SONIA_SHOCKS_BP = (-200, -100, 0, 100, 200)


def boe_csv_url(date_from: str = DATE_FROM, date_to: str = "now") -> str:
    """IADB CSV endpoint. VPD=Y asks the Bank to include provisional values."""
    codes = ",".join(SERIES)
    return (
        "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
        f"?csv.x=yes&Datefrom={date_from}&Dateto={date_to}"
        f"&SeriesCodes={codes}&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N"
    )


def shock_name(bp: int) -> str:
    if bp == 0:
        return "base"
    sign = "plus" if bp > 0 else "minus"
    return f"{sign}_{abs(bp)}bp"
