#!/usr/bin/env python3
"""외교부 AI 게시판에서 신규 글만 받아 collections/mofa-* 에 추가.

WAF가 브라우저 쿠키를 본다. MOFA_COOKIE 는 git에 넣지 말고
~/.ai_safety_daily_env 에 둔다. 만료되면 브라우저에서 Cookie 헤더를 다시 넣는다.

  python3 scripts/ingest_mofa_board.py
  python3 scripts/ingest_mofa_board.py --dry-run
"""
from __future__ import annotations

import argparse
import csv
import gzip
import os
import re
import sys
import time
import urllib.error
import urllib.request
from html import unescape
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_ko import load_env_file  # noqa: E402
from library_common import (  # noqa: E402
    ROOT,
    as_url_list,
    rebuild_collection_stats,
    save_collection,
    load_collection,
)

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.5 Safari/605.1.15"
)
REFERER = "https://www.mofa.go.kr/www/wpge/m_29690/contents.do"
BOARDS = (
    {
        "key": "mofa-governance",
        "name": "외교부 글로벌 AI거버넌스 논의",
        "board_id": "m_29691",
        "list": "https://www.mofa.go.kr/www/brd/m_29691/list.do",
        "view": "https://www.mofa.go.kr/www/brd/m_29691/view.do",
    },
    {
        "key": "mofa-country-policy",
        "name": "외교부 주요국 AI 정책",
        "board_id": "m_29692",
        "list": "https://www.mofa.go.kr/www/brd/m_29692/list.do",
        "view": "https://www.mofa.go.kr/www/brd/m_29692/view.do",
    },
)
_BRACKET_RE = re.compile(r"^\[([^\]]+)\]\s*(.*)$")
_SEQ_RE = re.compile(r"[?&]seq=(\d+)", re.I)
_WAF_HINTS = ("access denied", "웹방화벽", "captcha", "blocked", "요청이 차단")
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


def load_mofa_env() -> None:
    for p in (
        Path.home() / ".ai_safety_daily_env",
        Path.home() / "ai_safety_daily_env",
        ROOT.parent / "AI Safety" / "ai_safety_daily_env",
        ROOT / "ai_safety_library_env",
    ):
        load_env_file(p)


def cookie() -> str:
    return (os.environ.get("MOFA_COOKIE") or "").strip()


def user_agent() -> str:
    return (os.environ.get("MOFA_USER_AGENT") or DEFAULT_UA).strip() or DEFAULT_UA


def fetch(url: str) -> str:
    ck = cookie()
    if not ck:
        raise RuntimeError("MOFA_COOKIE 없음. ~/.ai_safety_daily_env 에 브라우저 Cookie 헤더를 넣어 주세요.")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Cookie": ck,
            "Referer": REFERER,
        },
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        raw = r.read()
        enc = (r.headers.get("Content-Encoding") or "").lower()
        if "gzip" in enc:
            raw = gzip.decompress(raw)
        html = raw.decode("utf-8", "replace")
    low = html.lower()
    if any(h in low for h in _WAF_HINTS) and "tableB" not in html and "bo_head" not in html:
        raise RuntimeError("외교부 WAF가 응답을 막았습니다. Cookie를 브라우저에서 다시 복사해 주세요.")
    return html


def txt(el) -> str:
    if el is None:
        return ""
    return unescape(el.get_text(" ", strip=True)).replace("\u00a0", " ").replace("\u200b", "").strip()


