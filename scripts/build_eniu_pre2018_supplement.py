#!/usr/bin/env python3
"""Create a conservative Enniu pre-2018 supplement.

Keep only A-share rows before 2018-01-01 whose security/date key is absent
from Baidu's pre-2018 dataset. Retain PE-TTM and PB only; the vendor PS basis
is unverified and is intentionally excluded from the formal build.
"""
from __future__ import annotations
import argparse, csv, json
from datetime import datetime, timezone
from pathlib import Path

FIELDS=["code","date","close","currency","peTtm","pb","source","sourceUrl"]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--candidate",default="data/valuation-history/raw/eniu-a-share-candidate.csv")
    p.add_argument("--baidu",default="data/valuation-history/raw/baidu-valuation-history.csv")
    p.add_argument("--output",default="data/valuation-history/raw/eniu-pre2018-supplement.csv")
    p.add_argument("--audit",default="data/valuation-history/raw/eniu-pre2018-supplement-audit.json")
    a=p.parse_args()
    baidu_keys=set()
    with open(a.baidu,encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f):
            code=(r.get("code") or "").strip().upper()
            day=(r.get("date") or "").strip()[:10]
            if code and day and day<"2018-01-01":
                baidu_keys.add((code,day))
    out=[]; seen=set(); excluded_overlap=0; excluded_post=0
    with open(a.candidate,encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f):
            code=(r.get("code") or "").strip().upper()
            day=(r.get("date") or "").strip()[:10]
            if not code or not day: continue
            if day>="2018-01-01":
                excluded_post+=1; continue
            key=(code,day)
            if key in baidu_keys:
                excluded_overlap+=1; continue
            if key in seen: continue
            pe=(r.get("peTtm") or "").strip()
            pb=(r.get("pb") or "").strip()
            close=(r.get("close") or "").strip()
            if not pe and not pb and not close: continue
            out.append({
                "code":code,"date":day,"close":close,"currency":(r.get("currency") or "CNY"),
                "peTtm":pe,"pb":pb,
                "source":"Eniu public A-share chart (pre-2018 supplement; PE-TTM/PB only)",
                "sourceUrl":(r.get("sourceUrl") or "https://eniu.com/"),
            })
            seen.add(key)
    out.sort(key=lambda x:(x["code"],x["date"]))
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    with open(a.output,"w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(out)
    audit={
      "source":"Eniu candidate filtered supplement",
      "generatedAt":datetime.now(timezone.utc).isoformat(timespec="seconds"),
      "candidate":"raw/eniu-a-share-candidate.csv",
      "excludedProviderOverlapWithBaiduRows":excluded_overlap,
      "excludedPost2017CandidateRows":excluded_post,
      "supplementRows":len(out),
      "companiesWithSupplement":len({r["code"] for r in out}),
      "firstDate":min((r["date"] for r in out),default=None),
      "lastDate":max((r["date"] for r in out),default=None),
      "metricsIncluded":["peTtm","pb","close"],
      "psRawIncluded":False,
      "policy":"No date overlap with any Baidu pre-2018 row; no interpolation; only candidate source raw observations.",
    }
    Path(a.audit).write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(audit,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
