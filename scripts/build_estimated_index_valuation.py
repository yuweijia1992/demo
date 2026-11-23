#!/usr/bin/env python3
"""Build an explicitly modelled monthly valuation layer for NDX and HSI.

This does NOT reconstruct actual historical index earnings or book value. It
anchors current PE/PB snapshots and backcasts/extends ratios using index price
history plus disclosed constant growth assumptions. Output is kept separate
from observed valuation data and is never merged into valuation-monthly-partial.csv.
"""
from __future__ import annotations
import csv, json, math, statistics, time, urllib.parse, urllib.request
from datetime import datetime, timezone, date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/index-valuation"
SNAPSHOTS = OUT / "public-valuation-snapshots.csv"
PRICE_OUT = OUT / "ndx-hsi-price-proxies-monthly.csv"
EST_OUT = OUT / "ndx-hsi-estimated-monthly.csv"
AUDIT_OUT = OUT / "ndx-hsi-estimated-audit.json"

# Annual earnings/book value growth is an explicit scenario assumption, not a
# reported fact. Ranges are intentionally broad given the sparse anchors.
MODELS = {
    "NDX": {
        "label": "Nasdaq-100",
        "ticker_candidates": ["^NDX", "QQQ"],
        "price_proxy_note": "Yahoo Finance ^NDX index monthly close; QQQ unadjusted close fallback",
        "growth": {"PE": {"base": 0.08, "low": 0.05, "high": 0.11},
                   "PB": {"base": 0.09, "low": 0.06, "high": 0.12}},
        "pb_band_pct": 0.15,
        "confidence": "低：PE来源之间存在明显差异；PB只有单个独立快照"
    },
    "HSI": {
        "label": "恒生指数",
        "ticker_candidates": ["^HSI", "2800.HK"],
        "price_proxy_note": "Yahoo Finance ^HSI index monthly close; 2800.HK unadjusted close fallback",
        "growth": {"PE": {"base": 0.04, "low": 0.02, "high": 0.06},
                   "PB": {"base": 0.05, "low": 0.03, "high": 0.07}},
        "pb_band_pct": 0.10,
        "confidence": "低：估值锚点来自公开页面快照，缺少完整历史财报聚合"
    }
}

