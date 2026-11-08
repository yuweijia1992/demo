#!/usr/bin/env python3
"""Normalize archived financial statements into a traceable issuer-level dataset."""
from __future__ import annotations
import hashlib, json, math, re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data/raw-financials"
OUT_DIR = ROOT / "data/financial-standardized"
MASTER_PATH = ROOT / "data/china-stocks-financial-valuation.json"
YEARS = list(range(2021, 2026))
DATE_FIELDS = ("报告日", "报告日期", "报告期", "截止日期", "期末日期", "STD_REPORT_DATE", "REPORT_DATE", "REPORT_PERIOD", "END_DATE")
ANNOUNCEMENT_FIELDS = ("公告日期", "披露日期", "公告日", "NOTICE_DATE", "ANN_DATE")
CURRENCY_FIELDS = ("币种", "货币币种", "报告币种", "CURRENCY")
UNIT_FIELDS = ("单位", "金额单位", "计量单位", "UNIT", "AMOUNT_UNIT")
MAP = {
 "income": {
  "revenue": ("营业总收入", "营业收入", "营业额", "营运收入", "经营收入总额", "经营收入"),
  "operatingProfit": ("营业利润", "经营利润", "经营溢利"),
  "profitBeforeTax": ("利润总额", "税前利润", "除税前利润", "除税前溢利"),
  "netProfitParent": ("归属于母公司所有者的净利润", "归属于母公司股东的净利润", "归属于母公司的净利润", "归母净利润", "股东应占溢利", "本公司拥有人应占溢利"),
  "netProfit": ("净利润", "净利润(含少数股东损益)", "除税后溢利", "持续经营业务税后利润"),
  "basicEps": ("基本每股收益", "基本每股收益(元/股)", "每股基本盈利"),
  "dilutedEps": ("稀释每股收益", "稀释每股收益(元/股)", "每股摊薄盈利"),
  "incomeTax": ("所得税费用", "税项"),
  "interestExpense": ("利息费用", "利息支出", "融资成本")
 },
 "balance": {
  "totalAssets": ("资产总计", "资产总额", "资产合计", "总资产"),
  "totalLiabilities": ("负债合计", "负债总计", "总负债"),
  "currentLiabilities": ("流动负债合计", "流动负债总额"),
  "totalEquity": ("所有者权益合计", "股东权益合计", "所有者权益总计", "总权益"),
  "parentEquity": ("归属于母公司所有者权益合计", "归属于母公司股东权益合计", "归属于母公司的股东权益合计", "归属于母公司所有者权益", "归属于母公司股东权益", "归属于母公司股东的权益", "股东权益"),
  "cash": ("货币资金", "现金及现金等价物", "现金及等价物"),
  "shortBorrowings": ("短期借款", "短期贷款", "银行贷款及透支"),
  "longBorrowings": ("长期借款", "长期贷款", "长期银行贷款"),
  "bondsPayable": ("应付债券", "债券", "已发行债券", "可转换票据及债券"),
  "currentLeaseLiabilities": ("一年内到期的租赁负债", "租赁负债(流动)", "融资租赁负债(流动)"),
  "leaseLiabilities": ("租赁负债", "融资租赁负债(非流动)"),
  "shareCapital": ("股本", "普通股股本"),
  "accountsReceivable": ("应收账款", "应收帐款"),
  "inventory": ("存货",),
  "goodwill": ("商誉",),
  "shortTermInvestments": ("交易性金融资产", "短期投资", "短期存款", "其他流动金融资产"),
  "longTermInvestments": ("长期股权投资", "联营公司权益", "其他权益工具投资", "可供出售投资")
 },
 "cashflow": {
  "operatingCashFlow": ("经营活动产生的现金流量净额", "经营活动现金流量净额", "经营业务现金净额", "经营产生现金"),
  "capex": ("购建固定资产、无形资产和其他长期资产支付的现金", "购建固定资产、无形资产和其他长期资产所支付的现金", "购建固定资产、无形资产和其他长期资产支付现金"),
  "dividendsPaid": ("分配股利、利润或偿付利息支付的现金", "分配股利、利润或偿付利息所支付的现金", "已付股息(融资)"),
  "dividendsPaidOnly": ("分配股利、利润支付的现金", "分配股利、利润所支付的现金"),
  "acquisitionsPaid": ("取得子公司及其他营业单位支付的现金净额", "收购附属公司支付的现金"),
  "investmentsPurchased": ("投资支付的现金", "购买投资支付的现金"),
  "investmentsDisposed": ("收回投资收到的现金", "出售投资收到的现金"),
  "shareBuybacksPaid": ("回购股份支付的现金", "购回股份支付的现金"),
  "debtRepayments": ("偿还债务支付的现金", "偿还借款支付的现金"),
  "interestPaid": ("偿付利息支付的现金", "已付利息"),
  "equityRaised": ("吸收投资收到的现金", "发行股份所得款项")
 }
}
def clean(v):
 if v is None: return None
 s=str(v).strip()
 return None if s in ("","-","--","—","–","不适用","nan","None") else s
