#!/usr/bin/env python3
"""V1.2 public-data extension: S&P total returns + ALFRED monthly vintages.

No API key is required. The script deliberately stores ALFRED vintage matrices
separately from current FRED series so revised history cannot silently leak
into point-in-time backtests.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "index-valuation"
USER_AGENT = "InvestmentLab-V12-research/1.0 (public-data; contact via repository)"
SHILLER_CSV = "https://firenum.com/data/shiller-monthly.csv"
ALFRED_CSV = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
SERIES = ("NFCI",)
CURRENT_SERIES = ("DFII10", "FEDFUNDS", "GS10", "CPIAUCSL")
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
START = dt.date(2003, 1, 1)


def get(url: str, attempts: int = 5, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(min(30, 3 ** attempt))
    raise RuntimeError(f"Download failed after {attempts} attempts (timeout={timeout}s): {url}") from last_error


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def month_ends(start: dt.date, end: dt.date) -> list[str]:
    result = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        if month == 12:
            nxt = dt.date(year + 1, 1, 1)
        else:
            nxt = dt.date(year, month + 1, 1)
        last = nxt - dt.timedelta(days=1)
        if last <= end:
            result.append(last.isoformat())
        year, month = nxt.year, nxt.month
    return result


def build_sp500_total_return() -> dict:
    raw = get(SHILLER_CSV, attempts=5, timeout=180).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    required = {"year", "month", "nominalReturn", "cpi"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise RuntimeError(f"Unexpected Shiller CSV headers: {reader.fieldnames}")
    rows = []
    seen = set()
    for row in reader:
        year, month = int(row["year"]), int(row["month"])
        date = f"{year:04d}-{month:02d}-01"
        if date in seen or not 1 <= month <= 12:
            raise RuntimeError(f"Duplicate/invalid Shiller month: {date}")
        seen.add(date)
        ret, cpi = float(row["nominalReturn"]), float(row["cpi"])
        if not (-1 < ret < 5) or cpi <= 0:
            raise RuntimeError(f"Implausible Shiller observation: {row}")
        rows.append((date, f"{ret:.6f}", f"{cpi:.4f}"))
    rows.sort()
    if len(rows) < 1800 or rows[0][0] > "1871-02-01":
        raise RuntimeError(f"Unexpected Shiller coverage: {len(rows)} rows, {rows[0][0] if rows else 'empty'}")
    if rows[-1][0] < "2026-08-01":
        raise RuntimeError(f"Shiller feed is stale: latest {rows[-1][0]}")
    path = OUT / "sp500-long-run-total-return-monthly.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["month", "total_return_decimal", "shiller_cpi"])
        w.writerows(rows)
    return {
        "file": path.name, "rows": len(rows), "start": rows[0][0],
        "end": rows[-1][0], "sha256": sha256(path),
        "source": SHILLER_CSV, "license": "CC BY 4.0 as stated by Firenum; attribution required",
        "method": "Monthly nominal total return with dividends reinvested; CPI kept separately; source uses Shiller monthly-average prices."
    }


def fetch_alfred_series(series_id: str, vintages: list[str], batch_size: int = 3) -> dict:
    matrix: dict[str, dict[str, str]] = {}
    columns = []
    for offset in range(0, len(vintages), batch_size):
        batch = vintages[offset:offset + batch_size]
        params = {
            "id": ",".join([series_id] * len(batch)),
            "vintage_date": ",".join(batch),
        }
        url = ALFRED_CSV + "?" + urllib.parse.urlencode(params)
        content = get(url, attempts=5, timeout=180).decode("utf-8-sig")
        reader = csv.reader(io.StringIO(content))
        header = next(reader, [])
        expected = [f"{series_id}_{d.replace('-', '')}" for d in batch]
        if len(header) != len(expected) + 1 or header[1:] != expected:
            raise RuntimeError(
                f"{series_id}: ALFRED header mismatch. Expected {expected[:2]}..., got {header[:4]}"
            )
        columns.extend(header[1:])
        for row in reader:
            if not row:
                continue
            obs_date = row[0].strip()
            if not obs_date:
                continue
            target = matrix.setdefault(obs_date, {})
            for col, value in zip(header[1:], row[1:]):
                target[col] = value.strip()
        time.sleep(0.25)
    if len(matrix) < 100:
        raise RuntimeError(f"{series_id}: too few ALFRED observations: {len(matrix)}")
    path = OUT / f"alfred-{series_id.lower()}-vintages.csv.gz"
    with path.open("wb") as raw_file:
        with gzip.GzipFile(fileobj=raw_file, mode="wb", compresslevel=9, mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["observation_date", *columns])
                for obs_date in sorted(matrix):
                    w.writerow([obs_date, *[matrix[obs_date].get(c, ".") for c in columns]])
    return {
        "file": path.name, "observation_rows": len(matrix), "vintage_columns": len(columns),
        "first_observation": min(matrix), "last_observation": max(matrix),
        "first_vintage": vintages[0], "last_vintage": vintages[-1],
        "sha256": sha256(path),
        "source": f"https://alfred.stlouisfed.org/series?seid={series_id}",
        "method": "Monthly month-end as-of vintages from ALFRED graph CSV; each column is the full series as known on that vintage date."
    }


def fetch_fred_current(series_id: str) -> dict:
    url = FRED_CSV + "?" + urllib.parse.urlencode({"id": series_id})
    raw = get(url).decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(raw)))
    if len(rows) < 100 or not rows[0] or rows[0][1:] != [series_id]:
        raise RuntimeError(f"{series_id}: unexpected FRED CSV response/header {rows[:2]}")
    path = OUT / f"fred-{series_id.lower()}-current.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerows(rows)
    valid_dates = [r[0] for r in rows[1:] if len(r) > 1 and r[1] not in ("", ".")]
    if not valid_dates:
        raise RuntimeError(f"{series_id}: no valid observations")
    return {
        "file": path.name, "rows": len(valid_dates), "start": min(valid_dates),
        "end": max(valid_dates), "sha256": sha256(path),
        "source": f"https://fred.stlouisfed.org/series/{series_id}",
        "method": "Current FRED graph CSV download; latest revised history, not an ALFRED point-in-time vintage."
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2003-01-01")
    parser.add_argument("--end", default=None, help="Last vintage month; defaults to previous completed month.")
    parser.add_argument("--series", default=",".join(SERIES))
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    today = dt.date.today()
    end = dt.date.fromisoformat(args.end) if args.end else (today.replace(day=1) - dt.timedelta(days=1))
    vintages = month_ends(dt.date.fromisoformat(args.start), end)
    if not vintages:
        raise RuntimeError("No vintage dates requested")
    audit = {
        "title": "V1.2 Historical Data Extension",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "vintage_policy": "Calendar month-end as-of snapshots; no API key; ALFRED header is validated for every requested vintage.",
        "vintage_dates": {"count": len(vintages), "first": vintages[0], "last": vintages[-1]},
        "series": {},
        "current_fred_series": {},
        "sp500_total_return": build_sp500_total_return(),
        "limitations": [
            "ALFRED graph CSV is a public download endpoint, not the documented FRED API; endpoint changes will fail header validation rather than silently mislabel vintages.",
            "DFII10 is daily, NFCI weekly, and FEDFUNDS/GS10/CPIAUCSL monthly; downstream aggregation must respect frequency and publication timing.",
            "Vintage-date snapshots are not themselves a ready-made monthly factor panel. Build signals only from observations available in each vintage.",
            "The S&P total-return series is a Shiller-derived historical composite. Pre-1926 values are reconstructed and less precise than modern index history.",
            "This long-run S&P series is USD nominal total return, not RMB return; FX conversion is a separate step."
        ]
    }
    for series_id in CURRENT_SERIES:
        print(f"Downloading current FRED series {series_id}", flush=True)
        audit["current_fred_series"][series_id] = fetch_fred_current(series_id)
    for series_id in [x.strip().upper() for x in args.series.split(",") if x.strip()]:
        if series_id not in SERIES:
            raise RuntimeError(f"Series not on approved ALFRED allowlist: {series_id}")
        print(f"Downloading ALFRED {series_id}: {len(vintages)} monthly vintages in batches of 3", flush=True)
        audit["series"][series_id] = fetch_alfred_series(series_id, vintages)
    audit_path = OUT / "v12-historical-data-audit.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
