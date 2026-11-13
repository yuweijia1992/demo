#!/usr/bin/env python3
"""Pilot walk-forward calibration of an S&P 500 CAPE allocation rule.

The CAPE signal is lagged by one complete month before use. This is only a
single-market pilot, not the final 400万元 multi-asset decision rule.
"""
from __future__ import annotations
import csv,json,math,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MATRIX=ROOT/"data/investment-monthly.csv"
VALUATION=ROOT/"data/index-valuation/valuation-monthly-partial.csv"
OUT=ROOT/"data/research"
def n(x):
 try:return float(x)/100 if x is not None and str(x).strip() else None
 except:return None
def pct(x):return x*100 if x is not None else None
def stats(rs):
 wealth=1.;peak=1.;mdd=0.;nav=[]
 for r in rs:
  wealth*=1+r;peak=max(peak,wealth);mdd=min(mdd,wealth/peak-1);nav.append(wealth)
 vol=statistics.stdev(rs)*math.sqrt(12) if len(rs)>1 else 0
 ann=wealth**(12/len(rs))-1 if rs and wealth>0 else None
 return {"months":len(rs),"annualized_return":ann,"annualized_volatility":vol,"max_drawdown":mdd,"terminal_wealth_multiple":wealth,"worst_month":min(rs) if rs else None}
def main():
 cape={}
 with VALUATION.open(encoding="utf-8-sig",newline="") as f:
  for r in csv.DictReader(f):
   if r["asset"]=="S&P 500" and r["metric"]=="CAPE":
    p=r.get("10Y_percentile","")
    if p:cape[r["date"]]=float(p)/100
 rows=[]
 with MATRIX.open(encoding="utf-8-sig",newline="") as f:
  for r in csv.DictReader(f):
   eq=n(r.get("sp500_total_return_cny_pct"));cash=n(r.get("cny_cash_return_pct"))
   if eq is not None and cash is not None:rows.append({"date":r["date"],"eq":eq,"cash":cash})
 lookup={r["date"]:r for r in rows}
 def prev_month(m):
  y,mo=map(int,m.split("-"))
  return f"{y-1:04d}-12" if mo==1 else f"{y:04d}-{mo-1:02d}"
 strategies={"SP500_buy_hold":[],"Fixed_60_40":[],"CAPE_tilt_100_75_50":[]}
 paths={k:[] for k in strategies}
 current={"Fixed_60_40":.60,"CAPE_tilt_100_75_50":None}
 for r in rows:
  sig=cape.get(prev_month(r["date"]))
  if sig is None:continue
  target=1.0 if sig<=.20 else (.75 if sig<.80 else .50)
  strategies["SP500_buy_hold"].append(r["eq"])
  paths["SP500_buy_hold"].append({"date":r["date"],"return":r["eq"],"equity_weight":1.0,"lagged_cape_percentile":sig})
  for name,w in (("Fixed_60_40",.60),("CAPE_tilt_100_75_50",target)):
   old=current[name] if current[name] is not None else w
   turnover=abs(w-old) if current[name] is not None else 0.0
   gross=w*r["eq"]+(1-w)*r["cash"]
   ret=(1+gross)*(1-.001*turnover)-1
   strategies[name].append(ret)
   paths[name].append({"date":r["date"],"return":ret,"equity_weight":w,"lagged_cape_percentile":sig})
   post_eq=w*(1+r["eq"]);post_cash=(1-w)*(1+r["cash"]);total=post_eq+post_cash
   current[name]=post_eq/total if total>0 else w
 if not strategies["CAPE_tilt_100_75_50"] or len(strategies["CAPE_tilt_100_75_50"])<60:
  raise SystemExit("Insufficient overlapping S&P 500 CAPE, total-return and cash observations.")
 result={"status":"PILOT_ONLY_NOT_GLOBAL_POLICY","signal":"S&P 500 CAPE 10Y percentile observed at t-1","rules":{"SP500_buy_hold":"100% S&P 500 total return","Fixed_60_40":"60% S&P 500 / 40% RMB cash, monthly rebalance with 10bp one-way cost","CAPE_tilt_100_75_50":"100% equity if lagged CAPE percentile <=20; 75% if >20 and <80; 50% if >=80; remaining weight RMB cash; 10bp one-way cost on equity-weight changes"},"sample":{"start":paths["CAPE_tilt_100_75_50"][0]["date"],"end":paths["CAPE_tilt_100_75_50"][-1]["date"],"months":len(paths["CAPE_tilt_100_75_50"])},"strategies":{k:stats(v) for k,v in strategies.items()},"limitations":["Single S&P 500 + RMB cash pilot only; not a global 52/28/10/10 portfolio.","CAPE is a slow-moving valuation metric and may remain high for years; results are highly sample-dependent.","Signal is deliberately lagged by one full month; no look-ahead from same-month returns.","No taxes, bid-ask spread, ETF tracking difference, withholding tax or account-specific FX conversion cost.","No optimization on the test sample; thresholds are fixed ex ante at 20/80 percentile and 100/75/50% equity weights.","Must compare against alternative thresholds and rolling out-of-sample periods before any policy use."]}
 (OUT/"cape_rule_calibration.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
 with (OUT/"cape_rule_calibration_monthly.csv").open("w",encoding="utf-8-sig",newline="") as f:
  w=csv.DictWriter(f,fieldnames=["strategy","date","return","equity_weight","lagged_cape_percentile"]);w.writeheader()
  for name,items in paths.items():
   for x in items:w.writerow({"strategy":name,**x})
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
