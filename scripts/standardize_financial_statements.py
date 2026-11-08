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
  "revenue": ("营业总收入", "营业收入", "营业总收入(元)", "营业收入合计"),
  "operatingProfit": ("营业利润", "经营利润"),
  "netProfitParent": ("归属于母公司所有者的净利润", "归属于母公司股东的净利润", "归母净利润"),
  "netProfit": ("净利润", "净利润(含少数股东损益)"),
  "basicEps": ("基本每股收益", "基本每股收益(元/股)"),
  "dilutedEps": ("稀释每股收益", "稀释每股收益(元/股)"),
  "incomeTax": ("所得税费用",), "interestExpense": ("利息费用", "利息支出")
 },
 "balance": {
  "totalAssets": ("资产总计", "资产总额", "资产合计"),
  "totalLiabilities": ("负债合计", "负债总计"),
  "totalEquity": ("所有者权益合计", "股东权益合计", "所有者权益总计"),
  "parentEquity": ("归属于母公司所有者权益合计", "归属于母公司股东权益合计", "归属于母公司所有者权益", "归属于母公司股东权益"),
  "cash": ("货币资金", "现金及现金等价物"),
  "shortBorrowings": ("短期借款", "短期贷款"), "longBorrowings": ("长期借款", "长期贷款"),
  "bondsPayable": ("应付债券", "债券"), "leaseLiabilities": ("租赁负债",),
  "shareCapital": ("股本", "普通股股本"), "accountsReceivable": ("应收账款",),
  "inventory": ("存货",), "goodwill": ("商誉",)
 },
 "cashflow": {
  "operatingCashFlow": ("经营活动产生的现金流量净额", "经营活动现金流量净额"),
  "capex": ("购建固定资产、无形资产和其他长期资产支付的现金", "购建固定资产、无形资产和其他长期资产所支付的现金", "购建固定资产、无形资产和其他长期资产支付现金"),
  "dividendsPaid": ("分配股利、利润或偿付利息支付的现金", "分配股利、利润或偿付利息所支付的现金")
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
  raw,field=first(row,aliases); val=number(raw)
  fields[key]={"value":val,"rawValue":clean(raw),"sourceField":field,"status":"derived" if val is not None else "pending"}
 date,date_field=row_date(row)
 cur,_=first(row,CURRENCY_FIELDS); unit,_=first(row,UNIT_FIELDS); ann,_=first(row,ANNOUNCEMENT_FIELDS)
 return {"reportDate":date,"dateField":date_field,"announcementDate":clean(ann),"currency":clean(cur),"reportedUnit":clean(unit),"fields":fields,"provider":record.get("provider"),"sourceUrl":record.get("source_url"),"periodMode":record.get("period_mode"),"sourceStatus":record.get("status")}
def value(item,key):
 return (item or {}).get("fields",{}).get(key,{}).get("value")
def main():
 master=json.loads(MASTER_PATH.read_text(encoding="utf-8")); stocks=master.get("stocks",[])
 archives=sorted(RAW_DIR.glob("company_statements_*.json"))
 if not archives:raise SystemExit("No raw statement archive found")
 archive=archives[-1]; payload=json.loads(archive.read_text(encoding="utf-8"))
 archive_sha=hashlib.sha256(archive.read_bytes()).hexdigest()
 stock_map={}
 for stock in stocks:
  code=stock.get("code",""); stock_map[code]=stock; stock_map[code.split(".")[0]]=stock
 grouped=defaultdict(lambda:defaultdict(list))
 for rec in payload.get("records",[]):
  code=str(rec.get("master_code") or rec.get("code") or "")
  stock=stock_map.get(code) or stock_map.get(code.split(".")[0])
  if not stock:continue
  section={"利润表":"income","资产负债表":"balance","现金流量表":"cashflow"}.get(rec.get("statement"))
  if not section:continue
  for raw in expand_rows(rec.get("rows") or [], rec.get("company"), rec.get("statement"), rec.get("period_mode")):
   item=mapped(raw,section,rec)
   if item["reportDate"]:grouped[stock["code"]][section].append(item)
 companies=[]; audit_rows=[]
 for stock in stocks:
  code=stock.get("code"); market="HK" if code.endswith(".HK") else "CN"; groups=grouped.get(code,{})
  annual_by_year={}; interim_by_date={}
  for section in ("income","balance","cashflow"):
   for item in groups.get(section,[]):
    date=item["reportDate"]; year=int(date[:4]); mode=item.get("periodMode") or ""
    annual_flag=(mode=="年度") or (market=="CN" and date[5:]=="12-31")
    if annual_flag and year in YEARS:
     dest=annual_by_year.setdefault(year,{})
     if section not in dest or mode=="年度":dest[section]=item
    elif year>=2025:interim_by_date.setdefault(date,{}).setdefault(section,item)
  annual=[]
  for year in YEARS:
   sections=annual_by_year.get(year,{})
   valid={
    "income": all(value(sections.get("income"),k) is not None for k in ("revenue","netProfitParent")),
    "balance": all(value(sections.get("balance"),k) is not None for k in ("totalAssets","parentEquity")),
    "cashflow": all(value(sections.get("cashflow"),k) is not None for k in ("operatingCashFlow","capex"))
   }
   annual.append({"year":year,"income":sections.get("income"),"balance":sections.get("balance"),"cashflow":sections.get("cashflow"),"completeness":valid,"sourceRowsPresent":{s:bool(sections.get(s)) for s in ("income","balance","cashflow")}})
  ttm={"status":"pending","method":None,"asOf":None,"fields":{}}
  if market=="CN":
   dates=sorted(d for d in interim_by_date if d.startswith("2026-"))
   if dates:
    latest=dates[-1]; prior="2025"+latest[4:]; current=interim_by_date.get(latest,{}); previous=interim_by_date.get(prior,{}); fy=annual_by_year.get(2025,{})
    formulas={"revenue":("income","revenue"),"netProfitParent":("income","netProfitParent"),"operatingCashFlow":("cashflow","operatingCashFlow"),"capex":("cashflow","capex")}
    ok=True
    for out_key,(section,key) in formulas.items():
     fyv=value(fy.get(section),key); cyv=value(current.get(section),key); pyv=value(previous.get(section),key)
     result=fyv+cyv-pyv if None not in (fyv,cyv,pyv) else None
     ttm["fields"][out_key]={"value":result,"formula":"FY2025 + 2026 YTD - 2025 same-period YTD","inputs":{"FY2025":fyv,"currentYTD":cyv,"priorYTD":pyv},"status":"derived" if result is not None else "pending"}
     if result is None:ok=False
    ttm.update({"status":"derived" if ok else "partial","method":"FY2025 + 2026 YTD - 2025 same-period YTD","asOf":latest,"warning":"Confirm matching accounting scope, currency and cumulative period basis before using TTM."})
  else:ttm["warning"]="HK fiscal-year alignment not standardized; TTM left pending."
  all_items=[x for section in groups.values() for x in section]
  currencies=sorted({x["currency"] for x in all_items if x.get("currency")}); units=sorted({x["reportedUnit"] for x in all_items if x.get("reportedUnit")})
  coverage={"annualYears":{str(x["year"]):x["completeness"] for x in annual},"annualIncomeYears":sum(x["completeness"]["income"] for x in annual),"annualBalanceYears":sum(x["completeness"]["balance"] for x in annual),"annualCashflowYears":sum(x["completeness"]["cashflow"] for x in annual),"sourceRowCount":sum(len(v) for v in groups.values())}
  companies.append({"name":stock.get("name"),"code":code,"industry":stock.get("industry"),"businessType":stock.get("businessType"),"modelType":stock.get("method"),"market":market,"masterCurrency":stock.get("currency"),"sourceCurrencies":currencies,"reportedUnits":units,"unitPolicy":"Raw source values retained; unit is not inferred or converted.","annual":annual,"interim":{d:secs for d,secs in sorted(interim_by_date.items())},"ttm":ttm,"coverage":coverage,"sourcePolicy":"Sina Finance via AKShare (A-share) or Eastmoney HK via AKShare; raw archive retained separately."})
  audit_rows.append({"name":stock.get("name"),"code":code,"annualIncomeYears":coverage["annualIncomeYears"],"annualBalanceYears":coverage["annualBalanceYears"],"annualCashflowYears":coverage["annualCashflowYears"],"ttmStatus":ttm["status"],"ttmAsOf":ttm["asOf"],"sourceCurrencies":currencies,"reportedUnits":units})
 OUT_DIR.mkdir(parents=True,exist_ok=True)
 output={"schemaVersion":"1.0.0","generatedAtUtc":datetime.now(timezone.utc).isoformat(),"sourceArchive":str(archive.relative_to(ROOT)),"sourceArchiveSha256":archive_sha,"sourceRunId":payload.get("run_id"),"companyCount":len(companies),"years":YEARS,"fieldPolicy":"Exact source-field mappings only. Raw source values remain in reported units; no currency/unit conversion, interpolation, ROIC, net debt or per-share derivation.","ttmPolicy":"Calendar-year A-share TTM = FY2025 + 2026 cumulative period - 2025 same-period cumulative. HK TTM pending fiscal-year alignment.","companies":companies}
 (OUT_DIR/"company-financials-2021-2025.json").write_text(json.dumps(output,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
 audit={"generatedAtUtc":output["generatedAtUtc"],"sourceArchive":output["sourceArchive"],"sourceArchiveSha256":archive_sha,"sourceRunId":payload.get("run_id"),"masterCompanies":len(stocks),"normalizedCompanies":len(companies),"annualCoverageByMetric":{"income":sum(x["coverage"]["annualIncomeYears"]==5 for x in companies),"balance":sum(x["coverage"]["annualBalanceYears"]==5 for x in companies),"cashflow":sum(x["coverage"]["annualCashflowYears"]==5 for x in companies)},"ttmDerived":sum(x["ttm"]["status"]=="derived" for x in companies),"ttmPartial":sum(x["ttm"]["status"]=="partial" for x in companies),"ttmPending":sum(x["ttm"]["status"]=="pending" for x in companies),"unitCaution":"No conversion performed; source units require validation before cross-company or per-share use.","companies":audit_rows}
 (OUT_DIR/"standardization-audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
 (OUT_DIR/"hk-item-map-audit.json").write_text(json.dumps(HK_ITEM_AUDIT,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps({k:v for k,v in audit.items() if k!="companies"},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
