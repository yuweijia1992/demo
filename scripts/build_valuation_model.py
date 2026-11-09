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
REPORT_INDEX = ROOT / "data/valuation-model/issuer-report-index-49.json"
OUT = ROOT / "data/valuation-model"
YEARS = list(range(2021, 2026))
METRICS = ("peTtm", "pb", "psTtm")

MODEL_DRIVER_TEMPLATES = {
 "quality_earnings_fcf": [
  ("volumeGrowth","销量/业务量增长率","%","销量、出货量、客户数或门店数的历史与指引"),
  ("priceMixGrowth","价格与产品结构变化","%","ASP、产品结构、提价与折扣"),
  ("grossMargin","毛利率","%","产品结构、原材料成本、产能利用率"),
  ("opexRatio","销售及管理研发费用率","%","分项费用率和经营杠杆"),
  ("workingCapitalDays","营运资本周转天数","days","应收、存货、应付及合同负债"),
  ("maintenanceCapex","维护性资本开支","currency/year","维持现有产能所需资本开支"),
  ("growthCapex","扩张性资本开支","currency/year","新增产能、产线、门店和项目投资"),
  ("normalizedTaxRate","正常化税率","%","所得税调节表及优惠到期时间")],
 "normalized_cycle": [
  ("midCyclePrice","中周期产品价格","currency/unit","至少一个完整行业周期的价格与成本"),
  ("midCycleVolume","中周期销量/产能利用率","units or %","产能、产量、库存和利用率"),
  ("midCycleUnitCost","中周期单位成本","currency/unit","成本曲线、原料和能源成本"),
  ("normalizedMargin","正常化利润率","%","跨周期毛利率和费用率"),
  ("replacementCapex","维持性资本开支","currency/year","设备更新与环保安全投入"),
  ("cycleLength","行业周期长度","years","历史供需周期证据")],
 "growth_dcf": [
  ("addressableMarket","可服务市场规模","currency","可核验市场规模及统计口径"),
  ("marketShare","市场份额","%","公司收入/同口径市场规模"),
  ("volumeGrowth","销量/用户/订单增长率","%","出货量、用户、订单、产能爬坡"),
  ("aspArpuGrowth","ASP/ARPU增长率","%","价格、产品组合或用户变现"),
  ("grossMargin","毛利率路径","%","规模效应、产品结构与竞争"),
  ("reinvestmentRate","再投资率","%","研发、资本开支、营运资本及并购"),
  ("dilution","年度股本稀释率","%","股权激励、可转债、增发及回购")],
 "cashflow_dcf": [
  ("regulatedVolume","业务量/发电量/客流","units/year","发电量、客流、处理量、利用小时"),
  ("tariffPrice","核准价格/单位收入","currency/unit","监管核价、合同价格与调价机制"),
  ("utilization","产能利用率","%","可用率、利用小时、产能"),
  ("maintenanceCapex","维护性资本开支","currency/year","检修、更新改造与安全环保"),
  ("growthCapex","扩张性资本开支","currency/year","在建工程、项目预算和投产时间"),
  ("concessionLife","特许经营/资产剩余期限","years","特许经营权、项目协议及到期安排"),
  ("netDebtSchedule","债务偿还与融资成本","currency/year","债务期限、利率、再融资安排")],
 "bank_pb_roe": [
  ("sustainableROE","可持续ROE","%","五至十年ROE、拨备周期和资本约束"),
  ("costOfEquity","股权资本成本","%","估值日无风险利率、Beta、ERP"),
  ("bookValueGrowth","每股净资产增长率","%","留存收益、分红、增发及回购"),
  ("payoutRatio","可持续分红率","%","现金分红、资本补充和监管要求"),
  ("creditCost","信用成本","%","不良生成率、核销、拨备覆盖"),
  ("capitalAdequacy","核心一级资本充足率","%","监管披露和资本规划"),
  ("assetQuality","不良率/关注类贷款率","%","五级分类、逾期及重组贷款")],
 "broker_pb_roe": [
  ("normalizedROE","正常化ROE","%","至少一个完整市场周期的平均ROE及投资损益拆分"),
  ("netAssetsPerShare","每股净资产","currency/share","归母权益、期末股数、库存股与股本变化"),
  ("investmentIncomeNormalized","正常化投资收益","currency/year","自营投资收益、OCI、公允价值变动和减值"),
  ("commissionRate","经纪/投行/资管费率","%","业务收入、成交额、承销规模和管理规模"),
  ("capitalAdequacy","净资本及风险覆盖率","%","监管资本、风险资本准备和流动性指标"),
  ("creditRisk","两融/股票质押风险","currency","融资融券余额、担保品折扣、减值与追偿"),
  ("costOfEquity","股权资本成本","%","估值日无风险利率、Beta、ERP"),
  ("payoutRatio","可持续分红率","%","现金分红、资本补充和监管要求")],
 "semiconductor_growth_dcf": [
  ("waferShipments","出货量/设备交付量","units/year","产能、订单、交付、客户验证与库存"),
  ("yieldAndUtilization","良率/产能利用率","%","制程节点、产品良率、稼动率和爬坡周期"),
  ("productMixASP","产品结构与平均售价","currency/unit","先进制程/成熟制程、产品组合及价格"),
  ("backlog","在手订单/客户资本开支","currency","客户订单、交期、取消条款及资本开支周期"),
  ("grossMargin","毛利率路径","%","折旧、良率、产品组合与供应链成本"),
  ("rdIntensity","研发费用率","%","研发费用、资本化政策、核心产品路线图"),
  ("capexAndDepreciation","资本开支与折旧","currency/year","厂房设备投入、折旧年限、产能投放"),
  ("exportControls","出口管制/供应链限制","scenario","许可、客户集中度、关键设备和替代能力")],
 "pharma_medtech_growth_dcf": [
  ("pipelineMilestones","研发管线/注册里程碑","milestones","临床阶段、成功概率、注册审批和适应症"),
  ("launchRevenue","新产品收入贡献","currency/year","已上市产品销售、渗透率、医保与渠道"),
  ("volumeAndPricing","销量与价格","units and currency","终端量、集采、医保谈判和价格变化"),
  ("grossMargin","毛利率路径","%","产品结构、自产比例和产能利用率"),
  ("rdIntensity","研发费用率","%","研发费用、临床投入和资本化政策"),
  ("salesEfficiency","销售费用率/渠道效率","%","销售队伍、医院覆盖、经销商库存"),
  ("patentAndCompetition","专利期限与竞争格局","scenario","专利到期、仿制药、竞品和替代技术")],
 "digital_platform_growth_dcf": [
  ("activeUsers","活跃用户/客户数","users","MAU/DAU、付费用户、留存与获客成本"),
  ("monetization","ARPU/广告变现率","currency/user","广告加载率、付费率、客单价和变现"),
  ("takeRate","平台抽佣率/变现率","%","GMV、平台收入、商家结构和佣金政策"),
  ("cloudOrNewBusinessGrowth","云/新业务增长率","%","分部收入、订单、客户数和毛利"),
  ("grossMargin","分部毛利率","%","业务组合、履约成本和内容成本"),
  ("contentAndRAndD","内容/研发投入","currency/year","内容采购、研发费用和资本化"),
  ("regulatoryAndCompetition","监管与竞争情景","scenario","监管政策、反垄断、竞争强度和用户迁移"),
  ("dilution","年度股本稀释率","%","股权激励、可转债、增发及回购")],
 "insurance_ev": [
  ("nbvGrowth","新业务价值增长率","%","NBV/VNB、价值率、代理人和银保渠道"),
  ("csmRelease","CSM释放率","%","合同服务边际及释放节奏"),
  ("investmentReturn","投资收益率","%","总/综合投资收益率及资产配置"),
  ("solvency","偿付能力充足率","%","核心/综合偿付能力与资本补充"),
  ("sustainableROE","可持续ROE","%","保险服务结果、投资结果和资本"),
  ("costOfEquity","股权资本成本","%","估值日无风险利率、Beta、ERP"),
  ("dividendCapacity","可分配现金与分红能力","currency/year","偿付能力、现金流及分红约束")]
}

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
    return [v(balance,k) for k in ("shortBorrowings","shortTermBonds","currentPortionLongTermDebt","longBorrowings","bondsPayable","currentLeaseLiabilities","leaseLiabilities")]

