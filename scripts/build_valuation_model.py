#!/usr/bin/env python3
"""Build auditable company-level valuation inputs from standardized statements and monthly history.
No missing-value imputation, no inferred currency/unit conversion, no automatic buy recommendation.
"""
from __future__ import annotations
import csv, json, math, statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "data/china-stocks-financial-valuation.json"
FIN = ROOT / "data/financial-standardized/company-financials-2021-2025.json"
HISTORY = ROOT / "data/valuation-history/generated/valuation-monthly.csv"
OUT = ROOT / "data/valuation-model"
YEARS = list(range(2021, 2026))
METRICS = ("peTtm", "pb", "psTtm")

def v(item, key):
    x = ((item or {}).get("fields") or {}).get(key) or {}
    z = x.get("value")
    return float(z) if isinstance(z, (int, float)) and math.isfinite(z) else None

def median(xs):
    a = [float(x) for x in xs if x is not None and math.isfinite(float(x))]
    return statistics.median(a) if a else None

def cagr(first, last, periods):
    if first is None or last is None or first <= 0 or last <= 0 or periods <= 0:
        return None
    return (last / first) ** (1 / periods) - 1

def quantile(xs, p):
    a = sorted(x for x in xs if x is not None and math.isfinite(x))
    if not a: return None
    pos = (len(a) - 1) * p
    lo, hi = math.floor(pos), math.ceil(pos)
    return a[lo] if lo == hi else a[lo] * (hi - pos) + a[hi] * (pos - lo)

def percentile(xs, x):
    if x is None or not xs: return None
    return 100 * (sum(v < x for v in xs) + .5 * sum(v == x for v in xs)) / len(xs)

def month_index(date):
    try:
        return int(date[:4]) * 12 + int(date[5:7]) - 1
    except Exception:
        return None

def load_history():
    data = {}
    if not HISTORY.exists(): return data
    with HISTORY.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            code = str(r.get("code") or "").split("/")[0].strip().upper()
            mi = month_index(str(r.get("date") or ""))
            if not code or mi is None: continue
            row = {"date": str(r.get("date"))[:10], "monthIndex": mi, "source": r.get("source"), "sourceUrl": r.get("sourceUrl")}
            for k in (*METRICS, "close"):
                try:
                    n = float(r.get(k, ""))
                    row[k] = n if math.isfinite(n) and n > 0 else None
                except Exception: row[k] = None
            old = data.setdefault(code, {}).get(mi)
            if old is None or row["date"] > old["date"]:
                data[code][mi] = row
    return data

def history_metric(rows, metric):
    if not rows: return {"status":"missing","latest":None,"p5":None,"p10":None,"n5":0,"n10":0}
    series = sorted(rows.values(), key=lambda x:x["monthIndex"])
    latest = series[-1]
    current = latest.get(metric)
    out = {"status":"pending","latest":current,"date":latest["date"],"source":latest.get("source"),
           "sourceUrl":latest.get("sourceUrl"),"p5":None,"p10":None,"p20":None,"p50":None,"p80":None,
           "n5":0,"n10":0,"method":"latest valid monthly observation; 60/120 consecutive calendar months required"}
    if current is None:
        out["status"]="latest_missing"; return out
    for label, months in (("5",60),("10",120)):
        start = latest["monthIndex"] - months + 1
        by_month = {x["monthIndex"]:x.get(metric) for x in series if start <= x["monthIndex"] <= latest["monthIndex"]}
        vals = [by_month.get(i) for i in range(start, latest["monthIndex"]+1)]
        valid = [x for x in vals if x is not None]
        out["n"+label] = len(valid)
        if len(vals) == months and all(x is not None for x in vals):
            out["p"+label] = percentile(valid,current)
            if label == "5":
                out["p20"],out["p50"],out["p80"] = quantile(valid,.2),quantile(valid,.5),quantile(valid,.8)
    out["status"]="complete" if out["p5"] is not None and out["p10"] is not None else ("5y_complete" if out["p5"] is not None else "insufficient_contiguous_history")
    return out

def is_financial(stock):
    s = " ".join(str(stock.get(k) or "") for k in ("industry","businessType","method"))
    return any(t in s for t in ("银行","保险","证券","券商","金融"))

