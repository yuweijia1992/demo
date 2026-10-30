#!/usr/bin/env python3
"""Inspect public cibo.hk valuation pages for reusable historical chart endpoints.

This discovery probe makes a small number of page/script GETs and retains only
endpoint names and short diagnostics. It does not scrape or publish valuation
points. A second collector will be written only after a public data endpoint is
identified and its historical point-in-time semantics are understood.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

STOCKS = {
    "00700": "TENCENT",
    "02313": "SHENZHOU INTL",
    "09988": "ALIBABA-W",
    "09618": "JD-SW",
    "09626": "BILIBILI-W",
}
PAGE_URL = "https://cibo.hk/en/valuation-{code}.html"


class AssetsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts: list[str] = []
        self.links: list[str] = []
        self.inline_chunks: list[str] = []
        self._script_inline = False
        self._current: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            src = attrs.get("src")
            if src:
                self.scripts.append(src)
                self._script_inline = False
            else:
                self._script_inline = True
                self._current = []
        elif tag == "link" and attrs.get("href"):
            self.links.append(attrs["href"])

    def handle_data(self, data):
        if self._script_inline:
            self._current.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._script_inline:
            joined = "".join(self._current).strip()
            if joined:
                self.inline_chunks.append(joined[:120000])
            self._script_inline = False
            self._current = []


def endpoint_candidates(text: str, page_url: str) -> list[str]:
    patterns = [
        r"""["']([^"']{0,100}(?:/api/|api/|graphql|valuation|history|chart|series)[^"']{0,180})["']""",
        r"""(?:fetch|axios\.(?:get|post)|\.get|\.post)\(\s*["']([^"']+)["']""",
        r"""(?:baseURL|apiBase|endpoint)\s*[:=]\s*["']([^"']+)["']""",
    ]
    found = []
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            candidate = match.strip()
            if candidate and candidate not in found:
                found.append(candidate)
    return [urljoin(page_url, x) if x.startswith(("/", "./")) else x for x in found[:200]]


def relevant_snippets(text: str) -> list[str]:
    keywords = re.compile(r"valuation|fair.?range|price.?sales|price.?book|price.?earn|history|chart|series|api|graphql", re.I)
    snippets = []
    for match in keywords.finditer(text):
        start, end = max(0, match.start() - 180), min(len(text), match.end() + 260)
        snippet = re.sub(r"\s+", " ", text[start:end])
        if snippet not in snippets:
            snippets.append(snippet[:480])
        if len(snippets) >= 25:
            break
    return snippets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/valuation-history/raw/cibo-hk-page-probe.json")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    result: dict[str, Any] = {
        "source": "cibo.hk public historical valuation pages",
        "method": "Five valuation-page HTML and same-origin JavaScript asset discovery; no data points scraped",
        "auditedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stocks": [],
    }
    for index, (code, name) in enumerate(STOCKS.items()):
        url = PAGE_URL.format(code=code)
        record: dict[str, Any] = {"code": code, "name": name, "pageUrl": url}
        try:
            response = session.get(url, timeout=args.timeout)
            record["httpStatus"] = response.status_code
            record["finalUrl"] = response.url
            record["htmlBytes"] = len(response.content)
            response.raise_for_status()
            text = response.text
            parser_html = AssetsParser()
            parser_html.feed(text)
            record["scriptCount"] = len(parser_html.scripts)
            record["inlineScriptCount"] = len(parser_html.inline_chunks)
            record["linksSample"] = parser_html.links[:30]
            inline = "\n".join(parser_html.inline_chunks)
            endpoints = endpoint_candidates(text + "\n" + inline, response.url)
            snippets = relevant_snippets(inline)
            same_origin = []
            parsed_origin = urlparse(response.url).netloc
            for src in parser_html.scripts:
                full = urljoin(response.url, src)
                if urlparse(full).netloc == parsed_origin and full not in same_origin:
                    same_origin.append(full)
            script_findings = []
            for asset_url in same_origin[:25]:
                try:
                    js_response = session.get(asset_url, timeout=args.timeout)
                    if js_response.status_code != 200:
                        script_findings.append({"url": asset_url, "status": js_response.status_code})
                        continue
                    js = js_response.text
                    matches = endpoint_candidates(js, response.url)
                    if matches:
                        endpoints.extend(x for x in matches if x not in endpoints)
                    selected = relevant_snippets(js)
                    if matches or selected:
                        script_findings.append({
                            "url": asset_url,
                            "status": js_response.status_code,
                            "bytes": len(js_response.content),
                            "endpointCandidates": matches[:80],
                            "snippets": selected[:12],
                        })
                except Exception as exc:
                    script_findings.append({"url": asset_url, "error": str(exc)})
            record.update({
                "status": "OK",
                "endpointCandidates": endpoints[:250],
                "inlineSnippets": snippets,
                "scriptFindings": script_findings,
            })
        except Exception as exc:
            record.update({"status": "REQUEST_ERROR", "error": str(exc)})
        result["stocks"].append(record)
        print(f"{code}: {record['status']} scripts={record.get('scriptCount',0)} endpoints={len(record.get('endpointCandidates',[]))}", flush=True)
        if index + 1 < len(STOCKS) and args.delay > 0:
            time.sleep(args.delay)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "companies": len(result["stocks"]),
        "success": sum(1 for x in result["stocks"] if x["status"] == "OK"),
        "candidateEndpoints": sum(len(x.get("endpointCandidates", [])) for x in result["stocks"]),
        "output": str(output),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