def parse_list(html: str, board: dict, page: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for tr in soup.select("table.tableB tbody tr"):
        tds = tr.find_all("td")
        a = tr.select_one('a[href*="view.do"]')
        if not a:
            continue
        href = a.get("href") or ""
        m = _SEQ_RE.search(href)
        if not m:
            continue
        seq = m.group(1)
        title = txt(a)
        if not title:
            continue
        category = txt(tds[1]) if len(tds) > 1 else ""
        department = txt(tds[4]) if len(tds) > 4 else ""
        date = txt(tds[5]) if len(tds) > 5 else ""
        if re.match(r"^\d{4}-\d{2}-\d{2}", date):
            date = date[:10]
        no_raw = txt(tds[0]) if tds else ""
        no = int(no_raw) if no_raw.isdigit() else no_raw
        bm = _BRACKET_RE.match(title)
        org = bm.group(1).strip() if bm else category or "외교부"
        rows.append(
            {
                "seq": seq,
                "no": no,
                "title": title,
                "org": org,
                "category": category or "기타",
                "date": date,
                "department": department,
                "list_page": page,
                "page_url": f"{board['view']}?seq={seq}",
            }
        )
    return rows


def field_from_body(body: str, key: str) -> str:
    pat = re.compile(rf"(?:^|\n)●?\s*{re.escape(key)}\s*[:：]\s*(.+)", re.M)
    m = pat.search(body or "")
    return m.group(1).strip() if m else ""


def parse_detail(html: str, board: dict) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    h2 = soup.select_one(".bo_head h2")
    meta: dict[str, str] = {}
    dl = soup.select_one(".bo_head dl")
    if dl:
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            meta[txt(dt)] = txt(dd)
    body_el = soup.select_one(".bo_con")
    body = ""
    if body_el:
        clone = BeautifulSoup(str(body_el), "html.parser")
        for n in clone.select("script, style"):
            n.decompose()
        blocks = clone.select("li, p")
        if blocks:
            lines = [txt(el) for el in blocks if txt(el)]
            deduped: list[str] = []
            for line in lines:
                if not deduped or deduped[-1] != line:
                    deduped.append(line)
            body = "\n".join(deduped)
        else:
            body = txt(clone)
    source_urls: list[str] = []
    seen: set[str] = set()
    for a in soup.select("ul.bo_util li.link a[href]"):
        href = (a.get("href") or "").strip()
        if not href.startswith("http") or href in seen:
            continue
        if "mofa.go.kr/www/brd" in href:
            continue
        seen.add(href)
        source_urls.append(href)
    attachments = []
    for a in soup.select("ul.bo_file a[href]"):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("./"):
            href = href[2:]
        if not href.startswith("http"):
            href = f"https://www.mofa.go.kr/www/brd/{board['board_id']}/" + href.lstrip("/")
        attachments.append({"text": txt(a) or a.get("title") or "", "href": href.replace("&amp;", "&")})
    return {
        "detail_title": txt(h2),
        "modified": meta.get("수정일") or "",
        "views": re.sub(r"[^0-9]", "", meta.get("조회수") or "") or None,
        "body": body,
        "source_urls": source_urls,
        "attachments": attachments,
    }


def make_item(board: dict, row: dict, detail: dict) -> dict:
    body = detail.get("body") or ""
    views = detail.get("views")
    item = {
        "id": f"{board['key']}-{row['seq']}",
        "collection": board["key"],
        "collection_name": board["name"],
        "seq": str(row["seq"]),
        "no": row.get("no"),
        "title": row["title"],
        "org": row.get("org") or "",
        "category": row.get("category") or "기타",
        "date": row.get("date") or "",
        "modified": detail.get("modified") or "",
        "department": row.get("department") or "",
        "institution": field_from_body(body, "기관"),
        "document_name": field_from_body(body, "문서명"),
        "document_type": field_from_body(body, "문서종류"),
        "published": field_from_body(body, "발표시점") or field_from_body(body, "게시시점"),
        "page_url": row["page_url"],
        "source_urls": detail.get("source_urls") or [],
        "attachments": detail.get("attachments") or [],
        "body": body,
        "list_page": row.get("list_page"),
    }
    if views:
        item["views"] = int(views) if str(views).isdigit() else views
    return item


def write_csv(key: str, items: list[dict]) -> None:
    path = ROOT / "collections" / key / "items.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in items:
            w.writerow(
                {
                    **{k: r.get(k, "") for k in CSV_FIELDS},
                    "source_urls": " | ".join(as_url_list(r.get("source_urls"))),
                    "body": (r.get("body") or "")[:8000],
                }
            )


def write_catalog(board: dict, items: list[dict]) -> None:
    dates = [r.get("date") or "" for r in items if r.get("date")]
    period = ""
    if dates:
        period = f"{min(dates)} ~ {max(dates)}"
    lines = [
        f"# {board['name']}",
        "",
        "- 큐레이터: 외교부 국제과학기술규범과",
        f"- 출처: [{board['name']}]({board['list']})",
        "- 데이터: `items.json` · `items.csv` · 본문 `posts.md`",
        f"- 건수: **{len(items)}건**",
    ]
    if period:
        lines.append(f"- 기간: {period}")
    lines += ["", "| 날짜 | 분류 | 제목 | 원문 |", "|---|---|---|---|"]
    for r in items:
        src = (as_url_list(r.get("source_urls")) or [None])[0]
        src_md = f"[원문]({src})" if src else ""
        title = (r.get("title") or "").replace("|", "\\|")
        page = r.get("page_url") or ""
        lines.append(
            f"| {r.get('date') or ''} | {(r.get('category') or '')[:20]} | [{title}]({page}) | {src_md} |"
        )
    (ROOT / "collections" / board["key"] / "catalog.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def ingest_board(board: dict, *, max_pages: int, sleep: float, dry_run: bool) -> list[dict]:
    data = load_collection(board["key"])
    items = list(data.get("items") or [])
    known = {str(it.get("seq") or "") for it in items if it.get("seq")}
    new_rows: list[dict] = []
    seen: set[str] = set()

    for page in range(1, max_pages + 1):
        url = f"{board['list']}?page={page}"
        print(f"{board['board_id']} 목록 p{page}: {url}")
        html = fetch(url)
        rows = parse_list(html, board, page)
        if not rows:
            print("  (빈 페이지 — 중단)")
            break
        page_new = page_known = 0
        for row in rows:
            seq = row["seq"]
            if seq in seen:
                continue
            seen.add(seq)
            if seq in known:
                page_known += 1
                continue
            new_rows.append(row)
            known.add(seq)
            page_new += 1
        print(f"  파싱 {len(rows)} · 신규 {page_new} · 기존 {page_known}")
        if page_new == 0 and page_known > 0:
            print("  (이 페이지부터 전부 기존 — 중단)")
            break
        if page < max_pages:
            time.sleep(sleep)

    if not new_rows:
        print(f"{board['key']}: 신규 없음")
        return []

    built: list[dict] = []
    for row in new_rows:
        print(f"  + {row.get('date') or '?'}  {row['title'][:80]}")
        if dry_run:
            continue
        time.sleep(sleep)
        detail = parse_detail(fetch(row["page_url"]), board)
        built.append(make_item(board, row, detail))

    if dry_run:
        print(f"{board['key']}: dry-run {len(new_rows)}건")
        return new_rows

    for item in reversed(built):
        items.insert(0, item)
    data["items"] = items
    rebuild_collection_stats(data)
    save_collection(board["key"], data)
    write_csv(board["key"], items)
    write_catalog(board, items)
    print(f"저장: collections/{board['key']}/items.json (총 {data['count']}건)")
    return built


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-pages", type=int, default=3)
    ap.add_argument("--sleep", type=float, default=0.5)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--board", choices=["mofa-governance", "mofa-country-policy", "all"], default="all")
    args = ap.parse_args()

    load_mofa_env()
    if not cookie():
        print("MOFA_COOKIE 없음 — 외교부 수집 건너뜀", file=sys.stderr)
        return 0

    boards = [b for b in BOARDS if args.board == "all" or b["key"] == args.board]
    added = 0
    new_ids: list[str] = []
    try:
        for board in boards:
            rows = ingest_board(board, max_pages=args.max_pages, sleep=args.sleep, dry_run=args.dry_run)
            added += len(rows)
            new_ids.extend(str(r.get("seq") or r.get("id") or "") for r in rows)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.reason}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1

    out = ROOT / "cache" / "mofa_board_new_seqs.txt"
    if added and not args.dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(x for x in new_ids if x) + "\n", encoding="utf-8")
    elif out.exists() and not added:
        out.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
