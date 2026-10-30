#!/usr/bin/env python3
"""Audit Enniu A-share candidate against existing Baidu and Eastmoney series.

The candidate is never merged here. Comparisons use each provider's last
available valid observation per calendar month after XSHG session filtering.
PS is compared only as a diagnostic: Enniu's raw 'ps' basis is unverified.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

import exchange_calendars as xcals


def number(value: Any) -> float | None:
    if value is None:
        return None
    raw = str(value).strip().replace(",", "").replace("%", "")
    if raw.lower() in {"", "-", "--", "null", "none", "nan", "n/a", "na"}:
        return None
    try:
        result = float(raw)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def day(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if len(raw) >= 10 and raw[4] == "-":
            return date.fromisoformat(raw[:10]).isoformat()
        if len(raw) == 8 and raw.isdigit():
            return datetime.strptime(raw, "%Y%m%d").date().isoformat()
    except ValueError:
        return None
    return None


def read_csv(path: Path, source: str) -> tuple[dict[str, dict[str, dict[str, float]]], dict[str, Any]]:
    data: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    row_count = 0
    if not path.exists():
        return data, {"source": source, "path": str(path), "exists": False, "rows": 0}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            code = str(row.get("code", "")).strip().upper()
            d = day(row.get("date"))
            if not code or not d:
                continue
            row_count += 1
            for metric in ("peTtm", "pb", "psTtm", "psRaw", "close"):
                value = number(row.get(metric))
                if value is not None:
                    data[code][metric][d] = value
    return data, {"source": source, "path": str(path), "exists": True, "rows": row_count}


def valid_sessions(start: str, end: str) -> set[str]:
    cal = xcals.get_calendar("XSHG", start=start, end=end)
    return {str(x)[:10] for x in cal.sessions_in_range(start, end)}


def monthly_last(series: dict[str, float], sessions: set[str]) -> dict[str, tuple[str, float]]:
    output: dict[str, tuple[str, float]] = {}
    for d, value in series.items():
        if d not in sessions or value <= 0:
            continue
        month = d[:7]
        if month not in output or d > output[month][0]:
            output[month] = (d, value)
    return output


def compare(a: dict[str, tuple[str, float]], b: dict[str, tuple[str, float]]) -> dict[str, Any]:
    months = sorted(set(a).intersection(b))
    errors = []
    ratios = []
    lags = []
    for month in months:
        da, va = a[month]
        db, vb = b[month]
        if vb == 0:
            continue
        ratios.append(va / vb)
        errors.append(abs(va / vb - 1.0))
        lags.append(abs((date.fromisoformat(da) - date.fromisoformat(db)).days))
    if not errors:
        return {
            "overlapMonths": 0, "medianAbsRelativeError": None, "p90AbsRelativeError": None,
            "medianEnniuToOtherRatio": None, "within5pct": None, "within10pct": None,
            "within20pct": None, "medianCalendarDayLag": None,
        }
    ordered = sorted(errors)
    p90 = ordered[min(len(ordered) - 1, math.ceil(0.90 * len(ordered)) - 1)]
    return {
        "overlapMonths": len(errors),
        "medianAbsRelativeError": median(errors),
        "p90AbsRelativeError": p90,
        "medianEnniuToOtherRatio": median(ratios),
        "within5pct": sum(x <= .05 for x in errors) / len(errors),
        "within10pct": sum(x <= .10 for x in errors) / len(errors),
        "within20pct": sum(x <= .20 for x in errors) / len(errors),
        "medianCalendarDayLag": median(lags),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", default="data/valuation-history/raw/eniu-a-share-candidate.csv")
    parser.add_argument("--baidu", default="data/valuation-history/raw/baidu-valuation-history.csv")
    parser.add_argument("--eastmoney", default="data/valuation-history/raw/eastmoney-a-share-daily.csv")
    parser.add_argument("--output", default="data/valuation-history/raw/eniu-overlap-audit.json")
    args = parser.parse_args()

    eniu, eniu_meta = read_csv(Path(args.candidate), "Eniu candidate")
    baidu, baidu_meta = read_csv(Path(args.baidu), "Baidu")
    east, east_meta = read_csv(Path(args.eastmoney), "Eastmoney")
    dates = []
    for dataset in (eniu, baidu, east):
        for metrics in dataset.values():
            for series in metrics.values():
                dates.extend(series.keys())
    sessions = valid_sessions(min(dates), max(dates)) if dates else set()

    securities = sorted(set(eniu) | set(baidu) | set(east))
    metric_summary: dict[str, Any] = {}
    metric_map = {
        "peTtm": ("peTtm", "peTtm"),
        "pb": ("pb", "pb"),
        # Never promote this field to PS-TTM: compare it only diagnostically.
        "psRaw_vs_Eastmoney_psTtm": ("psRaw", "psTtm"),
    }
    per_security = []
    for code in securities:
        eniu_month = {
            metric: monthly_last(eniu.get(code, {}).get(metric, {}), sessions)
            for metric in ("peTtm", "pb", "psRaw")
        }
        for other_name, other in (("Baidu", baidu), ("Eastmoney", east)):
            for label, (eniu_metric, other_metric) in metric_map.items():
                left = eniu_month[eniu_metric]
                right = monthly_last(other.get(code, {}).get(other_metric, {}), sessions)
                result = compare(left, right)
                per_security.append({
                    "code": code, "comparison": other_name, "metric": label, **result
                })

    for comparison in ("Baidu", "Eastmoney"):
        for label in metric_map:
            rows = [x for x in per_security if x["comparison"] == comparison and x["metric"] == label and x["overlapMonths"] > 0]
            weights = sum(x["overlapMonths"] for x in rows)
            errs = []
            for x in rows:
                errs.extend([x["medianAbsRelativeError"]] * x["overlapMonths"])
            metric_summary[f"{comparison}:{label}"] = {
                "securitiesWithOverlap": len(rows),
                "overlapMonthsTotal": weights,
                "medianOfSecurityMedianAbsRelativeError": median([x["medianAbsRelativeError"] for x in rows]) if rows else None,
                "medianEnniuToOtherRatioAcrossSecurityMedians": median([x["medianEnniuToOtherRatio"] for x in rows]) if rows else None,
            }

    security_coverage = {}
    for metric in ("peTtm", "pb", "psRaw", "close"):
        security_coverage[metric] = sum(
            1 for code in securities
            if any(value > 0 for value in eniu.get(code, {}).get(metric, {}).values())
        )
    audit = {
        "source": "Eniu candidate overlap audit",
        "auditedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": [eniu_meta, baidu_meta, east_meta],
        "requestedSecurities": len(securities),
        "eniuCompaniesWithValidMetrics": security_coverage,
        "comparisonMethod": "XSHG sessions only; provider's last valid observation per calendar month; relative errors on positive values",
        "aggregateComparisons": metric_summary,
        "securityComparisons": per_security,
        "interpretation": {
            "peTtm": "Eniu explicit pe_ttm candidate; compare to Baidu PE-TTM and Eastmoney PE-TTM.",
            "pb": "Eniu pb candidate; compare to Baidu PB and Eastmoney PB-MRQ.",
            "psRaw_vs_Eastmoney_psTtm": "Diagnostic only. Eniu raw 'ps' basis is not proven TTM; do not merge as PS-TTM even if values correlate.",
        },
        "warning": "This report is an overlap/consistency audit only; it does not authorize merging candidate series into the official monthly file.",
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "requestedSecurities": len(securities),
        "eniuCompaniesWithValidMetrics": security_coverage,
        "aggregateComparisons": metric_summary,
        "output": str(path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
