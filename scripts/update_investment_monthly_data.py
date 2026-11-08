#!/usr/bin/env python3
"""Refresh the auditable RMB monthly matrix for Investment Lab V2.2.

Canonical return series:
- CSI 300 price and total-return index levels from a public copy that documents
  the official CSIndex 000300 / H00300 sources.
- S&P 500 total-return index (^SP500TR) from a monthly dividend-adjusted series.
- World Bank Pink Sheet gold monthly average USD/oz.
- Federal Reserve G.5 monthly-average EXCHUS (CNY per USD).
- FRED macro indicators, sampled at the final observation in each month.

No interpolation, forward-fill or missing-as-zero is permitted. Incomplete latest
months remain marked partial and their monthly return is blank.
"""
from __future__ import annotations
import csv, io, json, math, time
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "investment-monthly.csv"
MANIFEST = ROOT / "data" / "investment-monthly-manifest.json"
HEADERS = [
    "date",
    "csi300_price_index_cny","csi300_price_return_pct",
    "csi300_total_return_index_cny","csi300_total_return_pct","csi300_period_status",
    "sp500_total_return_index_usd","sp500_total_return_pct","sp500_total_return_cny_pct",
    "gold_usd_oz","gold_cny_per_oz_monthly_avg","gold_cny_return_pct",
    "usd_cny","usd_cny_change_pct",
    "hang_seng_total_return_index_hkd","hang_seng_total_return_pct","hang_seng_total_return_cny_pct",
    "china_bond_wealth_index_cny","china_bond_wealth_return_cny_pct",
    "us_treasury_7_10y_total_return_index_usd","us_treasury_7_10y_total_return_pct","us_treasury_7_10y_total_return_cny_pct",
    "cny_cash_rate_pct","cny_cash_return_pct","us_tbill_1m_return_pct","us_tbill_1m_return_cny_pct",
    "china_cpi_mom_pct","china_cpi_yoy_pct","us_cpi_index","us_cpi_yoy_pct",
    "dgs10_pct","dfii10_pct","dxy_index","vix_index","brent_usd_bbl","fedfunds_pct","china10y_pct",
    "portfolio_return_cny_pct",
    "sp500_shiller_total_return_pct","sp500_shiller_cpi_index"
]
# EXCHUS is the Federal Reserve's monthly-average Chinese yuan per U.S. dollar rate.
# Daily FRED macro series are represented by the final available observation in each month.
FRED_MAP = {
    "EXCHUS":"usd_cny",
    "DGS10":"dgs10_pct","DFII10":"dfii10_pct","DTWEXBGS":"dxy_index",
    "VIXCLS":"vix_index","CPIAUCSL":"us_cpi_index","FEDFUNDS":"fedfunds_pct",
    "DCOILBRENTEU":"brent_usd_bbl"
}
URLS = {
    "csi_index_levels":"https://raw.githubusercontent.com/dongzhaohe321418-lab/csi300-spmo-index/main/output/performance/index_levels.csv",
    "sp500tr":"https://raw.githubusercontent.com/vanexymx/sp500-historical-analysis/main/data/SP500TR_monthly.json",
    "gold":"https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv",
    "shiller":"https://firenum.com/data/shiller-monthly.csv"
}
USER_AGENT="InvestmentLabMonthlyData/2.2 (research; source attribution in manifest)"
TODAY=date.today()

def fetch(url:str,timeout:int=50)->str:
    req=Request(url,headers={"User-Agent":USER_AGENT})
    with urlopen(req,timeout=timeout) as res:
        return res.read().decode("utf-8-sig")

def num(value):
    try:
        x=float(value)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError):
        return None

def prev_month(month:str)->str:
    y,m=map(int,month.split("-"))
    return f"{y-1:04d}-12" if m==1 else f"{y:04d}-{m-1:02d}"

