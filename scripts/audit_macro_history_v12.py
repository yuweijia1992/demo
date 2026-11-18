#!/usr/bin/env python3
"""Strict V1.2 audit and reproducible monthly panel builder.

Current FRED histories are explicitly non-point-in-time. Only NFCI ALFRED
vintages are treated as historical snapshots. Missing inputs never get filled.
"""
from __future__ import annotations
import csv, gzip, hashlib, json, math
from pathlib import Path
from datetime import date
ROOT = Path("data/index-valuation")
FILES = {
 "sp500_total_return": "sp500-long-run-total-return-monthly.csv",
 "nfci_vintages": "alfred-nfci-vintages.csv.gz",
 "DFII10": "fred-dfii10-current.csv",
 "FEDFUNDS": "fred-fedfunds-current.csv",
 "GS10": "fred-gs10-current.csv",
 "CPIAUCSL": "fred-cpiaucsl-current.csv",
}
SOURCES = {
 "sp500_total_return":"https://firenum.com/data/shiller-monthly.csv",
 "nfci_vintages":"https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=NFCI",
 "DFII10":"https://fred.stlouisfed.org/series/DFII10",
 "FEDFUNDS":"https://fred.stlouisfed.org/series/FEDFUNDS",
 "GS10":"https://fred.stlouisfed.org/series/GS10",
 "CPIAUCSL":"https://fred.stlouisfed.org/series/CPIAUCSL",
}
def sha(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
 return h.hexdigest()
def read_csv(p, zipped=False):
 op=gzip.open if zipped else open
 with op(p,"rt",encoding="utf-8-sig",newline="") as f: return list(csv.reader(f))
def month(s):
 return s[:7]
def main():
 ROOT.mkdir(parents=True,exist_ok=True)
 audit={"title":"V1.2 strict source audit","generated_at_utc":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),"files":{},"checks":{},"panel":{"file":"v12-monthly-panel.csv","rows":0},"limitations":[]}
 parsed={}
 for key,name in FILES.items():
  p=ROOT/name
  if not p.exists():
   audit["files"][key]={"file":name,"status":"MISSING","source":SOURCES[key]}
   continue
  try:
   rows=read_csv(p,key=="nfci_vintages")
   if not rows or len(rows[0])<2: raise ValueError("empty or malformed CSV")
   if key=="sp500_total_return":
    header=rows[0]
    required=["month","total_return_decimal","shiller_cpi"]
    if header!=required: raise ValueError(f"header mismatch: {header}")
    dates=[r[0] for r in rows[1:] if len(r)==3]
    vals=[float(r[1]) for r in rows[1:] if len(r)==3]
    if len(dates)!=len(set(dates)): raise ValueError("duplicate months")
    if len(dates)<1800 or dates[0]>"1871-02-01": raise ValueError("coverage below agreed threshold")
    if any(not (-1<float(v)<5) for v in vals): raise ValueError("implausible total return")
    parsed[key]=rows
    audit["files"][key]={"file":name,"status":"PASS","rows":len(dates),"start":min(dates),"end":max(dates),"duplicate_dates":0,"sha256":sha(p),"source":SOURCES[key],"frequency":"monthly","point_in_time":False,"note":"Shiller-derived monthly-average-price total return; USD nominal."}
   elif key=="nfci_vintages":
    header=rows[0]; cols=header[1:]
    if not cols or any(not c.startswith("NFCI_") for c in cols): raise ValueError("vintage columns are not NFCI-tagged")
    labels=[c[5:] for c in cols]
    if len(labels)!=len(set(labels)): raise ValueError("duplicate vintage columns")
    if any(len(x)!=8 or not x.isdigit() for x in labels): raise ValueError("invalid vintage date label")
    obs=[r[0] for r in rows[1:] if r and r[0]]
    if len(obs)<100: raise ValueError("insufficient observation history")
    if len(cols)<200: raise ValueError(f"only {len(cols)} vintage columns; expected at least 200")
    import datetime as dt
    for label in labels:
     d=dt.date(int(label[:4]),int(label[4:6]),int(label[6:8]))
     if d.day != __import__("calendar").monthrange(d.year,d.month)[1]:
      raise ValueError(f"vintage label is not calendar month-end: {label}")
    parsed[key]=rows
    audit["files"][key]={"file":name,"status":"PASS","observation_rows":len(obs),"vintage_columns":len(cols),"first_vintage":labels[0],"last_vintage":labels[-1],"vintage_labels_valid":True,"sha256":sha(p),"source":SOURCES[key],"frequency":"weekly observations × monthly vintage snapshots","point_in_time":True}
   else:
    sid=key; header=rows[0]
    if header[0] not in ("observation_date","DATE") or header[1]!=sid: raise ValueError(f"expected date,{sid}; got {header[:2]}")
    vals=[r for r in rows[1:] if len(r)>1 and r[1] not in ("",".","nan","NaN")]
    dates=[r[0] for r in vals]
    if not vals: raise ValueError("no observations")
    minimum={"DFII10":3000,"FEDFUNDS":200,"GS10":200,"CPIAUCSL":200}[sid]
    if len(vals)<minimum: raise ValueError(f"coverage too short: {len(vals)} < {minimum}")
    if len(dates)!=len(set(dates)): raise ValueError("duplicate observation dates")
    for r in vals: float(r[1])
    diffs=[]
    import datetime as dt
    ds=[dt.date.fromisoformat(x) for x in dates]
    if sid=="DFII10":
     freq="daily"; diffs=[(b-a).days for a,b in zip(ds,ds[1:])]
    else:
     freq="monthly" if sid in ("FEDFUNDS","GS10","CPIAUCSL") else "unknown"
    parsed[key]=rows
    audit["files"][key]={"file":name,"status":"PASS","rows":len(vals),"start":min(dates),"end":max(dates),"missing_observations":sum(1 for r in rows[1:] if len(r)>1 and r[1] in ("",".","nan","NaN")),"sha256":sha(p),"source":SOURCES[key],"frequency":freq,"point_in_time":False,"date_order_checked":dates==sorted(dates),"duplicate_dates":0,"note":"Current revised FRED history; not suitable as historical vintage inputs."}
  except Exception as e:
   audit["files"][key]={"file":name,"status":"FAIL","error":str(e),"source":SOURCES[key]}
 # Monthly panel only created if every required source exists and parses.
 required=set(FILES)
 if required.issubset(parsed):
  # Current FRED series are retained as revised-history context, not point-in-time signals.
  series={}
  for sid in ("DFII10","FEDFUNDS","GS10","CPIAUCSL"):
   rows=parsed[sid]; series[sid]=[(r[0],r[1]) for r in rows[1:] if len(r)>1 and r[1] not in ("",".","nan","NaN")]
  # NFCI: use the value in the vintage column matching the panel month-end.
  nfci=parsed["nfci_vintages"]; nhead=nfci[0]; nmap={r[0]:r[1:] for r in nfci[1:] if r}
  ncols={c[5:]:i for i,c in enumerate(nhead[1:])}
  sh={month(r[0]):r[1] for r in parsed["sp500_total_return"][1:] if len(r)>=2}
  import calendar, datetime as dt
  out=[]
  months=sorted(set(month(x) for x in sh))
  for m in months:
   y,mo=map(int,m.split("-")); me=f"{y:04d}-{mo:02d}-{calendar.monthrange(y,mo)[1]:02d}"
   row={"month":m,"month_end":me,"sp500_total_return_usd_nominal":sh.get(m,""),"nfci_asof_month_end":""}
   # exact vintage column is required; never substitute another month's vintage.
   vkey=me.replace("-","")
   ci=ncols.get(vkey)
   if ci is not None:
    candidates=[(d,vals[ci]) for d,vals in nmap.items() if d<=me and ci<len(vals) and vals[ci] not in ("",".")]
    if candidates: row["nfci_asof_month_end"]=max(candidates,key=lambda z:z[0])[1]
   for sid,items in series.items():
    eligible=[(d,v) for d,v in items if d<=me]
    row[sid+"_current_revised"]=eligible[-1][1] if eligible else ""
   row["nfci_is_point_in_time"]="true" if row["nfci_asof_month_end"]!="" else "false"
   row["fred_fields_are_point_in_time"]="false"
   out.append(row)
  panel=ROOT/"v12-monthly-panel.csv"
  with panel.open("w",encoding="utf-8",newline="") as f:
   w=csv.DictWriter(f,fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
  audit["panel"]={"file":panel.name,"rows":len(out),"start":months[0],"end":months[-1],"sha256":sha(panel),"status":"BUILT_WITH_EXPLICIT_PIT_FLAGS","rule":"No interpolation or backfill. NFCI uses exact month-end ALFRED vintage; FRED columns are latest observation dated on/before month-end from current revised history and are NOT point-in-time publication-aware."}
 else:
  audit["panel"]["status"]="NOT_BUILT_MISSING_OR_INVALID_INPUTS"
 audit["checks"]={"all_six_source_files_present_and_valid":len(parsed)==len(FILES),"sha256_for_each_present_file":all("sha256" in v for v in audit["files"].values() if v["status"]=="PASS"),"nfci_vintage_dates_column_audited":audit["files"].get("nfci_vintages",{}).get("status")=="PASS","monthly_panel_built":audit["panel"].get("status","").startswith("BUILT"),"strict_v12_pass":False}
 audit["limitations"] += ["A panel containing current revised FRED histories is not a fully point-in-time five-factor panel.","The FRED current-history fields are marked non-PIT and must not be used in strict historical information-set backtests.","A publication-calendar/vintage history is still required for DFII10, FEDFUNDS, GS10 and CPIAUCSL before the full five-factor model can claim strict PIT validity.","No missing values are interpolated or silently filled."]
 # strict pass requires all six files, valid NFCI vintages, panel, and source metadata; PIT restrictions remain explicitly reported.
 # Strict PIT is deliberately stricter than file completeness. The current V1.2
 # bundle has only NFCI vintage snapshots; DFII10/FEDFUNDS/GS10/CPI are
 # revised-current histories, and Shiller CAPE vintage history is not yet
 # supplied. Therefore a successful download/audit must NOT imply PIT pass.
 pit_required = ("CAPE", "DFII10", "NFCI", "FEDFUNDS")
 pit_status = {
  "CAPE": False, "DFII10": False,
  "NFCI": audit["files"].get("nfci_vintages", {}).get("point_in_time") is True,
  "FEDFUNDS": False
 }
 audit["checks"]["factor_pit_eligibility"] = pit_status
 audit["checks"]["all_five_factor_inputs_strict_pit"] = all(pit_status.values())
 audit["checks"]["strict_v12_pass"] = bool(
  audit["checks"]["all_six_source_files_present_and_valid"]
  and audit["checks"]["nfci_vintage_dates_column_audited"]
  and audit["checks"]["monthly_panel_built"]
  and audit["checks"]["sha256_for_each_present_file"]
  and audit["checks"]["all_five_factor_inputs_strict_pit"]
 )
 p=ROOT/"v12-historical-data-audit.json"; p.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps(audit,ensure_ascii=False,indent=2))
 if not audit["checks"]["strict_v12_pass"]: raise SystemExit(2)
if __name__=="__main__": main()
