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

def field(item, key):
    return (((item or {}).get("fields") or {}).get(key) or {})
def v(item, key):
    z = field(item,key).get("value")
    return float(z) if isinstance(z,(int,float)) and math.isfinite(z) else None
def unit_multiplier(item):
    unit=str((item or {}).get("reportedUnit") or "").strip().lower().replace(" ","")
    return {"元":1,"人民币元":1,"人民币":1,"港元":1,"美元":1,
            "千元":1e3,"人民币千元":1e3,"千港元":1e3,"千美元":1e3,
            "万元":1e4,"人民币万元":1e4,"万港元":1e4,"万美元":1e4,
            "百万元":1e6,"人民币百万元":1e6,"百万港元":1e6,"百万美元":1e6,
            "亿元":1e8,"人民币亿元":1e8,"亿港元":1e8,"亿美元":1e8}.get(unit)
def debt_components(balance):
    return [v(balance,k) for k in ("shortBorrowings","longBorrowings","bondsPayable","currentLeaseLiabilities","leaseLiabilities")]
def calc_effective_tax_rate(income):
    pbt,tax=v(income,"profitBeforeTax"),v(income,"incomeTax")
    if pbt is None or tax is None or pbt<=0:return None
    rate=tax/pbt
    return rate if 0<=rate<=0.50 else None

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

def classify_source(url):
    u=str(url or "").lower()
    if not u:return "missing"
    if any(d in u for d in ("cninfo.com.cn","hkexnews.hk","sec.gov")):return "official_regulatory_filing"
    return "secondary_or_unclassified"

def is_financial(stock):
    s = " ".join(str(stock.get(k) or "") for k in ("industry","businessType","method"))
    return any(t in s for t in ("银行","保险","证券","券商","金融"))

