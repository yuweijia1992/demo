#!/usr/bin/env python3
"""Fetch official ChinaBond Composite Wealth Index (CBA00201) and merge monthly levels/returns.

The endpoint is the public ChinaBond index query used by the open-source AKShare
implementation. Data-use and redistribution terms remain subject to ChinaBond's terms.
"""
from __future__ import annotations
import csv, json, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
MATRIX=ROOT/"data"/"investment-monthly.csv"
RAW=ROOT/"data"/"sources"/"chinabond-cba00201-monthly.csv"
STATUS=ROOT/"data"/"research"/"chinabond_fetch_status.json"
URL="https://yield.chinabond.com.cn/cbweb-mn/indices/singleIndexQuery"
PARAMS={"indexid":"2c90818811afed8d0111c0c672b31578","qxlxt":"00","zslxt":"CFZS","lx":"1","locale":"zh_CN"}

def fetch():
    query=urllib.parse.urlencode(PARAMS)
    req=urllib.request.Request(URL+"?"+query,headers={
        "User-Agent":"Mozilla/5.0 InvestmentLab research data audit",
        "Accept":"application/json, text/plain, */*",
        "Referer":"https://yield.chinabond.com.cn/cbweb-mn/indices/single_index_query?locale=zh_CN",
    },method="POST")
    with urllib.request.urlopen(req,timeout=35) as response:
        payload=json.loads(response.read().decode("utf-8"))
    series=payload.get("CFZS_00")
    if not isinstance(series,dict) or len(series)<1000:
        raise RuntimeError("ChinaBond response missing CFZS_00 daily series or too few observations")
    daily=[]
    sh=ZoneInfo("Asia/Shanghai")
    for ms,value in series.items():
        dt=datetime.fromtimestamp(int(ms)/1000,tz=timezone.utc).astimezone(sh)
        daily.append((dt.date().isoformat(),float(value)))
    daily.sort()
    monthly={}
    counts={}
    for day,value in daily:
        month=day[:7]
        monthly[month]=(day,value)
        counts[month]=counts.get(month,0)+1
    out=[]
    for month,(last_day,value) in sorted(monthly.items()):
        out.append({"month":month,"last_daily_date":last_day,"wealth_index":value,"daily_observations":counts[month]})
    if not any(x["month"]=="2005-12" for x in out):
        raise RuntimeError("ChinaBond series does not include 2005-12; cannot calculate Jan 2006 return safely")
    return out,len(daily),daily[0][0],daily[-1][0]

def main():
    STATUS.parent.mkdir(parents=True,exist_ok=True)
    try:
        monthly,n_daily,start,end=fetch()
        RAW.parent.mkdir(parents=True,exist_ok=True)
        with RAW.open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=["month","last_daily_date","wealth_index","daily_observations"])
            w.writeheader();w.writerows(monthly)
        by_month={x["month"]:x["wealth_index"] for x in monthly}
        with MATRIX.open("r",encoding="utf-8-sig",newline="") as f:
            reader=csv.DictReader(f); rows=list(reader); fields=list(reader.fieldnames or [])
        for field in ("china_bond_wealth_index_cny","china_bond_wealth_return_cny_pct"):
            if field not in fields: fields.append(field)
        prior=by_month.get("2005-12")
        prior_month="2005-12"
        for row in rows:
            month=row["date"]
            level=by_month.get(month)
            row["china_bond_wealth_index_cny"]="" if level is None else f"{level:.8f}"
            y,m=map(int,month.split("-"))
            expected_prev=f"{y-1}-12" if m==1 else f"{y}-{m-1:02d}"
            if level is None or prior is None or prior_month!=expected_prev:
                row["china_bond_wealth_return_cny_pct"]=""
            else:
                row["china_bond_wealth_return_cny_pct"]=f"{(level/prior-1)*100:.8f}"
            if level is not None:
                prior=level
                prior_month=month
        with MATRIX.open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
        status={"status":"SUCCESS","index_code":"CBA00201","index_name":"ChinaBond Composite Wealth Total Value Index",
          "index_id":"2c90818811afed8d0111c0c672b31578","indicator":"CFZS","frequency":"daily source, month-end last observation",
          "daily_observations":n_daily,"daily_start":start,"daily_end":end,"monthly_observations":len(monthly),
          "monthly_start":monthly[0]["month"],"monthly_end":monthly[-1]["month"],
          "raw_monthly_file":"data/sources/chinabond-cba00201-monthly.csv",
          "matrix_fields":["china_bond_wealth_index_cny","china_bond_wealth_return_cny_pct"],
          "limitation":"Verify index identity/code and permitted use with ChinaBond before redistribution or benchmark/product use."}
    except Exception as exc:
        status={"status":"UNAVAILABLE","error":str(exc),"index_code":"CBA00201",
          "note":"No values were imputed. Existing matrix fields remain blank unless a prior successful fetch populated them."}
        print(json.dumps(status,ensure_ascii=False))
    STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if status["status"]=="SUCCESS":
        print(json.dumps(status,ensure_ascii=False))
if __name__=="__main__":
    main()
