#!/usr/bin/env python3
"""Build auditable portfolio risk statistics from the canonical RMB monthly matrix.

Missing observations are never filled. All portfolio statistics use the same
complete common sample across the nine target sleeves. Stress shocks are
transparent deterministic assumptions, not forecasts.
"""
from __future__ import annotations
import csv, json, math, statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data/investment-monthly.csv"
OUT=ROOT/"data/research"
OUT.mkdir(parents=True,exist_ok=True)
ASSETS={
 "A_shares_CSI300":("csi300_total_return_pct",0.08,"CNY"),
 "HK_2800_proxy":("hang_seng_etf_2800_total_return_cny_pct",0.02,"HKD/CNY proxy"),
 "US_equity_SP500":("sp500_total_return_cny_pct",0.25,"USD/CNY"),
 "Developed_exUS_EFA":("efa_developed_markets_etf_total_return_cny_pct",0.11,"basket/CNY"),
 "Emerging_EEM":("eem_emerging_markets_etf_total_return_cny_pct",0.06,"basket/CNY"),
 "ChinaBond_CBA00201_candidate":("china_bond_wealth_return_cny_pct",0.23,"CNY"),
 "US_AGG_proxy":("us_agg_etf_total_return_cny_pct",0.05,"USD/CNY"),
 "Gold_CNY":("gold_cny_return_pct",0.10,"CNY"),
 "Cash_H11025":("cny_cash_return_pct",0.10,"CNY"),
}
COST=0.001
THRESHOLD=0.05
SCENARIOS={
 "Global recession":{"A_shares_CSI300":-0.35,"HK_2800_proxy":-0.40,"US_equity_SP500":-0.30,"Developed_exUS_EFA":-0.32,"Emerging_EEM":-0.38,"ChinaBond_CBA00201_candidate":0.03,"US_AGG_proxy":0.04,"Gold_CNY":0.08,"Cash_H11025":0.0},
 "Inflation and rate shock":{"A_shares_CSI300":-0.20,"HK_2800_proxy":-0.22,"US_equity_SP500":-0.25,"Developed_exUS_EFA":-0.22,"Emerging_EEM":-0.25,"ChinaBond_CBA00201_candidate":-0.05,"US_AGG_proxy":-0.08,"Gold_CNY":0.05,"Cash_H11025":0.01},
 "Taiwan Strait / limited US-China conflict":{"A_shares_CSI300":-0.35,"HK_2800_proxy":-0.45,"US_equity_SP500":-0.20,"Developed_exUS_EFA":-0.18,"Emerging_EEM":-0.35,"ChinaBond_CBA00201_candidate":-0.03,"US_AGG_proxy":0.02,"Gold_CNY":0.15,"Cash_H11025":0.0},
 "Liquidity selloff":{"A_shares_CSI300":-0.30,"HK_2800_proxy":-0.35,"US_equity_SP500":-0.30,"Developed_exUS_EFA":-0.30,"Emerging_EEM":-0.35,"ChinaBond_CBA00201_candidate":-0.04,"US_AGG_proxy":-0.06,"Gold_CNY":-0.08,"Cash_H11025":0.0},
 "Stagflation":{"A_shares_CSI300":-0.25,"HK_2800_proxy":-0.30,"US_equity_SP500":-0.25,"Developed_exUS_EFA":-0.25,"Emerging_EEM":-0.30,"ChinaBond_CBA00201_candidate":-0.06,"US_AGG_proxy":-0.08,"Gold_CNY":0.10,"Cash_H11025":0.01},
}
def num(x):
 try:
  return float(x)/100 if x is not None and str(x).strip() else None
 except ValueError:return None
def quantile(xs,p):
 ys=sorted(xs)
 if not ys:return None
 pos=(len(ys)-1)*p; lo=math.floor(pos); hi=math.ceil(pos)
 return ys[lo] if lo==hi else ys[lo]*(hi-pos)+ys[hi]*(pos-lo)
def maxdd(returns):
 wealth=1.; peak=1.; peak_i=0; worst=0.; trough_i=0; peak_at_trough=0
 nav=[1.]
 for i,r in enumerate(returns,1):
  wealth*=1+r;nav.append(wealth)
  if wealth>peak:peak=wealth;peak_i=i
  dd=wealth/peak-1
  if dd<worst:worst=dd;trough_i=i;peak_at_trough=peak_i
 # recovery time after the worst trough, if the old peak was regained
 target=nav[peak_at_trough]; recovery=None
 for j in range(trough_i+1,len(nav)):
  if nav[j]>=target:recovery=j-trough_i;break
 ongoing=(len(nav)-1-trough_i) if recovery is None and worst<0 else 0
 return worst, (trough_i-peak_at_trough), recovery, ongoing, nav
def stats(returns):
 if not returns:return {}
 ann=math.prod(1+x for x in returns)**(12/len(returns))-1
 vol=statistics.stdev(returns)*math.sqrt(12) if len(returns)>1 else 0
 dd,dd_months,recovery,ongoing,nav=maxdd(returns)
 return {"months":len(returns),"annualized_return":ann,"annualized_volatility":vol,
 "max_drawdown":dd,"drawdown_peak_to_trough_months":dd_months,
 "months_to_recover_old_peak":recovery,"ongoing_drawdown_months":ongoing,
 "worst_month":min(returns),"best_month":max(returns),"terminal_wealth_multiple":nav[-1]}
