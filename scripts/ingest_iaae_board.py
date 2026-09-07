#!/usr/bin/env python3
"""IAAE 연구자료실 목록을 긁어 collections/iaae-ethics 에 신규 항목만 추가.

Digest 일일 수집은 중단됐고, Library 일일 파이프라인에서만 호출한다.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from library_common import (  # noqa: E402
    ROOT,
    load_collection,
    rebuild_collection_stats,
    save_collection,
)

UA = "AI-Safety-Library/0.1 (research archive; ingest iaae board)"
BOARD = "https://iaae.ai/research/"
_BRACKET_RE = re.compile(r"^\[([^\]]+)\]\s*(.*)$")
_IDX_RE = re.compile(r"(?:[?&]idx=|/idx/)(\d+)", re.I)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def extract_idx(url: str) -> str:
    m = _IDX_RE.search(url or "")
    if m:
        return m.group(1)
    try:
        qs = parse_qs(urlparse(url).query)
        vals = qs.get("idx") or []
        if vals:
            return str(vals[0]).strip()
    except Exception:
        pass
    return ""


def parse_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for row in soup.select("ul.li_body"):
        title_el = row.select_one("a.list_text_title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue
        href = (title_el.get("href") or "").strip()
        if not href:
            continue
        link = href if href.startswith("http") else f"https://iaae.ai{href}"
        idx = extract_idx(link)
        if not idx:
            continue
        # canonical page URL (q= 파라미터 제거)
        page_url = f"https://iaae.ai/research/?bmode=view&idx={idx}"
        date = ""
        time_el = row.select_one("li.time")
        if time_el:
            raw = (time_el.get("title") or time_el.get_text(strip=True) or "").strip()
            if re.match(r"^\d{4}-\d{2}-\d{2}", raw):
                date = raw[:10]
        m = _BRACKET_RE.match(title)
        org = m.group(1).strip() if m else "IAAE"
        rows.append(
            {
                "idx": idx,
                "title": title,
                "org": org,
                "category": org,
                "date": date,
                "page_url": page_url,
            }
        )
    return rows


def make_item(row: dict) -> dict:
    idx = row["idx"]
    return {
        "id": f"iaae-ethics-{idx}",
        "collection": "iaae-ethics",
        "collection_name": "IAAE 연구자료실",
        "idx": idx,
        "title": row["title"],
        "org": row["org"],
        "category": row["category"],
        "date": row.get("date") or "",
        "page_url": row["page_url"],
        "source_urls": [],
        "body": "",
        "digest_file": None,
        "list_page": None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-pages", type=int, default=5, help="신규 탐색 시 최대 목록 페이지")
    ap.add_argument("--sleep", type=float, default=0.6)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = load_collection("iaae-ethics")
    items = list(data.get("items") or [])
    known = {str(it.get("idx") or "") for it in items if it.get("idx")}
    new_rows: list[dict] = []
    seen_this_run: set[str] = set()

    for page in range(1, args.max_pages + 1):
        url = f"{BOARD}?page={page}"
        print(f"목록 p{page}: {url}")
        try:
            html = fetch(url)
        except Exception as e:
            print(f"  fetch 실패: {e}", file=sys.stderr)
            break
        rows = parse_list(html)
        if not rows:
            print("  (빈 페이지 — 중단)")
            break
        page_new = 0
        page_known = 0
        for row in rows:
            idx = row["idx"]
            if idx in seen_this_run:
                continue
            seen_this_run.add(idx)
            if idx in known:
                page_known += 1
                continue
            new_rows.append(row)
            known.add(idx)
            page_new += 1
        print(f"  파싱 {len(rows)} · 신규 {page_new} · 기존 {page_known}")
        # 한 페이지가 전부 기존이면 더 깊은 페이지는 보통 더 오래됨 → 중단
        if page_new == 0 and page_known > 0:
            print("  (이 페이지부터 전부 기존 — 중단)")
            break
        if page < args.max_pages:
            time.sleep(args.sleep)

    if not new_rows:
        print("신규 없음")
        # 이전 실행 잔여 파일 제거 — 텔레그램 +N 오인 방지
        stale = ROOT / "cache" / "iaae_board_new_idxs.txt"
        if stale.exists():
            stale.unlink()
        return 0

    print(f"신규 {len(new_rows)}건 추가 예정")
    for row in new_rows:
        print(f"  + {row.get('date') or '?'}  {row['title'][:80]}")
        items.insert(0, make_item(row))

    if args.dry_run:
        print("(dry-run — 저장 안 함)")
        return 0

    data["items"] = items
    rebuild_collection_stats(data)
    save_collection("iaae-ethics", data)
    # catalog.md 는 enrich_iaae 가 다시 씀
    print(f"저장: collections/iaae-ethics/items.json (총 {data['count']}건)")
    out = ROOT / "cache" / "iaae_board_new_idxs.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(r["idx"] for r in new_rows) + "\n", encoding="utf-8")
    print(f"신규 idx: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
