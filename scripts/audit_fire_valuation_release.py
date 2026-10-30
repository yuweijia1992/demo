#!/usr/bin/env python3
"""Cross-check the 2015-2025 public F.I.R.E. A-share valuation release.

The release is large (~1.4 GB). This script downloads it to a temporary file,
extracts only the five small axis/valuation Feather members, projects only the
44 A-share columns in our universe, compares monthly observations with Enniu
and Eastmoney, then writes only a compact audit. It does NOT redistribute the
third-party raw package or merge its rows into the formal valuation database.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

ASSET_URL = "https://github.com/fire-institute/fire/releases/download/marketdata/AStockData.tar.gz"
RELEASE_API = "https://api.github.com/repos/fire-institute/fire/releases/tags/marketdata"
TARGET_FILES = {"columns.feather", "index.feather", "pe_ratio.feather", "pb_ratio.feather", "ps_ratio.feather"}
FIRE_METRICS = {"pe_ratio": "peTtm", "pb_ratio": "pb", "ps_ratio": "psTtm"}


def norm_code(value: Any) -> str:
    digits = "".join(re.findall(r"\d", str(value or "")))
    return digits[-6:] if len(digits) >= 6 else ""


def parse_day(value: Any) -> str | None:
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if len(raw) >= 10 and raw[4] == "-":
            return date.fromisoformat(raw[:10]).isoformat()
        if len(raw) == 8 and raw.isdigit():
            return datetime.strptime(raw, "%Y%m%d").date().isoformat()
        if raw.isdigit() and len(raw) >= 10:
            stamp = int(raw[:13]) / 1000 if len(raw) >= 13 else int(raw)
            return datetime.fromtimestamp(stamp, tz=timezone.utc).date().isoformat()
    except (ValueError, OverflowError, OSError):
        return None
    return None


def number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def download_asset(path: Path, timeout: int) -> tuple[int, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ValuationResearch/1.0)",
        "Accept": "application/octet-stream,*/*",
    }
    request = urllib.request.Request(ASSET_URL, headers=headers)
    digest = hashlib.sha256()
    byte_count = 0
    with urllib.request.urlopen(request, timeout=timeout) as response, path.open("wb") as handle:
        while True:
            block = response.read(8 * 1024 * 1024)
            if not block:
                break
            handle.write(block)
            digest.update(block)
            byte_count += len(block)
            if byte_count and byte_count % (128 * 1024 * 1024) < len(block):
                print(f"Downloaded {byte_count:,} bytes", flush=True)
    return byte_count, digest.hexdigest()


def extract_target_members(archive_path: Path, output_dir: Path) -> dict[str, Any]:
    found: dict[str, str] = {}
    total_members = 0
    with tarfile.open(archive_path, mode="r:gz") as archive:
        for member in archive:
            total_members += 1
            if not member.isfile():
                continue
            name = Path(member.name).name
            if name not in TARGET_FILES or name in found:
                continue
            source = archive.extractfile(member)
            if source is None:
                continue
            destination = output_dir / name
            with source, destination.open("wb") as target:
                shutil.copyfileobj(source, target, length=8 * 1024 * 1024)
            found[name] = member.name
            print(f"Extracted {name} ({member.size:,} bytes)", flush=True)
            if len(found) == len(TARGET_FILES):
                break
    missing = sorted(TARGET_FILES - set(found))
    return {"tarMembersVisited": total_members, "extractedMembers": found, "missingMembers": missing}


def axis_values(path: Path) -> list[Any]:
    import pandas as pd
    frame = pd.read_feather(path)
    if isinstance(frame.index, pd.DatetimeIndex):
        return list(frame.index)
    if frame.shape[1] == 0:
        return list(frame.index)
    # Axis Feather may encode values in a single data column, or through index metadata.
    if frame.shape[1] == 1:
        return frame.iloc[:, 0].tolist()
    return frame.iloc[:, 0].tolist()


def code_from_column(value: Any) -> str:
    return norm_code(value)


def load_metric_monthly(path: Path, code_map: dict[str, str], dates: list[str]) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    import pandas as pd
    frame = pd.read_feather(path)
    original_columns = list(frame.columns)
    selected: dict[str, str] = {}
    for column in original_columns:
        code = code_from_column(column)
        if code and code in code_map:
            selected[code] = str(column)

    # Fall back to the shared columns.feather axis if field columns are generic numeric labels.
    if not selected:
        raise RuntimeError(f"No security ticker columns recognized in {path.name}: {original_columns[:20]}")

    data = frame[[selected[code] for code in selected]].copy()
    if len(data) != len(dates):
        # Feather may restore a date index rather than store a separate data row.
        frame_dates = [parse_day(x) for x in frame.index]
        if len(frame_dates) == len(data) and all(frame_dates):
            dates = [x for x in frame_dates if x]
        else:
            raise RuntimeError(f"{path.name}: row count {len(data)} does not match date axis {len(dates)}")

    monthly: dict[str, dict[str, float]] = {}
    per_code: dict[str, dict[str, float]] = {}
    for code, column in selected.items():
        values = pd.to_numeric(data[column], errors="coerce")
        series: dict[str, float] = {}
        for d, raw in zip(dates, values.tolist()):
            value = number(raw)
            if d and value is not None and value > 0:
                month = d[:7]
                if month not in series or d > series[month]["date"]:
                    series[month] = {"date": d, "value": value}
        per_code[code] = {month: item["value"] for month, item in series.items()}
        monthly[code] = per_code[code]
    return monthly, {
        "columnsMatched": len(selected),
        "rows": len(frame),
        "firstDate": min((d for d in dates if d), default=None),
        "lastDate": max((d for d in dates if d), default=None),
        "tickersMatchedSample": list(selected.items())[:8],
    }


def read_monthly_csv(path: Path, metric_field: str) -> dict[str, dict[str, float]]:
    output: dict[str, dict[str, tuple[str, float]]] = {}
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            code = str(row.get("code", "")).upper()
            day = parse_day(row.get("date"))
            value = number(row.get(metric_field))
            if not code or not day or value is None or value <= 0:
                continue
            month = day[:7]
            current = output.setdefault(code, {})
            if month not in current or day > current[month][0]:
                current[month] = (day, value)
    return {code: {month: value for month, (_, value) in months.items()} for code, months in output.items()}


def compare_months(left: dict[str, float], right: dict[str, float]) -> dict[str, Any]:
    common = sorted(set(left) & set(right))
    errors = [abs(left[m] / right[m] - 1.0) for m in common if right[m] != 0]
    if not errors:
        return {"overlapMonths": 0, "medianAbsRelativeError": None, "p90AbsRelativeError": None}
    ordered = sorted(errors)
    return {
        "overlapMonths": len(errors),
        "medianAbsRelativeError": median(errors),
        "p90AbsRelativeError": ordered[min(len(ordered)-1, math.ceil(.9*len(ordered))-1)],
        "within5pct": sum(x <= .05 for x in errors) / len(errors),
        "within10pct": sum(x <= .10 for x in errors) / len(errors),
    }


def summarize_comparison(fire: dict[str, dict[str, float]], other: dict[str, dict[str, float]]) -> dict[str, Any]:
    rows = [compare_months(fire.get(code, {}), other.get(code, {})) for code in sorted(set(fire) & set(other))]
    valid = [x for x in rows if x["overlapMonths"] > 0]
    if not valid:
        return {"securitiesWithOverlap": 0, "overlapMonths": 0}
    return {
        "securitiesWithOverlap": len(valid),
        "overlapMonths": sum(x["overlapMonths"] for x in valid),
        "medianOfSecurityMedianAbsRelativeError": median(x["medianAbsRelativeError"] for x in valid),
        "medianOfSecurityP90AbsRelativeError": median(x["p90AbsRelativeError"] for x in valid),
        "securitiesMedianErrorUnder5pct": sum(x["medianAbsRelativeError"] <= .05 for x in valid),
        "securitiesMedianErrorUnder10pct": sum(x["medianAbsRelativeError"] <= .10 for x in valid),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default="data/valuation-history/universe.json")
    parser.add_argument("--eniu", default="data/valuation-history/raw/eniu-a-share-candidate.csv")
    parser.add_argument("--eastmoney", default="data/valuation-history/raw/eastmoney-a-share-daily.csv")
    parser.add_argument("--output", default="data/valuation-history/raw/fire-release-crosscheck-audit.json")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-download-bytes", type=int, default=1_600_000_000)
    args = parser.parse_args()

    universe = json.loads(Path(args.universe).read_text(encoding="utf-8"))
    securities = [x for x in universe["securities"] if x.get("market") == "CN"]
    code_map = {norm_code(x["securityCode"]): x["securityCode"] for x in securities}

    import requests
    meta_response = requests.get(RELEASE_API, timeout=30, headers={"User-Agent": "ValuationResearch/1.0"})
    meta_response.raise_for_status()
    release = meta_response.json()
    asset = next((x for x in release.get("assets", []) if x.get("name") == "AStockData.tar.gz"), None)
    if not asset:
        raise RuntimeError("AStockData.tar.gz not listed in the F.I.R.E. marketdata release")
    expected_size = int(asset.get("size") or 0)
    if expected_size and expected_size > args.max_download_bytes:
        raise RuntimeError(f"release asset size {expected_size:,} exceeds configured limit {args.max_download_bytes:,}")

    with tempfile.TemporaryDirectory(prefix="fire-stock-data-") as temp:
        temp_path = Path(temp)
        archive_path = temp_path / "AStockData.tar.gz"
        byte_count, sha256 = download_asset(archive_path, args.timeout)
        if expected_size and byte_count != expected_size:
            raise RuntimeError(f"download size mismatch: expected {expected_size}, got {byte_count}")
        extract_dir = temp_path / "extracted"
        extract_dir.mkdir()
        extract_audit = extract_target_members(archive_path, extract_dir)
        if extract_audit["missingMembers"]:
            raise RuntimeError(f"F.I.R.E. archive missing required Feather members: {extract_audit['missingMembers']}")

        import pandas as pd
        index_raw = axis_values(extract_dir / "index.feather")
        dates = [parse_day(x) for x in index_raw]
        if not any(dates):
            # Some packages encode the date index directly into each Feather file.
            raise RuntimeError("Cannot parse date axis from index.feather")
        first_date = min(x for x in dates if x)
        last_date = max(x for x in dates if x)

        metric_series: dict[str, dict[str, dict[str, float]]] = {}
        axis_audit: dict[str, Any] = {}
        for filename, metric in FIRE_METRICS.items():
            series, audit = load_metric_monthly(extract_dir / f"{filename}.feather", code_map, dates)
            metric_series[metric] = series
            axis_audit[metric] = audit

        eniu = {m: read_monthly_csv(Path(args.eniu), m) for m in ("peTtm", "pb", "psTtm")}
        east = {m: read_monthly_csv(Path(args.eastmoney), m) for m in ("peTtm", "pb", "psTtm")}
        comparisons = {}
        for metric in FIRE_METRICS.values():
            comparisons[f"FIRE:{metric}:Enniu"] = summarize_comparison(metric_series[metric], eniu[metric])
            if metric in east:
                comparisons[f"FIRE:{metric}:Eastmoney"] = summarize_comparison(metric_series[metric], east[metric])

        securities_audit = []
        for code in sorted(code_map):
            metrics = {}
            for metric in FIRE_METRICS.values():
                series = metric_series[metric].get(code, {})
                months = sorted(series)
                metrics[metric] = {
                    "validMonths": len(months),
                    "firstMonth": months[0] if months else None,
                    "lastMonth": months[-1] if months else None,
                }
            securities_audit.append({"code": code_map[code], "metrics": metrics})

        output = {
            "source": "F.I.R.E. Institute public A-stock release AStockData.tar.gz",
            "releaseUrl": ASSET_URL,
            "releaseTag": release.get("tag_name"),
            "releasePublishedAt": release.get("published_at"),
            "releaseUpdatedAt": release.get("updated_at"),
            "packageBytes": byte_count,
            "packageSha256": sha256,
            "archiveExtraction": extract_audit,
            "dataRange": {"firstDate": first_date, "lastDate": last_date, "dailyRows": len(dates)},
            "marketScope": "44 selected A-share securities only; Hong Kong stocks not included in this source",
            "metricFields": {
                "peTtm": "pe_ratio (documented TTM)",
                "pb": "pb_ratio",
                "psTtm": "ps_ratio (documented TTM)",
            },
            "matchedAshareCompanies": len(securities_audit),
            "axisAudit": axis_audit,
            "monthlyOverlapComparisons": comparisons,
            "perSecurityCoverage": securities_audit,
            "redistributionNote": "Only a compact coverage/consistency audit is retained. The 1.4GB third-party raw package is not copied into this repository. Verify underlying data rights before redistribution.",
            "auditedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "matchedAshareCompanies": len(securities_audit),
            "dataRange": output["dataRange"],
            "monthlyOverlapComparisons": comparisons,
            "output": str(out_path),
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
