#!/usr/bin/env python3
"""Fetch public Baidu Stock Tong historical valuation series for A/H shares.

A-share data is clipped to pre-2018 to complement Eastmoney without overlapping
its existing daily history. HK data is retained from the earliest returned date.
Only PE-TTM and PB are supplied by this endpoint; PS remains unavailable here.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

A_ENDPOINT = "https://gushitong.baidu.com/opendata"
HK_ENDPOINT = "https://finance.baidu.com/opendata"
A_PAGE = "https://gushitong.baidu.com/stock/ab-{code}"
HK_PAGE = "https://gushitong.baidu.com/stock/hk-{code}"
SOURCE_LABEL = "Baidu Stock Tong / valuation history (AKShare endpoint specification)"
INDICATORS = {"peTtm": ("市盈率(TTM)",), "pb": ("市净率",), "psTtm": ("市销率(TTM)", "市销率")}
COLUMNS = ["code", "date", "close", "currency", "peTtm", "pb", "psTtm", "source", "sourceUrl"]


def load_universe(path: Path) -> list[dict[str, Any]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    return doc.get("securities", [])


def canonical_code(item: dict[str, Any]) -> str:
    return str(item["securityCode"]).strip().upper()


def parse_day(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if len(raw) >= 10 and raw[4] == "-":
            return date.fromisoformat(raw[:10]).isoformat()
        if len(raw) == 8 and raw.isdigit():
            return datetime.strptime(raw, "%Y%m%d").date().isoformat()
        # Handle unix timestamps in seconds or milliseconds if the API changes shape.
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


def build_url(market: str, code: str, indicator: str, period: str) -> str:
    base = A_ENDPOINT if market == "CN" else HK_ENDPOINT
    params = {
        "openapi": "1",
        "dspName": "iphone",
        "tn": "tangram",
        "client": "app",
        "query": indicator,
        "code": code,
        "word": "",
        "resource_id": "51171",
        "market": "ab" if market == "CN" else "hk",
        "tag": indicator,
        "chart_select": period,
        "industry_select": "",
        "skip_industry": "1",
        "finClientType": "pc",
    }
    return base + "?" + urllib.parse.urlencode(params)


def fetch_series(url: str, page_url: str, timeout: int, retries: int) -> list[tuple[str, float | None]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
        "Referer": page_url,
    }
    last_error = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            results = payload.get("Result") or payload.get("result")
            if not isinstance(results, list) or not results:
                raise RuntimeError(f"API returned no Result array: {str(payload)[:300]}")
            chart = (
                results[0].get("DisplayData", {})
                .get("resultData", {})
                .get("tplData", {})
                .get("result", {})
                .get("chartInfo", [])
            )
            if not chart:
                raise RuntimeError(f"API returned no chartInfo: {str(payload)[:300]}")
            body = chart[0].get("body", [])
            output: dict[str, float | None] = {}
            if isinstance(body, dict):
                date_key = next((key for key in ("date", "日期", "x") if key in body), None)
                value_key = next((key for key in ("value", "值", "y") if key in body), None)
                if date_key and value_key:
                    dates = body[date_key] if isinstance(body[date_key], list) else [body[date_key]]
                    values = body[value_key] if isinstance(body[value_key], list) else [body[value_key]]
                    body = list(zip(dates, values))
                else:
                    body = list(body.items())
            for point in body:
                if isinstance(point, (list, tuple)) and len(point) >= 2:
                    raw_day, raw_value = point[0], point[1]
                elif isinstance(point, dict):
                    raw_day = point.get("date") or point.get("日期") or point.get("x")
                    raw_value = point.get("value") or point.get("值") or point.get("y")
                else:
                    continue
                day = parse_day(raw_day)
                if day:
                    output[day] = parse_number(raw_value)
            return sorted(output.items())
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, KeyError, TypeError, RuntimeError) as exc:
            last_error = str(exc)
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(last_error or "unknown Baidu API failure")


def fetch_eniu_series(code: str, metric: str, timeout: int, retries: int) -> tuple[list[tuple[str, float | None]], str]:
    """Fetch Enniu's public HK PE/PB and optional PS chart as an older-history fallback.

    AKShare documents this source as potentially stale. It is therefore used
    only strictly before the earliest dated observation from Baidu for a code.
    """
    suffix = {"peTtm": "peh", "pb": "pbh", "psTtm": "psh"}[metric]
    url = f"https://eniu.com/chart/{suffix}/hk{code}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
        "Referer": f"https://eniu.com/gu/hk{code}/roe",
    }
    last_error = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, dict):
                payload = payload.get("data") or payload.get("result") or []
            if not isinstance(payload, list):
                raise RuntimeError(f"Enniu returned unexpected payload: {str(payload)[:300]}")
            keys = {"peTtm": ("pe", "PE", "pe_ttm", "value"), "pb": ("pb", "PB", "value"), "psTtm": ("ps", "PS", "ps_ttm", "value")}[metric]
            points: dict[str, float | None] = {}
            for point in payload:
                if not isinstance(point, dict):
                    continue
                day = parse_day(point.get("date") or point.get("日期") or point.get("x"))
                raw_value = next((point.get(key) for key in keys if point.get(key) is not None), None)
                if day:
                    points[day] = parse_number(raw_value)
            return sorted(points.items()), url
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, TypeError, RuntimeError) as exc:
            last_error = str(exc)
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(last_error or "unknown Enniu API failure")


def load_excluded(path: Path | None) -> set[tuple[str, str]]:
    excluded: set[tuple[str, str]] = set()
    if not path or not path.exists():
        return excluded
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            code = str(row.get("code") or "").strip().upper()
            day = parse_day(row.get("date"))
            if code and day:
                excluded.add((code, day))
    return excluded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default="data/valuation-history/universe.json")
    parser.add_argument("--output", default="data/valuation-history/raw/baidu-valuation-history.csv")
    parser.add_argument("--audit", default="data/valuation-history/raw/baidu-fetch-audit.json")
    parser.add_argument("--exclude-file", default="data/valuation-history/raw/baostock-pre2018-daily.csv")
    parser.add_argument("--a-share-cutoff", default="2018-01-01")
    parser.add_argument("--period", default="全部", choices=["近一年", "近三年", "近五年", "近十年", "全部"])
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--pause", type=float, default=0.35)
    args = parser.parse_args()

    securities = load_universe(Path(args.universe))
    excluded = load_excluded(Path(args.exclude_file) if args.exclude_file else None)
    cutoff = date.fromisoformat(args.a_share_cutoff)
    output_rows: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    any_codes: set[str] = set()
    hk_codes: set[str] = set()
    a_pre2018_codes: set[str] = set()

    print(f"Fetching Baidu historical PE/PB for {len(securities)} A/H securities; period={args.period}", flush=True)
    for security in securities:
        code = canonical_code(security)
        market = str(security.get("market", "")).upper()
        raw_code = code.split(".")[0]
        if market not in {"CN", "HK"}:
            continue
        page_url = (A_PAGE if market == "CN" else HK_PAGE).format(code=raw_code)
        by_day: dict[str, dict[str, float | None]] = defaultdict(dict)
        day_sources: dict[str, set[str]] = defaultdict(set)
        day_source_urls: dict[str, set[str]] = defaultdict(set)
        for metric, indicator_candidates in INDICATORS.items():
            series: list[tuple[str, float | None]] = []
            attempts: list[dict[str, str]] = []
            chosen_indicator = None
            request_url = ""
            for indicator in indicator_candidates:
                request_url = build_url(market, raw_code, indicator, args.period)
                try:
                    candidate_series = fetch_series(request_url, page_url, args.timeout, args.retries)
                    attempts.append({"indicator": indicator, "status": "OK" if candidate_series else "EMPTY"})
                    if candidate_series:
                        series = candidate_series
                        chosen_indicator = indicator
                        break
                except Exception as exc:
                    attempts.append({"indicator": indicator, "status": "ERROR", "error": str(exc)})
                time.sleep(max(0.0, args.pause))
            for day, value in series:
                if market == "CN" and date.fromisoformat(day) >= cutoff:
                    continue
                by_day[day][metric] = value
                day_sources[day].add(SOURCE_LABEL)
                day_source_urls[day].add(page_url)
            kept = sum(1 for day, _ in series if market != "CN" or date.fromisoformat(day) < cutoff)
            metric_status = "OK" if series else ("ERROR" if attempts and all(x["status"] == "ERROR" for x in attempts) else "EMPTY")
            audits.append({
                "code": code, "market": market, "metric": metric,
                "indicator": chosen_indicator or indicator_candidates[0],
                "indicatorAttempts": attempts,
                "periodRequested": args.period, "rowsReturned": len(series),
                "rowsRetainedForBuild": kept,
                "firstDate": series[0][0] if series else None,
                "lastDate": series[-1][0] if series else None,
                "endpoint": request_url.split("?")[0] if request_url else "",
                "sourceUrl": page_url, "status": metric_status,
                "undocumentedIndicatorProbe": metric == "psTtm",
            })
            print(f"  {code} {metric}: {len(series)} raw points" if series else f"  {code} {metric}: {metric_status}", flush=True)

        # Enniu is a secondary HK-only source. Keep only dates strictly earlier
        # than Baidu's earliest dated point, so no daily observation is silently
        # chosen between two vendors with potentially different valuation bases.
        if market == "HK":
            for metric in ("peTtm", "pb", "psTtm"):
                baidu_metric_dates = [day for day, values in by_day.items() if values.get(metric) is not None]
                baidu_first = min(baidu_metric_dates) if baidu_metric_dates else None
                try:
                    eniu_series, eniu_url = fetch_eniu_series(raw_code, metric, args.timeout, args.retries)
                    eligible = [(day, value) for day, value in eniu_series
                                if (baidu_first is None or date.fromisoformat(day) < date.fromisoformat(baidu_first))
                                and by_day.get(day, {}).get(metric) is None]
                    for day, value in eligible:
                        by_day.setdefault(day, {})[metric] = value
                        day_sources[day].add("Eniu public HK indicator chart (historical fallback)")
                        day_source_urls[day].add(eniu_url)
                    audits.append({
                        "code": code, "market": market, "metric": metric,
                        "source": "Eniu public HK indicator chart", "rowsReturned": len(eniu_series),
                        "rowsRetainedBeforeBaidu": len(eligible),
                        "firstDate": eniu_series[0][0] if eniu_series else None,
                        "lastDate": eniu_series[-1][0] if eniu_series else None,
                        "sourceUrl": eniu_url, "status": "OK" if eniu_series else "EMPTY",
                    })
                except Exception as exc:
                    audits.append({
                        "code": code, "market": market, "metric": metric,
                        "source": "Eniu public HK indicator chart", "rowsReturned": 0,
                        "rowsRetainedBeforeBaidu": 0, "firstDate": None, "lastDate": None,
                        "sourceUrl": f"https://eniu.com/chart/{ {'peTtm': 'peh', 'pb': 'pbh', 'psTtm': 'psh'}[metric] }/hk{raw_code}",
                        "status": "ERROR", "error": str(exc),
                    })
                time.sleep(max(0.0, args.pause))

        for day, values in sorted(by_day.items()):
            if (code, day) in excluded:
                continue
            output_rows.append({
                "code": code, "date": day, "close": "", "currency": security.get("currency", ""),
                "peTtm": values.get("peTtm", ""), "pb": values.get("pb", ""),
                "psTtm": values.get("psTtm", ""),
                "source": " + ".join(sorted(day_sources.get(day) or {SOURCE_LABEL})),
                "sourceUrl": " ; ".join(sorted(day_source_urls.get(day) or {page_url})),
            })
            any_codes.add(code)
            if market == "HK":
                hk_codes.add(code)
            else:
                a_pre2018_codes.add(code)

    output_rows.sort(key=lambda row: (row["code"], row["date"]))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)

    audit_doc = {
        "source": SOURCE_LABEL,
        "sourceDocumentation": "https://github.com/akfamily/akshare/blob/master/docs/data/stock/stock_valuation.md",
        "endpointImplementation": "https://github.com/akfamily/akshare/blob/master/akshare/stock/valuation/stock_zh_valuation_baidu.py",
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "requestedPeriod": args.period,
        "aShareCutoffExclusive": args.a_share_cutoff,
        "requestedCompanies": len(securities),
        "companiesWithAnyData": len(any_codes),
        "aShareCompaniesWithPre2018Data": len(a_pre2018_codes),
        "hkCompaniesWithData": len(hk_codes),
        "dailyRowsWritten": len(output_rows),
        "eniuHistoricalFallbackRows": sum(1 for row in output_rows if row["source"].startswith("Eniu")),
        "aShareRowsArePre2018Only": True,
        "documentedMetrics": ["PE-TTM", "PB"],
        "undocumentedPSProbeLabels": ["市销率(TTM)", "市销率"],
        "metricsWithReturnedRows": sorted({item["metric"] for item in audits if item["status"] == "OK"}),
        "psTtmReturnedByProbe": any(item["metric"] == "psTtm" and item["status"] == "OK" for item in audits),
        "excludedSameDayKeysFromBaoStock": len(excluded),
        "indicators": audits,
        "note": "Baidu documents PE-TTM and PB. The fetcher also probes undocumented PS labels; PS is included only if the endpoint returns dated values. For HK, Enniu PE/PB data is retained only strictly before Baidu's earliest date as a potentially stale historical fallback. A-share rows are clipped before Eastmoney's 2018-onward window; HK rows retain Baidu's full returned history. Failed/empty queries remain visible in the audit; no interpolation or imputation.",
    }
    audit_path = Path(args.audit)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "companiesWithAnyData": audit_doc["companiesWithAnyData"],
        "aShareCompaniesWithPre2018Data": audit_doc["aShareCompaniesWithPre2018Data"],
        "hkCompaniesWithData": audit_doc["hkCompaniesWithData"],
        "dailyRowsWritten": audit_doc["dailyRowsWritten"],
        "failedOrEmptyIndicators": sum(1 for item in audits if item["status"] != "OK"),
        "output": str(output_path), "audit": str(audit_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