def cash_equivalents_for_net_debt(balance,cashflow=None):
    # Do not net all "monetary funds": restricted deposits may not be freely available.
    ce = v(balance,"cashAndCashEquivalents")
    if ce is not None:
        return ce, "balance_sheet_cash_and_cash_equivalents"
    ce_end = v(cashflow,"cashAndCashEquivalentsEnding")
    if ce_end is not None:
        return ce_end, "cash_flow_statement_ending_cash_equivalents"
    cash_field = field(balance,"cash")
    source_name = str(cash_field.get("sourceField") or "").strip()
    if source_name in ("现金及现金等价物","现金和现金等价物","现金及等价物"):
        return cash_field.get("value"), "cash_field_explicitly_cash_equivalents"
    return None, "cash_equivalents_not_separately_identified"

def current_interest_bearing_debt(balance):
    # Only add back debt demonstrably included in current liabilities.
    keys = ("shortBorrowings","shortTermBonds","currentPortionLongTermDebt","currentLeaseLiabilities")
    vals = [v(balance,k) for k in keys]
    if all(x is not None for x in vals):
        return sum(vals), dict(zip(keys,vals))
    return None, dict(zip(keys,vals))
def calc_invested_capital(total_assets,current_liabilities,current_interest_debt,cash_equivalents,short_investments,long_investments):
    values=(total_assets,current_liabilities,current_interest_debt,cash_equivalents,short_investments,long_investments)
    if any(x is None for x in values):
        return None
    non_interest_current_liabilities=current_liabilities-current_interest_debt
    if non_interest_current_liabilities<0:
        return None
    result=total_assets-non_interest_current_liabilities-cash_equivalents-short_investments-long_investments
    return result if result>0 else None

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