def number(v):
 s=clean(v)
 if s is None:return None
 s=s.replace(",","").replace("，","").replace("%","")
 if s.startswith("(") and s.endswith(")"):s="-"+s[1:-1]
 try:
  x=float(s); return x if math.isfinite(x) else None
 except (ValueError,TypeError):return None
def first(row, fields):
 for f in fields:
  if f in row and clean(row.get(f)) is not None:return row.get(f),f
 return None,None
def row_date(row):
 v,f=first(row,DATE_FIELDS)
 if v is None:return None,None
 s=re.sub(r"[^0-9]","",str(v))
 if len(s)>=8:
  try:return datetime.strptime(s[:8],"%Y%m%d").date().isoformat(),f
  except ValueError:pass
 return None,f
HK_ITEM_AUDIT = []
def expand_rows(rows, company, statement, mode):
 if not rows or "STD_ITEM_NAME" not in rows[0]: return rows
 names={}
 grouped={}
 for raw in rows:
  date=raw.get("REPORT_DATE") or raw.get("STD_REPORT_DATE")
  name=clean(raw.get("STD_ITEM_NAME"))
  if name: names[name]=raw.get("STD_ITEM_CODE")
  if not date or not name: continue
  key=str(date)[:10]
  row=grouped.setdefault(key,{"REPORT_DATE":date,"STD_REPORT_DATE":raw.get("STD_REPORT_DATE"),"FISCAL_YEAR":raw.get("FISCAL_YEAR"),"DATE_TYPE_CODE":raw.get("DATE_TYPE_CODE")})
  row[name]=raw.get("AMOUNT")
 HK_ITEM_AUDIT.append({"company":company,"statement":statement,"periodMode":mode,"itemNames":[{"name":k,"itemCode":v} for k,v in sorted(names.items())]})
 return list(grouped.values())
def mapped(row, section, record):
 fields={}
 for key,aliases in MAP[section].items():
  raw,field=first(row,aliases); val=number(raw); status="pending"; mapping_status="mapped" if val is not None else "pending"
  if section=="cashflow" and key=="capex" and val is None:
   fixed=number(row.get("购建固定资产")); intangible=number(row.get("购建无形资产及其他资产"))
   if fixed is not None and intangible is not None:
    val=fixed+intangible; field="购建固定资产 + 购建无形资产及其他资产"; raw=f"{fixed} + {intangible}"; status="derived"; mapping_status="derived_sum"
   elif fixed is not None or intangible is not None:
    val=None; field="购建固定资产 / 购建无形资产及其他资产"; raw=clean(fixed) or clean(intangible); status="pending"; mapping_status="partial_components"
  fields[key]={"value":val,"rawValue":clean(raw),"sourceField":field,"status":status,"mappingStatus":mapping_status,"sourceVerification":"pending"}
 date,date_field=row_date(row)
 cur,_=first(row,CURRENCY_FIELDS); unit,_=first(row,UNIT_FIELDS); ann,_=first(row,ANNOUNCEMENT_FIELDS)
 return {"reportDate":date,"fiscalYear":clean(row.get("FISCAL_YEAR")),"dateField":date_field,"announcementDate":clean(ann),"currency":clean(cur),"reportedUnit":clean(unit),"fields":fields,"provider":record.get("provider"),"sourceUrl":record.get("source_url"),"periodMode":record.get("period_mode"),"sourceStatus":record.get("status")}
def value(item,key):
 return (item or {}).get("fields",{}).get(key,{}).get("value")