def main():
    master=json.loads(MASTER.read_text(encoding="utf-8"))
    fin=json.loads(FIN.read_text(encoding="utf-8"))
    audit_path=ROOT/"data/valuation-inputs/valuation-input-audit-49.json"
    input_audit=json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else {"records":[]}
    audit_by_code={x["code"]:x for x in input_audit.get("records",[])}
    financial_by_code={x["code"]:x for x in fin.get("companies",[])}
    history=load_history()
    results=[]
    audit={"generatedAtUtc":datetime.now(timezone.utc).isoformat(),"masterCompanies":len(master.get("stocks",[])),
           "financialRecordsMatched":0,"historyRecordsMatched":0,
           "metrics":{"annualRevenue":0,"annualProfit":0,"annualROE":0,"annualFCF":0,"annualNetDebt":0,"annualNetDebtKnownComponents":0,
                      "annualROIC":0,"annualDividendCashFlowOnly":0,"annualDilutedShareProxy":0,"annualShareCapital":0,"annualAcquisitions":0,"annualInvestments":0,
                      "annualBuybacks":0,"annualDebtRepayments":0,"annualDividendsOnly":0},
           "historyCoverage":{m:{"latest":0,"5Y":0,"10Y":0} for m in METRICS},
           "verification":{"issuerReportCrossChecksPending":49,"currentFullyDilutedSharesVerified":0,
                           "dividendPerShareHistoryVerified":0,"companySpecificScenarioVerified":0,
                           "costOfCapitalVerified":0},
           "warnings":["Provider fields are not independently issuer-report verified merely because they were retrieved.",
                       "Reported currency and unit are not inferred; no cross-company comparison is permitted without normalization.",
                       "ROIC is a derived approximation only where operating profit, pretax profit, tax, current liabilities, debt, cash and investments are complete.",
                       "Net debt is gross interest-bearing debt less cash; short/long investments are not netted.",
                       "DividendsPaidCombinedWithInterest is not a dividend-only field and is never used as a payout ratio.",
                       "Implied weighted-average diluted shares are not current fully diluted shares; per-share fair value remains blocked."]}
    for stock in master.get("stocks",[]):
        code=stock["code"].split("/")[0].strip()
        c=financial_by_code.get(stock["code"]) or financial_by_code.get(code)
        fdata=(c or {}).get("primaryFinancials") or {}
        financial=is_financial(stock)
        annual=[]
        prior_equity=None
        prior_invested_capital=None
        for yr in YEARS:
            rec=next((x for x in (fdata.get("annual") or []) if int(x.get("year",0))==yr),None)
            inc=(rec or {}).get("income") or {}
            bal=(rec or {}).get("balance") or {}
            cf=(rec or {}).get("cashflow") or {}
            revenue=v(inc,"revenue"); profit=v(inc,"netProfitParent")
            equity=v(bal,"parentEquity"); total_equity=v(bal,"totalEquity")
            assets=v(bal,"totalAssets"); current_liabilities=v(bal,"currentLiabilities")
            op=v(inc,"operatingProfit"); pbt=v(inc,"profitBeforeTax"); tax=v(inc,"incomeTax")
            interest=v(inc,"interestExpense"); diluted_eps=v(inc,"dilutedEps")
            ocf=v(cf,"operatingCashFlow"); capex=v(cf,"capex")
            dividends_only=v(cf,"dividendsPaidOnly"); dividends_combined=v(cf,"dividendsPaid")
            share_capital=v(bal,"shareCapital")
            acquisitions_paid=v(cf,"acquisitionsPaid"); investments_purchased=v(cf,"investmentsPurchased")
            investments_disposed=v(cf,"investmentsDisposed"); buybacks_paid=v(cf,"shareBuybacksPaid")
            debt_repayments=v(cf,"debtRepayments"); interest_paid=v(cf,"interestPaid"); equity_raised=v(cf,"equityRaised")
            cash=v(bal,"cash"); short_invest=v(bal,"shortTermInvestments"); long_invest=v(bal,"longTermInvestments")
            debts=debt_components(bal)
            gross_debt=sum(debts) if all(x is not None for x in debts) else None
            net_debt=(gross_debt-cash) if (not financial and gross_debt is not None and cash is not None) else None
            known_debt_values=[x for x in debts if x is not None]
            net_debt_known_components=(sum(known_debt_values)-cash) if (not financial and known_debt_values and cash is not None) else None
            avg_equity=(equity+prior_equity)/2 if equity is not None and prior_equity is not None and (equity+prior_equity)>0 else None
            roe=profit/avg_equity*100 if profit is not None and avg_equity else None
            tax_rate=calc_effective_tax_rate(inc)
            nopat=op*(1-tax_rate) if (not financial and op is not None and tax_rate is not None) else None
            invested_capital=None
            if not financial and all(x is not None for x in (assets,current_liabilities,cash,short_invest,long_invest,*debts)):
                invested_capital=assets-current_liabilities+gross_debt-cash-short_invest-long_invest
            avg_invested=(invested_capital+prior_invested_capital)/2 if invested_capital is not None and prior_invested_capital is not None and invested_capital>0 and prior_invested_capital>0 else None
            roic=(nopat/avg_invested*100) if (nopat is not None and avg_invested is not None and avg_invested>0) else None
            fcf=ocf-capex if (not financial and ocf is not None and capex is not None) else None
            capex_intensity=capex/revenue*100 if capex is not None and revenue not in (None,0) else None
            dividend_payout=dividends_only/profit*100 if dividends_only is not None and profit is not None and profit>0 else None
            implied_diluted_shares=None
            amount_multiplier=unit_multiplier(inc)
            if profit is not None and diluted_eps not in (None,0) and amount_multiplier is not None:
                implied_diluted_shares=profit*amount_multiplier/diluted_eps
            annual.append({"year":yr,"revenue":revenue,"netProfitParent":profit,"operatingProfit":op,"profitBeforeTax":pbt,
                           "incomeTax":tax,"effectiveTaxRate":tax_rate,"nopat":nopat,"totalAssets":assets,
                           "currentLiabilities":current_liabilities,"parentEquity":equity,"totalEquity":total_equity,
                           "averageParentEquity":avg_equity,"roePct":roe,"operatingCashFlow":ocf,"capex":capex,
                           "freeCashFlow":fcf,"capexToRevenuePct":capex_intensity,"cash":cash,
                           "shortTermInvestments":short_invest,"longTermInvestments":long_invest,
                           "interestBearingDebtComponents":{"shortBorrowings":debts[0],"longBorrowings":debts[1],
                             "bondsPayable":debts[2],"currentLeaseLiabilities":debts[3],"leaseLiabilities":debts[4]},
                           "grossDebt":gross_debt,"netDebt":net_debt,"netDebtKnownComponents":net_debt_known_components,
                           "knownDebtComponentCount":len(known_debt_values),"investedCapital":invested_capital,
                           "averageInvestedCapital":avg_invested,"roicPct":roic,"interestExpense":interest,
                           "basicEps":v(inc,"basicEps"),"dilutedEps":diluted_eps,
                           "impliedWeightedAverageDilutedShares":implied_diluted_shares,"shareCapitalRaw":share_capital,
                           "dividendsPaidOnly":dividends_only,"dividendsPaidCombinedWithInterest":dividends_combined,
                           "cashDividendPayoutRatioPct":dividend_payout,
                           "capitalAllocation":{"acquisitionsPaid":acquisitions_paid,"investmentsPurchased":investments_purchased,
                             "investmentsDisposed":investments_disposed,"shareBuybacksPaid":buybacks_paid,
                             "debtRepayments":debt_repayments,"interestPaid":interest_paid,"equityRaised":equity_raised},
                           "status":{"roic":"derived" if roic is not None else "pending_missing_or_incomparable_inputs",
                             "netDebt":"derived" if net_debt is not None else ("not_applicable_financial_institution" if financial else "pending_missing_debt_or_cash"),
                             "dividend":"separate_cash_dividend_field" if dividends_only is not None else ("combined_with_interest_or_missing" if dividends_combined is not None else "pending"),
                             "dilutedShares":"weighted_average_proxy_only" if implied_diluted_shares is not None else "pending_unit_or_eps"}})
            prior_equity=equity
            prior_invested_capital=invested_capital
        last5=[x for x in annual if x["revenue"] is not None]
        growth=cagr(last5[0]["revenue"],last5[-1]["revenue"],last5[-1]["year"]-last5[0]["year"]) if len(last5)>=2 else None
        margins=[x["netProfitParent"]/x["revenue"] for x in annual[-3:] if x["netProfitParent"] is not None and x["revenue"] not in (None,0)]
        fcf_margins=[x["freeCashFlow"]/x["revenue"] for x in annual[-3:] if x["freeCashFlow"] is not None and x["revenue"] not in (None,0)]
        capex_ratios=[x["capexToRevenuePct"] for x in annual[-3:] if x["capexToRevenuePct"] is not None]
        forecast={"status":"reference_only" if growth is not None and margins else "insufficient_history",
                  "label":"estimated_mechanical_scenario_not_guidance","baseRevenueCagr":growth,
                  "baseNetMargin":median(margins),"baseFcfMargin":None if financial else median(fcf_margins),
                  "baseCapexToRevenuePct":median(capex_ratios),"scenarios":{},
                  "limitations":["No issuer guidance or analyst consensus embedded.",
                    "No verified reinvestment schedule, dilution, M&A, working-capital or capital-cycle forecast.",
                    "Forecast inputs are mechanical historical starting points, not a company-specific investment thesis."]}
        if forecast["status"]=="reference_only":
            for name,spread in (("bear",-0.05),("base",0.0),("bull",0.05)):
                g=max(-0.20,min(0.30,growth+spread))
                margin=forecast["baseNetMargin"]
                nm=max(-0.50,min(0.80,margin+{"bear":-0.015,"base":0.0,"bull":0.015}[name]))
                fm=forecast["baseFcfMargin"]
                if not financial and fm is not None: fm=max(-0.50,min(0.80,fm+{"bear":-0.03,"base":0.0,"bull":0.03}[name]))
                base_rev=last5[-1]["revenue"]; rows=[]
                for n in range(1,6):
                    base_rev*=1+g
                    rows.append({"year":last5[-1]["year"]+n,"revenue":base_rev,
                                 "netProfit":base_rev*nm if nm is not None else None,
                                 "freeCashFlow":None if financial or fm is None else base_rev*fm})
                forecast["scenarios"][name]={"revenueGrowth":g,"netMargin":nm,
                    "fcfMargin":None if financial else fm,"years":rows}
        hrows=history.get(code,{})
        h={m:history_metric(hrows,m) for m in METRICS}
        for m,x in h.items():
            if x["latest"] is not None:audit["historyCoverage"][m]["latest"]+=1
            if x["p5"] is not None:audit["historyCoverage"][m]["5Y"]+=1
            if x["p10"] is not None:audit["historyCoverage"][m]["10Y"]+=1
        if c:audit["financialRecordsMatched"]+=1
        if hrows:audit["historyRecordsMatched"]+=1
        checks=(("annualRevenue",lambda x:x["revenue"] is not None),("annualProfit",lambda x:x["netProfitParent"] is not None),
                ("annualROE",lambda x:x["roePct"] is not None),("annualFCF",lambda x:x["freeCashFlow"] is not None),
                ("annualNetDebt",lambda x:x["netDebt"] is not None),
                ("annualNetDebtKnownComponents",lambda x:x["netDebtKnownComponents"] is not None),("annualROIC",lambda x:x["roicPct"] is not None),
                ("annualDividendCashFlowOnly",lambda x:x["dividendsPaidOnly"] is not None),
                ("annualDilutedShareProxy",lambda x:x["impliedWeightedAverageDilutedShares"] is not None),
                ("annualShareCapital",lambda x:x["shareCapitalRaw"] is not None),
                ("annualAcquisitions",lambda x:x["capitalAllocation"]["acquisitionsPaid"] is not None),
                ("annualInvestments",lambda x:x["capitalAllocation"]["investmentsPurchased"] is not None),
                ("annualBuybacks",lambda x:x["capitalAllocation"]["shareBuybacksPaid"] is not None),
                ("annualDebtRepayments",lambda x:x["capitalAllocation"]["debtRepayments"] is not None),
                ("annualDividendsOnly",lambda x:x["dividendsPaidOnly"] is not None))
        for k,cond in checks:
            if any(cond(x) for x in annual):audit["metrics"][k]+=1
        source_audit=audit_by_code.get(stock["code"]) or audit_by_code.get(code) or {}
        fin_source=source_audit.get("source",{}).get("financial")
        capex_source=source_audit.get("source",{}).get("capex")
        verification_register={
          "officialReportCrossCheck":{"status":"pending","sourceClass":classify_source(fin_source),"sourceUrl":fin_source,"required":"发行人/交易所正式年报、审计意见、合并范围、币种单位及关键科目逐项核对"},
          "roic":{"status":"calculated_not_independently_verified" if any(x["roicPct"] is not None for x in annual) else "pending_inputs","availableYears":sum(x["roicPct"] is not None for x in annual),"required":"NOPAT税基、全部有息债务、现金、投资、商誉、租赁口径及平均投入资本"},
          "netDebt":{"status":"calculated_not_independently_verified" if any(x["netDebt"] is not None for x in annual) else ("not_applicable_financial" if financial else "pending_inputs"),"availableYears":sum(x["netDebt"] is not None for x in annual),"knownComponentsYears":sum(x["netDebtKnownComponents"] is not None for x in annual),"required":"短借、长借、债券、流动/非流动租赁负债、现金逐项勾稽；若部分债项缺失，只报告已识别债务项净额，不称为完整净债务"},
          "shareCapital":{"status":"raw_share_capital_only" if any(x["shareCapitalRaw"] is not None for x in annual) else "pending","availableYears":sum(x["shareCapitalRaw"] is not None for x in annual),"required":"期末股本、股数、面值、送转、增发、回购、库存股及A/H/ADR换算"},
          "currentFullyDilutedShares":{"status":"pending","required":"估值日已发行股数+期权/限制股/可转债等潜在稀释，需与公告及股权激励文件核对"},
          "dividendPerShareHistory":{"status":"pending","required":"逐年每股股息、特别股息、除权日、派息币种及股息再投资口径"},
          "capitalAllocation":{"status":"partial_cashflow_fields_only","sourceClass":classify_source(capex_source),"required":"维护/扩张资本开支、并购、投资、分红、回购、偿债和股权融资逐项核对"},
          "companySpecificForecast":{"status":"mechanical_reference_only","required":"量价驱动、产能/门店/用户/订单、价格、毛利率、费用率、税率、再投资率及管理层指引"},
          "costOfCapital":{"status":"pending","required":"估值日无风险利率、Beta估计窗口、股权风险溢价、债务成本、税率和目标资本结构"}
        }
        results.append({"name":stock.get("name"),"code":stock.get("code"),"primaryListingCode":(c or {}).get("primaryListingCode"),
                        "industry":stock.get("industry"),"businessType":stock.get("businessType"),"modelType":stock.get("method"),
                        "isFinancialInstitution":financial,"currency":stock.get("currency"),
                        "sourceCurrencies":fdata.get("sourceCurrencies",[]),"reportedUnits":fdata.get("reportedUnits",[]),
                        "sourceLinks":source_audit.get("source",{}),"officialSearchUrl":"https://www.cninfo.com.cn/new/index" if stock.get("code","").split("/")[0].endswith((".SH",".SZ")) else "https://www.hkexnews.hk/index.htm?sc_lang=en","annual":annual,"history":h,"forecast5Y":forecast,
                        "valuationFramework":{"method":stock.get("method"),"requiredInputs":stock.get("requiredMetrics",[]),
                          "status":"pending_company_specific_assumptions_and_independent_verification",
                          "companySpecificAssumptions":{"historicalRevenueCagr":growth,"recentThreeYearMedianNetMargin":median(margins),"recentThreeYearMedianCapexToRevenue":median(capex_ratios),"sustainableROE":None,"normalizedROIC":median([x["roicPct"] for x in annual if x["roicPct"] is not None]),"WACC":None,"costOfEquity":None,"terminalGrowth":None,"currentFullyDilutedShares":None,"fairValuePerShare":None,"status":"historical_reference_only_until_official_crosscheck"},
                          "requiredAssumptions":["normalized earnings / sustainable ROE","forecast revenue and margin drivers",
                            "reinvestment and maintenance capex","cost of equity or WACC with dated inputs",
                            "terminal growth or exit multiple","current fully diluted shares","dividend and buyback policy"],
                          "valuationOutputStatus":"blocked_no_verified_per_share_fair_value"},
                        "verification":{"financialSourceCrossCheck":"pending_official_issuer_report","register":verification_register,"shareCount":"pending_current_fully_diluted_shares",
                          "dividendHistory":"pending_per_share_and_ex_date_history","capitalAllocation":"pending_capex_mna_dividend_buyback_reconciliation",
                          "companySpecificScenarios":"pending_driver_based_forecast","costOfCapital":"pending_dated_risk_free_beta_erp"},
                        "quality":{"financialHistoryMatched":bool(c),"annualRevenueYears":sum(x["revenue"] is not None for x in annual),
                          "annualProfitYears":sum(x["netProfitParent"] is not None for x in annual),
                          "annualROEYears":sum(x["roePct"] is not None for x in annual),
                          "annualFCFYears":sum(x["freeCashFlow"] is not None for x in annual),
                          "annualNetDebtYears":sum(x["netDebt"] is not None for x in annual),
                          "annualNetDebtKnownComponentsYears":sum(x["netDebtKnownComponents"] is not None for x in annual),
                          "annualROICYears":sum(x["roicPct"] is not None for x in annual),
                          "annualDividendCashFlowOnlyYears":sum(x["dividendsPaidOnly"] is not None for x in annual),
                          "annualDilutedShareProxyYears":sum(x["impliedWeightedAverageDilutedShares"] is not None for x in annual),
                          "annualShareCapitalYears":sum(x["shareCapitalRaw"] is not None for x in annual),
                          "annualAcquisitionsYears":sum(x["capitalAllocation"]["acquisitionsPaid"] is not None for x in annual),
                          "annualInvestmentPurchaseYears":sum(x["capitalAllocation"]["investmentsPurchased"] is not None for x in annual),
                          "annualBuybackYears":sum(x["capitalAllocation"]["shareBuybacksPaid"] is not None for x in annual),
                          "annualDebtRepaymentYears":sum(x["capitalAllocation"]["debtRepayments"] is not None for x in annual),
                          "roicStatus":"calculated_only_if_complete_components_and_tax_base_available",
                          "dilutedSharesStatus":"weighted_average_proxy_not_current_fully_diluted",
                          "perShareFairValueStatus":"blocked_until_current_share_count_currency_unit_and_assumptions_verified"}})
    OUT.mkdir(parents=True,exist_ok=True)
    output={"schemaVersion":"1.1.0","generatedAtUtc":datetime.now(timezone.utc).isoformat(),
            "sourceFiles":{"master":str(MASTER.relative_to(ROOT)),"financial":str(FIN.relative_to(ROOT)),
                           "history":str(HISTORY.relative_to(ROOT)),"inputAudit":str(audit_path.relative_to(ROOT))},
            "companyCount":len(results),
            "methodology":{"roe":"归母净利润 / 年初年末归母权益平均值；首年无上年权益时留空",
              "fcf":"经营活动现金流净额 - 购建固定资产、无形资产和其他长期资产支付的现金；简化FCF，不等于股权自由现金流",
              "netDebt":"完整净债务=短期借款+长期借款+应付债券+流动及非流动租赁负债-现金；仅当全部债务分项与现金均有值时计算。另列已识别债务项净额，仅作不完整分项汇总，不得称为完整净债务；不扣短/长期投资；金融企业不适用",
              "roic":"NOPAT=营业利润*(1-所得税费用/利润总额)；投入资本=总资产-流动负债+全部已映射有息债务(短借+长借+债券+流动租赁负债+非流动租赁负债)-现金-短期投资-长期投资；ROIC=NOPAT/平均投入资本；税率限定0%-50%，缺项留空。该口径为近似值，需逐项核验。不得只加回短借和流动租赁负债。",
              "dilutedShares":"归母净利润/稀释EPS并按财报金额单位换算，只代表年度加权平均稀释股数代理，不代表估值日当前完全稀释股数；单位不明则留空。",
              "dividends":"单列现金股息支付字段才计算现金派息率；股利/利润与利息合并字段不视为纯股息。",
              "forecast":"历史收入CAGR及最近三年净利率中位数的机械情景，不是公司指引或分析师预测。"},
            "companies":results}
    (OUT/"valuation-model-49.json").write_text(json.dumps(output,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    register={"schemaVersion":"1.0.0","generatedAtUtc":datetime.now(timezone.utc).isoformat(),
              "companyCount":len(results),"records":[{"code":x["code"],"name":x["name"],"industry":x["industry"],
              "modelType":x["modelType"],"sourceLinks":x["sourceLinks"],"officialSearchUrl":x["officialSearchUrl"],"verification":x["verification"]["register"],
              "companySpecificAssumptions":x["valuationFramework"]["companySpecificAssumptions"],
              "valuationOutputStatus":x["valuationFramework"]["valuationOutputStatus"]} for x in results]}
    (OUT/"valuation-verification-register-49.json").write_text(json.dumps(register,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"valuation-model-audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
