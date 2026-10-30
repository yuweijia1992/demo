#!/usr/bin/env python3
"""Fetch Yahoo Finance monthly valuation-measure histories for the five HK names.

This is a candidate source, deliberately separate from the official monthly
series. Yahoo labels the measures "Trailing P/E", "Price/Book" and
"Price/Sales"; the latter is preserved as psRaw until its TTM basis and
historical consistency are independently validated.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

TICKERS = {
    "00700.HK": "0700.HK",
    "02313.HK": "2313.HK",
    "09988.HK": "9988.HK",
    "09618.HK": "9618.HK",
    "09626.HK": "9626.HK",
}
SOURCE = "Yahoo Finance fundamentals-timeseries monthly valuation measures (candidate)"
URL = "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries"
OUTPUT_COLUMNS = [
    "code", "date", "close", "currency", "peTtm", "pb", "psRaw",
    "psRawBasis", "marketCap", "source", "sourceUrl",
]


def parse_date_label(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw or raw.lower() == "current":
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%b %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def to_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def find_label(frame, candidates: tuple[str, ...]):
    normalized = {re.sub(r"[^a-z]", "", str(idx).lower()): idx for idx in frame.index}
    for candidate in candidates:
        key = re.sub(r"[^a-z]", "", candidate.lower())
        if key in normalized:
            return normalized[key]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/valuation-history/raw/yahoo-hk-candidate.csv")
    parser.add_argument("--audit", default="data/valuation-history/raw/yahoo-hk-fetch-audit.json")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    import yfinance as yf

    rows: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    for index, (code, ticker_symbol) in enumerate(TICKERS.items()):
        page_url = f"https://finance.yahoo.com/quote/{ticker_symbol}/key-statistics/"
        try:
            ticker = yf.Ticker(ticker_symbol)
            frame = ticker.get_valuation_measures(freq="monthly", periods=None)
            if frame is None or frame.empty:
                raise RuntimeError("Yahoo returned an empty monthly valuation-measures DataFrame")
            pe_label = find_label(frame, ("Trailing P/E",))
            pb_label = find_label(frame, ("Price/Book",))
            ps_label = find_label(frame, ("Price/Sales",))
            cap_label = find_label(frame, ("Market Cap",))
            missing_labels = [name for name, label in (("Trailing P/E", pe_label), ("Price/Book", pb_label), ("Price/Sales", ps_label)) if label is None]
            date_columns = []
            for column in frame.columns:
                d = parse_date_label(column)
                if d:
                    date_columns.append((column, d))
            date_columns.sort(key=lambda x: x[1])
            metric_valid = {"peTtm": 0, "pb": 0, "psRaw": 0}
            for column, day in date_columns:
                value = lambda label: to_number(frame.loc[label, column]) if label is not None else None
                pe, pb, ps, cap = value(pe_label), value(pb_label), value(ps_label), value(cap_label)
                if all(x is None for x in (pe, pb, ps)):
                    continue
                if pe is not None and pe > 0:
                    metric_valid["peTtm"] += 1
                if pb is not None and pb > 0:
                    metric_valid["pb"] += 1
                if ps is not None and ps > 0:
                    metric_valid["psRaw"] += 1
                rows.append({
                    "code": code,
                    "date": day,
                    "close": "",
                    "currency": "HKD",
                    "peTtm": "" if pe is None or pe <= 0 else pe,
                    "pb": "" if pb is None or pb <= 0 else pb,
                    "psRaw": "" if ps is None or ps <= 0 else ps,
                    "psRawBasis": "Yahoo Price/Sales; TTM basis to be independently checked",
                    "marketCap": "" if cap is None else cap,
                    "source": SOURCE,
                    "sourceUrl": page_url,
                })
            audits.append({
                "code": code,
                "ticker": ticker_symbol,
                "status": "OK" if rows and any(x["code"] == code for x in rows) else "EMPTY",
                "rowsWritten": sum(1 for x in rows if x["code"] == code),
                "firstDate": date_columns[0][1] if date_columns else None,
                "lastDate": date_columns[-1][1] if date_columns else None,
                "validMetricMonths": metric_valid,
                "fieldLabels": {"peTtm": pe_label, "pb": pb_label, "psRaw": ps_label, "marketCap": cap_label},
                "missingLabels": missing_labels,
                "frameShape": list(frame.shape),
                "frameColumns": [str(x) for x in frame.columns[:12]],
                "sourceUrl": page_url,
            })
            print(f"{code} ({ticker_symbol}): {audits[-1]['status']} rows={audits[-1]['rowsWritten']} dates={audits[-1]['firstDate']}..{audits[-1]['lastDate']}", flush=True)
        except Exception as exc:
            audits.append({
                "code": code, "ticker": ticker_symbol, "status": "REQUEST_ERROR",
                "rowsWritten": 0, "error": str(exc), "sourceUrl": page_url,
            })
            print(f"{code} ({ticker_symbol}): REQUEST_ERROR {exc}", flush=True)
        if index + 1 < len(TICKERS) and args.delay > 0:
            time.sleep(args.delay)

    rows.sort(key=lambda x: (x["code"], x["date"]))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "source": SOURCE,
        "apiFamily": "Yahoo Finance fundamentals-timeseries",
        "apiUrlPattern": URL + "/{symbol}?symbol={symbol}&type=monthlyMarketCap,monthlyPeRatio,monthlyPsRatio,monthlyPbRatio",
        "method": "yfinance.Ticker.get_valuation_measures(freq='monthly', periods=None)",
        "periodStartLimitInCurrentYFinanceImplementation": "2016-12-31",
        "requestedCompanies": len(TICKERS),
        "companiesWithHistory": sum(1 for x in audits if x.get("rowsWritten", 0) > 0),
        "monthlyRowsWritten": len(rows),
        "securityAudits": audits,
        "caveats": [
            "Yahoo monthly measures are independent vendor calculations, not an exchange official record.",
            "Price/Sales is retained as psRaw; it is not relabelled PS-TTM without method/overlap validation.",
            "PE values that are non-positive are left blank, not forced into a valuation percentile.",
            "Yahoo's current yfinance implementation requests valuation time series from 2016-12-31, so this source cannot alone provide 120 full monthly observations at 2026-10.",
            "This source is for the five HK-listed securities only; no ADR or mainland listing is substituted."
        ],
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    audit = Path(args.audit)
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "requestedCompanies": len(TICKERS),
        "companiesWithHistory": summary["companiesWithHistory"],
        "monthlyRowsWritten": len(rows),
        "perSecurity": [{k: x.get(k) for k in ("code", "status", "rowsWritten", "firstDate", "lastDate", "validMetricMonths", "error")} for x in audits],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
