#!/usr/bin/env python3
"""Refresh auditable monthly market/macro observations for Investment Lab V2.1.

Sources:
- Shiller/Firenum monthly S&P composite total returns (CC BY 4.0; attribution required).
- FRED monthly/daily public series, sampled at the last available observation in each month.
- Tencent Finance K-line for CSI 300 daily close; aggregated to calendar month-end.
No interpolation, forward-fill, or missing-as-zero behavior is permitted.
"""
from __future__ import annotations
import csv, io, json, math, time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "investment-monthly.csv"
MANIFEST = ROOT / "data" / "investment-monthly-manifest.json"
HEADERS = [
    "date","csi300_price_index_cny","csi300_price_return_pct","csi300_period_status",
    "sp500_total_return_pct","sp500_cpi_index","hang_seng_price_index_hkd",
    "hang_seng_total_return_pct","china_bond_total_return_index_cny",
    "us_treasury_total_return_index_usd","gold_usd_oz","usd_cny",
    "china_cpi_mom_pct","china_cpi_yoy_pct","us_cpi_index","us_cpi_yoy_pct",
    "dgs10_pct","dfii10_pct","dxy_index","vix_index","brent_usd_bbl",
    "fedfunds_pct","china10y_pct","cn_pmi","us_pmi","us_unemployment_pct",
    "credit_spread_pct","sp500_forward_pe","csi300_pe","cash_rate_cny_pct",
    "portfolio_return_cny_pct"
]
FRED_MAP = {
    "DGS10":"dgs10_pct", "DFII10":"dfii10_pct", "DTWEXBGS":"dxy_index",
    "VIXCLS":"vix_index", "DEXCHUS":"usd_cny", "CPIAUCSL":"us_cpi_index",
    "FEDFUNDS":"fedfunds_pct", "DCOILBRENTEU":"brent_usd_bbl"
}
USER_AGENT = "InvestmentLabMonthlyData/2.1 (research; contact via repository)"
TODAY = date.today()

def fetch(url: str, timeout: int = 40) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8-sig")

def num(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def read_existing():
    out = {}
    if not DATA.exists():
        return out
    with DATA.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            m = str(row.get("date",""))[:7]
            if len(m) == 7:
                out[m] = {k:(row.get(k,"") or "") for k in HEADERS}
                out[m]["date"] = m
    return out

def load_shiller(rows):
    url = "https://firenum.com/data/shiller-monthly.csv"
    text = fetch(url)
    count = 0
    for row in csv.DictReader(io.StringIO(text)):
        try:
            month = f'{int(row["year"]):04d}-{int(row["month"]):02d}'
        except (KeyError, ValueError):
            continue
        ret, cpi = num(row.get("nominalReturn")), num(row.get("cpi"))
        if ret is None:
            continue
        item = rows.setdefault(month, {k:"" for k in HEADERS})
        item["date"] = month
        item["sp500_total_return_pct"] = f"{ret*100:.8f}"
        if cpi is not None:
            item["sp500_cpi_index"] = f"{cpi:.6f}"
        count += 1
    return count

def load_fred(rows):
    results = {}
    for sid, field in FRED_MAP.items():
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={quote(sid)}"
        text = fetch(url)
        parsed = {}
        for row in csv.DictReader(io.StringIO(text)):
            dt = row.get("observation_date") or row.get("DATE") or row.get("date")
            if not dt or len(dt) < 7:
                continue
            # FRED returns one observation per day for daily series, and one per month otherwise.
            value = num(row.get(sid))
            if value is None:
                continue
            parsed[dt[:7]] = value
        for month, value in parsed.items():
            item = rows.setdefault(month, {k:"" for k in HEADERS})
            item["date"] = month
            item[field] = f"{value:.8f}"
        results[sid] = len(parsed)
        time.sleep(0.15)
    return results

def load_csi300(rows):
    daily = {}
    for year in range(2005, TODAY.year + 1):
        start = f"{year}-01-01"
        if year == 2005:
            start = "2005-04-01"
        end = f"{year}-12-31" if year < TODAY.year else TODAY.isoformat()
        param = f"sh000300,day,{start},{end},640,qfq"
        url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=" + quote(param, safe=",")
        payload = json.loads(fetch(url))
        node = payload.get("data", {}).get("sh000300", {})
        candles = node.get("qfqday") or node.get("day") or []
        for item in candles:
            if len(item) < 3:
                continue
            dt = str(item[0])
            close = num(item[2])
            if len(dt) == 10 and close is not None and close > 0:
                daily[dt] = close
        time.sleep(0.25)
    month_end = {}
    for dt, close in sorted(daily.items()):
        month_end[dt[:7]] = (dt, close)
    prev_close = None
    count = 0
    for month, (last_date, close) in sorted(month_end.items()):
        item = rows.setdefault(month, {k:"" for k in HEADERS})
        item["date"] = month
        item["csi300_price_index_cny"] = f"{close:.3f}"
        status = "complete"
        ret = ""
        # The current calendar month is partial until its final calendar day.
        is_current_month = month == TODAY.strftime("%Y-%m")
        if prev_close is None:
            status = "partial_index_start"
        elif is_current_month:
            status = "partial_current_month"
        else:
            ret = f"{(close/prev_close-1)*100:.8f}"
        item["csi300_price_return_pct"] = ret
        item["csi300_period_status"] = status
        # For the next month's return, use this month's latest close.
        prev_close = close
        count += 1
    return {"daily_observations":len(daily),"monthly_rows":count,
            "latest_observation":max(daily) if daily else None}

def main():
    rows = read_existing()
    errors = {}
    stats = {}
    for name, fn in (("shiller_firenum",load_shiller),("fred",load_fred),("csi300_tencent",load_csi300)):
        try:
            stats[name] = fn(rows)
        except Exception as exc:
            errors[name] = f"{type(exc).__name__}: {exc}"
            print(f"[WARN] {name} refresh failed; existing observations retained: {errors[name]}")
    if not rows:
        raise RuntimeError("No monthly rows are available; refusing to write an empty dataset.")
    months = sorted(rows)
    DATA.parent.mkdir(parents=True, exist_ok=True)
    with DATA.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS, extrasaction="ignore")
        writer.writeheader()
        for month in months:
            writer.writerow({k:rows[month].get(k,"") for k in HEADERS})
    coverage = {}
    for field in HEADERS[1:]:
        valid = [m for m in months if num(rows[m].get(field)) is not None]
        coverage[field] = {
            "count":len(valid),
            "start":valid[0] if valid else None,
            "end":valid[-1] if valid else None
        }
    manifest = {}
    if MANIFEST.exists():
        try:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
    manifest.update({
        "dataset_version":"2.1.0",
        "generated_at":datetime.utcnow().replace(microsecond=0).isoformat()+"Z",
        "dataset_file":"data/investment-monthly.csv",
        "frequency":"monthly",
        "row_count":len(months),
        "date_start":months[0],
        "date_end":months[-1],
        "coverage":coverage,
        "refresh_sources":stats,
        "refresh_errors":errors,
        "policy":["No forward-fill","No missing-as-zero","Price return and total return remain separate",
                  "USD asset CNY return must be calculated with matched monthly FX observations"]
    })
    MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"rows":len(months),"coverage":coverage,"sources":stats,"errors":errors},ensure_ascii=False,indent=2))
    if not any(stats.values()):
        raise RuntimeError("All external refresh sources failed; no new observations were retrieved.")

if __name__ == "__main__":
    main()