def company_driver_template(stock):
    model_type=stock.get("method")
    industry=" ".join(str(stock.get(k) or "") for k in ("industry","businessType","name"))
    if any(x in industry for x in ("证券","券商")):
        template="broker_pb_roe"
    elif any(x in industry for x in ("半导体","芯片","光模块","光通信")):
        template="semiconductor_growth_dcf"
    elif any(x in industry for x in ("医药","医疗器械","创新药","眼科医疗")):
        template="pharma_medtech_growth_dcf"
    elif any(x in industry for x in ("平台","电商","社交","视频社区","互联网","云与算力")):
        template="digital_platform_growth_dcf"
    else:
        template=model_type if model_type in MODEL_DRIVER_TEMPLATES else "quality_earnings_fcf"
    rows=MODEL_DRIVER_TEMPLATES[template]
    return [{"key":k,"label":label,"unit":unit,"value":None,
             "status":"needs_company_specific_source","template":template,
             "sourceRequirement":source,
             "note":"不允许以行业均值或模型猜测填入公司实际值"} for k,label,unit,source in rows]

def issuer_search_url(stock,official_reports=None):
    code=str(stock.get("code") or "").split("/")[0].strip()
    base=code.split(".")[0]
    if code.endswith((".SH",".SZ")):
        org=(official_reports or {}).get("orgId")
        if org:
            return "https://www.cninfo.com.cn/new/disclosure/stock?orgId="+str(org)+"&stockCode="+base
        return "https://www.cninfo.com.cn/new/fulltextSearch?notautosubmit=&keyWord="+base
    return "https://www1.hkexnews.hk/search/titlesearch.xhtml?lang=en"

def is_financial(stock):
    s = " ".join(str(stock.get(k) or "") for k in ("industry","businessType","method"))
    return any(t in s for t in ("银行","保险","证券","券商","金融"))

