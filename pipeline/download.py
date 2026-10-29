"""Download the Bank of England IADB CSV and cache it unchanged.

The raw file is the response body. Nothing in this module fills gaps or
rewrites numbers. A short SOURCE.md next to the file records the retrieval
date, the URL, the series and the licence.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

from pipeline import config as cfg

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _fetch(url: str) -> tuple[bytes, str, list[dict]]:
    """Try each User-Agent. Return the body, the agent that worked, and the attempt log."""
    attempts = []
    last_error = "no attempt made"
    for agent in cfg.USER_AGENTS:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": agent, "Accept": "text/csv,text/plain,*/*"},
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                body = response.read()
            head = body[:400].lstrip().lower()
            if head.startswith(b"<") or b"<html" in head:
                raise RuntimeError("response was HTML, not a CSV")
            attempts.append({"user_agent": agent, "ok": True})
            return body, agent, attempts
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            attempts.append({"user_agent": agent, "ok": False, "error": last_error})
            print(f"BoE download attempt failed ({agent.split()[0]}): {last_error}")
    raise SystemExit(
        "Could not download Bank of England data after trying alternate User-Agent "
        f"headers. Last error: {last_error}. Market data has not been fabricated."
    )


def _parse_header(body: bytes) -> tuple[list[str], int, str, str]:
    text = body.decode("utf-8-sig")
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("DATE")), None)
    if start is None:
        raise SystemExit("BoE response has no DATE header. File was not cached as data.")
    reader = csv.reader(io.StringIO("\n".join(lines[start:])))
    header = next(reader)
    missing = [code for code in cfg.SERIES if code not in header]
    if missing:
        raise SystemExit(f"BoE CSV is missing series codes: {', '.join(missing)}")
    first_date = None
    last_date = None
    n = 0
    for row in reader:
        if not row or not row[0].strip():
            continue
        n += 1
        last_date = row[0].strip()
        if first_date is None:
            first_date = last_date
    if n < 1000 or first_date is None or last_date is None:
        raise SystemExit(f"BoE CSV looks too short to be the daily history (rows={n}).")
    return header, n, first_date, last_date


def _source_note(meta: dict) -> str:
    series_lines = "\n".join(
        f"| `{code}` | {info['name']} | {info['unit']} |"
        for code, info in cfg.SERIES.items()
    )
    attempt_lines = "\n".join(
        f"- {'OK' if item['ok'] else 'failed'}: `{item['user_agent']}`"
        + (f" — {item['error']}" if not item["ok"] else "")
        for item in meta["attempts"]
    )
    return f"""# Bank of England data cache

- Downloaded: {meta['downloaded_at']}
- File: `boe_iadb.csv` (unmodified response body)
- SHA-256: `{meta['sha256']}`
- Data rows: {meta['n_rows']}
- First DATE cell: {meta['date_min_raw']}
- Last DATE cell: {meta['date_max_raw']}

## Source

Bank of England Interactive Statistical Database (IADB), CSV endpoint:

{meta['source_url']}

Database home: {cfg.IADB_HOME}

`CSVF=TN` asks for series codes in the header. `UsingCodes=Y` selects by code.
`VPD=Y` includes provisional observations, which the Bank may revise.
`Dateto=now` requests the latest published day at the time of the download.

The file is cached exactly as returned. Blank cells (a series not yet published
on the newest business day) are left blank. This project does not interpolate them.

## Retrieval

{attempt_lines}

## Series

| Code | Description | Unit |
| --- | --- | --- |
{series_lines}

## Licence

Contains public sector information licensed under the Open Government Licence v3.0
({cfg.LICENCE_URL}).

Also subject to the Bank of England terms and conditions ({cfg.BOE_TERMS_URL}).

This is an independent educational portfolio. It is not affiliated with, endorsed
by, or published by the Bank of England.
"""


def main() -> None:
    url = cfg.boe_csv_url()
    print(f"Downloading Bank of England IADB CSV\n  {url}")
    body, agent, attempts = _fetch(url)
    header, n_rows, first_raw, last_raw = _parse_header(body)
    downloaded_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    cfg.RAW_DIR.mkdir(parents=True, exist_ok=True)
    cfg.RAW_CSV.write_bytes(body)
    meta = {
        "downloaded_at": downloaded_at,
        "source_url": url,
        "user_agent": agent,
        "attempts": attempts,
        "licence": cfg.LICENCE_NAME,
        "licence_url": cfg.LICENCE_URL,
        "boe_terms_url": cfg.BOE_TERMS_URL,
        "sha256": hashlib.sha256(body).hexdigest(),
        "n_bytes": len(body),
        "n_rows": n_rows,
        "header": header,
        "series_codes": list(cfg.SERIES),
        "date_min_raw": first_raw,
        "date_max_raw": last_raw,
        "fallback_user_agent_used": agent != cfg.USER_AGENTS[0],
    }
    cfg.DOWNLOAD_META.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    cfg.SOURCE_NOTE.write_text(_source_note(meta), encoding="utf-8")
    print(
        f"Cached {n_rows} rows ({first_raw} to {last_raw}), "
        f"sha256 {meta['sha256'][:12]}…, User-Agent ok on attempt {len(attempts)}."
    )


if __name__ == "__main__":
    main()