def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept": "application/json,text/csv,*/*"
    })
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                return resp.read()
        except Exception as exc:
            last = exc
            if attempt < 3:
                time.sleep(2 ** attempt)
    raise RuntimeError(str(last))

def yahoo_monthly(ticker: str):
    encoded = urllib.parse.quote(ticker, safe="")
    errors = []
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = f"https://{host}/v8/finance/chart/{encoded}?range=max&interval=1mo&events=div%2Csplits"
        try:
            payload = json.loads(fetch(url).decode("utf-8"))
            result = payload.get("chart", {}).get("result") or []
            if not result:
                raise RuntimeError(str(payload.get("chart", {}).get("error")))
            item = result[0]
            timestamps = item.get("timestamp") or []
            quote = (item.get("indicators", {}).get("quote") or [{}])[0]
            closes = quote.get("close") or []
            rows = {}
            for ts, close in zip(timestamps, closes):
                if close is None or not math.isfinite(float(close)) or float(close) <= 0:
                    continue
                month = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m")
                rows[month] = float(close)
            if len(rows) < 24:
                raise RuntimeError(f"only {len(rows)} monthly closes")
            return rows, host
        except Exception as exc:
            errors.append(f"{host}: {exc}")
    raise RuntimeError(" | ".join(errors))

def read_snapshots():
    out = []
    if not SNAPSHOTS.exists():
        return out
    with SNAPSHOTS.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                v = float(row.get("value", ""))
                if v > 0:
                    row["value_num"] = v
                    out.append(row)
            except Exception:
                pass
    return out

def get_anchor(snapshots, index, metric):
    rows = [r for r in snapshots if r.get("index") == index and r.get("metric") == metric]
    if not rows:
        defaults = {
            ("NDX", "PE_TTM"): [("2026-11-12", 26.97, "Guchacha"), ("2026-11-12", 29.83, "WorldPEratio QQQ NAV proxy"), ("2026-10-31", 32.76, "Siblis")],
            ("NDX", "PB"): [("2026-11-12", 8.43, "Guchacha")],
            ("HSI", "PE_TTM"): [("2026-11-11", 10.80, "Guchacha"), ("2026-11-11", 10.93, "Guchacha")],
            ("HSI", "PB"): [("2026-11-11", 1.14, "Guchacha"), ("2026-11-11", 1.15, "Guchacha")],
        }
        rows = [{"date": d, "value_num": v, "source": s} for d, v, s in defaults.get((index, metric), [])]
    if not rows:
        raise RuntimeError(f"Missing snapshot anchor for {index} {metric}")
    latest_day = max(r["date"] for r in rows)
    latest_dt = date.fromisoformat(latest_day)
    # Keep only observations within 31 days of the latest snapshot; different
    # provider methodologies remain visible in the audit and in the envelope.
    recent = [r for r in rows if (latest_dt - date.fromisoformat(r["date"])).days <= 31]
    values = [r["value_num"] for r in recent]
    central = statistics.median(values)
    return {
        "date": latest_day,
        "anchor_value": round(central, 6),
        "low": min(values),
        "high": max(values),
        "sources": [{"date": r["date"], "value": r["value_num"], "source": r.get("source", "")} for r in recent],
        "n": len(values)
    }

def month_no(s):
    y, m = map(int, s.split("-"))
    return y * 12 + m

def month_label(n):
    y = (n - 1) // 12
    m = (n - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"

def complete_month_grid(observed):
    """Create a monthly price-proxy grid; intervening values are explicitly interpolated."""
    keys = sorted(observed)
    if len(keys) < 2:
        raise RuntimeError("At least two provider price observations are required")
    first, last = month_no(keys[0]), month_no(keys[-1])
    obs_nums = [month_no(k) for k in keys]
    grid, quality = {}, {}
    for n in range(first, last + 1):
        month = month_label(n)
        if month in observed:
            grid[month] = float(observed[month])
            quality[month] = "provider_observation"
            continue
        lefts = [x for x in obs_nums if x < n]
        rights = [x for x in obs_nums if x > n]
        if not lefts or not rights:
            continue
        left, right = max(lefts), min(rights)
        m0, m1 = month_label(left), month_label(right)
        weight = (n - left) / (right - left)
        # Log-linear interpolation maintains positive prices and smooth compound growth.
        grid[month] = math.exp(math.log(float(observed[m0])) * (1-weight) +
                               math.log(float(observed[m1])) * weight)
        quality[month] = "log_linear_interpolation_between_sparse_provider_points"
    return grid, quality, max((b-a for a,b in zip(obs_nums, obs_nums[1:])), default=0)

def main():
    snapshots = read_snapshots()
    price_rows, estimates, audit = [], [], {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "PARTIAL",
        "classification": "MODELLED_ESTIMATE_NOT_OBSERVED_HISTORY",
        "method": "Anchor valuation × (monthly index price proxy / anchor-month price proxy) ÷ assumed earnings/book growth factor; no actual historical index EPS/BVPS reconstruction.",
        "assumptions": {},
        "coverage": {},
        "errors": {},
        "limitations": [
            "所有估计月份均为模型估计，不是历史公布的PE/PB观测，不得称作真实历史估值。",
            "PE估计依赖恒定年化EPS增长率；PB估计依赖恒定年化净资产增长率。实际增长存在周期、减值、回购、成分股变化和会计口径影响。",
            "NDX/HSi指数成分及权重会变化；本模型未重建历史成分股与点时财务信息。",
            "历史分位只表示模型路径内部的相对位置，不能与真实观测分位等同。",
            "估值锚点来自公开页面快照，不同供应商计算口径并不完全一致；范围是情景包络，不是统计置信区间。",
            "指数行情优先使用Yahoo Finance指数月收盘价；备选ETF价格只用于相对价格变化，仍会带来费用、跟踪误差和结构差异。"
        ]
    }
    for index, cfg in MODELS.items():
        try:
            ticker, host = None, None
            closes = None
            failures = []
            for candidate in cfg["ticker_candidates"]:
                try:
                    closes, host = yahoo_monthly(candidate)
                    ticker = candidate
                    break
                except Exception as exc:
                    failures.append(f"{candidate}: {exc}")
            if not closes:
                raise RuntimeError(" ; ".join(failures))
            observed_closes = closes
            closes, price_quality, max_source_gap = complete_month_grid(observed_closes)
            anchor_pe = get_anchor(snapshots, index, "PE_TTM")
            anchor_pb = get_anchor(snapshots, index, "PB")
            anchor_month = anchor_pe["date"][:7]
            # If a ticker has no price candle in the snapshot month, use the latest
            # available month at or before it and disclose the alignment.
            eligible = [m for m in closes if m <= anchor_month]
            if not eligible:
                raise RuntimeError("No price observations on/before valuation anchor month")
            price_anchor_month = max(eligible)
            price_anchor = closes[price_anchor_month]
            growth = cfg["growth"]
            audit["assumptions"][index] = {
                "label": cfg["label"], "ticker_used": ticker, "price_source": f"Yahoo Finance ({host})",
                "price_proxy_note": cfg["price_proxy_note"], "anchor_pe": anchor_pe, "anchor_pb": anchor_pb,
                "price_anchor_month": price_anchor_month, "price_anchor": price_anchor,
                "annual_growth_assumptions": growth, "confidence": cfg["confidence"]
            }
            ordered = sorted(closes.items())
            valid_months = []
            for month, price in ordered:
                if month > max(ordered)[0]:
                    continue
                delta_years = (month_no(anchor_month) - month_no(month)) / 12.0
                ratio = price / price_anchor
                row = {
                    "date": month, "index": index, "index_name": cfg["label"],
                    "price_proxy": round(price, 6), "price_proxy_ticker": ticker,
                    "price_proxy_source": f"Yahoo Finance ({host})",
                    "price_proxy_status": price_quality.get(month, "unknown"),
                    "anchor_date": anchor_pe["date"], "anchor_price_month": price_anchor_month,
                    "status": "MODELLED_ESTIMATE", "confidence": cfg["confidence"]
                }
                for metric, anchor in (("PE_TTM", anchor_pe), ("PB", anchor_pb)):
                    kind = "PE" if metric == "PE_TTM" else "PB"
                    g = growth[kind]
                    month_year_gap = (month_no(month) - month_no(anchor_month)) / 12.0
                    base = anchor["anchor_value"] * ratio / ((1 + g["base"]) ** month_year_gap)
                    # Explicitly envelope anchor source dispersion and growth scenarios.
                    anchor_low, anchor_high = anchor["low"], anchor["high"]
                    if kind == "PB" and anchor["n"] == 1:
                        # One PB snapshot cannot identify source dispersion; apply a disclosed model band.
                        anchor_low = anchor["anchor_value"] * (1 - cfg["pb_band_pct"])
                        anchor_high = anchor["anchor_value"] * (1 + cfg["pb_band_pct"])
                    scenario = []
                    for a in (anchor_low, anchor_high):
                        for rate in (g["low"], g["high"]):
                            scenario.append(a * ratio / ((1 + rate) ** month_year_gap))
                    low, high = min(scenario), max(scenario)
                    row[metric] = round(base, 4)
                    row[metric + "_low"] = round(low, 4)
                    row[metric + "_high"] = round(high, 4)
                    row[metric + "_anchor"] = anchor["anchor_value"]
                    row[metric + "_growth_base"] = g["base"]
                    row[metric + "_growth_low"] = g["low"]
                    row[metric + "_growth_high"] = g["high"]
                    row[metric + "_anchor_sources"] = "; ".join(
                        f'{s["source"]} {s["date"]}={s["value"]}' for s in anchor["sources"])
                estimates.append(row)
                valid_months.append(row)
            # Rolling model-internal empirical percentiles; no claim of actual-data rank.
            valid_months.sort(key=lambda x: x["date"])
            for i, row in enumerate(valid_months):
                for years, window in (("5Y", 60), ("10Y", 120)):
                    sample = [x for x in valid_months[max(0, i-window+1):i+1]]
                    if len(sample) >= window:
                        for metric in ("PE_TTM", "PB"):
                            vals = [x[metric] for x in sample]
                            row[metric + "_" + years + "_estimated_percentile"] = round(
                                100 * sum(v <= row[metric] for v in vals) / len(vals), 2)
                        row[years + "_sample_n"] = len(sample)
                    else:
                        row[years + "_sample_n"] = len(sample)
                        row["PE_TTM_" + years + "_estimated_percentile"] = ""
                        row["PB_" + years + "_estimated_percentile"] = ""
            for month, close in ordered:
                price_rows.append({"date": month, "index": index, "ticker": ticker,
                                   "close": round(close, 6), "frequency": "monthly_grid",
                                   "source": f"Yahoo Finance ({host})",
                                   "source_observation_status": price_quality.get(month, "unknown"),
                                   "status": "price_proxy_not_valuation"})
            audit["coverage"][index] = {
                "ticker_used": ticker, "first_month": ordered[0][0], "last_month": ordered[-1][0],
                "provider_price_observations": len(observed_closes),
                "monthly_grid_observations": len(ordered),
                "interpolated_months": sum(1 for v in price_quality.values() if v != "provider_observation"),
                "max_gap_between_provider_points_months": max_source_gap,
                "price_grid_method": "log-linear interpolation between sparse Yahoo historical points; observed points retained",
                "estimated_valuation_rows": len(valid_months),
                "price_anchor_month": price_anchor_month, "anchor_date": anchor_pe["date"],
                "status": "OK_MODELLED_GRID", "confidence": cfg["confidence"]
            }
        except Exception as exc:
            audit["errors"][index] = str(exc)[:600]
            audit["coverage"][index] = {"status": "ERROR", "error": str(exc)[:600]}
    price_cols = ["date", "index", "ticker", "close", "frequency", "source", "source_observation_status", "status"]
    with PRICE_OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=price_cols); w.writeheader(); w.writerows(price_rows)
    cols = [
        "date", "index", "index_name", "price_proxy", "price_proxy_ticker", "price_proxy_source", "price_proxy_status",
        "anchor_date", "anchor_price_month", "status", "confidence",
        "PE_TTM", "PE_TTM_low", "PE_TTM_high", "PE_TTM_anchor", "PE_TTM_growth_base", "PE_TTM_growth_low", "PE_TTM_growth_high", "PE_TTM_anchor_sources", "PE_TTM_5Y_estimated_percentile", "PE_TTM_10Y_estimated_percentile",
        "PB", "PB_low", "PB_high", "PB_anchor", "PB_growth_base", "PB_growth_low", "PB_growth_high", "PB_anchor_sources", "PB_5Y_estimated_percentile", "PB_10Y_estimated_percentile", "5Y_sample_n", "10Y_sample_n"
    ]
    estimates.sort(key=lambda x: (x["index"], x["date"]))
    with EST_OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(estimates)
    audit["status"] = "OK" if len(audit["coverage"]) == len(MODELS) and not audit["errors"] else "PARTIAL"
    audit["outputs"] = {
        "price_proxy_csv": str(PRICE_OUT.relative_to(ROOT)),
        "estimated_valuation_csv": str(EST_OUT.relative_to(ROOT)),
        "classification": "modelled estimate only; not observed history"
    }
    AUDIT_OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": audit["status"], "coverage": audit["coverage"], "errors": audit["errors"]}, ensure_ascii=False, indent=2))
    if not estimates:
        raise SystemExit("No estimated valuation rows generated; inspect audit errors.")

if __name__ == "__main__":
    main()
