#!/usr/bin/env python3
"""Audit A-share V2 monthly CSV files without altering source files.

Usage:
  python scripts/a_share_v2_audit.py data/a-share-v2/raw/*.csv --date-column date
Outputs a JSON coverage report to stdout. Uses only Python standard library.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path


def month_key(value: str) -> str:
    value = value.strip()
    if len(value) >= 7 and value[4] in "-/":
        return value[:7].replace("/", "-")
    if len(value) == 6 and value.isdigit():
        return value[:4] + "-" + value[4:]
    raise ValueError(f"Unsupported date value: {value!r}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit(path: Path, date_column: str) -> dict:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or date_column not in reader.fieldnames:
            raise ValueError(f"{path}: missing date column {date_column!r}")
        dates = [month_key(row[date_column]) for row in reader if row.get(date_column)]
    counts = Counter(dates)
    unique = sorted(counts)
    missing = []
    if unique:
        y, m = map(int, unique[0].split("-"))
        end_y, end_m = map(int, unique[-1].split("-"))
        while (y, m) <= (end_y, end_m):
            key = f"{y:04d}-{m:02d}"
            if key not in counts:
                missing.append(key)
            m += 1
            if m == 13:
                y, m = y + 1, 1
    return {
        "file": str(path),
        "sha256": sha256(path),
        "rows_with_date": len(dates),
        "unique_months": len(unique),
        "start_month": unique[0] if unique else None,
        "end_month": unique[-1] if unique else None,
        "duplicate_months": {k: v for k, v in counts.items() if v > 1},
        "missing_months_inside_coverage": missing,
        "status": "review_required" if not unique or missing or any(v > 1 for v in counts.values()) else "structural_checks_passed",
        "note": "Structural checks only; this does not validate source authenticity, return methodology, total-return status, units, or economic correctness."
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--date-column", default="date")
    args = parser.parse_args()
    reports = []
    for path in args.files:
        reports.append(audit(path, args.date_column))
    print(json.dumps(reports, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
