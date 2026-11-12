#!/usr/bin/env python3
"""Reproducible RMB portfolio backtest, data audit and 50-year withdrawal simulation.
Research benchmark weights are explicitly provisional and are not an approved personal allocation.
"""
from __future__ import annotations
import csv, json, math, random, statistics
from pathlib import Path
from collections import defaultdict

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"/"investment-monthly.csv"
OUT=ROOT/"data"/"research"
OUT.mkdir(parents=True,exist_ok=True)
SEED=20261113
N_PATHS=500
CAPITAL=4_000_000
SPENDS=(80_000,90_000,100_000)
YEARS=50
ASSETS={
 "A_shares_CSI300":("csi300_total_return_pct",0.20),
 "US_equity_SP500":("sp500_total_return_cny_pct",0.12),
 "Developed_exUS_EFA":("efa_developed_markets_etf_total_return_cny_pct",0.10),
 "Emerging_EEM":("eem_emerging_markets_etf_total_return_cny_pct",0.10),
 "US_aggregate_bonds_AGG":("us_agg_etf_total_return_cny_pct",0.28),
 "Gold_proxy":("gold_cny_return_pct",0.10),
 "CNY_cash_H11025":("cny_cash_return_pct",0.10),
}
# Equity 52%=20/12/10/10; bonds 28%=US AGG proxy; gold/cash 10% each.
# This is an explicit research proxy, NOT an approved or final policy allocation.
COSTS=(0.0,0.001,0.003) # one-way transaction cost per RMB traded
THRESHOLD=0.05 # absolute target-weight deviation, percentage points
FIELDS=("date",)+tuple(v[0] for v in ASSETS.values())
def read_data():
 with DATA.open(encoding="utf-8-sig",newline="") as f:
  reader=csv.DictReader(f); rows=list(reader); headers=reader.fieldnames or []
 return rows,headers
def number(x):
 try:
  if x is None or x.strip()=="": return None
  return float(x)/100
 except (ValueError,AttributeError): return None
def coverage(rows,headers):
 result=[]
 for field in headers:
  if field=="date": continue
  vals=[r.get(field,"") for r in rows]
  valid=[(r["date"],r[field]) for r in rows if r.get(field,"").strip()!=""]
  miss=[r["date"] for r in rows if r.get(field,"").strip()==""]
  result.append({"field":field,"observations":len(valid),"missing_months":len(miss),
   "first":valid[0][0] if valid else None,"last":valid[-1][0] if valid else None,
   "missing_dates":";".join(miss)})
 with (OUT/"monthly_coverage_audit.csv").open("w",encoding="utf-8-sig",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(result[0]));w.writeheader();w.writerows(result)
 return result
def annualized(vals):
 n=len(vals)
 if not n:return None
 wealth=math.prod(1+x for x in vals)
 return wealth**(12/n)-1 if wealth>0 else -1
def stats(vals):
 if not vals:return {}
 wealth=1;peak=1;mdd=0
 for r in vals:
  wealth*=1+r;peak=max(peak,wealth);mdd=min(mdd,wealth/peak-1)
 mu=statistics.mean(vals)
 vol=statistics.stdev(vals)*math.sqrt(12) if len(vals)>1 else 0
 return {"months":len(vals),"annualized_return":annualized(vals),"annualized_volatility":vol,
  "max_drawdown":mdd,"worst_month":min(vals),"terminal_growth":wealth}
def rolling_worst(vals,window):
 if len(vals)<window:return None
 return min(math.prod(1+x for x in vals[i:i+window])-1 for i in range(len(vals)-window+1))
def run_strategy(data,weights,mode,cost):
 names=list(weights); target=[weights[n] for n in names]
 current=target[:]; wealth=1; output=[]; turnovers=[]
 for i,row in enumerate(data):
  if mode=="annual" and i>0 and row["date"][5:7]=="01":
   pass
  rebalance=(mode=="annual" and i>0 and i%12==0)
  if mode=="threshold" and i>0:
   drift=[x/sum(current) for x in current]
   rebalance=any(abs(d-t)>THRESHOLD for d,t in zip(drift,target))
  turnover=0.0
  if rebalance:
   turnover=sum(abs(a-b) for a,b in zip(current,target))/2
   current=target[:]
  gross=sum(w*row[n] for w,n in zip(current,names))
  net=(1+gross)*(1-cost*turnover)-1
  output.append(net);turnovers.append(turnover)
  post=[w*(1+row[n]) for w,n in zip(current,names)]
  total=sum(post)
  current=[x/total for x in post] if total>0 else target[:]
 return output,turnovers
