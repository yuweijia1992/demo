#!/usr/bin/env python3
"""Probe Enniu's public A-share historical valuation chart endpoints.

Candidate-only: output is deliberately isolated from the formal valuation
database until metric basis, source freshness, calendar coverage, and overlap
against Eastmoney/Baidu have been audited.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

BASE = "https://eniu.com/chart"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"
SOURCE = "Eniu public A-share historical charts (candidate; pending metric-basis review)"
OUT_COLUMNS = [
    "code", "date", "close", "currency", "peTtm", "pb", "psRaw",
    "psRawBasis", "source", "sourceUrl", "peSourceUrl", "pbSourceUrl", "psSourceUrl",
]
METRICS = {
    "peTtm": {"path": "pea", "value_keys": ("pe_ttm", "peTtm"), "basis": "TTM"},
    "pb": {"path": "pba", "value_keys": ("pb",), "basis": "MRQ/Book"},
    "psRaw": {"path": "psa", "value_keys": ("ps",), "basis": "UNVERIFIED"},
    "close": {"path": "pricea", "value_keys": ("price", "close"), "basis": "Price"},
}


def security_symbol(security: dict[str, Any]) -> str:
    code = str(security["securityCode"]).upper()
    if code.endswith(".SH"):
        return "sh" + code.split(".")[0]
    if code.endswith(".SZ"):
        return "sz" + code.split(".")[0]
    raise ValueError(f"Not an A-share security code: {code}")


def parse_day(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
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
    raw = str(value).strip().replace(",", "").replace("%", "")
    if raw.lower() in {"", "-", "--", "null", "none", "nan", "n/a", "na"}:
        return None
    try:
        result = float(raw)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def normalize_payload(payload: Any, value_keys: tuple[str, ...]) -> tuple[dict[str, float | None], dict[str, Any]]:
    """Handle Enniu's known columnar arrays and row-wise JSON variants."""
    if isinstance(payload, dict):
        container = payload.get("data") or payload.get("result") or payload
        if isinstance(container, dict):
            date_values = container.get("date") or container.get("日期") or container.get("x")
            value_key = next((key for key in value_keys if key in container), None)
            value_values = container.get(value_key) if value_key else None
            if isinstance(date_values, list) and isinstance(value_values, list):
                if len(date_values) != len(value_values):
                    raise RuntimeError(f"date/value array length mismatch: {len(date_values)} vs {len(value_values)}")
                rows = {}
                for day_raw, value_raw in zip(date_values, value_values):
                    day = parse_day(day_raw)
                    if day:
                        rows[day] = number(value_raw)
                return rows, {
                    "shape": "columnar_arrays",
                    "rootKeys": sorted(str(k) for k in container.keys()),
                    "valueField": value_key,
                }
            # Some endpoints wrap row objects in a dict.
            for key in ("items", "rows", "list"):
                if isinstance(container.get(key), list):
                    payload = container[key]
                    break
            else:
                raise RuntimeError(f"unknown object payload schema keys={list(container.keys())[:30]}")
    if isinstance(payload, list):
        rows: dict[str, float | None] = {}
        for point in payload:
            if not isinstance(point, dict):
                continue
            day = parse_day(point.get("date") or point.get("日期") or point.get("x"))
            raw_value = next((point.get(key) for key in value_keys if point.get(key) is not None), None)
            if day:
                rows[day] = number(raw_value)
        return rows, {"shape": "row_objects", "rowCount": len(payload), "valueFields": value_keys}
    raise RuntimeError(f"unexpected JSON payload type: {type(payload).__name__}")


