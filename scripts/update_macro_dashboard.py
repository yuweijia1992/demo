#!/usr/bin/env python3
"""Build a resilient macro snapshot from FRED public CSV; missing values stay null."""
import csv, io, json, os, time, urllib.request
from datetime import datetime, timezone, timedelta

SERIES = {
    "us10y_nominal": ("DGS10", "US 10Y Treasury yield", "%"),
    "us10y_real": ("DFII10", "US 10Y real yield", "%"),
    "yield_curve_10y2y": ("T10Y2Y", "US 10Y minus 2Y Treasury spread", "%"),
    "inflation_breakeven_10y": ("T10YIE", "US 10Y breakeven inflation", "%"),
    "inflation_forward_5y5y": ("T5YIFR", "US 5Y5Y forward inflation expectation", "%"),
    "vix": ("VIXCLS", "VIX", "index"),
    "dxy_broad": ("DTWEXBGS", "US dollar broad index", "index"),
    "usdcny": ("DEXCHUS", "USD/CNY", "CNY per USD"),
    "brent": ("DCOILBRENTEU", "Brent crude", "USD/barrel"),
    "fed_funds": ("FEDFUNDS", "Federal funds effective rate", "%"),
    "us_cpi_index": ("CPIAUCSL", "US CPI index (level)", "index"),
    "financial_conditions_nfci": ("NFCI", "Chicago Fed National Financial Conditions Index", "index"),
    "credit_conditions_subindex": ("NFCICREDIT", "Chicago Fed NFCI Credit Subindex (not a spread)", "index"),
    "financial_stress_stl": ("STLFSI4", "St. Louis Fed Financial Stress Index", "index"),
    "financial_stress_kc": ("KCFSI", "Kansas City Financial Stress Index", "index"),
}

def latest(series_id):
    # A short recent window is enough for the live snapshot and avoids multi-decade payloads.
    start = (datetime.now(timezone.utc).date() - timedelta(days=550)).isoformat()
    urls = [
        f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}",
        f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}",
    ]
    errors = []
    for url in urls:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; InvestmentLabResearch/2.0)",
            "Accept": "text/csv,*/*",
            "Cache-Control": "no-cache",
        })
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=25) as response:
                    raw = response.read().decode("utf-8-sig")
                rows = list(csv.DictReader(io.StringIO(raw)))
                for row in reversed(rows):
                    value = row.get(series_id, "")
                    if value and value not in (".", "ND", "nan"):
                        return {"date": row.get("observation_date") or row.get("DATE"),
                                "value": float(value)}
                raise ValueError("No numeric observations in response")
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
    raise RuntimeError(" | ".join(errors[-3:])[:500])

data, errors = {}, {}
# Sequential requests reduce the chance of FRED throttling or timing out concurrent calls.
for key, (sid, label, unit) in SERIES.items():
    try:
        data[key] = {"series_id": sid, "label": label, "unit": unit, **latest(sid)}
    except Exception as exc:
        data[key] = {"series_id": sid, "label": label, "unit": unit,
                     "value": None, "date": None}
        errors[key] = str(exc)[:500]
    time.sleep(0.35)

def alert(key, threshold, level, message, direction="above"):
    item = data.get(key, {})
    value = item.get("value")
    hit = value is not None and (value >= threshold if direction == "above" else value <= threshold)
    return {"level": level, "key": key, "value": value, "threshold": threshold, "message": message} if hit else None

alerts = [
    alert("vix", 30, "high", "VIX达到30：市场波动压力升高，检查组合风险与流动性。"),
    alert("us10y_real", 2.25, "medium", "美国10年期实际利率达到2.25%：重新检查长久期资产估值敏感性。"),
    alert("us10y_nominal", 5, "medium", "美国10年期名义收益率达到5%：检查利率与债券久期风险。"),
    alert("yield_curve_10y2y", 0, "medium", "10Y-2Y利差转正：收益率曲线已脱离倒挂，需结合经济数据判断。"),
    alert("usdcny", 7.3, "medium", "USD/CNY达到7.30：检查人民币计价组合的汇率敞口。"),
    alert("brent", 100, "medium", "布伦特原油达到100美元：关注能源成本与通胀传导。"),
    alert("credit_conditions_subindex", 0, "medium", "Chicago Fed信用条件子指数转正：信用条件较长期均值偏紧（不是信用利差）。"),
    alert("financial_stress_stl", 0, "medium", "St. Louis金融压力指数转正：综合金融市场压力高于长期均值。"),
    alert("financial_stress_kc", 0, "medium", "Kansas City金融压力指数转正：综合金融系统压力高于长期均值。"),
]
payload = {
    "schema_version": "2.0",
    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "timezone": "UTC",
    "status": "ok" if not errors else ("partial" if len(errors) < len(SERIES) else "error"),
    "source": "Federal Reserve Bank of St. Louis FRED public CSV graph endpoint",
    "source_url": "https://fred.stlouisfed.org/",
    "series": data,
    "alerts": [x for x in alerts if x],
    "errors": errors,
    "limitations": [
        "FRED series update frequencies differ; latest observation dates are shown per series.",
        "The snapshot fetches recent observations only; use separately archived history files for backtests.",
        "VIX and some market series may have licensing or redistribution restrictions; this file is a minimal latest-value monitor, not a bulk historical redistribution.",
        "DXY uses the broad trade-weighted dollar index DTWEXBGS, not ICE DXY.",
        "NFCI and NFCICREDIT are financial-conditions indices, not quoted corporate credit spreads or OAS.",
        "STLFSI4 and KCFSI are composite financial-stress indices, not standalone credit spreads.",
        "T10YIE and T5YIFR are market-based breakeven/forward inflation expectations, not direct CPI forecasts.",
        "CPIAUCSL is a seasonally adjusted index level; it is not year-over-year inflation.",
        "This dashboard is monitoring only, not a trading signal or investment recommendation."
    ]
}
os.makedirs("data", exist_ok=True)
tmp = "data/macro-dashboard.json.tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
os.replace(tmp, "data/macro-dashboard.json")
print(json.dumps({"status": payload["status"], "series": len(data),
                  "successful": len(data)-len(errors), "errors": errors,
                  "latest": {k: {"date": v["date"], "value": v["value"]} for k,v in data.items()}},
                 ensure_ascii=False, indent=2))
