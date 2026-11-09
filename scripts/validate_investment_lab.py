#!/usr/bin/env python3
"""Static validation for the Investment Lab V2.5 RMB monthly matrix with ETF proxies and GitHub Pages modules."""
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
require(len(rows)==250,"matrix must contain 250 months from 2006-01 through 2026-10")
require(dates[0]=="2006-01" and dates[-1]=="2026-10","matrix date window must be 2006-01 to 2026-10")
by_month={r["date"]:r for r in rows}
jan=by_month["2006-01"]
sep=by_month["2026-09"]
october=by_month["2026-10"]
require(bool(jan.get("csi300_price_return_pct")),"Jan-2006 CSI 300 return must use Dec-2005 as calculation predecessor")
require(bool(jan.get("csi300_total_return_pct")),"Jan-2006 CSI 300 total return must use Dec-2005 as calculation predecessor")
require(sep.get("csi300_period_status")=="partial_source_cutoff","Sep-2026 CSI 300 source cutoff must be disclosed")
require(not sep.get("csi300_price_return_pct") and not sep.get("csi300_total_return_pct"),"partial Sep-2026 CSI month returns must be blank")
require(not october.get("csi300_price_index_cny") and not october.get("csi300_total_return_index_cny"),"Oct-2026 CSI 300 values must remain missing when source observations are unavailable")
require(bool(october.get("gold_cny_return_pct")) and bool(october.get("usd_cny")),"Oct-2026 gold and FX values should be present")
require(manifest.get("coverage",{}).get("csi300_total_return_pct",{}).get("count")==sum(bool(r.get("csi300_total_return_pct")) for r in rows),"manifest CSI 300 TR coverage differs from matrix")
require(manifest.get("coverage",{}).get("sp500_total_return_cny_pct",{}).get("count")==sum(bool(r.get("sp500_total_return_cny_pct")) for r in rows),"manifest S&P RMB coverage differs from matrix")
require(manifest.get("coverage",{}).get("gold_cny_return_pct",{}).get("count")==sum(bool(r.get("gold_cny_return_pct")) for r in rows),"manifest gold RMB coverage differs from matrix")
etf_fields=[
 "us_agg_etf_total_return_usd_pct","us_agg_etf_total_return_cny_pct",
 "us_ief_7_10y_etf_total_return_usd_pct","us_ief_7_10y_etf_total_return_cny_pct",
 "us_shy_1_3y_etf_total_return_usd_pct","us_shy_1_3y_etf_total_return_cny_pct",
 "fxi_china_largecap_etf_total_return_usd_pct","fxi_china_largecap_etf_total_return_cny_pct",
 "efa_developed_markets_etf_total_return_usd_pct","efa_developed_markets_etf_total_return_cny_pct",
 "eem_emerging_markets_etf_total_return_usd_pct","eem_emerging_markets_etf_total_return_cny_pct"
]
for field in etf_fields:
    actual=sum(bool(r.get(field)) for r in rows)
    cov=manifest.get("coverage",{}).get(field,{})
    require(actual==247,f"{field} must contain 247 months from 2006-01 to 2026-07")
    require(cov.get("count")==actual and cov.get("start")=="2006-01" and cov.get("end")=="2026-07",f"manifest ETF coverage incorrect for {field}")
require(not any(r.get("portfolio_return_cny_pct") for r in rows),"full portfolio return must remain blank until all strategic sleeves and policy weights are approved")
require(all(f in headers for f in etf_fields),"EFA/EEM global equity proxy fields must exist in the unified matrix schema")

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
require("port.length>=120" in sim,"block bootstrap must require at least 120 monthly portfolio observations")
print(json.dumps({
    "status":"PASS","strategic_weights":weights,"monthly_rows":len(rows),
    "monthly_start":dates[0],"monthly_end":dates[-1],
    "csi300_full_month_return_observations":sum(bool(r.get("csi300_price_return_pct")) for r in rows),
    "validated_pages":pages,"checks":["configuration","CSV chronology","250-month RMB matrix","partial CSI cutoff","manifest coverage consistency","ETF proxy month counts and ranges","portfolio-return gate","Python syntax","shared JS syntax","inline JS syntax","module wiring"]
},ensure_ascii=False,indent=2))