def main():
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    fin = json.loads(FIN.read_text(encoding="utf-8"))
    financial_by_code = {x["code"]:x for x in fin.get("companies",[])}
    history = load_history()
    results=[]
    audit={"generatedAtUtc":datetime.now(timezone.utc).isoformat(),"masterCompanies":len(master.get("stocks",[])),
           "financialRecordsMatched":0,"historyRecordsMatched":0,"metrics":{"annualRevenue":0,"annualProfit":0,"annualROE":0,"annualFCF":0,"annualNetDebt":0,"annualROIC":0},
           "historyCoverage":{m:{"latest":0,"5Y":0,"10Y":0} for m in METRICS},
           "warnings":["Financial fields from data provider remain pending independent issuer-report verification unless source audit says otherwise.",
                       "Source currency and reported unit are not converted or inferred.",
                       "ROIC is not calculated unless NOPAT and average invested capital are both supported by complete, comparable source fields.",
                       "Net debt is not calculated unless cash and every mapped interest-bearing debt component are present; null is not treated as zero.",
                       "No per-share fair value is generated without verified diluted shares, consistent units and security-specific currency."]}
    for stock in master.get("stocks",[]):
        code=stock["code"].split("/")[0].strip()
        c=financial_by_code.get(stock["code"]) or financial_by_code.get(code)
        fdata=(c or {}).get("primaryFinancials") or {}
        financial=is_financial(stock)
        annual=[]
        prior_equity=None
        for yr in YEARS:
            rec=next((x for x in (fdata.get("annual") or []) if int(x.get("year",0))==yr),None)
            inc=(rec or {}).get("income") or {}
            bal=(rec or {}).get("balance") or {}
            cf=(rec or {}).get("cashflow") or {}
            revenue=v(inc,"revenue"); profit=v(inc,"netProfitParent")
            equity=v(bal,"parentEquity"); assets=v(bal,"totalAssets")
            op=v(inc,"operatingProfit"); tax=v(inc,"incomeTax")
            ocf=v(cf,"operatingCashFlow"); capex=v(cf,"capex")
            cash=v(bal,"cash")
            debt_parts=[v(bal,k) for k in ("shortBorrowings","longBorrowings","bondsPayable","leaseLiabilities")]
            net_debt=(sum(debt_parts)-cash) if (not financial and cash is not None and all(x is not None for x in debt_parts)) else None
            avg_equity=(equity+prior_equity)/2 if equity is not None and prior_equity is not None and (equity+prior_equity)>0 else None
            roe=profit/avg_equity*100 if profit is not None and avg_equity else None
            # Deliberately conservative: current mapping does not establish a comparable NOPAT tax base and invested-capital scope.
            roic=None
            fcf=ocf-capex if (not financial and ocf is not None and capex is not None) else None
            annual.append({"year":yr,"revenue":revenue,"netProfitParent":profit,"operatingProfit":op,"incomeTax":tax,
                           "totalAssets":assets,"parentEquity":equity,"averageParentEquity":avg_equity,
                           "roePct":roe,"operatingCashFlow":ocf,"capex":capex,"freeCashFlow":fcf,
                           "cash":cash,"interestBearingDebtComponents":debt_parts,"netDebt":net_debt,
                           "roicPct":roic,"status":{"revenue":"derived_from_source_mapping" if revenue is not None else "missing",
                           "profit":"derived_from_source_mapping" if profit is not None else "missing",
                           "roe":"derived" if roe is not None else "pending",
                           "fcf":"derived" if fcf is not None else "pending",
                           "netDebt":"derived" if net_debt is not None else "pending",
                           "roic":"pending_methodology_and_source_inputs"}})
            prior_equity=equity
        last5=[x for x in annual if x["revenue"] is not None]
        profit5=[x for x in annual if x["netProfitParent"] is not None]
        roe5=[x["roePct"] for x in annual if x["roePct"] is not None]
        fcf5=[x["freeCashFlow"] for x in annual if x["freeCashFlow"] is not None]
        growth=cagr(last5[0]["revenue"],last5[-1]["revenue"],last5[-1]["year"]-last5[0]["year"]) if len(last5)>=2 else None
        margins=[x["netProfitParent"]/x["revenue"] for x in annual[-3:] if x["netProfitParent"] is not None and x["revenue"] not in (None,0)]
        fcf_margins=[x["freeCashFlow"]/x["revenue"] for x in annual[-3:] if x["freeCashFlow"] is not None and x["revenue"] not in (None,0)]
        forecast={"status":"reference_only" if growth is not None and margins else "insufficient_history",
                  "label":"estimated_mechanical_scenario_not_guidance",
                  "baseRevenueCagr":growth,"baseNetMargin":median(margins),
                  "baseFcfMargin":None if financial else median(fcf_margins),
                  "scenarios":{},"limitations":["No analyst consensus or company guidance is embedded.",
                  "Mechanical sensitivity only; no explicit reinvestment, dilution, acquisitions, working-capital, capital-cycle or macro shock model."]}
        if forecast["status"]=="reference_only":
            for name,spread in (("bear",-0.05),("base",0.0),("bull",0.05)):
                g=max(-0.20,min(0.30,growth+spread))
                margin=forecast["baseNetMargin"]
                mshift={"bear":-0.015,"base":0.0,"bull":0.015}[name]
                nm=max(-0.50,min(0.80,margin+mshift))
                fm=forecast["baseFcfMargin"]
                if not financial and fm is not None: fm=max(-0.50,min(0.80,fm+{"bear":-0.03,"base":0.0,"bull":0.03}[name]))
                base_rev=last5[-1]["revenue"]
                rows=[]
                for n in range(1,6):
                    base_rev*=1+g
                    rows.append({"year":last5[-1]["year"]+n,"revenue":base_rev,
                                 "netProfit":base_rev*nm if nm is not None else None,
                                 "freeCashFlow":None if financial or fm is None else base_rev*fm})
                forecast["scenarios"][name]={"revenueGrowth":g,"netMargin":nm,"fcfMargin":None if financial else fm,"years":rows}
        hrows=history.get(code,{})
        h={m:history_metric(hrows,m) for m in METRICS}
        for m,x in h.items():
            if x["latest"] is not None:audit["historyCoverage"][m]["latest"]+=1
            if x["p5"] is not None:audit["historyCoverage"][m]["5Y"]+=1
            if x["p10"] is not None:audit["historyCoverage"][m]["10Y"]+=1
        if c:audit["financialRecordsMatched"]+=1
        if hrows:audit["historyRecordsMatched"]+=1
        for k,cond in (("annualRevenue",lambda x:x["revenue"] is not None),("annualProfit",lambda x:x["netProfitParent"] is not None),
                       ("annualROE",lambda x:x["roePct"] is not None),("annualFCF",lambda x:x["freeCashFlow"] is not None),
                       ("annualNetDebt",lambda x:x["netDebt"] is not None),("annualROIC",lambda x:x["roicPct"] is not None)):
            if any(cond(x) for x in annual):audit["metrics"][k]+=1
        results.append({"name":stock.get("name"),"code":stock.get("code"),"primaryListingCode":(c or {}).get("primaryListingCode"),
                        "industry":stock.get("industry"),"businessType":stock.get("businessType"),"modelType":stock.get("method"),
                        "isFinancialInstitution":financial,"currency":stock.get("currency"),
                        "financialSource":(c or {}).get("primaryFinancials",{}).get("unitPolicy"),
                        "sourceCurrencies":fdata.get("sourceCurrencies",[]),"reportedUnits":fdata.get("reportedUnits",[]),
                        "annual":annual,"history":h,"forecast5Y":forecast,
                        "quality":{"financialHistoryMatched":bool(c),"annualRevenueYears":sum(x["revenue"] is not None for x in annual),
                                   "annualProfitYears":sum(x["netProfitParent"] is not None for x in annual),
                                   "annualROEYears":sum(x["roePct"] is not None for x in annual),
                                   "annualFCFYears":sum(x["freeCashFlow"] is not None for x in annual),
                                   "annualNetDebtYears":sum(x["netDebt"] is not None for x in annual),
                                   "roicStatus":"not_calculated_conservative_policy",
                                   "dilutedSharesStatus":"not_available_in_standardized_dataset",
                                   "perShareFairValueStatus":"blocked_until_currency_unit_and_diluted_shares_verified"}})
    OUT.mkdir(parents=True,exist_ok=True)
    output={"schemaVersion":"1.0.0","generatedAtUtc":datetime.now(timezone.utc).isoformat(),
            "sourceFiles":{"master":str(MASTER.relative_to(ROOT)),"financial":str(FIN.relative_to(ROOT)),"history":str(HISTORY.relative_to(ROOT))},
            "companyCount":len(results),"methodology":{"roe":"归母净利润 / 年初年末归母权益平均值；首年无上年权益时留空",
            "fcf":"经营活动现金流净额 - 购建固定资产、无形资产和其他长期资产支付的现金；简化FCF，不等于股权自由现金流",
            "netDebt":"短期借款+长期借款+应付债券+租赁负债-现金；仅当四类债务与现金均有值时计算，金融机构不解释为普通企业净债务",
            "roic":"本版不计算：缺少可比NOPAT税基及投入资本完整口径，不以营业利润或税费代理",
            "forecast":"历史收入CAGR及最近三年利润率中位数的机械情景；悲观/乐观分别对增长率±5个百分点、净利率±1.5个百分点；FCF利润率±3个百分点；仅作假设起点"},
            "companies":results}
    (OUT/"valuation-model-49.json").write_text(json.dumps(output,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    (OUT/"valuation-model-audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=="__main__": main()

# Pipeline revision: trigger a fresh run after wiring the web dashboard.