def target_months():
    # Only include completed calendar months; partial latest-source observations are
    # still included in the source columns but not converted into full-month returns.
    y,m=TODAY.year,TODAY.month-1
    if m==0:y,m=y-1,12
    start=2006*12
    stop=y*12+m
    return [f"{n//12:04d}-{n%12+1:02d}" for n in range(start,stop+1)]

def read_existing():
    out={}
    if DATA.exists():
        with DATA.open("r",encoding="utf-8-sig",newline="") as fh:
            for r in csv.DictReader(fh):
                month=str(r.get("date",""))[:7]
                if len(month)==7:
                    out[month]={k:(v or "") for k,v in r.items()}
                    out[month]["date"]=month
    return out

def ensure_rows(rows):
    # A hidden Dec-2005 row is retained only as a predecessor for Jan-2006
    # FX/asset return calculations; it is never written into the matrix output.
    months=[prev_month(target_months()[0])]+target_months()
    for month in months:
        item=rows.setdefault(month,{})
        for field in HEADERS:item.setdefault(field,"")
        item["date"]=month
    keep=set(months)
    return {m:r for m,r in rows.items() if m in keep}

def load_csi_index_levels(rows):
    """Load monthly last-observation levels for CSI 300 price and H00300 total return."""
    text=fetch(URLS["csi_index_levels"])
    monthly={}
    for r in csv.DictReader(io.StringIO(text)):
        dt=r.get("Date","")
        if len(dt)<10:continue
        month=dt[:7]
        p,tr=num(r.get("CSI300")),num(r.get("CSI300_TR"))
        if p is None or tr is None:continue
        monthly[month]={"date":dt,"price":p,"total_return":tr}
    if not monthly:raise RuntimeError("CSI index-level CSV contains no valid observations")
    for month in rows:
        obs=monthly.get(month)
        if not obs:continue
        item=rows[month]
        item["csi300_price_index_cny"]=f'{obs["price"]:.8f}'
        item["csi300_total_return_index_cny"]=f'{obs["total_return"]:.8f}'
        item["csi300_period_status"]="complete"
    last_month=max(monthly)
    last=monthly[last_month]
    try: day=int(last["date"][8:10])
    except (ValueError,TypeError):day=0
    # A latest-source observation well before calendar month-end is partial.
    if day and day<20 and last_month in rows:
        rows[last_month]["csi300_period_status"]="partial_source_cutoff"
        rows[last_month]["csi300_price_return_pct"]=""
        rows[last_month]["csi300_total_return_pct"]=""
    # Calculate monthly returns from the raw source map, including Dec-2005 as a
    # calculation-only predecessor for Jan-2006. Do not require that predecessor
    # to appear as a matrix row.
    for month,item in rows.items():
        prev=monthly.get(prev_month(month));cur=monthly.get(month)
        if not cur or not prev or item.get("csi300_period_status")=="partial_source_cutoff":
            item["csi300_price_return_pct"]=""
            item["csi300_total_return_pct"]=""
            continue
        item["csi300_price_return_pct"]=f'{(cur["price"]/prev["price"]-1)*100:.8f}'
        item["csi300_total_return_pct"]=f'{(cur["total_return"]/prev["total_return"]-1)*100:.8f}'
    return {"monthly_observations":len(monthly),"latest_observation":last["date"],
            "last_source_month":last_month,"price_return_months":sum(bool(x.get("csi300_price_return_pct")) for x in rows.values()),
            "total_return_months":sum(bool(x.get("csi300_total_return_pct")) for x in rows.values())}

