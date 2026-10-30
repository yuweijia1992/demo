#!/usr/bin/env python3
"""Fetch publicly available A-share daily valuation history from Eastmoney.

Source: Eastmoney Data Center RPT_VALUEANALYSIS_DET.
Fields: PE_TTM, PB_MRQ, PS_TTM, CLOSE_PRICE.
No account token is required by this public endpoint. Respect upstream rate limits.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ENDPOINT = "https://datacenter-web.eastmoney.com/api/data/v1/get"
SOURCE_LABEL = "Eastmoney Data Center / RPT_VALUEANALYSIS_DET"


def get_json(url: str, referer: str, retries: int = 2) -> dict[str, Any]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; YumuResearch/1.0; +https://yuweijia1992.github.io/demo/)",
        "Accept": "application/json, text/plain, */*",
        "Referer": referer,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    }
    for attempt in range(retries):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=18) as response:
                raw = response.read()
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("upstream response is not a JSON object")
            return payload
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"request failed after {retries} attempts: {exc}") from exc
            time.sleep((2 ** attempt) + random.uniform(0.2, 0.8))
    raise RuntimeError("unreachable")


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def clean_date(value: Any) -> str:
    raw = as_text(value)
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return raw[:10]
    return raw


def get_code_rows(code: str, max_pages: int = 10) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    url = f"https://data.eastmoney.com/gzfx/detail/{code}.html"
    all_rows: list[dict[str, Any]] = []
    page_size = 5000
    page = 1
    total_pages = 1

    while page <= total_pages and page <= max_pages:
        params = {
            "sortColumns": "TRADE_DATE",
            "sortTypes": "-1",
            "pageSize": str(page_size),
            "pageNumber": str(page),
            "reportName": "RPT_VALUEANALYSIS_DET",
            "columns": "ALL",
            "quoteColumns": "",
            "source": "WEB",
            "client": "WEB",
            "filter": f'(SECURITY_CODE="{code}")',
        }
        request_url = ENDPOINT + "?" + urllib.parse.urlencode(params)
        payload = get_json(request_url, url)
        result = payload.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"{code}: missing result object: {str(payload)[:300]}")
        rows = result.get("data")
        if not isinstance(rows, list):
            raise RuntimeError(f"{code}: result.data is not an array")
        if page == 1:
            try:
                total_pages = max(1, int(result.get("pages") or 1))
            except (TypeError, ValueError):
                total_pages = 1
        all_rows.extend(rows)
        if not rows:
            break
        page += 1
        if page <= total_pages:
            time.sleep(0.35)

    if page > max_pages and total_pages > max_pages:
        raise RuntimeError(f"{code}: API reports {total_pages} pages, above safety cap {max_pages}")

    normalized: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    for row in all_rows:
        date = clean_date(row.get("TRADE_DATE"))
        if not date or date in seen_dates:
            continue
        seen_dates.add(date)
        normalized.append({
            "code": code,
            "date": date,
            "close": as_text(row.get("CLOSE_PRICE")),
            "currency": "CNY",
            "peTtm": as_text(row.get("PE_TTM")),
            "pb": as_text(row.get("PB_MRQ")),
            "psTtm": as_text(row.get("PS_TTM")),
            "source": SOURCE_LABEL,
            "sourceUrl": url,
        })
    normalized.sort(key=lambda x: x["date"])
    audit = {
        "code": code,
        "rows": len(normalized),
        "firstDate": normalized[0]["date"] if normalized else None,
        "lastDate": normalized[-1]["date"] if normalized else None,
        "pages": total_pages,
        "sourceUrl": url,
        "status": "OK" if normalized else "EMPTY",
    }
    return normalized, audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default="data/valuation-history/universe.json")
    parser.add_argument("--output", default="data/valuation-history/raw/eastmoney-a-share-daily.csv")
    parser.add_argument("--audit", default="data/valuation-history/raw/eastmoney-fetch-audit.json")
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--workers", type=int, default=4, help="Concurrent security requests; keep low to respect the public source")
    parser.add_argument("--pause", type=float, default=0.35)
    args = parser.parse_args()

    universe_path = Path(args.universe)
    if not universe_path.exists():
        parser.error(f"universe file not found: {universe_path}")
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    securities = [
        item for item in universe.get("securities", [])
        if item.get("market") == "CN"
        and str(item.get("securityCode", "")).endswith((".SH", ".SZ"))
    ]
    if not securities:
        parser.error("universe contains no A-share securities")

    output_rows: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    def fetch_one(security: dict[str, Any]) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None, str | None]:
        full_code = str(security["securityCode"])
        code = full_code.split(".")[0]
        try:
            rows, audit = get_code_rows(code, max_pages=args.max_pages)
            for row in rows:
                row["code"] = full_code
            time.sleep(max(0.0, args.pause))
            return full_code, rows, audit, None
        except Exception as exc:
            return full_code, [], None, str(exc)

    max_workers = max(1, min(int(args.workers), 6))
    print(f"Fetching {len(securities)} A-share securities with {max_workers} workers.", flush=True)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_one, security): security for security in securities}
        done = 0
        for future in as_completed(futures):
            done += 1
            security = futures[future]
            full_code, rows, audit, error = future.result()
            print(f"[{done}/{len(securities)}] {security['issuerName']} {full_code}: "
                  f"{len(rows)} daily rows" if error is None else
                  f"[{done}/{len(securities)}] {security['issuerName']} {full_code}: ERROR {error}",
                  flush=True)
            output_rows.extend(rows)
            if audit is not None:
                audits.append(audit)
                if audit["status"] != "OK":
                    failures.append({"code": full_code, "error": "empty history"})
            else:
                failures.append({"code": full_code, "error": error or "unknown error"})
                audits.append({"code": full_code, "rows": 0, "status": "ERROR", "error": error or "unknown error"})

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["code", "date", "close", "currency", "peTtm", "pb", "psTtm", "source", "sourceUrl"]
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(output_rows, key=lambda x: (x["code"], x["date"])))

    audit_doc = {
        "source": SOURCE_LABEL,
        "endpoint": ENDPOINT,
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "requestedAshareCompanies": len(securities),
        "companiesWithData": sum(1 for x in audits if x.get("status") == "OK"),
        "dailyRows": len(output_rows),
        "failedCompanies": failures,
        "securities": audits,
        "note": "Raw daily source data. Negative PE values are preserved here and excluded from positive-multiple percentile calculations downstream. Missing values remain blank.",
    }
    audit_path = Path(args.audit)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit_doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "requested": len(securities),
        "withData": audit_doc["companiesWithData"],
        "dailyRows": len(output_rows),
        "failed": failures,
        "csv": str(output_path),
        "audit": str(audit_path),
    }, ensure_ascii=False, indent=2))

    # Keep the audit even when some securities fail; the workflow checks coverage after committing the audit files.\n    return 0


if __name__ == "__main__":
    sys.exit(main())