def fetch_chart(
    symbol: str, code: str, metric: str, config: dict[str, Any],
    timeout: int, retries: int,
) -> tuple[dict[str, float | None], dict[str, Any]]:
    url = f"{BASE}/{config['path']}/{symbol}/t/1"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json,text/plain,*/*",
        "Referer": f"https://eniu.com/gu/{symbol}",
    }
    last_error = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                status = response.status
            payload = json.loads(body)
            points, schema = normalize_payload(payload, config["value_keys"])
            return points, {
                "code": code, "metric": metric, "status": "OK" if points else "EMPTY",
                "url": url, "httpStatus": status, "returnedPoints": len(points),
                "firstDate": min(points) if points else None,
                "lastDate": max(points) if points else None,
                "validValues": sum(1 for value in points.values() if value is not None),
                "schema": schema, "error": None,
            }
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, RuntimeError, OSError) as exc:
            last_error = str(exc)
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    return {}, {
        "code": code, "metric": metric, "status": "REQUEST_ERROR",
        "url": url, "returnedPoints": 0, "validValues": 0,
        "error": last_error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default="data/valuation-history/universe.json")
    parser.add_argument("--output", default="data/valuation-history/raw/eniu-a-share-candidate.csv")
    parser.add_argument("--audit", default="data/valuation-history/raw/eniu-a-share-fetch-audit.json")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()

    universe = json.loads(Path(args.universe).read_text(encoding="utf-8"))
    securities = [x for x in universe.get("securities", []) if str(x.get("market", "")).upper() == "CN"]
    requests = []
    for security in securities:
        code = str(security["securityCode"]).upper()
        symbol = security_symbol(security)
        for metric, config in METRICS.items():
            requests.append((symbol, code, metric, config))

    all_series: dict[str, dict[str, dict[str, float | None]]] = {}
    audit_rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 5))) as pool:
        futures = {
            pool.submit(fetch_chart, symbol, code, metric, config, args.timeout, args.retries): (symbol, code, metric, config)
            for symbol, code, metric, config in requests
        }
        for future in as_completed(futures):
            symbol, code, metric, config = futures[future]
            try:
                points, audit = future.result()
            except Exception as exc:
                points = {}
                audit = {"code": code, "metric": metric, "status": "UNEXPECTED_ERROR", "error": str(exc), "returnedPoints": 0}
            all_series.setdefault(code, {})[metric] = points
            audit_rows.append(audit)
            print(f"{code} {metric}: {audit['status']} points={audit.get('returnedPoints',0)}", flush=True)

    output_rows = []
    security_audits = []
    for security in securities:
        code = str(security["securityCode"]).upper()
        series = all_series.get(code, {})
        days = sorted(set().union(*(set(x.keys()) for x in series.values()))) if series else []
        symbol = security_symbol(security)
        page_url = f"https://eniu.com/gu/{symbol}"
        for day in days:
            output_rows.append({
                "code": code,
                "date": day,
                "close": "" if series.get("close", {}).get(day) is None else series["close"][day],
                "currency": "CNY",
                "peTtm": "" if series.get("peTtm", {}).get(day) is None else series["peTtm"][day],
                "pb": "" if series.get("pb", {}).get(day) is None else series["pb"][day],
                "psRaw": "" if series.get("psRaw", {}).get(day) is None else series["psRaw"][day],
                "psRawBasis": "UNVERIFIED_VENDOR_FIELD_ps",
                "source": SOURCE,
                "sourceUrl": page_url,
                "peSourceUrl": f"{BASE}/pea/{symbol}/t/1",
                "pbSourceUrl": f"{BASE}/pba/{symbol}/t/1",
                "psSourceUrl": f"{BASE}/psa/{symbol}/t/1",
            })
        security_audits.append({
            "code": code,
            "symbol": symbol,
            "dailyUnionRows": len(days),
            "firstDate": days[0] if days else None,
            "lastDate": days[-1] if days else None,
            "metrics": {
                metric: {
                    "points": len(series.get(metric, {})),
                    "validValues": sum(1 for v in series.get(metric, {}).values() if v is not None),
                    "firstDate": min(series[metric]) if series.get(metric) else None,
                    "lastDate": max(series[metric]) if series.get(metric) else None,
                }
                for metric in METRICS
            },
        })

    output_rows.sort(key=lambda x: (x["code"], x["date"]))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUT_COLUMNS)
        writer.writeheader()
        writer.writerows(output_rows)

    summary = {
        "source": SOURCE,
        "sourceReference": "Legacy public Eniu chart endpoint mappings in jstarcraft-crawler En(iu).java; candidate source, metric freshness/basis pending verification",
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "requestedAshareCompanies": len(securities),
        "candidateDailyRowsWritten": len(output_rows),
        "companiesWithAnyHistory": sum(1 for x in security_audits if x["dailyUnionRows"] > 0),
        "metricCoverageCompanies": {
            metric: sum(1 for x in security_audits if x["metrics"][metric]["validValues"] > 0)
            for metric in METRICS
        },
        "metrics": audit_rows,
        "securities": security_audits,
        "qualityWarning": "PE-TTM field is explicitly pe_ttm; PB field is pb. PS endpoint returns vendor field ps, but its basis is not confirmed as TTM. Candidate data are not merged into the formal monthly valuation series.",
    }
    audit_path = Path(args.audit)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("requestedAshareCompanies", "candidateDailyRowsWritten", "companiesWithAnyHistory", "metricCoverageCompanies")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
