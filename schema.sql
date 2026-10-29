-- Treasury case-study schema.
-- rates and fx are Bank of England observations.
-- cash_flows and the parameters that govern them are a SYNTHETIC example
-- (Northvale Components Ltd, fictional). is_synthetic is constrained to 1
-- so a market row cannot be inserted into the company ledger by mistake.

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS cash_flows;
DROP TABLE IF EXISTS fx;
DROP TABLE IF EXISTS rates;
DROP TABLE IF EXISTS company_parameters;
DROP TABLE IF EXISTS series_catalog;

CREATE TABLE series_catalog (
    series_code   TEXT PRIMARY KEY,
    series_name   TEXT NOT NULL,
    category      TEXT NOT NULL CHECK (category IN ('rate', 'fx')),
    unit          TEXT NOT NULL,
    pair          TEXT,
    source_url    TEXT NOT NULL,
    licence       TEXT NOT NULL,
    downloaded_at TEXT NOT NULL
);

-- Daily interest rates and gilt par yields, percent per annum.
CREATE TABLE rates (
    date        TEXT NOT NULL,          -- ISO date, observation date
    series_code TEXT NOT NULL,
    value_pct   REAL NOT NULL,
    PRIMARY KEY (date, series_code),
    FOREIGN KEY (series_code) REFERENCES series_catalog (series_code)
);

-- Spot FX as published: units of foreign currency per one pound sterling.
-- GBPUSD is US dollars per GBP (BoE XUDLUSS). GBPEUR is euros per GBP (XUDLERS).
CREATE TABLE fx (
    date             TEXT NOT NULL,
    pair             TEXT NOT NULL,
    series_code      TEXT NOT NULL,
    foreign_per_gbp  REAL NOT NULL,
    PRIMARY KEY (date, pair),
    FOREIGN KEY (series_code) REFERENCES series_catalog (series_code)
);

-- Example RCF and cash policy. SQL reads these instead of hard-coding them.
CREATE TABLE company_parameters (
    name        TEXT PRIMARY KEY,
    value       REAL NOT NULL,
    description TEXT NOT NULL
);

-- Weekly ledger for the fictional company. One row is a Friday week-ending.
-- Money columns are GBP except usd_costs_fc / eur_costs_fc and the two FX rates.
CREATE TABLE cash_flows (
    week_ending                  TEXT PRIMARY KEY,
    fixing_date                  TEXT NOT NULL,  -- BoE date used for SONIA and FX
    receipts_gbp                 REAL NOT NULL,
    payroll_gbp                  REAL NOT NULL,
    other_opex_gbp               REAL NOT NULL,
    tax_gbp                      REAL NOT NULL,
    dividend_gbp                 REAL NOT NULL,
    usd_costs_fc                 REAL NOT NULL,
    eur_costs_fc                 REAL NOT NULL,
    usd_per_gbp                  REAL NOT NULL,
    eur_per_gbp                  REAL NOT NULL,
    usd_costs_gbp                REAL NOT NULL,
    eur_costs_gbp                REAL NOT NULL,
    sonia_pct                    REAL NOT NULL,
    interest_gbp                 REAL NOT NULL,
    total_operating_outflow_gbp  REAL NOT NULL,
    net_operating_gbp            REAL NOT NULL,
    opening_cash_gbp             REAL NOT NULL,
    opening_drawn_gbp            REAL NOT NULL,
    drawdown_gbp                 REAL NOT NULL,
    repayment_gbp                REAL NOT NULL,
    closing_cash_gbp             REAL NOT NULL,
    closing_drawn_gbp            REAL NOT NULL,
    is_synthetic                 INTEGER NOT NULL CHECK (is_synthetic = 1),
    example_label                TEXT NOT NULL
);

CREATE INDEX idx_rates_code_date ON rates (series_code, date);
CREATE INDEX idx_fx_pair_date ON fx (pair, date);
