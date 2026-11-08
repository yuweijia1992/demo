#!/usr/bin/env python3
"""Static validation for the Investment Lab V2.1 GitHub Pages modules."""
from __future__ import annotations
import ast, csv, json, re, subprocess, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def require(condition,message):
    if not condition: raise SystemExit("FAIL: "+message)
def node_check(source,label):
    with tempfile.NamedTemporaryFile("w",suffix=".js",encoding="utf-8",delete=False) as f:
        f.write(source); path=Path(f.name)
    try:
        run=subprocess.run(["node","--check",str(path)],capture_output=True,text=True)
        require(run.returncode==0,f"JavaScript syntax error in {label}: "+(run.stderr or run.stdout))
    finally:
        path.unlink(missing_ok=True)

# Shared configuration: exact policy allocation and a 100% sum.
config=(ROOT/"assets/investment-config.js").read_text(encoding="utf-8")
block=re.search(r"allocation\s*:\s*\[(.*?)\]\s*,\s*backtestProxy",config,re.S)
require(bool(block),"shared allocation block not found")
weights=[int(x) for x in re.findall(r"weight\s*:\s*(\d+)",block.group(1))]
require(weights==[52,28,10,10],"shared strategic weights differ from [52,28,10,10]")
require(sum(weights)==100,"strategic allocation does not total 100%")

# Monthly data integrity and manifest agreement.
csv_path=ROOT/"data/investment-monthly.csv"
with csv_path.open("r",encoding="utf-8-sig",newline="") as f:
    reader=csv.DictReader(f); rows=list(reader); headers=reader.fieldnames or []
require("date" in headers,"monthly CSV has no date field")
require("csi300_price_return_pct" in headers,"CSI 300 monthly price-return field missing")
require("sp500_total_return_pct" in headers,"S&P 500 total-return field missing from schema")
dates=[r["date"] for r in rows]
require(bool(rows),"monthly CSV is empty")
require(dates==sorted(dates),"monthly dates are not sorted")
require(len(dates)==len(set(dates)),"duplicate monthly dates detected")
require(all(re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])",d or "") for d in dates),"invalid monthly date format")
manifest=json.loads((ROOT/"data/investment-monthly-manifest.json").read_text(encoding="utf-8"))
require(manifest.get("row_count")==len(rows),"manifest row_count differs from CSV")
first=rows[0]; last=rows[-1]
require(first.get("csi300_period_status")=="partial_index_start","first CSI 300 month must be marked partial")
require(last.get("csi300_period_status") in {"partial_source_cutoff","partial_current_month"},"latest CSI 300 month must be marked partial")
require(not first.get("csi300_price_return_pct"),"first partial month must not have a monthly return")
require(not last.get("csi300_price_return_pct"),"latest partial month must not have a full monthly return")

# Script syntax.
ast.parse((ROOT/"scripts/update_investment_monthly_data.py").read_text(encoding="utf-8"))
node_check((ROOT/"assets/investment-data-core.js").read_text(encoding="utf-8"),"investment-data-core.js")

pages=[
    "articles/global-macro-model.html",
    "articles/risk-monitor.html",
    "articles/historical-backtest.html",
    "articles/financial-independence-simulator.html",
]
for rel in pages:
    html=(ROOT/rel).read_text(encoding="utf-8")
    require("../assets/investment-data-core.js" in html,f"{rel} does not load the shared monthly data layer")
    for i,match in enumerate(re.finditer(r"<script\b([^>]*)>(.*?)</script\s*>",html,re.I|re.S),1):
        attrs,body=match.group(1),match.group(2)
        if re.search(r"\bsrc\s*=",attrs,re.I) or not body.strip(): continue
        node_check(body,f"{rel} inline script #{i}")

home=(ROOT/"articles/investment-lab.html").read_text(encoding="utf-8")
require("financial-independence-simulator.html" in home,"homepage does not link to the 50-year simulator")
risk=(ROOT/"articles/risk-monitor.html").read_text(encoding="utf-8")
require("portfolio_return_cny_pct" in risk,"risk monitor must gate portfolio statistics on CNY portfolio returns")
sim=(ROOT/"articles/financial-independence-simulator.html").read_text(encoding="utf-8")
require("returns.length>=120" in sim,"block bootstrap must require at least 120 monthly portfolio observations")
print(json.dumps({
    "status":"PASS","strategic_weights":weights,"monthly_rows":len(rows),
    "monthly_start":dates[0],"monthly_end":dates[-1],
    "csi300_full_month_return_observations":sum(bool(r.get("csi300_price_return_pct")) for r in rows),
    "validated_pages":pages,"checks":["configuration","CSV chronology","partial-month boundaries","manifest","Python syntax","shared JS syntax","inline JS syntax","module wiring"]
},ensure_ascii=False,indent=2))