def load_sp500_total_return(rows):
    """Load ^SP500TR adjusted monthly total-return index and derive monthly USD returns."""
    payload=json.loads(fetch(URLS["sp500tr"]))
    months=payload.get("months",[]);levels=payload.get("close",[])
    source={m:num(v) for m,v in zip(months,levels) if num(v) is not None and num(v)>0}
    if not source:raise RuntimeError("S&P 500 total-return source is empty")
    for month,item in rows.items():
        level=source.get(month);prior=source.get(prev_month(month))
        if level is not None:item["sp500_total_return_index_usd"]=f"{level:.8f}"
        if level is not None and prior is not None and prior>0:
            item["sp500_total_return_pct"]=f"{(level/prior-1)*100:.8f}"
    return {"monthly_index_observations":len(source),"coverage_start":min(source),"coverage_end":max(source)}

def load_gold_monthly(rows):
    """Load World Bank Pink Sheet monthly average gold price in USD/troy oz."""
    source={}
    for r in csv.DictReader(io.StringIO(fetch(URLS["gold"]))):
        month=(r.get("Date") or "")[:7];price=num(r.get("Price"))
        if len(month)==7 and price is not None and price>0:source[month]=price
    if not source:raise RuntimeError("World Bank gold monthly source is empty")
    for month,item in rows.items():
        v=source.get(month)
        if v is not None:item["gold_usd_oz"]=f"{v:.8f}"
    return {"monthly_observations":len(source),"coverage_start":min(source),"coverage_end":max(source)}

def load_shiller_validation(rows):
    """Keep Shiller/Firenum total returns as an independent validation column."""
    count=0
    for r in csv.DictReader(io.StringIO(fetch(URLS["shiller"]))):
        try:month=f'{int(r["year"]):04d}-{int(r["month"]):02d}'
        except (KeyError,ValueError):continue
        ret,cpi=num(r.get("nominalReturn")),num(r.get("cpi"))
        if month not in rows:continue
        if ret is not None:rows[month]["sp500_shiller_total_return_pct"]=f"{ret*100:.8f}"
        if cpi is not None:rows[month]["sp500_shiller_cpi_index"]=f"{cpi:.8f}"
        if ret is not None:count+=1
    return {"observations":count,"role":"independent_cross_check_not_primary_series"}

def load_fred(rows):
    results={}
    for sid,field in FRED_MAP.items():
        url=f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
        parsed={}
        for r in csv.DictReader(io.StringIO(fetch(url))):
            dt=r.get("observation_date") or r.get("DATE") or r.get("date") or ""
            value=num(r.get(sid))
            if len(dt)<7 or value is None:continue
            # Rows are chronologically ordered; overwrite each month with its final
            # observation. EXCHUS/FEDFUNDS/CPIAUCSL are monthly source observations.
            parsed[dt[:7]]=value
        for month,value in parsed.items():
            if month in rows:rows[month][field]=f"{value:.8f}"
        results[sid]={"months":len(parsed),"start":min(parsed) if parsed else None,
                      "end":max(parsed) if parsed else None}
        time.sleep(.1)
    return results

def derive_rmb_returns(rows):
    for month,item in rows.items():
        prior=rows.get(prev_month(month),{})
        fx=num(item.get("usd_cny"));pfx=num(prior.get("usd_cny"))
        sp=num(item.get("sp500_total_return_pct"))
        gold=num(item.get("gold_usd_oz"));pgold=num(prior.get("gold_usd_oz"))
        if fx is not None and pfx is not None and pfx>0:
            item["usd_cny_change_pct"]=f"{(fx/pfx-1)*100:.8f}"
        if sp is not None and fx is not None and pfx is not None and pfx>0:
            item["sp500_total_return_cny_pct"]=f"{((1+sp/100)*(fx/pfx)-1)*100:.8f}"
        else:
            item["sp500_total_return_cny_pct"]=""
        if gold is not None and pgold is not None and pgold>0 and fx is not None and pfx is not None and pfx>0:
            curr=gold*fx;prev=pgold*pfx
            item["gold_cny_per_oz_monthly_avg"]=f"{curr:.8f}"
            item["gold_cny_return_pct"]=f"{(curr/prev-1)*100:.8f}"
        else:
            item["gold_cny_per_oz_monthly_avg"]=f"{gold*fx:.8f}" if gold is not None and fx is not None else ""
            item["gold_cny_return_pct"]=""
        # Portfolio return is never manufactured from component proxies.
        item.setdefault("portfolio_return_cny_pct","")