def drawdown_scenarios(data,weights):
 result={}
 for mode in ("buy_hold","annual","threshold"):
  vals,turn=run_strategy(data,weights,mode,0.001)
  s=stats(vals);s.update({"avg_annual_turnover":statistics.mean(turn)*12 if turn else 0,
    "worst_12m":rolling_worst(vals,12),"worst_36m":rolling_worst(vals,36),
    "worst_60m":rolling_worst(vals,60),"worst_120m":rolling_worst(vals,120)})
  result[mode]=s
 return result
def block_path(history,block,n_months,rng):
 out=[]
 while len(out)<n_months:
  start=rng.randrange(len(history))
  for k in range(block):
   out.append(history[(start+k)%len(history)])
   if len(out)>=n_months:break
 return out
def withdraw_path(returns,spend,inflation,crash=0.0):
 bal=CAPITAL;ruin=None
 for m,r in enumerate(returns):
  year=m//12
  monthly_spend=spend*((1+inflation)**year)/12
  bal-=monthly_spend
  if bal<=0:
   bal=0;ruin=m+1;break
  if m==0 and crash: bal*=1-crash
  bal*=1+r
 return {"survived":ruin is None and len(returns)>=YEARS*12,
  "ending_balance":bal,"depletion_month":ruin,
  "depletion_year":(ruin/12 if ruin else None)}
def bootstrap(strategy,history_rows,weights,block,spend,inflation,crash=0.0):
 rng=random.Random(SEED+block+spend+int(inflation*10000)+int(crash*100))
 finals=[];ruins=0;ruin_years=[]
 for _ in range(N_PATHS):
  asset_path=block_path(history_rows,block,YEARS*12,rng)
  path,_=run_strategy(asset_path,weights,strategy,0.001)
  r=withdraw_path(path,spend,inflation,crash)
  finals.append(r["ending_balance"])
  if not r["survived"]:
   ruins+=1
   if r["depletion_year"] is not None:ruin_years.append(r["depletion_year"])
 finals.sort()
 q=lambda p:finals[min(len(finals)-1,int((len(finals)-1)*p))]
 return {"strategy":strategy,"block_months":block,"spend_first_year":spend,"inflation":inflation,"early_crash":crash,
  "paths":N_PATHS,"survival_rate":1-ruins/N_PATHS,"ending_balance_median":q(.5),
  "ending_balance_p10":q(.1),"ending_balance_p90":q(.9),
  "depletion_year_median":statistics.median(ruin_years) if ruin_years else None}
