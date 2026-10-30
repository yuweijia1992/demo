#!/usr/bin/env python3
"""Probe the legacy public Legulegu single-stock history endpoint.

This is intentionally a *candidate-only* collector. It never feeds the formal
valuation database until field semantics, coverage, and duplicates are reviewed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import time
import http.cookiejar
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

API_URLS = [
    "https://legulegu.com/api/s/base-info/",
]
PAGE_URLS = [
    "https://legulegu.com/s/{code}",
    "https://www.legulegu.com/s/{code}",
]
SOURCE = "Legulegu legacy public single-stock base-info API (candidate; pending validation)"
COLUMNS = ["code", "date", "close", "currency", "peTtm", "pb", "psTtm", "source", "sourceUrl"]

ALIASES = {
    "date": {"tradedate", "date", "tradingdate", "datetime"},
    "close": {"close", "closeprice", "price"},
    "peTtm": {"pettm", "petrailingtwelvemonths", "pe12m"},
    "pb": {"pb", "pbmrq", "pricebook"},
    "psTtm": {"psttm", "pstrailingtwelvemonths", "ps12m"},
}


def token_for(day: date, compact: bool = False) -> str:
    token_date = day.strftime("%Y%m%d") if compact else day.isoformat()
    return hashlib.md5(token_date.encode("utf-8")).hexdigest()


def norm_key(value: Any) -> str:
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())


def parse_date(value: Any) -> str | None:
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


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    raw = str(value).strip().replace(",", "").replace("%", "")
    if raw.lower() in {"", "-", "--", "null", "none", "nan", "n/a", "na"}:
        return None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def bootstrap_legulegu_session(timeout: int, retries: int) -> tuple[Any, str, str, list[str]] | None:
    errors: list[str] = []
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"
    for api_url in API_URLS:
        origin = api_url.split("/api/", 1)[0]
        page_url = origin + "/"
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        for attempt in range(max(1, retries + 1)):
            try:
                with opener.open(urllib.request.Request(page_url, headers=headers), timeout=timeout) as resp:
                    html = resp.read().decode("utf-8", errors="replace")
                match = re.search(
                    r"""<meta[^>]+name=["']_csrf["'][^>]+content=["']([^"']+)["']""",
                    html,
                    flags=re.IGNORECASE,
                )
                if not match:
                    match = re.search(
                        r"""<meta[^>]+content=["']([^"']+)["'][^>]+name=["']_csrf["']""",
                        html,
                        flags=re.IGNORECASE,
                    )
                if not match:
                    raise RuntimeError("homepage did not expose meta[name=_csrf]")
                return opener, match.group(1), api_url, errors
            except Exception as exc:
                errors.append(f"{page_url} bootstrap attempt={attempt+1}: {exc}")
                if attempt < retries:
                    time.sleep(min(2 ** (attempt + 1), 6))
    return None


def request_payload(
    code: str, timeout: int, retries: int,
    session: tuple[Any, str, str] | None,
) -> tuple[dict[str, Any] | None, str, list[str]]:
    attempts: list[str] = []
    if session is None:
        return None, "", ["Legulegu homepage/CSRF bootstrap failed"]
    opener, csrf, api_url = session
    origin = api_url.split("/api/", 1)[0]
    page_url = PAGE_URLS[API_URLS.index(api_url)].format(code=code)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-CSRF-Token": csrf,
        "X-Requested-With": "XMLHttpRequest",
        "Origin": origin,
        "Referer": page_url,
    }
    now_cn = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    token_variants = [
        (now_cn, False), (now_cn, True), (now_cn - timedelta(days=1), False),
        (now_cn - timedelta(days=1), True),
    ]
    for day, compact in token_variants:
        params = urllib.parse.urlencode({"token": token_for(day, compact=compact), "id": code})
        for method in ("POST", "GET"):
            for attempt in range(retries + 1):
                try:
                    if method == "POST":
                        req = urllib.request.Request(api_url, data=params.encode("utf-8"), headers=headers, method="POST")
                    else:
                        req = urllib.request.Request(api_url + "?" + params, headers=headers, method="GET")
                    with opener.open(req, timeout=timeout) as resp:
                        body = resp.read().decode("utf-8", errors="replace")
                    if not body.strip():
                        raise RuntimeError("empty response body")
                    data = json.loads(body)
                    if not isinstance(data, dict):
                        raise RuntimeError(f"unexpected top-level type: {type(data).__name__}")
                    data_block = data.get("data")
                    if not isinstance(data_block, dict) or not isinstance(data_block.get("fields"), list) or not isinstance(data_block.get("items"), list):
                        preview = json.dumps(data, ensure_ascii=False)[:240]
                        attempts.append(f"{method} {api_url} tokenDate={day.isoformat()} returned JSON without data.fields/items: {preview}")
                        continue
                    return data, api_url, attempts
                except urllib.error.HTTPError as exc:
                    attempts.append(f"{method} {api_url} tokenDate={day.isoformat()} status={exc.code}")
                    if exc.code == 429:
                        time.sleep(min(3 * (attempt + 1), 8))
                    elif 500 <= exc.code < 600:
                        time.sleep(min(2 ** (attempt + 1), 6))
                    if attempt < retries and exc.code not in (401, 403):
                        continue
                except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError, OSError) as exc:
                    attempts.append(f"{method} {api_url} tokenDate={day.isoformat()} attempt={attempt+1}: {exc}")
                    if attempt < retries:
                        time.sleep(min(2 ** (attempt + 1), 6))
    return None, "", attempts

