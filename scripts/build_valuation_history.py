#!/usr/bin/env python3
"""Build auditable month-end PE/PB/PS history from daily vendor exports.

No network calls, API tokens, interpolation, or synthetic historical values.
Standard-library only.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import exchange_calendars as xcals

METRICS = ("peTtm", "pb", "psTtm")
WINDOWS = {
    "5Y": {"months": 60, "minimum": 60},
    "10Y": {"months": 120, "minimum": 120},
}
ALIASES = {
    "code": ("code", "ts_code", "stockCode", "securityCode", "security_code"),
    "date": ("date", "trade_date", "tradeDate"),
    "close": ("close", "sp", "close_price"),
    "peTtm": ("peTtm", "pe_ttm", "peTtmValue", "peTTM"),
    "pb": ("pb", "pb_lf", "pbMRQ"),
    "psTtm": ("psTtm", "ps_ttm", "psTtmValue", "psTTM"),
    "currency": ("currency", "cur"),
    "source": ("source", "provider", "data_source"),
    "sourceUrl": ("sourceUrl", "source_url", "sourceURL", "url"),
}


def parse_date(value: Any) -> date:
    raw = str(value or "").strip()
    if re.fullmatch(r"\d{8}", raw):
        return datetime.strptime(raw, "%Y%m%d").date()
    return date.fromisoformat(raw[:10])


def month_index(d: date) -> int:
    return d.year * 12 + d.month - 1


def month_label(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def pick(row: dict[str, Any], key: str, default: Any = None) -> Any:
    for alias in ALIASES[key]:
        if alias in row and str(row[alias]).strip() != "":
            return row[alias]
    return default


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    raw = str(value).strip().replace(",", "")
    if raw.lower() in {"", "-", "--", "null", "none", "nan", "n/a", "na"}:
        return None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def canonical_code(value: Any) -> str:
    code = str(value or "").strip().upper()
    if re.fullmatch(r"\d{5}", code):
        return code + ".HK"
    return code


def percentile_rank(values: list[float], current: float) -> float | None:
    if not values or not math.isfinite(current):
        return None
    lower = sum(1 for value in values if value < current)
    equal = sum(1 for value in values if value == current)
    return 100.0 * (lower + 0.5 * equal) / len(values)


def quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def build_exchange_session_maps(end_month: str) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, int]]]:
    """Return expected last trading session by market/month and ordered session indexes."""
    end_first = date.fromisoformat(end_month + "-01")
    if end_first.month == 12:
        end_exclusive = date(end_first.year + 1, 1, 1)
    else:
        end_exclusive = date(end_first.year, end_first.month + 1, 1)
    requested_end = end_exclusive - timedelta(days=1)
    end_day = min(requested_end, date.today()).isoformat()
    start_day = "1999-01-04"
    expected_last: dict[str, dict[str, str]] = {}
    session_indexes: dict[str, dict[str, int]] = {}
    for market, calendar_name in (("CN", "XSHG"), ("HK", "XHKG")):
        calendar = xcals.get_calendar(calendar_name, start=start_day, end=end_day)
        sessions = [str(value)[:10] for value in calendar.sessions_in_range(start_day, end_day)]
        if not sessions:
            raise RuntimeError(f"No exchange sessions returned for {market} ({calendar_name})")
        month_last: dict[str, str] = {}
        for session in sessions:
            month_last[session[:7]] = session
        expected_last[market] = month_last
        session_indexes[market] = {session: index for index, session in enumerate(sessions)}
    return expected_last, session_indexes


def summarize_session_lags(values: list[int]) -> dict[str, Any]:
    ordered = sorted(values)
    if not ordered:
        return {
            "observations": 0, "exactMonthEnd": 0, "lag1to2Sessions": 0,
            "lag3to5Sessions": 0, "lag6PlusSessions": 0,
            "medianLagSessions": None, "p90LagSessions": None, "maxLagSessions": None,
        }
    return {
        "observations": len(ordered),
        "exactMonthEnd": sum(value == 0 for value in ordered),
        "lag1to2Sessions": sum(1 <= value <= 2 for value in ordered),
        "lag3to5Sessions": sum(3 <= value <= 5 for value in ordered),
        "lag6PlusSessions": sum(value >= 6 for value in ordered),
        "medianLagSessions": quantile(ordered, 0.5),
        "p90LagSessions": quantile(ordered, 0.9),
        "maxLagSessions": max(ordered),
    }


def csv_write(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, help="Daily valuation CSV; may be repeated for non-overlapping sources")
    parser.add_argument("--universe", default="data/valuation-history/universe.json")
    parser.add_argument("--out-dir", default="data/valuation-history/generated")
    parser.add_argument("--start-month", default=None)
    parser.add_argument("--end-month", default=None)
    parser.add_argument("--source-label", default="")
    parser.add_argument("--source-url", default="")
    args = parser.parse_args()

    universe_path = Path(args.universe)
    input_paths = [Path(value) for value in args.input]
    out_dir = Path(args.out_dir)
    if not universe_path.exists():
        parser.error(f"universe file not found: {universe_path}")
    for input_path in input_paths:
        if not input_path.exists():
            parser.error(f"input file not found: {input_path}")

    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    universe_range = universe.get("range", {})
    start_month = args.start_month or universe_range.get("startMonth", "2006-01")
    end_month = args.end_month or universe_range.get("endMonth") or datetime.now().strftime("%Y-%m")
    if not re.fullmatch(r"\d{4}-\d{2}", start_month) or not re.fullmatch(r"\d{4}-\d{2}", end_month):
        parser.error("--start-month / --end-month must use YYYY-MM")
    start_idx = month_index(date.fromisoformat(start_month + "-01"))
    end_idx = month_index(date.fromisoformat(end_month + "-01"))
    if start_idx > end_idx:
        parser.error("start-month must not be later than end-month")

    securities = universe.get("securities", [])
    by_code = {canonical_code(item["securityCode"]): item for item in securities}
    if len(by_code) != len(securities):
        parser.error("duplicate securityCode in universe.json")

    daily: dict[str, dict[date, dict[str, Any]]] = defaultdict(dict)
    invalid_dates = 0
    unknown_codes: set[str] = set()
    duplicate_identical = 0
    duplicate_conflicts: list[str] = []
    invalid_values = defaultdict(int)
    missing_provenance = 0
    currency_mismatches: list[str] = []
    input_rows = 0

    for input_path in input_paths:
        with input_path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            headers = set(reader.fieldnames or [])
            if not any(alias in headers for alias in ALIASES["code"]):
                parser.error(f"{input_path}: missing code/ts_code/stockCode")
            if not any(alias in headers for alias in ALIASES["date"]):
                parser.error(f"{input_path}: missing date/trade_date")
            for row_number, row in enumerate(reader, start=2):
                input_rows += 1
                raw_code = pick(row, "code")
                code = canonical_code(raw_code)
                if code not in by_code:
                    unknown_codes.add(code or f"(blank row {input_path}:{row_number})")
                    continue
                try:
                    day = parse_date(pick(row, "date"))
                except Exception:
                    invalid_dates += 1
                    continue
                idx = month_index(day)
                if idx < start_idx or idx > end_idx:
                    continue
                source = str(pick(row, "source", args.source_label) or "").strip()
                source_url = str(pick(row, "sourceUrl", args.source_url) or "").strip()
                if not source or not source_url.startswith(("https://", "http://")):
                    missing_provenance += 1
                    continue

                expected_currency = str(by_code[code].get("currency", "")).strip().upper()
                row_currency = str(pick(row, "currency", expected_currency) or expected_currency).strip().upper()
                currency_aliases = {"RMB": "CNY", "CNH": "CNY"}
                row_currency = currency_aliases.get(row_currency, row_currency)
                if expected_currency and row_currency and row_currency != expected_currency:
                    currency_mismatches.append(f"{code} {day.isoformat()}: expected {expected_currency}, got {row_currency}")
                    continue

                record: dict[str, Any] = {
                    "code": code,
                    "issuerName": by_code[code]["issuerName"],
                    "date": day.isoformat(),
                    "month": month_label(idx),
                    "close": as_float(pick(row, "close")),
                    "currency": row_currency or expected_currency,
                    "source": source,
                    "sourceUrl": source_url,
                }
                for metric in METRICS:
                    raw = as_float(pick(row, metric))
                    if raw is not None and raw <= 0:
                        invalid_values[metric] += 1
                        raw = None
                    record[metric] = raw

                existing = daily[code].get(day)
                if existing is not None:
                    # Eastmoney is the preferred source from 2018 onward; BaoStock backfill ends in 2017.
                    same_metrics = all(existing.get(k) == record.get(k) for k in ("close", "peTtm", "pb", "psTtm"))
                    if same_metrics:
                        duplicate_identical += 1
                    else:
                        duplicate_conflicts.append(f"{code} {day.isoformat()} ({existing.get('source')} vs {record.get('source')})")
                    continue
                daily[code][day] = record

    if duplicate_conflicts:
        sample = ", ".join(duplicate_conflicts[:10])
        parser.error(f"conflicting duplicate security/date rows ({len(duplicate_conflicts)}); examples: {sample}")
    if currency_mismatches:
        sample = "; ".join(currency_mismatches[:10])
        parser.error(f"security currency mismatch ({len(currency_mismatches)}); examples: {sample}")
    if missing_provenance:
        parser.error(
            f"{missing_provenance} rows have no source label or valid sourceUrl. "
            "Use per-row source/sourceUrl columns or --source-label and --source-url."
        )

    expected_last_session, session_indexes = build_exchange_session_maps(end_month)
    monthly_rows: list[dict[str, Any]] = []
    audit_securities: list[dict[str, Any]] = []

    for code, dates in daily.items():
        grouped: dict[str, dict[str, Any]] = {}
        for day, record in dates.items():
            key = record["month"]
            if key not in grouped or day > date.fromisoformat(grouped[key]["date"]):
                grouped[key] = record
        series = sorted(grouped.values(), key=lambda x: x["date"])
        market = str(by_code[code].get("market", "CN")).upper()
        market_session_index = session_indexes.get(market, {})
        market_expected_last = expected_last_session.get(market, {})
        security_lags: list[int] = []

        for position, record in enumerate(series):
            current_idx = month_index(date.fromisoformat(record["date"]))
            output = dict(record)
            expected_last = market_expected_last.get(record["month"])
            actual_day = record["date"]
            if expected_last and actual_day in market_session_index and expected_last in market_session_index:
                lag_sessions = market_session_index[expected_last] - market_session_index[actual_day]
                if lag_sessions >= 0:
                    security_lags.append(lag_sessions)
                else:
                    lag_sessions = None
            else:
                lag_sessions = None
            output["expectedLastTradingDate"] = expected_last
            output["monthEndTradingSessionLag"] = lag_sessions
            output["isExactMonthEndObservation"] = (lag_sessions == 0) if lag_sessions is not None else False
            for metric in METRICS:
                for label, config in WINDOWS.items():
                    lower_idx = current_idx - config["months"] + 1
                    window_values = [
                        item[metric] for item in series[: position + 1]
                        if item[metric] is not None
                        and lower_idx <= month_index(date.fromisoformat(item["date"])) <= current_idx
                    ]
                    enough = len(window_values) >= config["minimum"]
                    output[f"{metric}Pct{label}"] = (
                        round(percentile_rank(window_values, record[metric]), 4)
                        if enough and record[metric] is not None else None
                    )
                    output[f"{metric}N{label}"] = len(window_values)
                    if label == "5Y":
                        for q in (20, 50, 80):
                            value = quantile(window_values, q / 100) if enough else None
                            output[f"{metric}P{q}_5Y"] = round(value, 6) if value is not None else None
            monthly_rows.append(output)

        first_idx = month_index(date.fromisoformat(series[0]["date"])) if series else None
        last_idx = month_index(date.fromisoformat(series[-1]["date"])) if series else None
        expected = last_idx - first_idx + 1 if series else 0
        missing_months = max(0, expected - len(series))
        audit_securities.append({
            "code": code,
            "issuerName": by_code[code]["issuerName"],
            "market": by_code[code]["market"],
            "currency": by_code[code]["currency"],
            "monthlyRows": len(series),
            "firstMonth": series[0]["month"] if series else None,
            "lastMonth": series[-1]["month"] if series else None,
            "missingCalendarMonthsBetweenFirstAndLast": missing_months,
            "peTtmValidMonths": sum(x["peTtm"] is not None for x in series),
            "pbValidMonths": sum(x["pb"] is not None for x in series),
            "psTtmValidMonths": sum(x["psTtm"] is not None for x in series),
            "monthEndSessionLag": summarize_session_lags(security_lags),
            "sourceLabels": sorted({x["source"] for x in series}),
            "sourceUrls": sorted({x["sourceUrl"] for x in series}),
        })

    monthly_rows.sort(key=lambda x: (x["code"], x["date"]))
    columns = ["code", "issuerName", "date", "month", "expectedLastTradingDate", "monthEndTradingSessionLag", "isExactMonthEndObservation", "close", "currency", "peTtm", "pb", "psTtm", "source", "sourceUrl"]
    for metric in METRICS:
        for label in ("5Y", "10Y"):
            columns.extend((f"{metric}Pct{label}", f"{metric}N{label}"))
        columns.extend((f"{metric}P20_5Y", f"{metric}P50_5Y", f"{metric}P80_5Y"))

    csv_write(out_dir / "valuation-monthly.csv", monthly_rows, columns)

    covered_codes = {row["code"] for row in monthly_rows}
    latest_by_code: dict[str, dict[str, Any]] = {}
    for row in monthly_rows:
        code = row["code"]
        if code not in latest_by_code or latest_by_code[code]["date"] < row["date"]:
            latest_by_code[code] = row
    latest_percentile_coverage = {
        metric: {
            "5Y": sum(1 for row in latest_by_code.values() if row.get(f"{metric}Pct5Y") is not None),
            "10Y": sum(1 for row in latest_by_code.values() if row.get(f"{metric}Pct10Y") is not None),
        }
        for metric in METRICS
    }
    latest_exact_month_end_coverage = {
        metric: {
            "5Y": sum(1 for row in latest_by_code.values() if row.get("monthEndTradingSessionLag") == 0 and row.get(f"{metric}Pct5Y") is not None),
            "10Y": sum(1 for row in latest_by_code.values() if row.get("monthEndTradingSessionLag") == 0 and row.get(f"{metric}Pct10Y") is not None),
        }
        for metric in METRICS
    }
    latest_within_5_sessions_coverage = {
        metric: {
            "5Y": sum(1 for row in latest_by_code.values() if row.get("monthEndTradingSessionLag") is not None and row["monthEndTradingSessionLag"] <= 5 and row.get(f"{metric}Pct5Y") is not None),
            "10Y": sum(1 for row in latest_by_code.values() if row.get("monthEndTradingSessionLag") is not None and row["monthEndTradingSessionLag"] <= 5 and row.get(f"{metric}Pct10Y") is not None),
        }
        for metric in METRICS
    }
    overall_lags = [row["monthEndTradingSessionLag"] for row in monthly_rows if row.get("monthEndTradingSessionLag") is not None]
    lag_by_market = {
        market: summarize_session_lags([
            row["monthEndTradingSessionLag"] for row in monthly_rows
            if row.get("monthEndTradingSessionLag") is not None
            and str(by_code[row["code"]].get("market", "CN")).upper() == market
        ])
        for market in ("CN", "HK")
    }
    coverage = {
        "title": "中国49家公司历史估值月度序列覆盖审计",
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputFiles": [str(path) for path in input_paths],
        "universeFile": str(universe_path),
        "period": {"startMonth": start_month, "endMonth": end_month},
        "frequency": "latest observed valid exchange-session row per calendar month; actual last-session lag is audited separately",
        "calendarAudit": {
            "calendarSource": "exchange_calendars XSHG + XHKG",
            "byMarket": lag_by_market,
            "overall": summarize_session_lags(overall_lags),
            "latestObservationExactMonthEndCompanies": sum(1 for row in latest_by_code.values() if row.get("monthEndTradingSessionLag") == 0),
            "latestObservationWithin5SessionsCompanies": sum(1 for row in latest_by_code.values() if row.get("monthEndTradingSessionLag") is not None and row["monthEndTradingSessionLag"] <= 5),
        },
        "inputDailyRowsRead": input_rows,
        "monthlyRowsWritten": len(monthly_rows),
        "companiesInUniverse": len(securities),
        "companiesWithHistory": len(covered_codes),
        "companiesWithoutHistory": sorted(set(by_code) - covered_codes),
        "unknownOrNonPrimaryCodes": sorted(unknown_codes),
        "invalidDateRows": invalid_dates,
        "identicalDuplicateRowsIgnored": duplicate_identical,
        "invalidNonPositiveValuesSetNull": dict(invalid_values),
        "percentileMethod": "100 * (count(x < current) + 0.5 * count(x == current)) / N",
        "windows": WINDOWS,
        "latestMonthEndPercentileCoverage": latest_percentile_coverage,
        "latestExactMonthEndPercentileCoverage": latest_exact_month_end_coverage,
        "latestWithin5TradingSessionsPercentileCoverage": latest_within_5_sessions_coverage,
        "securities": sorted(audit_securities, key=lambda x: x["code"]),
        "status": "NO_HISTORICAL_DATA" if not monthly_rows else "REVIEW_AUDIT_BEFORE_PUBLISH",
        "warnings": [
            "No missing month is interpolated.",
            "Only each issuer's primary securityCode is accepted; alternate listings must be a separate security series.",
            "Rows with no source label and valid sourceUrl are rejected.",
            "Negative or zero PE/PB/PS values are excluded from percentile calculations.",
            "A monthly row uses the latest observed in-month exchange-session observation; expected last session and lag are recorded and must be reviewed before calling it a strict month-end close.",
            "Sparse vendor history can omit calendar months or leave an observation several trading sessions before month-end; no missing month is filled or forward-carried."
        ]
    }
    (out_dir / "coverage-audit.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "status": coverage["status"],
        "inputDailyRowsRead": input_rows,
        "monthlyRowsWritten": len(monthly_rows),
        "companiesWithHistory": len(covered_codes),
        "companiesWithoutHistory": coverage["companiesWithoutHistory"],
        "monthEndLagAudit": coverage["calendarAudit"],
        "latestExactMonthEndPercentileCoverage": latest_exact_month_end_coverage,
        "outputs": [str(out_dir / "valuation-monthly.csv"), str(out_dir / "coverage-audit.json")]
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