def main():
 rows,headers=read_data()
 audits=coverage(rows,headers)
 parsed=[]
 for r in rows:
  item={"date":r["date"]}
  for name,(field,_) in ASSETS.items(): item[name]=number(r.get(field,""))
  parsed.append(item)
 usable=[r for r in parsed if all(r[n] is not None for n in ASSETS)]
 if len(usable)<120: raise SystemExit(f"Only {len(usable)} complete common months; minimum 120 required.")
 weights={k:v[1] for k,v in ASSETS.items()}
 summaries=[]
 for mode in ("buy_hold","annual","threshold"):
  for cost in COSTS:
   vals,turn=run_strategy(usable,weights,mode,cost)
   s=stats(vals);s.update({"strategy":mode,"one_way_cost":cost,
    "average_annual_turnover":statistics.mean(turn)*12 if turn else 0,
    "worst_12m":rolling_worst(vals,12),"worst_36m":rolling_worst(vals,36),
    "worst_60m":rolling_worst(vals,60),"worst_120m":rolling_worst(vals,120)})
   summaries.append(s)
 with (OUT/"strategy_backtest_summary.json").open("w",encoding="utf-8") as f:
  json.dump({"status":"PROVISIONAL_RESEARCH_PROXY","sample_start":usable[0]["date"],
   "sample_end":usable[-1]["date"],"common_months":len(usable),"seed":SEED,
   "weights":weights,"asset_fields":{k:v[0] for k,v in ASSETS.items()},
   "methodology":{"buy_hold":"drift, no rebalance","annual":"rebalance each January",
    "threshold":"rebalance when any sleeve differs by more than 5 percentage points",
    "costs":"0/10/30 basis points per one-way RMB turnover; applied to half-L1 turnover",
    "block_bootstrap":"circular 12/24/36-month blocks sampled from joint asset-return vectors; each synthetic path reruns its own buy-hold/annual/threshold rebalance rule, 1,000 paths, 600 months; 2%/4% inflation and immediate 30% crash sensitivity for every spend and strategy",
    "limitations":["CSI300 total-return series is an index proxy, not an investable fund",
    "AGG is a US aggregate bond ETF proxy, not Chinese government/bond wealth index",
    "EEM includes China and Taiwan exposure; overlap with A-share sleeve must be reviewed",
    "EFA excludes US but does not cover all global markets","gold is a monthly-average valuation proxy",
    "cash H11025 contains backfilled pre-publication history","no official Hang Seng total-return series",
    "no rent growth, tax, pension, healthcare shock or personal cashflow additions"]},
   "strategies":summaries},f,ensure_ascii=False,indent=2)
 boot=[]
 for mode in ("buy_hold","annual","threshold"):
  for block in (12,24,36):
   for spend in SPENDS:
    for infl in (0.02,0.04):
     boot.append(bootstrap(mode,usable,weights,block,spend,infl,0.0))
     boot.append(bootstrap(mode,usable,weights,block,spend,infl,0.30))
 with (OUT/"withdrawal_bootstrap_results.csv").open("w",encoding="utf-8-sig",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(boot[0]));w.writeheader();w.writerows(boot)
 # Deterministic annual paths for 8/9/10w at low/base/high real-return assumptions.
 deterministic=[]
 for spend in SPENDS:
  for nominal,infl in ((0.03,.02),(.05,.02),(.04,.04)):
   for crash in (0.0,.30):
    bal=CAPITAL;depletion=None
    for m in range(YEARS*12):
     y=m//12;bal-=spend*((1+infl)**y)/12
     if bal<=0:bal=0;depletion=m+1;break
     if m==0 and crash:bal*=1-crash
     bal*=((1+nominal)**(1/12))
    deterministic.append({"spend_first_year":spend,"nominal_return":nominal,"inflation":infl,
      "early_crash":crash,"ending_balance":bal,"depletion_year":depletion/12 if depletion else None})
 with (OUT/"deterministic_withdrawal_scenarios.csv").open("w",encoding="utf-8-sig",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(deterministic[0]));w.writeheader();w.writerows(deterministic)
 with (OUT/"research_manifest.json").open("w",encoding="utf-8") as f:
  json.dump({"generated_by":"scripts/run_investment_research.py","status":"PROVISIONAL_RESEARCH_PROXY",
   "monthly_matrix_rows":len(rows),"common_complete_months":len(usable),
   "common_start":usable[0]["date"],"common_end":usable[-1]["date"],
   "coverage_audit":"monthly_coverage_audit.csv","strategy_summary":"strategy_backtest_summary.json",
   "bootstrap_results":"withdrawal_bootstrap_results.csv",
   "deterministic_scenarios":"deterministic_withdrawal_scenarios.csv",
   "notes":"Do not represent this proxy as the final approved 52/28/10/10 allocation."},f,ensure_ascii=False,indent=2)
 print(json.dumps({"status":"PASS","common_months":len(usable),"start":usable[0]["date"],
  "end":usable[-1]["date"],"audited_fields":len(audits),"strategy_rows":len(summaries),
  "bootstrap_rows":len(boot),"deterministic_rows":len(deterministic)},ensure_ascii=False))