def unpack_payload(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return [], []
    fields = data.get("fields")
    items = data.get("items")
    if not isinstance(fields, list) or not isinstance(items, list):
        return [], [str(k) for k in data.keys()]
    field_names = [str(x) for x in fields]
    output: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            output.append({str(k): v for k, v in item.items()})
        elif isinstance(item, (list, tuple)):
            output.append(dict(zip(field_names, item)))
    return output, field_names


def map_row(row: dict[str, Any]) -> dict[str, Any] | None:
    norm = {norm_key(k): v for k, v in row.items()}
    mapped: dict[str, Any] = {}
    for metric, candidates in ALIASES.items():
        key = next((k for k in candidates if k in norm), None)
        mapped[metric] = norm.get(key) if key else None
    day = parse_date(mapped.get("date"))
    if not day:
        return None
    return {
        "date": day,
        "close": parse_number(mapped.get("close")),
        "peTtm": parse_number(mapped.get("peTtm")),
        "pb": parse_number(mapped.get("pb")),
        "psTtm": parse_number(mapped.get("psTtm")),
    }


def load_universe(path: Path) -> list[dict[str, Any]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    return [s for s in doc.get("securities", []) if str(s.get("market", "")).upper() == "CN"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default="data/valuation-history/universe.json")
    parser.add_argument("--output", default="data/valuation-history/raw/legulegu-a-share-candidate.csv")
    parser.add_argument("--audit", default="data/valuation-history/raw/legulegu-fetch-audit.json")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--delay", type=float, default=0.6, help="seconds between securities; keep requests sequential to reduce upstream rate limiting")
    args = parser.parse_args()

    securities = sorted(load_universe(Path(args.universe)), key=lambda x: str(x["securityCode"]))
    all_rows: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []

    boot = bootstrap_legulegu_session(args.timeout, args.retries)
    session = (boot[0], boot[1], boot[2]) if boot else None
    bootstrap_errors = boot[3] if boot else ["Could not establish a public Legulegu homepage session"]

    for index, security in enumerate(securities):
        code = str(security["securityCode"]).split(".")[0]
        payload, api_url, attempts = request_payload(code, args.timeout, args.retries, session)
        if payload is None:
            audit = {
                "code": security["securityCode"], "status": "REQUEST_ERROR",
                "rowsReturned": 0, "rowsWithMappedMetrics": 0,
                "errors": (attempts or bootstrap_errors)[-12:],
                "sourcePage": PAGE_URLS[0].format(code=code),
            }
            rows = []
        else:
            raw_rows, fields = unpack_payload(payload)
            rows = []
            unmapped_non_date_fields: set[str] = set()
            for raw in raw_rows:
                mapped = map_row(raw)
                if mapped is None:
                    continue
                if all(mapped[k] is None for k in ("peTtm", "pb", "psTtm")):
                    unmapped_non_date_fields.update(str(k) for k in raw.keys())
                    continue
                rows.append({
                    "code": security["securityCode"],
                    "date": mapped["date"],
                    "close": "" if mapped["close"] is None else mapped["close"],
                    "currency": "CNY",
                    "peTtm": "" if mapped["peTtm"] is None else mapped["peTtm"],
                    "pb": "" if mapped["pb"] is None else mapped["pb"],
                    "psTtm": "" if mapped["psTtm"] is None else mapped["psTtm"],
                    "source": SOURCE,
                    "sourceUrl": PAGE_URLS[API_URLS.index(api_url)].format(code=code),
                })
            rows.sort(key=lambda x: x["date"])
            valid_counts = {
                metric: sum(1 for x in rows if x[metric] not in ("", None))
                for metric in ("peTtm", "pb", "psTtm")
            }
            audit = {
                "code": security["securityCode"],
                "status": "OK" if rows else ("SCHEMA_UNMAPPED" if raw_rows else "EMPTY"),
                "rowsReturned": len(raw_rows),
                "rowsWithMappedMetrics": len(rows),
                "firstDate": rows[0]["date"] if rows else None,
                "lastDate": rows[-1]["date"] if rows else None,
                "validMetricRows": valid_counts,
                "fieldNames": fields,
                "unmappedFieldsSample": sorted(unmapped_non_date_fields)[:40],
                "apiBase": api_url,
                "sourcePage": PAGE_URLS[API_URLS.index(api_url)].format(code=code),
                "resultCode": payload.get("code", payload.get("status")),
                "message": payload.get("msg", payload.get("message")),
                "errors": attempts[-12:],
            }
        all_rows.extend(rows)
        audits.append(audit)
        print(f"{audit['code']}: {audit['status']} rows={audit.get('rowsWithMappedMetrics',0)}", flush=True)
        if index + 1 < len(securities) and args.delay > 0:
            time.sleep(args.delay)

    all_rows.sort(key=lambda x: (x["code"], x["date"]))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)

    metric_coverage = {
        metric: sum(1 for row in all_rows if row[metric] not in ("", None))
        for metric in ("peTtm", "pb", "psTtm")
    }
    audit_doc = {
        "source": SOURCE,
        "sourceCandidates": API_URLS,
        "sourceReference": "Legacy AKShare and JS clients; current availability probed separately",
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "requestStrategy": "one CSRF/cookie session; sequential requests; date-token variants; 0.6s default delay",
        "requestedAshareCompanies": len(securities),
        "companiesWithMappedRows": sum(1 for x in audits if x.get("rowsWithMappedMetrics", 0) > 0),
        "dailyRowsWritten": len(all_rows),
        "validMetricRows": metric_coverage,
        "bootstrapErrors": bootstrap_errors,
        "securityAudits": audits,
        "warning": "Candidate data remain isolated and are not merged into generated/valuation-monthly.csv until source, metric definitions, duplicates, and point-in-time semantics pass review.",
    }
    audit_path = Path(args.audit)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: audit_doc[k] for k in ("requestedAshareCompanies", "companiesWithMappedRows", "dailyRowsWritten", "validMetricRows")}, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
