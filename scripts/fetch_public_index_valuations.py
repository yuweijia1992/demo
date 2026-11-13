#!/usr/bin/env python3
"""Fetch transparent public S&P 500 valuation history and derive RMB gold valuation bands.

This is an intentionally partial first tranche: it does not fabricate missing
CSI 300, HSI or Nasdaq-100 monthly valuation history. Source dates and raw values
are retained, and rolling percentiles require 60/120 real monthly observations.
"""
from __future__ import annotations
import csv, json, math, re, time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/index-valuation"
RAW=OUT/"raw"
RAW.mkdir(parents=True,exist_ok=True)
SOURCES={
 "sp500_cape":{"url":"https://www.multpl.com/shiller-pe/table/by-month","asset":"S&P 500","metric":"CAPE","method":"Shiller cyclically adjusted P/E; monthly series; first-of-month observations"},
 "sp500_pe_ttm":{"url":"https://dqydj.com/sp-500-pe-ratio/","asset":"S&P 500","metric":"PE_TTM","method":"Monthly average index level divided by trailing 12-month earnings per share"},
}
class TableParser(HTMLParser):
 def __init__(self):
  super().__init__();self.rows=[];self.row=None;self.cell=None
 def handle_starttag(self,tag,attrs):
  if tag=="tr":self.row=[]
  elif tag in ("td","th") and self.row is not None:self.cell=[]
  elif tag=="br" and self.cell is not None:self.cell.append(" ")
 def handle_data(self,data):
  if self.cell is not None:self.cell.append(data)
 def handle_endtag(self,tag):
  if tag in ("td","th") and self.cell is not None:
   self.row.append(" ".join(" ".join(self.cell).split()));self.cell=None
  elif tag=="tr" and self.row is not None:
   if self.row:self.rows.append(self.row)
   self.row=None
def fetch(url):
 req=Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; InvestmentLabResearch/1.0)","Accept":"text/html"})
 with urlopen(req,timeout=35) as r:return r.read().decode("utf-8","replace")
def num(s):
 try:
  x=float(str(s).replace(",","").replace("$","").strip())
  return x if math.isfinite(x) and x>0 else None
 except Exception:return None
def percentile(vals,current):
 return 100*(sum(x<current for x in vals)+.5*sum(x==current for x in vals))/len(vals) if vals else None
def collect_multpl(html):
 p=TableParser();p.feed(html);out={}
 for row in p.rows:
  if len(row)<2:continue
  try:d=datetime.strptime(row[0].strip()," %b %d, %Y".strip()).date()
  except ValueError:continue
  if d.day!=1:continue
  v=num(row[1])
  if v:out[d.strftime("%Y-%m")]=(d.isoformat(),v)
 return out
def collect_dqydj(html):
 p=TableParser();p.feed(html);out={}
 for row in p.rows:
  if len(row)<3:continue
  m=re.fullmatch(r"(0[1-9]|1[0-2])-(18\d{2}|19\d{2}|20\d{2}|21\d{2})",row[0].strip())
  if not m:continue
  month=f"{m.group(2)}-{m.group(1)}";v=num(row[-1])
  if v:out[month]=(month+"-01",v)
 return out
