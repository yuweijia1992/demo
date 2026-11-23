#!/usr/bin/env python3
"""Archive public Fed credit-conditions and financial-stress proxies.

No Moody's or ICE proprietary OAS values are copied. Monthly observations are
the last actual observation in each calendar month, never forward-filled.
"""
import csv, io, os, time, urllib.request
from datetime import datetime

SERIES = {
    "NFCICREDIT": ("Chicago Fed NFCI Credit Subindex", "index", "weekly"),
    "STLFSI4": ("St. Louis Fed Financial Stress Index v4", "index", "weekly"),
    "KCFSI": ("Kansas City Financial Stress Index", "index", "monthly"),
}
BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"

def fetch(series_id):
    req = urllib.request.Request(BASE.format(series_id), headers={
        "User-Agent": "Mozilla/5.0 (compatible; InvestmentLabResearch/2.0)",
        "Accept": "text/csv,*/*"
    })
    errors=[]
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                raw=r.read().decode("utf-8-sig")
            rows=[]
            for row in csv.DictReader(io.StringIO(raw)):
                date=row.get("observation_date") or row.get("DATE")
                value=row.get(series_id,"")
                if date and value and value not in (".","ND","nan"):
                    rows.append((date,float(value)))
            if not rows:
                raise ValueError("No numeric observations returned")
            return rows
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            if attempt<3: time.sleep(2**attempt)
    raise RuntimeError(" | ".join(errors[-3:]))

os.makedirs("data/macro",exist_ok=True)
long=[]
monthly={}
audit={}
for sid,(label,unit,freq) in SERIES.items():
    rows=fetch(sid)
    audit[sid]={"label":label,"frequency":freq,"observations":len(rows),
                "first_date":rows[0][0],"last_date":rows[-1][0],
                "source":f"https://fred.stlouisfed.org/series/{sid}"}
    by_month={}
    for date,value in rows:
        long.append((date,sid,value))
        month=date[:7]
        # Sorted upstream; retain the last real observation in each month.
        by_month[month]=(date,value)
    monthly[sid]=by_month
    time.sleep(.4)

long.sort(key=lambda x:(x[0],x[1]))
with open("data/macro/credit-stress-proxies-weekly.csv","w",newline="",encoding="utf-8") as f:
    w=csv.writer(f); w.writerow(["observation_date","series_id","value","unit","series_label"])
    for date,sid,value in long:
        label,unit,_=SERIES[sid]; w.writerow([date,sid,f"{value:.8f}",unit,label])

months=sorted(set().union(*(set(x) for x in monthly.values())))
with open("data/macro/credit-stress-proxies-monthly.csv","w",newline="",encoding="utf-8") as f:
    w=csv.writer(f); w.writerow(["month","NFCICREDIT_date","NFCICREDIT","STLFSI4_date","STLFSI4","KCFSI_date","KCFSI"])
    for month in months:
        row=[month]
        for sid in SERIES:
            item=monthly[sid].get(month)
            row.extend([item[0],f"{item[1]:.8f}"] if item else ["",""])
        w.writerow(row)

with open("data/macro/credit-stress-proxies-audit.txt","w",encoding="utf-8") as f:
    f.write("Public macro-financial stress proxy coverage audit\n")
    f.write("Generated UTC: "+datetime.utcnow().isoformat(timespec="seconds")+"Z\n")
    f.write("Monthly value = last actual observation in month; no interpolation or forward-fill.\n")
    f.write("These indices are not quoted corporate credit spreads / OAS.\n\n")
    for sid,item in audit.items():
        f.write(f"{sid}: {item['label']} | {item['frequency']} | {item['observations']} rows | {item['first_date']} to {item['last_date']} | {item['source']}\n")
print(audit)