def listing_dataset(listing_code, sections, financial=False):
 market="HK" if listing_code.endswith(".HK") else "CN"
 annual_by_year={}; interim_by_date={}
 for section in ("income","balance","cashflow"):
  for item in sections.get(section,[]):
   date=item["reportDate"]; mode=item.get("periodMode") or ""
   fiscal=number(item.get("fiscalYear"))
   year=int(fiscal) if fiscal is not None and 1900<=fiscal<=2100 else int(date[:4])
   annual_flag=(mode=="年度") or (market=="CN" and date[5:]=="12-31")
   if annual_flag and year in YEARS:
    dest=annual_by_year.setdefault(year,{})
    if section not in dest or mode=="年度":dest[section]=item
   elif int(date[:4])>=2025:
    interim_by_date.setdefault(date,{}).setdefault(section,item)
 annual=[]
 for year in YEARS:
  sections_y=annual_by_year.get(year,{})
  valid={"income":all(value(sections_y.get("income"),k) is not None for k in ("revenue","netProfitParent")),
         "balance":all(value(sections_y.get("balance"),k) is not None for k in ("totalAssets","parentEquity")),
         "cashflow":all(value(sections_y.get("cashflow"),k) is not None for k in ("operatingCashFlow","capex"))}
  annual.append({"year":year,"income":sections_y.get("income"),"balance":sections_y.get("balance"),"cashflow":sections_y.get("cashflow"),
                 "completeness":valid,"sourceRowsPresent":{k:bool(sections_y.get(k)) for k in ("income","balance","cashflow")}})
 ttm={"status":"pending","method":None,"asOf":None,"fields":{}}
 if market=="CN":
  dates=sorted(d for d in interim_by_date if d.startswith("2026-"))
  if dates:
   latest=dates[-1];prior="2025"+latest[4:];current=interim_by_date.get(latest,{});previous=interim_by_date.get(prior,{});fy=annual_by_year.get(2025,{})
   formulas={"revenue":("income","revenue"),"netProfitParent":("income","netProfitParent")}
   if not financial:
    formulas.update({"operatingCashFlow":("cashflow","operatingCashFlow"),"capex":("cashflow","capex")})
   ok=True
   for out_key,(section,key) in formulas.items():
    fyv=value(fy.get(section),key);cyv=value(current.get(section),key);pyv=value(previous.get(section),key)
    result=fyv+cyv-pyv if None not in (fyv,cyv,pyv) else None
    ttm["fields"][out_key]={"value":result,"formula":"FY2025 + 2026 YTD - 2025 same-period YTD","inputs":{"FY2025":fyv,"currentYTD":cyv,"priorYTD":pyv},
      "sourceDates":{"FY2025":fy.get(section,{}).get("reportDate"),"currentYTD":current.get(section,{}).get("reportDate"),"priorYTD":previous.get(section,{}).get("reportDate")},"status":"derived" if result is not None else "pending"}
    if result is None:ok=False
   ttm.update({"status":"derived" if ok else "partial","method":"FY2025 + 2026 YTD - 2025 same-period YTD","asOf":latest,"warning":"Confirm matching accounting scope, currency and cumulative-period basis before using TTM." if not financial else "Financial institution: TTM revenue and net profit only; ordinary-company FCF/EV cash-flow treatment is not applied."})
 else:ttm["warning"]="HK fiscal-year alignment not standardized; TTM left pending."
 all_items=[x for sec in sections.values() for x in sec]
 currencies=sorted({x["currency"] for x in all_items if x.get("currency")})
 units=sorted({x["reportedUnit"] for x in all_items if x.get("reportedUnit")})
 coverage={"annualYears":{str(x["year"]):x["completeness"] for x in annual},
  "annualIncomeYears":sum(x["completeness"]["income"] for x in annual),
  "annualBalanceYears":sum(x["completeness"]["balance"] for x in annual),
  "annualCashflowYears":sum(x["completeness"]["cashflow"] for x in annual),
  "sourceRowCount":sum(len(v) for v in sections.values())}
 return {"listingCode":listing_code,"market":market,"sourceCurrencies":currencies,"reportedUnits":units,
  "unitPolicy":"Raw source values retained; no conversion or inferred unit. Verify reporting currency/unit before per-share valuation.",
  "annual":annual,"ttm":ttm,"coverage":coverage}