def allocation_sensitivity():
 """Paired 52/45/42 equity sleeve comparison using the same proxy return rows."""
 rows,_=read_data()
 parsed=[]
 for r in rows:
  item={"date":r["date"]}
  for name,(field,_) in ASSETS.items(): item[name]=number(r.get(field,""))
  parsed.append(item)
 usable=[r for r in parsed if all(r[n] is not None for n in ASSETS)]
 equity_names=("A_shares_CSI300","US_equity_SP500","Developed_exUS_EFA","Emerging_EEM")
 equity_mix=(0.20,0.12,0.10,0.10)
 mix_total=sum(equity_mix)
 scenarios={}
 for eq in (0.52,0.45,0.42,0.38,0.35,0.30,0.25,0.20):
  w={n:eq*x/mix_total for n,x in zip(equity_names,equity_mix)}
  w["US_aggregate_bonds_AGG"]=1-eq-0.10-0.10
  w["Gold_proxy"]=0.10
  w["CNY_cash_H11025"]=0.10
  scenarios[f"equity_{int(eq*100)}"]=w
 summary=[]
 for label,w in scenarios.items():
  for mode in ("buy_hold","annual","threshold"):
   vals,turn=run_strategy(usable,w,mode,0.001)
   st=stats(vals)
   st.update({"allocation":label,"equity_weight":sum(w[n] for n in equity_names),
    "bond_proxy_weight":w["US_aggregate_bonds_AGG"],"gold_weight":w["Gold_proxy"],
    "cash_weight":w["CNY_cash_H11025"],"strategy":mode,"one_way_cost":0.001,
    "average_annual_turnover":statistics.mean(turn)*12 if turn else 0,
    "worst_12m":rolling_worst(vals,12),"worst_36m":rolling_worst(vals,36),
    "worst_60m":rolling_worst(vals,60),"worst_120m":rolling_worst(vals,120)})
   summary.append(st)
 with (OUT/"equity_allocation_comparison.csv").open("w",encoding="utf-8-sig",newline="") as f:
  wri=csv.DictWriter(f,fieldnames=list(summary[0]));wri.writeheader();wri.writerows(summary)
 # Paired block bootstrap: annual rebalancing only, same sampled asset paths for all allocations.
 boot=[]
 for block in (12,24,36):
  for spend in SPENDS:
   for infl in (0.02,0.04):
    for crash in (0.0,0.30):
     for label,w in scenarios.items():
      res=bootstrap("annual",usable,w,block,spend,infl,crash)
      res["allocation"]=label
      res["equity_weight"]=sum(w[n] for n in equity_names)
      res["bond_proxy_weight"]=w["US_aggregate_bonds_AGG"]
      boot.append(res)
 with (OUT/"equity_allocation_withdrawal_comparison.csv").open("w",encoding="utf-8-sig",newline="") as f:
  wri=csv.DictWriter(f,fieldnames=list(boot[0]));wri.writeheader();wri.writerows(boot)
 with (OUT/"equity_allocation_comparison_manifest.json").open("w",encoding="utf-8") as f:
  json.dump({"status":"PROVISIONAL_RESEARCH_PROXY","sample_start":usable[0]["date"],
   "sample_end":usable[-1]["date"],"common_months":len(usable),"paths_per_case":N_PATHS,
   "allocations":scenarios,"method":"Same monthly asset-return rows, same 10bp one-way trading cost, same 12/24/36-month circular block bootstrap; equity sleeve mix held proportional to the 52% draft; bonds absorb the equity-weight difference; gold and cash fixed at 10% each.",
   "important_limitations":["This is not a fully investable portfolio backtest.",
   "The 28/35/38% bond sleeve is proxied entirely by US AGG ETF RMB total return, not the intended CNY government/policy-bank bond portfolio.",
   "The equity proxies include CSI300, S&P500, EFA and EEM; EEM includes China, so exposure overlaps the China sleeves.",
   "Gold is a monthly-average spot valuation proxy; cash history includes backfilled index observations.",
   "No official Hang Seng total-return index, complete investable fund histories, taxes, personal tax status, rent growth or future contributions.",
   "Bootstrap survival rates are empirical resampling frequencies, not objective real-world probabilities."]},f,ensure_ascii=False,indent=2)
 print(json.dumps({"allocation_sensitivity":"PASS","rows":len(summary),"withdrawal_rows":len(boot)},ensure_ascii=False))

if __name__=="__main__":
 main()
 allocation_sensitivity()
