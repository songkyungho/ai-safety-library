#!/usr/bin/env python3
"""Scrape IAAE detail pages for original source URLs and short body text."""
from __future__ import annotations

import argparse
import csv
import html as html_mod
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from library_common import (  # noqa: E402
    ROOT,
    as_url_list,
    clean_scraped_url,
    is_bad_original,
    is_curator_url,
    is_http_url,
    is_scrape_chrome,
    rebuild_collection_stats,
    write_json,
)

UA = "AI-Safety-Library/0.1 (research archive; enrich iaae)"
CSV_FIELDS = [
    "id",
    "collection",
    "collection_name",
    "date",
    "category",
    "org",
    "title",
    "page_url",
    "source_urls",
    "document_name",
    "body",
]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def extract_links(html: str) -> list[str]:
    """Prefer [자료출처] links; avoid site chrome when falling back."""
    text = html_mod.unescape(html)
    found: list[str] = []
    seen = set()

    chrome_hosts = {
        "www.yna.co.kr",
        "yna.co.kr",
        "showroom.geoepic.io",
        "aseanai.net",
        "www.aseanai.net",
        "www.acrc.go.kr",
        "acrc.go.kr",
        "nts.go.kr",
        "www.nts.go.kr",
        "www.youtube.com",
        "youtube.com",
        "static.imweb.me",
        "imweb.me",
        "schema.org",
        "crm-onsite.imweb.me",
        "sstatic-g.rmcnmv.naver.net",
    }

    def add(url: str, *, allow_chrome: bool = False) -> None:
        url = clean_scraped_url(url)
        url = html_mod.unescape(url)
        if not is_http_url(url):
            return
        if is_curator_url(url) or is_bad_original(url):
            return
        host = url.split("/")[2].lower() if "://" in url else ""
        if host.startswith("www."):
            host_bare = host[4:]
        else:
            host_bare = host
        if any(x in host for x in ("imweb.me", "schema.org", "google-analytics", "googletagmanager", "facebook.net")):
            return
        if not allow_chrome and (host in chrome_hosts or host_bare in chrome_hosts):
            return
        if url in seen:
            return
        seen.add(url)
        found.append(url)

    # [자료출처] … (https://…) or href after 자료출처
    for m in re.finditer(
        r"자료출처[^<\n]{0,200}?(https?://[^\s\)\"'<>]+)",
        text,
        flags=re.IGNORECASE,
    ):
        add(m.group(1), allow_chrome=True)

    # 빈 <a href>는 이전 글 잔여 링크인 경우가 많아 쓰지 않는다.
    for m in re.finditer(
        r"자료출처[\s\S]{0,400}?<a[^>]+href=[\"'](https?://[^\"']+)[\"'][^>]*>(.*?)</a>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        inner = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if inner:
            add(m.group(1), allow_chrome=True)

    if found:
        return found
    if re.search(r"자료출처", text, flags=re.IGNORECASE):
        return found

    # Fallback: links immediately after 자료제목 / 원문 / PDF markers only
    for m in re.finditer(
        r"(?:원문|출처|다운로드|PDF|자료)[^<\n]{0,80}?(https?://[^\s\)\"'<>]+)",
        text,
        flags=re.IGNORECASE,
    ):
        add(m.group(1))

    # Last resort: first few non-chrome external hrefs in the main content window
    # Limit to avoid footer/nav pollution.
    hrefs = re.findall(r"<a[^>]+href=[\"'](https?://[^\"']+)[\"']", text, flags=re.IGNORECASE)
    for href in hrefs:
        before = len(found)
        add(href)
        if len(found) >= 3:
            break
        # if rejected, continue
        _ = before
    return found


def extract_body(html: str) -> str:
    """IAAE 상세는 첨부 안내만 있는 경우가 많다. 카드 요약으로 쓰지 않으므로 비운다."""
    return ""


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            row = dict(r)
            row["source_urls"] = " | ".join(as_url_list(r.get("source_urls")))
            row["body"] = (r.get("body") or "")[:8000]
            w.writerow(row)


def catalog_md(records: list[dict]) -> str:
    lines = [
        "# IAAE 연구자료실",
        "",
        "- 큐레이터: 국제인공지능윤리협회(IAAE)",
        "- 원본 URL은 상세 페이지 `[자료출처]`에서 추출",
        f"- 건수: **{len(records)}건**",
        "",
        "| 날짜 | 기관 | 제목 | 원문 |",
        "|---|---|---|---|",
    ]
    for r in records:
        src = (r.get("source_urls") or [None])[0] if r.get("source_urls") else ""
        src_md = f"[원문]({src})" if src else ""
        title = (r.get("title") or "").replace("|", "\\|")
        page = r.get("page_url") or ""
        lines.append(
            f"| {r.get('date') or ''} | {(r.get('org') or '')[:40]} | [{title}]({page}) | {src_md} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only first N items (0=all)")
    ap.add_argument("--sleep", type=float, default=0.35)
    ap.add_argument("--force", action="store_true", help="re-scrape even if source_urls present")
    args = ap.parse_args()

    path = ROOT / "collections/iaae-ethics/items.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items") or []
    if args.limit:
        items = items[: args.limit]

    ok = 0
    fail = 0
    for i, it in enumerate(items, 1):
        if is_scrape_chrome(it.get("body") or ""):
            it["body"] = ""
        if it.get("source_urls") and not args.force:
            ok += 1
            continue
        url = it.get("page_url") or ""
        print(f"[{i}/{len(items)}] {url}")
        try:
            html = fetch(url)
            links = extract_links(html)
            body = extract_body(html)
            it["source_urls"] = links
            if body and (args.force or not (it.get("body") or "").strip()):
                it["body"] = body
            if links:
                ok += 1
            else:
                fail += 1
                print("  no original links")
        except Exception as e:
            fail += 1
            print(f"  ERR {e}")
        time.sleep(args.sleep)

    # write full collection (mutate original list in data)
    rebuild_collection_stats(data)
    write_json(path, data)
    write_csv(ROOT / "collections/iaae-ethics/items.csv", data["items"])
    (ROOT / "collections/iaae-ethics/catalog.md").write_text(
        catalog_md(data["items"]), encoding="utf-8"
    )
    print(f"done with_source={sum(1 for x in data['items'] if x.get('source_urls'))} failish={fail}")


if __name__ == "__main__":
    main()
