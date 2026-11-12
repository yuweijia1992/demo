#!/usr/bin/env python3
"""Refresh the auditable RMB monthly matrix for Investment Lab V2.5.

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
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode

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
    "hang_seng_etf_2800_total_return_index_hkd","hang_seng_etf_2800_total_return_hkd_pct","hang_seng_etf_2800_total_return_cny_pct","hkd_per_usd",
    "china_bond_wealth_index_cny","china_bond_wealth_return_cny_pct",
    "cny_cash_index_h11025","china_treasury_etf_511010_adj_total_return_index_cny","china_treasury_etf_511010_total_return_cny_pct",
    "us_treasury_7_10y_total_return_index_usd","us_treasury_7_10y_total_return_pct","us_treasury_7_10y_total_return_cny_pct",
    "cny_cash_rate_pct","cny_cash_return_pct","us_tbill_1m_return_pct","us_tbill_1m_return_cny_pct",
    "china_cpi_mom_pct","china_cpi_yoy_pct","us_cpi_index","us_cpi_yoy_pct",
    "dgs10_pct","dfii10_pct","dxy_index","vix_index","brent_usd_bbl","fedfunds_pct","china10y_pct",
    "portfolio_return_cny_pct",
    "sp500_shiller_total_return_pct","sp500_shiller_cpi_index",
    "us_agg_etf_total_return_usd_pct","us_agg_etf_total_return_cny_pct",
    "us_ief_7_10y_etf_total_return_usd_pct","us_ief_7_10y_etf_total_return_cny_pct",
    "us_shy_1_3y_etf_total_return_usd_pct","us_shy_1_3y_etf_total_return_cny_pct",
    "fxi_china_largecap_etf_total_return_usd_pct","fxi_china_largecap_etf_total_return_cny_pct",
    "efa_developed_markets_etf_total_return_usd_pct","efa_developed_markets_etf_total_return_cny_pct",
    "eem_emerging_markets_etf_total_return_usd_pct","eem_emerging_markets_etf_total_return_cny_pct"
]
# EXCHUS is the Federal Reserve's monthly-average Chinese yuan per U.S. dollar rate.
# Daily FRED macro series are represented by the final available observation in each month.
FRED_MAP = {
    "EXHKUS":"hkd_per_usd",
    "DGS10":"dgs10_pct","DFII10":"dfii10_pct","DTWEXBGS":"dxy_index",
    "VIXCLS":"vix_index","CPIAUCSL":"us_cpi_index","FEDFUNDS":"fedfunds_pct",
    "DCOILBRENTEU":"brent_usd_bbl"
}
URLS = {
    "csi_index_levels":"https://raw.githubusercontent.com/dongzhaohe321418-lab/csi300-spmo-index/main/output/performance/index_levels.csv",
    "sp500tr":"https://raw.githubusercontent.com/vanexymx/sp500-historical-analysis/main/data/SP500TR_monthly.json",
    "gold":"https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv",
    "shiller":"https://firenum.com/data/shiller-monthly.csv",
    "exchange_rates_monthly":"https://raw.githubusercontent.com/datasets/exchange-rates/main/data/monthly.csv",
    "yahoo_etf_monthly_returns":"https://raw.githubusercontent.com/HerdingAI/stock-price-returns/main/output/monthly_returns_by_ticker.csv"
}
USER_AGENT="InvestmentLabMonthlyData/2.5 (research; source attribution in manifest)"
ETF_RETURN_FIELDS={
    "AGG":("us_agg_etf_total_return_usd_pct","us_agg_etf_total_return_cny_pct"),
    "IEF":("us_ief_7_10y_etf_total_return_usd_pct","us_ief_7_10y_etf_total_return_cny_pct"),
    "SHY":("us_shy_1_3y_etf_total_return_usd_pct","us_shy_1_3y_etf_total_return_cny_pct"),
    "FXI":("fxi_china_largecap_etf_total_return_usd_pct","fxi_china_largecap_etf_total_return_cny_pct"),
    "EFA":("efa_developed_markets_etf_total_return_usd_pct","efa_developed_markets_etf_total_return_cny_pct"),
    "EEM":("eem_emerging_markets_etf_total_return_usd_pct","eem_emerging_markets_etf_total_return_cny_pct"),
}
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
    stop=y*12+(m-1)
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

def load_yahoo_etf_monthly_returns(rows):
    """Load auto-adjusted ETF total returns (fraction) from the Yahoo data panel."""
    counts={ticker:0 for ticker in ETF_RETURN_FIELDS}
    text=fetch(URLS["yahoo_etf_monthly_returns"],timeout=90)
    for r in csv.DictReader(io.StringIO(text)):
        ticker=(r.get("ticker") or "").upper()
        month=(r.get("date") or "")[:7]
        value=num(r.get("monthly_return"))
        if ticker not in ETF_RETURN_FIELDS or month not in rows or value is None:
            continue
        usd_field,_=ETF_RETURN_FIELDS[ticker]
        rows[month][usd_field]=f"{value*100:.8f}"
        counts[ticker]+=1
    return {"ticker_months":counts,"source":"Yahoo Finance monthly auto-adjusted ETF total returns via HerdingAI dataset"}

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

def load_monthly_fx(rows):
    """Load monthly-average CNY per USD, including Dec-2005 predecessor, from the archived Fed G.5 panel."""
    source={}
    for r in csv.DictReader(io.StringIO(fetch(URLS["exchange_rates_monthly"],timeout=90))):
        if (r.get("Country") or "").strip()!="China":continue
        dt=r.get("Date") or ""
        value=num(r.get("Exchange rate"))
        if len(dt)>=7 and value is not None and value>0:source[dt[:7]]=value
    if not source:raise RuntimeError("monthly USD/CNY archive contains no China observations")
    for month in rows:
        if month in source:rows[month]["usd_cny"]=f"{source[month]:.8f}"
    return {"months":len(source),"coverage_start":min(source),"coverage_end":max(source),
            "source":"datasets/exchange-rates monthly.csv; China, CNY per USD; Fed G.5 monthly average"}
    
def load_cash_h11025(rows):
    """Official CSI money-market fund total-return index; historical values are backfilled to its base date."""
    source={}
    headers={"User-Agent":USER_AGENT,"Referer":"https://www.csindex.com.cn/","X-Requested-With":"XMLHttpRequest","Accept":"application/json, text/javascript, */*; q=0.01"}
    windows=[("20051230","20151231"),("20160101",TODAY.strftime("%Y%m%d")),("20160901","20170331")]
    for start,end in windows:
        url=f"https://www.csindex.com.cn/csindex-home/perf/index-perf?indexCode=H11025&startDate={start}&endDate={end}"
        req=Request(url,headers=headers)
        payload=json.loads(urlopen(req,timeout=90).read().decode("utf-8-sig"))
        items=payload.get("data",[])
        if isinstance(items,dict):items=items.get("data",[])
        for item in items:
            if isinstance(item,dict):
                dt=item.get("tradeDate") or item.get("date") or item.get("日期") or ""
                level=num(item.get("close") or item.get("收盘"))
            elif isinstance(item,(list,tuple)) and len(item)>9:
                dt=item[0];level=num(item[9])
            else:continue
            digits=str(dt).replace("-","").replace("/","")[:8]
            if len(digits)!=8 or level is None or level<=0:continue
            month=digits[:4]+"-"+digits[4:6]
            if month not in source or digits>source[month][0]:source[month]=(digits,level)
    if not source:raise RuntimeError("CSIndex H11025 API returned no valid daily levels")
    for month,item in rows.items():
        if month in source:item["cny_cash_index_h11025"]=f"{source[month][1]:.8f}"
    # H11025 base date is 2005-12-30 with base value 100; calculation predecessor only.
    first=prev_month(target_months()[0])
    if first in rows and first not in source:rows[first]["cny_cash_index_h11025"]="100.00000000"
    for month,item in rows.items():
        prior=rows.get(prev_month(month),{})
        cur=num(item.get("cny_cash_index_h11025"));prev=num(prior.get("cny_cash_index_h11025"))
        item["cny_cash_return_pct"]=f"{(cur/prev-1)*100:.8f}" if cur is not None and prev is not None and prev>0 else ""
    return {"months":len(source),"coverage_start":min(source),"coverage_end":max(source),
            "source":"CSIndex H11025 official daily total-return index; base 2005-12-30; published 2016-08-31"}

def load_yahoo_511010(rows):
    """CNY government-bond ETF proxy using Yahoo auto-adjusted daily close (dividends/splits adjusted)."""
    period2=int(datetime(TODAY.year,TODAY.month,TODAY.day).timestamp())+86400
    url=("https://query1.finance.yahoo.com/v8/finance/chart/511010.SS"
         f"?period1=1362441600&period2={period2}&interval=1d&events=div%2Csplits")
    payload=json.loads(fetch(url,timeout=90))
    result=(payload.get("chart") or {}).get("result") or []
    if not result:raise RuntimeError("Yahoo Finance returned no 511010.SS chart data")
    item=result[0];timestamps=item.get("timestamp") or []
    adj=((item.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
    monthly={}
    for ts,value in zip(timestamps,adj):
        level=num(value)
        if level is None or level<=0:continue
        dt=datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d");month=dt[:7]
        if month not in monthly or dt>monthly[month][0]:monthly[month]=(dt,level)
    if not monthly:raise RuntimeError("Yahoo 511010.SS adjusted-close series is empty")
    for month,row in rows.items():
        if month in monthly:row["china_treasury_etf_511010_adj_total_return_index_cny"]=f"{monthly[month][1]:.8f}"
    for month,row in rows.items():
        prev=rows.get(prev_month(month),{})
        cur=num(row.get("china_treasury_etf_511010_adj_total_return_index_cny"))
        old=num(prev.get("china_treasury_etf_511010_adj_total_return_index_cny"))
        row["china_treasury_etf_511010_total_return_cny_pct"]=f"{(cur/old-1)*100:.8f}" if cur is not None and old is not None and old>0 else ""
    return {"ticker":"511010.SS","months":len(monthly),"coverage_start":min(monthly),"coverage_end":max(monthly),
            "source":"Yahoo Finance adjusted close; CNY-listed 5-year China government bond ETF; ETF proxy, not ChinaBond wealth index"}

def load_hsi_2800_proxy(rows):
    """Tracker Fund of Hong Kong (2800.HK) adjusted-close proxy for HSI dividends reinvested."""
    period2=int(datetime(TODAY.year,TODAY.month,TODAY.day).timestamp())+86400
    url=("https://query1.finance.yahoo.com/v8/finance/chart/2800.HK"
         f"?period1=915148800&period2={period2}&interval=1d&events=div%2Csplits")
    payload=json.loads(fetch(url,timeout=90))
    result=(payload.get("chart") or {}).get("result") or []
    if not result:raise RuntimeError("Yahoo Finance returned no 2800.HK chart data")
    item=result[0];timestamps=item.get("timestamp") or []
    adj=((item.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
    monthly={}
    for ts,value in zip(timestamps,adj):
        level=num(value)
        if level is None or level<=0:continue
        dt=datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d");month=dt[:7]
        if month not in monthly or dt>monthly[month][0]:monthly[month]=(dt,level)
    if not monthly:raise RuntimeError("Yahoo 2800.HK adjusted-close series is empty")
    for month,row in rows.items():
        if month in monthly:row["hang_seng_etf_2800_total_return_index_hkd"]=f"{monthly[month][1]:.8f}"
    for month,row in rows.items():
        prev=rows.get(prev_month(month),{})
        cur=num(row.get("hang_seng_etf_2800_total_return_index_hkd"))
        old=num(prev.get("hang_seng_etf_2800_total_return_index_hkd"))
        row["hang_seng_etf_2800_total_return_hkd_pct"]=f"{(cur/old-1)*100:.8f}" if cur is not None and old is not None and old>0 else ""
        hret=num(row.get("hang_seng_etf_2800_total_return_hkd_pct"))
        hkfx=num(row.get("hkd_per_usd"));phkfx=num(prev.get("hkd_per_usd"))
        usd=num(row.get("usd_cny"));pusd=num(prev.get("usd_cny"))
        if hret is not None and hkfx is not None and phkfx is not None and phkfx>0 and usd is not None and pusd is not None and pusd>0:
            row["hang_seng_etf_2800_total_return_cny_pct"]=f"{((1+hret/100)*(usd/pusd)*(phkfx/hkfx)-1)*100:.8f}"
        else:row["hang_seng_etf_2800_total_return_cny_pct"]=""
    return {"ticker":"2800.HK","months":len(monthly),"coverage_start":min(monthly),"coverage_end":max(monthly),
            "source":"Yahoo Finance adjusted close; Tracker Fund of Hong Kong; HKD total-return ETF proxy, not official Hang Seng TRI"}

def load_chinabond_wealth(rows):
    """Official ChinaBond Aggregate Wealth (Total Value) index CBA00201 via ChinaBond public index endpoint."""
    params={"indexid":"2c90818811afed8d0111c0c672b31578","qxlxt":"00","ltcslx":"","zslxt":"CFZS","zslxt1":"CFZS","lx":"1","locale":"zh_CN"}
    url="https://yield.chinabond.com.cn/cbweb-mn/indices/singleIndexQueryResult"
    headers={"User-Agent":USER_AGENT,"Referer":"https://yield.chinabond.com.cn/cbweb-mn/indices/single_index_query?locale=zh_CN","Accept":"application/json, text/plain, */*","Content-Type":"application/x-www-form-urlencoded; charset=UTF-8"}
    req=Request(url,data=urlencode(params).encode("utf-8"),headers=headers,method="POST")
    payload=json.loads(urlopen(req,timeout=120).read().decode("utf-8-sig"))
    key="CFZS_00";series=payload.get(key)
    if not isinstance(series,dict) or not series:raise RuntimeError(f"ChinaBond CBA00201 endpoint missing {key}; keys={list(payload)[:10]}")
    monthly={}
    for stamp,value in series.items():
        level=num(value)
        if level is None or level<=0:continue
        try:dt=datetime.fromtimestamp(float(stamp)/1000,timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        except Exception:continue
        month=dt[:7]
        if month not in monthly or dt>monthly[month][0]:monthly[month]=(dt,level)
    if not monthly:raise RuntimeError("ChinaBond CBA00201 response contained no valid daily index levels")
    for month,row in rows.items():
        if month in monthly:row["china_bond_wealth_index_cny"]=f"{monthly[month][1]:.8f}"
    for month,row in rows.items():
        prev=rows.get(prev_month(month),{});cur=num(row.get("china_bond_wealth_index_cny"));old=num(prev.get("china_bond_wealth_index_cny"))
        row["china_bond_wealth_return_cny_pct"]=f"{(cur/old-1)*100:.8f}" if cur is not None and old is not None and old>0 else ""
    return {"index_code":"CBA00201","index_name":"中债-综合财富（总值）指数","months":len(monthly),"coverage_start":min(monthly),"coverage_end":max(monthly),
            "source":"ChinaBond official CFZS_00 daily total-wealth index, sampled at final trading day each month"}
def load_fred(rows):
    results={}
    for sid,field in FRED_MAP.items():
        url=f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
        parsed={}
        try:
            fred_csv=fetch(url,timeout=25)
        except Exception as exc:
            results[sid]={"months":0,"error":f"{type(exc).__name__}: {exc}"}
            continue
        for r in csv.DictReader(io.StringIO(fred_csv)):
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
        for usd_field,cny_field in ETF_RETURN_FIELDS.values():
            r_usd=num(item.get(usd_field))
            if r_usd is not None and fx is not None and pfx is not None and pfx>0:
                item[cny_field]=f"{((1+r_usd/100)*(fx/pfx)-1)*100:.8f}"
            else:
                item[cny_field]=""
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
        "dataset_version":"2.5.0",
        "generated_at":datetime.utcnow().replace(microsecond=0).isoformat()+"Z",
        "dataset_file":"data/investment-monthly.csv","frequency":"monthly",
        "row_count":len(rows),"date_start":min(rows),"date_end":max(rows),
        "coverage":coverage,
        "coverage_audit":{k:v for k,v in coverage.items() if k in ["csi300_price_return_pct","csi300_total_return_pct","sp500_total_return_cny_pct","gold_cny_return_pct","usd_cny","hang_seng_total_return_pct","hang_seng_etf_2800_total_return_cny_pct","china_bond_wealth_return_cny_pct","cny_cash_return_pct","portfolio_return_cny_pct","efa_developed_markets_etf_total_return_cny_pct","eem_emerging_markets_etf_total_return_cny_pct","china_treasury_etf_511010_total_return_cny_pct","hkd_per_usd"]},
        "refresh_sources":source_stats,"refresh_errors":errors,
        "portfolio_return_ready":False,
        "matrix_policy":[
            "No forward-fill and no missing-as-zero.",
            "Price returns and total returns remain separate.",
            "EFA is a developed-markets ex-US/Canada ETF proxy; EEM is an emerging-markets ETF proxy. Both are Yahoo auto-adjusted ETF total-return proxies, not official MSCI net/gross index returns.",
            "EEM country holdings include China and Taiwan; do not add EEM to A-share/HK exposures without country/issuer overlap review.",
            "USD/CNY uses the Federal Reserve G.5 monthly average EXCHUS series via the archived datasets/exchange-rates monthly panel.",
            "HKD/CNY conversion uses Federal Reserve G.5 monthly-average EXHKUS (HKD per USD) and USD/CNY: (1+rHKD)*(USD/CNY_t/USD/CNY_prev)*(HKDUSD_prev/HKDUSD_t)-1.",
            "CNY cash proxy uses official CSIndex H11025 money-market fund total-return index; base date 2005-12-30, publication date 2016-08-31; pre-publication history is backfilled.",
            "China government-bond investable proxy uses Yahoo auto-adjusted 511010.SS ETF close; CNY denominated, starts 2013; separate from official ChinaBond wealth index.",
            "USD asset CNY return=(1+rUSD)*(FX_t/FX_t-1)-1.",
            "Gold CNY monthly-average valuation=Gold USD monthly average*USD/CNY monthly average; it is an approximation.",
            "Official HSI gross TRI (HSIDV) remains separate from 2800.HK adjusted ETF proxy; 2800.HK includes fund fees and tracking difference.",
            "ChinaBond CBA00201 is the official aggregate total-wealth index; confirm vendor terms before redistributing source observations.",
            "Do not calculate a full 52/28/10/10 portfolio return while official HSI TRI or approved regional weights are missing."
        ]
    })
    manifest["series"]=[{"field":f,**coverage[f]} for f in HEADERS[1:]]
    manifest["gaps"]=[g for g in manifest.get("gaps",[]) if coverage.get(g.get("field"),{}).get("count",0)==0]
    sources=manifest.get("sources",[])
    if not any("HerdingAI" in str(x.get("source","")) for x in sources):
        sources.append({
            "series":[v[0] for v in ETF_RETURN_FIELDS.values()]+[v[1] for v in ETF_RETURN_FIELDS.values()],
            "name":"Auto-adjusted total-return ETF monthly proxy panel",
            "source":"Yahoo Finance via HerdingAI stock-price-returns dataset",
            "url":"https://github.com/HerdingAI/stock-price-returns",
            "data_url":"https://github.com/HerdingAI/stock-price-returns/blob/main/output/monthly_returns_by_ticker.csv",
            "source_sha":"ee6594efc62cff087fb23cad748c5f114029cbe8",
            "coverage_start":"2006-01","coverage_end":"2026-07",
            "method":"Monthly auto-adjusted ETF returns from Yahoo Finance; CNY conversion=(1+rUSD)*(EXCHUS_t/EXCHUS_t-1)-1.",
            "caveat":"AGG/IEF/SHY/FXI are investable ETF proxies, not official ChinaBond or Hang Seng total-return indices. The repository code is MIT but market data remains subject to Yahoo Finance terms."
        })
    if not any("H11025" in str(x.get("name","")) for x in sources):
        sources.append({"series":["cny_cash_index_h11025","cny_cash_return_pct"],"name":"中证货币基金指数 H11025","source":"中证指数有限公司","url":"https://www.csindex.com.cn/","data_url":"https://www.csindex.com.cn/csindex-home/perf/index-perf?indexCode=H11025","factsheet":"https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/H11025factsheet.pdf","method":"每日官方全收益指数水平取月末值；月收益=本月末指数/上月末指数-1","caveat":"指数发布日期2016-08-31，基日2005-12-30；发布日期前属于回溯历史，不等于当时可投资的实时指数产品。"})
    if not any("CBA00201" in str(x.get("name","")) for x in sources):
        sources.append({"series":["china_bond_wealth_index_cny","china_bond_wealth_return_cny_pct"],"name":"中债-综合财富（总值）指数 CBA00201","source":"中债金融估值中心 / 中国债券信息网","url":"https://yield.chinabond.com.cn/cbweb-mn/indices/single_index_query?locale=zh_CN","data_url":"https://yield.chinabond.com.cn/cbweb-mn/indices/singleIndexQueryResult","method":"官方CFZS_00日度财富指数水平取每月最后交易日；月收益=本月末/上月末-1","caveat":"指数数据再分发和作为业绩基准使用受中债授权条款约束；须核实许可。"});
    if not any("2800.HK" in str(x.get("name","")) for x in sources):
        sources.append({"series":["hang_seng_etf_2800_total_return_index_hkd","hang_seng_etf_2800_total_return_hkd_pct","hang_seng_etf_2800_total_return_cny_pct"],"name":"Tracker Fund of Hong Kong 2800.HK","source":"Yahoo Finance adjusted close","url":"https://finance.yahoo.com/quote/2800.HK/history/","method":"月末adjusted close构造含分红再投资ETF回报，再按HKD/CNY换算","caveat":"可投资ETF代理，不是恒生官方HSIDV总股息累计指数；包含基金费用、跟踪误差及Yahoo数据源风险。"});
    if not any("511010.SS" in str(x.get("name","")) for x in sources):
        sources.append({"series":["china_treasury_etf_511010_adj_total_return_index_cny","china_treasury_etf_511010_total_return_cny_pct"],"name":"国泰上证5年期国债ETF 511010","source":"Yahoo Finance adjusted close","url":"https://finance.yahoo.com/quote/511010.SS/history/","method":"Yahoo auto-adjusted daily close (dividends/splits adjusted), resampled to last trading day each month","caveat":"2013年成立，单只5年期国债ETF代理；不等于中债综合财富指数，数据源可能修订。"})
    return manifest

def main():
    rows=ensure_rows(read_existing())
    source_stats,errors={},{}
    loaders=[
        ("csi300_h00300",lambda:load_csi_index_levels(rows)),
        ("sp500_total_return",lambda:load_sp500_total_return(rows)),
        ("world_bank_gold",lambda:load_gold_monthly(rows)),
        ("monthly_usd_cny",lambda:load_monthly_fx(rows)),
        ("csindex_h11025_cash",lambda:load_cash_h11025(rows)),
        ("yahoo_511010_china_treasury_etf",lambda:load_yahoo_511010(rows)),
        ("chinabond_aggregate_wealth",lambda:load_chinabond_wealth(rows)),
        ("fred_macro_only",lambda:load_fred(rows)),
        ("yahoo_2800_hk_total_return_proxy",lambda:load_hsi_2800_proxy(rows)),
        ("yahoo_etf_total_returns",lambda:load_yahoo_etf_monthly_returns(rows)),
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
