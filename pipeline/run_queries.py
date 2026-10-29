"""Execute the commented SQL files and write one CSV per query."""

from __future__ import annotations

import sqlite3

import pandas as pd

from pipeline import config as cfg


def main() -> None:
    if not cfg.DB_PATH.exists():
        raise SystemExit(f"Missing {cfg.DB_PATH}. Run: python -m pipeline.load")
    cfg.TABLE_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(cfg.DB_PATH)
    try:
        for path in sorted(cfg.SQL_DIR.glob("*.sql")):
            frame = pd.read_sql_query(path.read_text(encoding="utf-8"), connection)
            destination = cfg.TABLE_DIR / f"{path.stem}.csv"
            frame.to_csv(destination, index=False)
            print(f"{path.name}: {len(frame)} rows -> {destination.name}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