def strategy(rows,weights,mode):
 names=list(weights);target=[weights[n] for n in names];cur=target[:];out=[];turns=[];nav=1.
 for i,row in enumerate(rows):
  rebalance=(mode=="annual" and i>0 and row["date"][5:7]=="01")
  if mode=="threshold" and i>0:
   drift=[x/sum(cur) for x in cur]
   rebalance=any(abs(x-y)>THRESHOLD for x,y in zip(drift,target))
  turnover=0.
  if rebalance:
   turnover=sum(abs(x-y) for x,y in zip(cur,target))/2
   cur=target[:]
  gross=sum(w*row[n] for w,n in zip(cur,names))
  net=(1+gross)*(1-COST*turnover)-1
  out.append(net);turns.append(turnover)
  post=[w*(1+row[n]) for w,n in zip(cur,names)];total=sum(post)
  cur=[x/total for x in post]
 return out,turns
def corr(xs,ys):
 pairs=[(x,y) for x,y in zip(xs,ys) if x is not None and y is not None]
 if len(pairs)<2:return None
 a=[x for x,y in pairs];b=[y for x,y in pairs]
 ma=statistics.mean(a);mb=statistics.mean(b)
 va=sum((x-ma)**2 for x in a);vb=sum((y-mb)**2 for y in b)
 return sum((x-ma)*(y-mb) for x,y in pairs)/math.sqrt(va*vb) if va and vb else None
def main():
 with DATA.open(encoding="utf-8-sig",newline="") as f:
  reader=csv.DictReader(f);raw=list(reader)
 rows=[]
 for r in raw:
  x={"date":r["date"]}
  for name,(field,_,_) in ASSETS.items():x[name]=num(r.get(field))
  if all(x[k] is not None for k in ASSETS):rows.append(x)
 if len(rows)<120:raise SystemExit(f"Only {len(rows)} complete months; need >=120")
 names=list(ASSETS);weights={k:v[1] for k,v in ASSETS.items()}
 # Pairwise correlations, with pair-specific sample counts.
 corr_rows=[]
 for a in names:
  row={"asset":a}
  for b in names:row[b]=corr([x[a] for x in rows],[x[b] for x in rows])
  corr_rows.append(row)
 with (OUT/"asset_correlation_matrix.csv").open("w",encoding="utf-8-sig",newline="") as f:
  w=csv.DictWriter(f,fieldnames=["asset"]+names);w.writeheader();w.writerows(corr_rows)
 summary={}
 nav_rows=[]
 for mode in ("buy_hold","annual","threshold"):
  rets,turns=strategy(rows,weights,mode);s=stats(rets)
  s["average_annual_turnover"]=statistics.mean(turns)*12
  s["one_way_transaction_cost"]=COST
  summary[mode]=s
  dd,_,_,_,nav=maxdd(rets)
  for i,(r,n) in enumerate(zip(rets,nav[1:])):
   nav_rows.append({"date":rows[i]["date"],"strategy":mode,"monthly_return":r,"nav":n})
 with (OUT/"portfolio_nav_monthly.csv").open("w",encoding="utf-8-sig",newline="") as f:
  w=csv.DictWriter(f,fieldnames=["date","strategy","monthly_return","nav"]);w.writeheader();w.writerows(nav_rows)
 stress=[]
 for label,shocks in SCENARIOS.items():
  ret=sum(weights[k]*shocks[k] for k in names)
  stress.append({"scenario":label,"portfolio_return":ret,"loss_cny_at_400w":-ret*4_000_000,
    "assumptions":json.dumps(shocks,ensure_ascii=False)})
 foreign=sum(weights[k] for k in ("HK_2800_proxy","US_equity_SP500","Developed_exUS_EFA","Emerging_EEM","US_AGG_proxy"))
 for fx_move in (-.20,-.10,.10,.20):
  stress.append({"scenario":f"Foreign-currency basket moves {fx_move:+.0%} vs CNY (simplified)","portfolio_return":foreign*fx_move,
    "loss_cny_at_400w":-foreign*fx_move*4_000_000,"assumptions":f"Gross foreign-currency-denominated sleeve {foreign:.1%}; assumes uniform currency move and unchanged local asset prices"})
 with (OUT/"portfolio_stress_scenarios.csv").open("w",encoding="utf-8-sig",newline="") as f:
  w=csv.DictWriter(f,fieldnames=["scenario","portfolio_return","loss_cny_at_400w","assumptions"]);w.writeheader();w.writerows(stress)
 payload={
 "schema_version":"1.0","status":"PROVISIONAL_PROXY_RESEARCH","generated_at":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds"),
 "sample":{"start":rows[0]["date"],"end":rows[-1]["date"],"months":len(rows),"complete_case_rule":"All nine return fields present; no forward-fill or missing-as-zero."},
 "target_weights":weights,"asset_fields":{k:v[0] for k,v in ASSETS.items()},
 "strategies":summary,
 "foreign_currency_gross_weight":foreign,
 "correlation_file":"asset_correlation_matrix.csv","nav_file":"portfolio_nav_monthly.csv","stress_file":"portfolio_stress_scenarios.csv",
 "stress_scenarios":stress,
 "limitations":["2800.HK is an ETF proxy, not official Hang Seng Gross TRI.","CBA00201 series is a ChinaBond Composite Wealth candidate; index-code mapping and redistribution rights remain unverified.","AGG is unhedged USD-denominated US aggregate bond ETF proxy, not a RMB-hedged offshore bond mandate.","EEM contains China and Taiwan exposure; geographical overlap remains.","EFA/EEM are ETF proxies and their local-currency exposure is a basket; foreign-currency shock assumes uniform basket movement.","Historical returns and deterministic stress scenarios are not forecasts; sample begins only when all nine fields overlap.","Monthly average gold price is not an investable fund total-return series.","Costs assume 10bp per one-way traded notional and do not include tax, spread, FX conversion or fund tracking error."]
 }
 (OUT/"portfolio-risk-dashboard.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps({"sample":payload["sample"],"strategies":summary,"foreign_currency_gross_weight":foreign},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