def main():
    master=json.loads(MASTER.read_text(encoding="utf-8"))
    fin=json.loads(FIN.read_text(encoding="utf-8"))
    audit_path=ROOT/"data/valuation-inputs/valuation-input-audit-49.json"
    input_audit=json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else {"records":[]}
    report_index=json.loads(REPORT_INDEX.read_text(encoding="utf-8")) if REPORT_INDEX.exists() else {"records":[]}
    reports_by_code={x["code"]:x for x in report_index.get("records",[])}
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
                       "ROIC is an approximate derived metric and remains null unless NOPAT, non-interest-bearing current liabilities, separately identified cash equivalents and non-operating investments are complete and comparable.",
                       "Net debt is gross interest-bearing debt less separately identified cash and cash equivalents; total monetary funds containing restricted deposits are not automatically deducted.",
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
            revenue_item=v(inc,"revenue"); total_operating_revenue=v(inc,"totalOperatingRevenue")
            revenue=revenue_item if revenue_item is not None else (total_operating_revenue if financial else None)
            revenue_basis="营业收入" if revenue_item is not None else ("营业总收入（金融企业回退）" if financial and total_operating_revenue is not None else None)
            profit=v(inc,"netProfitParent")
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
            cash=v(bal,"cash"); cash_equivalents,cash_basis=cash_equivalents_for_net_debt(bal,cf)
            restricted_cash=v(bal,"restrictedCash")
            short_invest=v(bal,"shortTermInvestments"); long_invest=v(bal,"longTermInvestments")
            debts=debt_components(bal)
            gross_debt=sum(debts) if all(x is not None for x in debts) else None
            net_debt=(gross_debt-cash_equivalents) if (not financial and gross_debt is not None and cash_equivalents is not None) else None
            known_debt_values=[x for x in debts if x is not None]
            net_debt_known_components=(sum(known_debt_values)-cash_equivalents) if (not financial and known_debt_values and cash_equivalents is not None) else None
            avg_equity=(equity+prior_equity)/2 if equity is not None and prior_equity is not None and (equity+prior_equity)>0 else None
            roe=profit/avg_equity*100 if profit is not None and avg_equity else None
            tax_rate=calc_effective_tax_rate(inc)
            nopat=op*(1-tax_rate) if (not financial and op is not None and tax_rate is not None) else None
            current_debt_in_current_liabilities,current_debt_detail=current_interest_bearing_debt(bal)
            # Long-term debt is not added again: it is already represented in assets/funding.
            invested_capital=calc_invested_capital(assets,current_liabilities,current_debt_in_current_liabilities,cash_equivalents,short_invest,long_invest) if not financial else None
            avg_invested=(invested_capital+prior_invested_capital)/2 if invested_capital is not None and prior_invested_capital is not None and invested_capital>0 and prior_invested_capital>0 else None
            roic=(nopat/avg_invested*100) if (nopat is not None and avg_invested is not None and avg_invested>0) else None
            fcf=ocf-capex if (not financial and ocf is not None and capex is not None) else None
            capex_intensity=capex/revenue*100 if capex is not None and revenue not in (None,0) else None
            dividend_payout=dividends_only/profit*100 if dividends_only is not None and profit is not None and profit>0 else None
            implied_diluted_shares=None
            amount_multiplier=unit_multiplier(inc)
            if profit is not None and diluted_eps not in (None,0) and amount_multiplier is not None:
                implied_diluted_shares=profit*amount_multiplier/diluted_eps
            annual.append({"year":yr,"revenue":revenue,"revenueBasis":revenue_basis,"totalOperatingRevenue":total_operating_revenue,"netProfitParent":profit,"operatingProfit":op,"profitBeforeTax":pbt,
                           "incomeTax":tax,"effectiveTaxRate":tax_rate,"nopat":nopat,"totalAssets":assets,
                           "currentLiabilities":current_liabilities,"parentEquity":equity,"totalEquity":total_equity,
                           "averageParentEquity":avg_equity,"roePct":roe,"operatingCashFlow":ocf,"capex":capex,
                           "freeCashFlow":fcf,"capexToRevenuePct":capex_intensity,"cash":cash,"cashAndCashEquivalents":cash_equivalents,"cashFlowEndingCashAndCashEquivalents":v(cf,"cashAndCashEquivalentsEnding"),"cashDeductionBasis":cash_basis,"restrictedCash":restricted_cash,
                           "shortTermInvestments":short_invest,"longTermInvestments":long_invest,
                           "interestBearingDebtComponents":{"shortBorrowings":debts[0],"shortTermBonds":debts[1],
                             "currentPortionLongTermDebt":debts[2],"longBorrowings":debts[3],"bondsPayable":debts[4],
                             "currentLeaseLiabilities":debts[5],"leaseLiabilities":debts[6]},
                           "grossDebt":gross_debt,"netDebt":net_debt,"netDebtKnownComponents":net_debt_known_components,
                           "knownDebtComponentCount":len(known_debt_values),"currentDebtIncludedInCurrentLiabilities":current_debt_detail,"nonInterestBearingCurrentLiabilities":(current_liabilities-current_debt_in_current_liabilities) if current_liabilities is not None and current_debt_in_current_liabilities is not None else None,"investedCapital":invested_capital,
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
        official_reports=reports_by_code.get(stock["code"]) or reports_by_code.get(code)
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
                        "sourceLinks":source_audit.get("source",{}),"officialSearchUrl":issuer_search_url(stock,official_reports),"officialReports":official_reports,"annual":annual,"history":h,"forecast5Y":forecast,
                        "valuationFramework":{"method":stock.get("method"),"requiredInputs":stock.get("requiredMetrics",[]),
                          "status":"pending_company_specific_assumptions_and_independent_verification",
                          "companySpecificAssumptions":{"historicalRevenueCagr":growth,"recentThreeYearMedianNetMargin":median(margins),"recentThreeYearMedianCapexToRevenue":median(capex_ratios),"sustainableROE":None,"normalizedROIC":median([x["roicPct"] for x in annual if x["roicPct"] is not None]),"WACC":None,"costOfEquity":None,"terminalGrowth":None,"currentFullyDilutedShares":None,"dividendPerShareHistory":None,"maintenanceCapex":None,"growthCapex":None,"costOfEquityInputs":None,"fairValuePerShare":None,"status":"historical_reference_only_until_official_crosscheck"},
                          "requiredAssumptions":["normalized earnings / sustainable ROE","forecast revenue and margin drivers",
                            "reinvestment and maintenance capex","cost of equity or WACC with dated inputs",
                            "terminal growth or exit multiple","current fully diluted shares","dividend and buyback policy"],
                          "companyDriverTemplate":company_driver_template(stock),
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
    evidence_path=OUT/"issuer-verification-evidence.json"
    manual_evidence=json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.exists() else {"records":[]}
    evidence_by_code={x["code"]:x for x in manual_evidence.get("records",[])}
    for company in results:
        ev=evidence_by_code.get(company["code"])
        if ev:
            company["verification"]["manualEvidence"]=ev
            company["verification"]["financialSourceCrossCheck"]=ev.get("status","partial_report_text_crosscheck")
            company["verification"]["register"]["officialReportCrossCheck"]["status"]=ev.get("status","partial_report_text_crosscheck")
            company["verification"]["register"]["officialReportCrossCheck"]["sourceClass"]="issuer_official_pdf_partial_crosscheck"
            company["verification"]["register"]["officialReportCrossCheck"]["sourceUrl"]=ev.get("officialPdfUrl")
            company["verification"]["register"]["officialReportCrossCheck"]["officialPdfUrl"]=ev.get("officialPdfUrl")
            company["verification"]["register"]["officialReportCrossCheck"]["issuerIRUrl"]=ev.get("issuerIRUrl")
            company["verification"]["register"]["officialReportCrossCheck"]["reportTextUrl"]=ev.get("reportTextUrl")
            company["verification"]["register"]["capitalAllocation"]["sourceClass"]="issuer_official_pdf_partial_crosscheck"
            company["verification"]["register"]["capitalAllocation"]["sourceUrl"]=ev.get("officialPdfUrl")
            verified=ev.get("verifiedFields") or {}
            if verified.get("netDebtFY2025"):
                debt_value=verified["netDebtFY2025"].get("value")
                company["verification"]["register"]["netDebt"]["status"]="partial_fy2025_official_pdf_verified_current_period_pending"
                company["verification"]["register"]["netDebt"]["sourceClass"]="issuer_official_pdf_crosschecked"
                company["verification"]["register"]["netDebt"]["verifiedFY2025"]=debt_value
                company["verification"]["register"]["netDebt"]["grossDebtFY2025"]=verified.get("grossInterestBearingDebtFY2025",{}).get("value")
                company["verification"]["register"]["netDebt"]["verifiedMethod"]=verified["netDebtFY2025"].get("method")
                company["verification"]["register"]["netDebt"]["required"]="FY2025已按官方年报核验；仍需核对FY2026半年报/三季报债务、现金及估值日后变动"
                for annual_row in company.get("annual",[]):
                    if annual_row.get("year")==2025:
                        annual_row["issuerVerifiedNetDebtFY2025"]=debt_value
                        annual_row["issuerVerifiedGrossDebtFY2025"]=verified.get("grossInterestBearingDebtFY2025",{}).get("value")
                        annual_row["issuerNetDebtEvidenceStatus"]="partial_official_pdf_crosscheck"
            if verified.get("paidFY2025InterimDividendPerShare") or verified.get("paidFY2025FinalDividendPerShare"):
                company["verification"]["register"]["dividendPerShareHistory"]["status"]="partial_paid_fy2025_and_proposed_fy2026_dividends"
                company["verification"]["register"]["dividendPerShareHistory"]["availablePeriods"]=["FY2025 interim 0.48元/股（已派）","FY2025 final 0.90元/股（已派）","FY2026 interim 0.42元/股（预案，待实施）"]
                company["verification"]["register"]["dividendPerShareHistory"]["required"]="仍需补齐至少五年历史、特别股息、除权/支付日期及估值日股数口径"
            if verified.get("sharesOutstandingNetOfTreasuryAsOf2026_11_02"):
                company["verification"]["register"]["shareCapital"]["status"]="reported_share_count_less_buyback_snapshot_not_fully_diluted"
                company["verification"]["register"]["shareCapital"]["sourceClass"]="issuer_official_pdf_crosschecked"
                company["verification"]["register"]["shareCapital"]["snapshotDate"]="2026-11-02"
                company["verification"]["register"]["shareCapital"]["totalShareCapital"]=verified.get("totalShareCapitalAt2026Q3",{}).get("value")
                company["verification"]["register"]["shareCapital"]["treasuryShares"]=verified.get("sharesRepurchasedAsOf2026_11_02",{}).get("value")
                company["verification"]["register"]["shareCapital"]["netOfTreasuryShares"]=verified["sharesOutstandingNetOfTreasuryAsOf2026_11_02"].get("value")
                company["verification"]["register"]["shareCapital"]["required"]="这是扣除已回购股份后的在外股数快照，不等于完全稀释股数；仍需核对回购注销、期权、股权激励和后续股本变化"
                company["verification"]["register"]["currentFullyDilutedShares"]["reportedSharesOutstandingSnapshot"]=verified.get("totalShareCapitalAt2026Q3",{}).get("value")
                company["verification"]["register"]["currentFullyDilutedShares"]["treasurySharesSnapshot"]=verified.get("sharesRepurchasedAsOf2026_11_02",{}).get("value")
                company["verification"]["register"]["currentFullyDilutedShares"]["netOfTreasurySnapshot"]=verified["sharesOutstandingNetOfTreasuryAsOf2026_11_02"].get("value")
                company["verification"]["register"]["currentFullyDilutedShares"]["status"]="reported_share_count_snapshot_not_fully_diluted"
    audit["verification"]["issuerVerifiedNetDebtCompanies"]=sum(1 for x in manual_evidence.get("records",[]) if (x.get("verifiedFields") or {}).get("netDebtFY2025",{}).get("value") is not None)
    audit["verification"]["issuerVerifiedShareCountSnapshots"]=sum(1 for x in manual_evidence.get("records",[]) if (x.get("verifiedFields") or {}).get("sharesOutstandingNetOfTreasuryAsOf2026_11_02",{}).get("value") is not None)
    audit["verification"]["issuerPartialDividendHistoryRecords"]=sum(1 for x in manual_evidence.get("records",[]) if (x.get("verifiedFields") or {}).get("paidFY2025FinalDividendPerShare",{}).get("value") is not None)
    audit["issuerEvidenceRecords"]=len(evidence_by_code)
    audit["issuerEvidenceCrossChecks"]=sum(1 for x in manual_evidence.get("records",[]) if x.get("status")=="fully_crosschecked")
    audit["issuerReportCrossChecksPartial"]=sum(1 for x in manual_evidence.get("records",[]) if x.get("status") in ("partial_report_text_crosscheck","partial_official_pdf_crosscheck"))
    audit["verification"]["issuerReportCrossChecksPending"]=max(0,len(results)-audit["issuerEvidenceCrossChecks"]-audit["issuerReportCrossChecksPartial"])
    OUT.mkdir(parents=True,exist_ok=True)
    output={"schemaVersion":"1.1.0","generatedAtUtc":datetime.now(timezone.utc).isoformat(),
            "sourceFiles":{"master":str(MASTER.relative_to(ROOT)),"financial":str(FIN.relative_to(ROOT)),
                           "history":str(HISTORY.relative_to(ROOT)),"inputAudit":str(audit_path.relative_to(ROOT)),"officialReportIndex":str(REPORT_INDEX.relative_to(ROOT)) if REPORT_INDEX.exists() else None},
            "companyCount":len(results),
            "methodology":{"roe":"归母净利润 / 年初年末归母权益平均值；首年无上年权益时留空",
              "fcf":"经营活动现金流净额 - 购建固定资产、无形资产和其他长期资产支付的现金；简化FCF，不等于股权自由现金流",
              "netDebt":"完整净债务=短期借款+短期应付债券+一年内到期长期债务+长期借款+应付债券+流动及非流动租赁负债-单独识别的现金及现金等价物；不以含受限资金的货币资金总额抵扣。仅当全部债务分项与现金等价物均有值时计算。金融企业不适用。",
              "roic":"近似ROIC：NOPAT=营业利润*(1-所得税费用/利润总额)；投入资本=总资产-(流动负债-明确列示且包含于流动负债的短借/短期债券/一年内到期长期债务/流动租赁负债)-现金及现金等价物-短期投资-长期投资；ROIC=NOPAT/平均投入资本。长期借款、长期债券及非流动租赁负债不得重复加回。当前债务分项不完整、现金等价物未单独识别或投资项缺失时不计算。税率限定0%-50%。",
              "dilutedShares":"归母净利润/稀释EPS并按财报金额单位换算，只代表年度加权平均稀释股数代理，不代表估值日当前完全稀释股数；单位不明则留空。",
              "dividends":"单列现金股息支付字段才计算现金派息率；股利/利润与利息合并字段不视为纯股息。",
              "forecast":"历史收入CAGR及最近三年净利率中位数的机械情景，不是公司指引或分析师预测。"},
            "companies":results}
    (OUT/"valuation-model-49.json").write_text(json.dumps(output,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    register={"schemaVersion":"1.0.0","generatedAtUtc":datetime.now(timezone.utc).isoformat(),
              "companyCount":len(results),"records":[{"code":x["code"],"name":x["name"],"industry":x["industry"],
              "modelType":x["modelType"],"sourceLinks":x["sourceLinks"],"officialSearchUrl":x["officialSearchUrl"],"officialReports":x.get("officialReports"),"verification":x["verification"]["register"],"manualEvidence":x["verification"].get("manualEvidence"),
              "companySpecificAssumptions":x["valuationFramework"]["companySpecificAssumptions"],
              "valuationOutputStatus":x["valuationFramework"]["valuationOutputStatus"]} for x in results]}
    (OUT/"valuation-verification-register-49.json").write_text(json.dumps(register,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"valuation-model-audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=="__main__": main()

# Rebuild after cash-equivalent and regression-test updates.

# Rebuild after official annual/interim/Q3 report index refresh.
