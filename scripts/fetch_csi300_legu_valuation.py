#!/usr/bin/env python3
"""Fetch public CSI 300 PE/PB history from Legu via AkShare; no user token required."""
import csv, json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import akshare as ak

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/index-valuation"
RAW=OUT/"raw"
RAW.mkdir(parents=True,exist_ok=True)
CUTOFF=(pd.Timestamp.today().to_period("M")-1).strftime("%Y-%m")
SPECS=[
 ("PE_TTM",ak.stock_index_pe_lg,["滚动市盈率","市盈率TTM","PE-TTM"],"https://legulegu.com/stockdata/sz50-ttm-lyr"),
 ("PB",ak.stock_index_pb_lg,["市净率","PB"],"https://legulegu.com/stockdata/sz50-pb"),
]
allrows=[]
audit={"generated_at":datetime.now(timezone.utc).isoformat(),"cutoff_month":CUTOFF,"source":"Legu Legulegu public valuation pages via AkShare; no user API token","series":{},"errors":{}}
for metric,func,candidates,url in SPECS:
 try:
  df=func(symbol="沪深300")
  if df is None or df.empty: raise RuntimeError("empty source dataframe")
  datecol=next((c for c in ["日期","date","Date"] if c in df.columns),None)
  valcol=next((c for c in candidates if c in df.columns),None)
  if not datecol or not valcol: raise RuntimeError("unexpected columns: "+repr(list(df.columns)))
  raw=RAW/f"csi300_legu_{metric.lower()}_daily.csv"
  df.to_csv(raw,index=False,encoding="utf-8-sig")
  x=df[[datecol,valcol]].copy()
  x.columns=["observed_date","value"]
  x["observed_date"]=pd.to_datetime(x["observed_date"],errors="coerce")
  x["value"]=pd.to_numeric(x["value"],errors="coerce")
  x=x.dropna().query("value > 0").sort_values("observed_date")
  x["date"]=x["observed_date"].dt.strftime("%Y-%m")
  x=x[x["date"]<=CUTOFF].groupby("date",as_index=False).tail(1).sort_values("date")
  vals=x["value"].tolist()
  for i,(_,r) in enumerate(x.iterrows()):
   rec={"date":r["date"],"asset":"CSI 300","metric":metric,"value":float(r["value"]),
    "observed_date":r["observed_date"].strftime("%Y-%m-%d"),"source":"Legu via AkShare",
    "source_url":url,"source_field":valcol,"method":"Last available source observation in each calendar month; no interpolation",
    "frequency":"monthly_sampled_from_daily"}
   for years,n in [("5Y",60),("10Y",120)]:
    sample=vals[max(0,i-n+1):i+1]
    rec[years+"_n"]=len(sample)
    rec[years+"_percentile"]=round(100*((sum(v<r["value"] for v in sample)+.5*sum(v==r["value"] for v in sample))/len(sample)),4) if len(sample)==n else None
   allrows.append(rec)
  audit["series"][metric]={"raw_file":str(raw.relative_to(ROOT)),"source_rows":len(df),"monthly_rows":len(x),
   "first_month":x["date"].min() if len(x) else None,"last_month":x["date"].max() if len(x) else None,
   "source_field":valcol,"status":"OK"}
 except Exception as e:
  audit["errors"][metric]=repr(e)
  audit["series"][metric]={"status":"ERROR","error":repr(e)}
cols=["date","asset","metric","value","observed_date","source","source_url","source_field","method","frequency","5Y_n","5Y_percentile","10Y_n","10Y_percentile"]
with (OUT/"csi300-legu-monthly.csv").open("w",encoding="utf-8-sig",newline="") as f:
 w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(allrows)
audit["status"]="OK" if len(audit["series"])==2 and not audit["errors"] else "PARTIAL"
(OUT/"csi300-legu-audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(audit,ensure_ascii=False,indent=2))
