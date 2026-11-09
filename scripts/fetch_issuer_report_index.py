#!/usr/bin/env python3
"""Resolve official CNINFO filing links for A-share issuers; HKEX entries remain official-search links.
This creates source locators only. It does not claim report-content verification.
"""
from __future__ import annotations
import json, re, time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPCookieProcessor

ROOT=Path(__file__).resolve().parents[1]
MASTER=ROOT/"data/china-stocks-financial-valuation.json"
OUT=ROOT/"data/valuation-model/issuer-report-index-49.json"
BASE="https://www.cninfo.com.cn"
SEARCH_PAGE=BASE+"/new/commonUrl/pageOfSearch?url=disclosure/list/search"
TOP=BASE+"/new/information/topSearch/query"
QUERY=BASE+"/new/hisAnnouncement/query"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

class Client:
    def __init__(self):
        self.opener=build_opener(HTTPCookieProcessor(CookieJar()))
        self.opener.open(Request(SEARCH_PAGE,headers={"User-Agent":UA}),timeout=25).read(1024)
    def post(self,url,data):
        body=urlencode(data).encode()
        req=Request(url,data=body,headers={
            "User-Agent":UA,"Referer":SEARCH_PAGE,"Origin":BASE,
            "X-Requested-With":"XMLHttpRequest",
            "Content-Type":"application/x-www-form-urlencoded; charset=UTF-8",
            "Accept":"application/json, text/javascript, */*; q=0.01"
        })
        with self.opener.open(req,timeout=35) as resp:
            return json.loads(resp.read().decode("utf-8"))
    def org(self,code):
        data=self.post(TOP,{"keyWord":code,"maxNum":10})
        rows=data if isinstance(data,list) else data.get("stockList",[]) if isinstance(data,dict) else []
        for x in rows:
            candidate=str(x.get("code") or x.get("orgId") or "")
            org=str(x.get("orgId") or candidate)
            sec=str(x.get("stockCode") or x.get("secCode") or x.get("code") or "")
            if code in (sec,candidate) or org:
                return org
        raise ValueError("orgId not resolved")
    def announcements(self,code,org,column,category,start,end):
        data=self.post(QUERY,{
            "pageNum":1,"pageSize":30,"column":column,"tabName":"fulltext",
            "plate":"","stock":code+","+org,"searchkey":"","secid":"",
            "category":category,"seDate":start+"~"+end,
            "sortName":"announcementTime","sortType":"desc","isHLtitle":"true"
        })
        return data.get("announcements") or []

def pdf_url(path):
    if not path:return None
    return path if path.startswith("http") else "https://static.cninfo.com.cn/"+path.lstrip("/")

def normalize_announcement(a,code,org):
    ms=int(a.get("announcementTime") or 0)
    date=datetime.fromtimestamp(ms/1000,timezone.utc).astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat() if ms else None
    ann_id=str(a.get("announcementId") or "")
    title=re.sub(r"<[^>]+>","",str(a.get("announcementTitle") or a.get("title") or ""))
    return {"title":title,"announcementDate":date,"announcementId":ann_id,
            "pdfUrl":pdf_url(a.get("adjunctUrl")),
            "detailUrl":f"{BASE}/new/disclosure/detail?stockCode={code}&announcementId={ann_id}&orgId={org}&announcementTime={date}" if ann_id and date else None}

def choose(rows,pattern):
    good=[]
    for a in rows:
        x=normalize_announcement(a,"","")
        if re.search(pattern,x["title"],re.I) and x["pdfUrl"] and not re.search(r"摘要|英文版|英文|取消|更正前",x["title"]):
            good.append(x)
    return sorted(good,key=lambda x:x.get("announcementDate") or "",reverse=True)[0] if good else None

def main():
    stocks=json.loads(MASTER.read_text(encoding="utf-8")).get("stocks",[])
    client=Client()
    records=[]
    for stock in stocks:
        full=str(stock.get("code") or "")
        primary=full.split("/")[0].strip()
        row={"code":full,"name":stock.get("name"),"industry":stock.get("industry"),
             "primaryListing":primary,"annual2025":None,"interim2026":None,"quarterly2026Q3":None,
             "status":"pending","verificationStatus":"official_link_only_not_content_verified"}
        if primary.endswith((".SH",".SZ")):
            code=primary.split(".")[0]
            column="sse" if primary.endswith(".SH") else "szse"
            try:
                org=client.org(code)
                annual_rows=client.announcements(code,org,column,"category_ndbg_szsh","2026-01-01","2026-07-31")
                interim_rows=client.announcements(code,org,column,"category_bndbg_szsh","2026-07-01","2026-11-09")
                q3_rows=client.announcements(code,org,column,"category_sjdbg_szsh","2026-10-01","2026-11-09")
                row["orgId"]=org
                row["annual2025"]=choose(annual_rows,r"2025年年度报告|2025年度报告|2025年年报")
                row["interim2026"]=choose(interim_rows,r"2026年半年度报告|2026年半年报|2026半年度报告")
                row["quarterly2026Q3"]=choose(q3_rows,r"2026年第三季度报告|2026年三季度报告|2026年三季报")
                for key in ("annual2025","interim2026","quarterly2026Q3"):
                    if row[key]:
                        source_rows=annual_rows if key=="annual2025" else interim_rows if key=="interim2026" else q3_rows
                        a=next((z for z in source_rows
                                if str(z.get("announcementId") or "")==row[key]["announcementId"]),None)
                        if a: row[key]=normalize_announcement(a,code,org)
                row["status"]="resolved" if row["annual2025"] and row["interim2026"] and row["quarterly2026Q3"] else "partial" if row["annual2025"] or row["interim2026"] or row["quarterly2026Q3"] else "not_found"
            except Exception as exc:
                row["status"]="error";row["error"]=str(exc)[:300]
            time.sleep(0.25)
        else:
            row["status"]="hkex_manual_lookup_required"
            row["officialSearchUrl"]="https://www1.hkexnews.hk/search/titlesearch.xhtml?lang=en"
            row["verificationStatus"]="official_hkex_search_link_only_not_content_verified"
        records.append(row)
    out={"schemaVersion":"1.0.0","generatedAtUtc":datetime.now(timezone.utc).isoformat(),
         "companyCount":len(records),"aShareCompanies":sum(x["primaryListing"].endswith((".SH",".SZ")) for x in records),
         "annual2025Resolved":sum(bool(x["annual2025"]) for x in records),
         "interim2026Resolved":sum(bool(x["interim2026"]) for x in records),
         "quarterly2026Q3Resolved":sum(bool(x["quarterly2026Q3"]) for x in records),
         "bothPeriodsResolved":sum(bool(x["annual2025"] and x["interim2026"]) for x in records),
         "allThreePeriodsResolved":sum(bool(x["annual2025"] and x["interim2026"] and x["quarterly2026Q3"]) for x in records),
         "hkexManualLookup":sum(x["status"]=="hkex_manual_lookup_required" for x in records),
         "records":records,
         "warning":"Official filing URLs are locators only. Values remain unverified until the actual report, audit opinion, reporting currency/unit, consolidation scope and line items are cross-checked."}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in out.items() if k!="records"},ensure_ascii=False,indent=2))

if __name__=="__main__": main()

# Refresh official filing locator index after workflow installation.

# Retry publication after integrating concurrent main-branch updates.