def build_manifest(rows,source_stats,errors):
    manifest={}
    if MANIFEST.exists():
        try:manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
        except json.JSONDecodeError:manifest={}
    coverage={}
    for field in HEADERS[1:]:
        valid=[m for m in sorted(rows) if num(rows[m].get(field)) is not None]
        coverage[field]={"count":len(valid),"start":valid[0] if valid else None,
                         "end":valid[-1] if valid else None}
    manifest.update({
        "dataset_version":"2.2.0",
        "generated_at":datetime.utcnow().replace(microsecond=0).isoformat()+"Z",
        "dataset_file":"data/investment-monthly.csv","frequency":"monthly",
        "row_count":len(rows),"date_start":min(rows),"date_end":max(rows),
        "coverage":coverage,
        "refresh_sources":source_stats,"refresh_errors":errors,
        "portfolio_return_ready":False,
        "matrix_policy":[
            "No forward-fill and no missing-as-zero.",
            "Price returns and total returns remain separate.",
            "USD/CNY uses the Federal Reserve G.5 monthly average EXCHUS series.",
            "USD asset CNY return=(1+rUSD)*(FX_t/FX_t-1)-1.",
            "Gold CNY monthly-average valuation=Gold USD monthly average*USD/CNY monthly average; it is an approximation.",
            "Do not calculate a full 52/28/10/10 portfolio return while HSI TRI, ChinaBond wealth, cash total return or sub-asset target weights are missing."
        ]
    })
    manifest["series"]=[{"field":f,**coverage[f]} for f in HEADERS[1:]]
    # Keep the manually curated source list, gap explanations and rights notes from
    # the committed manifest. Refresh only the numeric coverage fields above.
    return manifest

def main():
    rows=ensure_rows(read_existing())
    source_stats,errors={},{}
    loaders=[
        ("csi300_h00300",lambda:load_csi_index_levels(rows)),
        ("sp500_total_return",lambda:load_sp500_total_return(rows)),
        ("world_bank_gold",lambda:load_gold_monthly(rows)),
        ("fred_macro_and_fx",lambda:load_fred(rows)),
        ("shiller_cross_check",lambda:load_shiller_validation(rows))
    ]
    for name,fn in loaders:
        try:source_stats[name]=fn()
        except Exception as exc:
            errors[name]=f"{type(exc).__name__}: {exc}"
            print(f"[WARN] {name} refresh failed; retained existing observations: {errors[name]}")
    derive_rmb_returns(rows)
    if not rows:raise RuntimeError("No monthly rows; refusing to write empty dataset.")
    months=target_months()
    output_rows={m:rows[m] for m in months}
    with DATA.open("w",encoding="utf-8",newline="") as fh:
        writer=csv.DictWriter(fh,fieldnames=HEADERS,extrasaction="ignore")
        writer.writeheader()
        for m in months:writer.writerow({k:output_rows[m].get(k,"") for k in HEADERS})
    manifest=build_manifest(output_rows,source_stats,errors)
    MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    counts={f:manifest["coverage"][f]["count"] for f in [
        "csi300_price_return_pct","csi300_total_return_pct","sp500_total_return_pct",
        "sp500_total_return_cny_pct","gold_cny_return_pct","usd_cny",
        "hang_seng_total_return_pct","china_bond_wealth_return_cny_pct","cny_cash_return_pct",
        "portfolio_return_cny_pct"
    ]}
    print(json.dumps({"rows":len(rows),"coverage":counts,"sources":source_stats,"errors":errors},ensure_ascii=False,indent=2))
    if not source_stats:raise RuntimeError("All external refresh sources failed; no source observations retrieved.")

if __name__=="__main__":
    main()