def main():
 master=json.loads(MASTER_PATH.read_text(encoding="utf-8"));stocks=master.get("stocks",[])
 archives=sorted(RAW_DIR.glob("company_statements_*.json"))
 if not archives:raise SystemExit("No raw statement archive found")
 archive=archives[-1];payload=json.loads(archive.read_text(encoding="utf-8"));archive_sha=hashlib.sha256(archive.read_bytes()).hexdigest()
 stock_map={stock.get("code"):stock for stock in stocks}
 grouped=defaultdict(lambda:defaultdict(lambda:defaultdict(list)))
 for rec in payload.get("records",[]):
  stock=stock_map.get(str(rec.get("master_code") or ""))
  if not stock:continue
  exchange=str(rec.get("exchange") or "");raw_code=str(rec.get("code") or "")
  listing_code=(raw_code.zfill(5)+".HK") if exchange=="HK" else (raw_code.zfill(6)+"."+exchange if exchange in ("SH","SZ") else raw_code)
  section={"利润表":"income","资产负债表":"balance","现金流量表":"cashflow"}.get(rec.get("statement"))
  if not section:continue
  rows=expand_rows(rec.get("rows") or [],rec.get("company"),rec.get("statement"),rec.get("period_mode"))
  for raw in rows:
   item=mapped(raw,section,rec)
   if item["reportDate"]:grouped[stock["code"]][listing_code][section].append(item)
 companies=[];audit_rows=[]
 for stock in stocks:
  code=stock.get("code","");primary=code.split("/")[0].strip()
  listing_map=grouped.get(code,{})
  is_financial=any(term in (str(stock.get("industry",""))+str(stock.get("businessType",""))+str(stock.get("method",""))) for term in ("银行","保险","证券","券商","金融"))
  listing_data={k:listing_dataset(k,v,is_financial) for k,v in listing_map.items()}
  chosen=listing_data.get(primary)
  if chosen is None and listing_data:
   chosen=listing_data[sorted(listing_data)[0]];primary=chosen["listingCode"]
  if chosen is None:
   chosen={"listingCode":primary,"market":"HK" if primary.endswith(".HK") else "CN","annual":[],"ttm":{"status":"pending","fields":{}},"coverage":{"annualIncomeYears":0,"annualBalanceYears":0,"annualCashflowYears":0},"sourceCurrencies":[],"reportedUnits":[]}
  alternates=[v for k,v in listing_data.items() if k!=primary]
  companies.append({"name":stock.get("name"),"code":code,"primaryListingCode":primary,"industry":stock.get("industry"),"businessType":stock.get("businessType"),"modelType":stock.get("method"),
   "market":chosen["market"],"marketCurrency":stock.get("currency"),"primaryFinancials":chosen,"annual":chosen.get("annual",[]),"ttm":chosen.get("ttm",{}),"coverage":chosen.get("coverage",{}),"alternateListings":alternates,
   "sourcePolicy":"Primary listing financial statements only are used in the main series; alternate A/H listing data is retained separately and never merged."})
  audit_rows.append({"name":stock.get("name"),"code":code,"primaryListingCode":primary,"market":chosen["market"],
   "annualIncomeYears":chosen["coverage"].get("annualIncomeYears",0),"annualBalanceYears":chosen["coverage"].get("annualBalanceYears",0),
   "annualCashflowYears":chosen["coverage"].get("annualCashflowYears",0),"ttmStatus":chosen["ttm"].get("status"),
   "ttmAsOf":chosen["ttm"].get("asOf"),"alternateListingCodes":[x["listingCode"] for x in alternates]})
 OUT_DIR.mkdir(parents=True,exist_ok=True)
 output={"schemaVersion":"1.1.0","generatedAtUtc":datetime.now(timezone.utc).isoformat(),"sourceArchive":str(archive.relative_to(ROOT)),
  "sourceArchiveSha256":archive_sha,"sourceRunId":payload.get("run_id"),"companyCount":len(companies),"years":YEARS,
  "fieldPolicy":"Exact field mapping. Source-retrieved values remain pending independent report verification; calculated formulas are marked derived. Raw values remain in source-reported units; no currency/unit conversion, interpolation, ROIC, net debt or per-share derivation.",
  "listingPolicy":"A/H cross-listings are standardized separately. The first listing in the master code is primary; alternate listing statements are never merged.",
  "ttmPolicy":"Calendar-year A-share TTM = FY2025 + 2026 cumulative period - 2025 same-period cumulative. HK TTM pending fiscal-year alignment.",
  "companies":companies}
 (OUT_DIR/"company-financials-2021-2025.json").write_text(json.dumps(output,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
 annual_cov={m:sum(x["coverage"].get(k,0)==5 for x in companies) for m,k in (("income","annualIncomeYears"),("balance","annualBalanceYears"),("cashflow","annualCashflowYears"))}
 audit={"generatedAtUtc":output["generatedAtUtc"],"sourceArchive":output["sourceArchive"],"sourceArchiveSha256":archive_sha,"sourceRunId":payload.get("run_id"),
  "masterCompanies":len(stocks),"normalizedCompanies":len(companies),"annualFiveYearCompleteByMetric":annual_cov,
  "ttmDerived":sum(x["ttm"].get("status")=="derived" for x in companies),"ttmPartial":sum(x["ttm"].get("status")=="partial" for x in companies),
  "ttmPending":sum(x["ttm"].get("status")=="pending" for x in companies),
  "unitCaution":"No unit conversion. A/H alternate listing statements are not merged into primary listing data.","companies":audit_rows}
 (OUT_DIR/"standardization-audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
 (OUT_DIR/"hk-item-map-audit.json").write_text(json.dumps(HK_ITEM_AUDIT,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps({k:v for k,v in audit.items() if k!="companies"},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