def build():
 observations=[];errors={};source_counts={}
 now=datetime.now()
 cutoff=f"{now.year-1:04d}-12" if now.month==1 else f"{now.year:04d}-{now.month-1:02d}"
 for key,meta in SOURCES.items():
  try:
   html=fetch(meta["url"])
   (RAW/(key+".html")).write_text(html,encoding="utf-8")
   data=collect_multpl(html) if key=="sp500_cape" else collect_dqydj(html)
   if len(data)<120:raise RuntimeError(f"Only {len(data)} monthly observations parsed; expected at least 120")
   for month,(day,value) in sorted(data.items()):
    if "2006-01"<=month<=cutoff:
     observations.append({"date":month,"asset":meta["asset"],"metric":meta["metric"],"value":value,
      "observed_date":day,"source":key,"source_url":meta["url"],"method":meta["method"],"frequency":"monthly"})
   source_counts[key]={"parsed_months":len(data),"used_months":sum("2006-01"<=m<=cutoff for m in data),"first_month":min(data),"last_month":max(data),"status":"OK"}
  except Exception as exc:
   errors[key]=str(exc)[:400];source_counts[key]={"status":"ERROR","error":str(exc)[:400]}
  time.sleep(.5)
 # RMB gold is sourced from the already-audited monthly matrix; the source fields are
 # retained in the main manifest. This is a spot-price valuation series, not fund NAV.
 matrix=ROOT/"data/investment-monthly.csv"
 with matrix.open(encoding="utf-8-sig",newline="") as f:
  for row in csv.DictReader(f):
   value=num(row.get("gold_cny_per_oz_monthly_avg",""))
   if value:
    observations.append({"date":row["date"],"asset":"Gold (CNY)","metric":"CNY_per_troy_ounce","value":value,
     "observed_date":row["date"],"source":"World Bank Pink Sheet gold monthly average × monthly USD/CNY",
     "source_url":"https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/world-bank-commodities-price-data-the-pink-sheet",
     "method":"Gold USD/troy oz monthly average × USD/CNY monthly average","frequency":"monthly"})
 observations.sort(key=lambda x:(x["asset"],x["metric"],x["date"]))
 groups={}
 for x in observations:groups.setdefault((x["asset"],x["metric"]),[]).append(x)
 for key,items in groups.items():
  items.sort(key=lambda x:x["date"])
  for i,item in enumerate(items):
   for years,window in (("5Y",60),("10Y",120)):
    sample=[z["value"] for z in items[max(0,i-window+1):i+1]]
    item[years+"_n"]=len(sample)
    item[years+"_percentile"]=round(percentile(sample,item["value"]),4) if len(sample)>=window else None
    item[years+"_min"]=min(sample) if len(sample)>=window else None
    item[years+"_max"]=max(sample) if len(sample)>=window else None
 cols=["date","asset","metric","value","observed_date","source","source_url","method","frequency","5Y_n","5Y_percentile","5Y_min","5Y_max","10Y_n","10Y_percentile","10Y_min","10Y_max"]
 with (OUT/"valuation-monthly-partial.csv").open("w",encoding="utf-8-sig",newline="") as f:
  w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(observations)
 latest={}
 for key,items in groups.items():
  x=items[-1];latest[x["asset"]+"|"+x["metric"]]={k:x.get(k) for k in ("date","value","5Y_n","5Y_percentile","5Y_min","5Y_max","10Y_n","10Y_percentile","10Y_min","10Y_max","source","source_url")}
 audit={"schema_version":"0.1","status":"PARTIAL" if errors or len(groups)<5 else "OK","generated_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),"completed_month_cutoff":cutoff,
 "coverage":{"assets_metrics":len(groups),"observations":len(observations),"start":min(x["date"] for x in observations) if observations else None,"end":max(x["date"] for x in observations) if observations else None},
 "sources":source_counts,"latest":latest,"errors":errors,
 "limitations":["Only S&P 500 CAPE, S&P 500 trailing PE and RMB gold spot-price valuation are included in this tranche.",
 "CSI 300 and Hang Seng monthly index valuation history require a verifiable public raw data feed or licensed provider; a Lixinger API token is required for its documented historical index fundamentals endpoint.",
 "Nasdaq-100 complete monthly valuation history is not available in Siblis free tier; full historical database is subscription data. Public page snapshots are not treated as a continuous monthly series.",
 "CAPE and trailing PE are different metrics and must not be compared as if identical.",
 "Gold has no PE/PB; monthly CNY spot price percentile is a price-history indicator, not intrinsic-value valuation.",
 "No interpolation, forward filling, or extrapolation is applied; rolling percentile is blank until a full 60/120-month window exists.",
 "Only completed calendar months are included; the in-progress current month is excluded. The Multpl CAPE source labels monthly observations on the first calendar day of the month; the month label is retained and not misrepresented as a month-end close."]}
 (OUT/"valuation-source-audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps({"coverage":audit["coverage"],"sources":source_counts,"latest":latest,"errors":errors},ensure_ascii=False,indent=2))
if __name__=="__main__":build()
