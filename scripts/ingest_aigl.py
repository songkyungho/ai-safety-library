#!/usr/bin/env python3
"""Digest·CSV의 AIGL(aigl.blog) 카드를 collections/aigl 로 옮긴다.

원문 URL은 아직 안 붙인다(중복 정리는 나중). 랜딩은 AIGL 카드 URL.
Digest 일일 수집은 중단됐고, 이 스크립트는 기존 적재·재동기화용이다.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from library_common import ROOT, rebuild_collection_stats, write_json  # noqa: E402

COL_KEY = "aigl"
COL_NAME = "AI Governance Library"
DIGEST_ROOT = ROOT.parent / "AI Safety"
_TRAILING_DATE_RE = re.compile(r"\((\d{4})\.(\d{1,2})\.(\d{1,2})\)\s*$")
_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_DOT_RE = re.compile(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})")
_SPLIT_RE = re.compile(r"\n-{3,}\n")
_SOURCE_LINE_RE = re.compile(r"^출처:\s*(.*)$")


def is_aigl_url(url: str) -> bool:
    return "aigl.blog" in (url or "").lower()


def is_aigl_source(source: str) -> bool:
    s = (source or "").strip()
    if s == "AIGovernanceLibrary":
        return True
    return "aigl" in s.lower()


def canonical_aigl_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    p = urlparse(u)
    host = (p.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host != "aigl.blog":
        return u.split("#")[0].rstrip("/")
    path = (p.path or "/").rstrip("/") or "/"
    return urlunparse(("https", "www.aigl.blog", path, "", "", ""))


def slug_from_url(url: str) -> str:
    path = urlparse(canonical_aigl_url(url) or url).path.strip("/")
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", path).strip("-").lower()
    return slug[:80]


def title_and_date(title_line: str) -> tuple[str, str]:
    raw = (title_line or "").strip()
    raw = re.sub(r"^\*\*(.+)\*\*$", r"\1", raw).strip()
    m = _TRAILING_DATE_RE.search(raw)
    date = ""
    if m:
        date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        raw = raw[: m.start()].rstrip()
    return raw, date


def normalize_date(raw: str) -> str:
    s = (raw or "").strip()
    if not s or s.lower() == "nan":
        return ""
    m = _ISO_RE.match(s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = _DOT_RE.match(s.replace("/", "."))
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return ""


def block_url(block: str) -> str:
    for line in block.splitlines():
        s = line.strip()
        if s.startswith("http://") or s.startswith("https://"):
            return s
    return ""


def block_source(block: str) -> str:
    for line in block.splitlines():
        m = _SOURCE_LINE_RE.match(line.strip())
        if m:
            return m.group(1).strip()
    return ""


def parse_digest_aigl(digest_dir: Path) -> list[dict]:
    rows: list[dict] = []
    if not digest_dir.is_dir():
        return rows
    for path in sorted(digest_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for raw in _SPLIT_RE.split(text.strip()):
            block = raw.strip()
            url = block_url(block)
            if not url:
                continue
            src = block_source(block)
            if not (is_aigl_url(url) or is_aigl_source(src)):
                continue
            lines = [ln for ln in block.splitlines()]
            title_line = lines[1].strip() if len(lines) >= 2 else ""
            title, date_from_title = title_and_date(title_line)
            body_lines: list[str] = []
            seen_blank = False
            meta_done = False
            for ln in lines[2:]:
                s = ln.strip()
                if not meta_done:
                    if not s:
                        meta_done = True
                        seen_blank = True
                        continue
                    if s.startswith("출처:") or s.startswith("관련:"):
                        continue
                    continue
                if s.startswith("관련:"):
                    continue
                body_lines.append(ln)
            body = "\n".join(body_lines).strip()
            rows.append(
                {
                    "url": canonical_aigl_url(url) or url,
                    "title": title or url,
                    "date": date_from_title,
                    "body": body,
                    "digest_file": path.name,
                }
            )
    return rows


def parse_csv_aigl(csv_path: Path) -> list[dict]:
    rows: list[dict] = []
    if not csv_path.is_file():
        return rows
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            link = (r.get("Link") or "").strip()
            src = (r.get("Source") or "").strip()
            if not (is_aigl_url(link) or is_aigl_source(src)):
                continue
            title = (r.get("Title") or "").strip()
            date = normalize_date(r.get("Date") or "")
            excerpt = (r.get("Excerpt") or "").strip()
            rows.append(
                {
                    "url": canonical_aigl_url(link) or link,
                    "title": title or link,
                    "date": date,
                    "body": excerpt,
                    "digest_file": None,
                }
            )
    return rows


def merge_rows(digest_rows: list[dict], csv_rows: list[dict]) -> list[dict]:
    by_url: dict[str, dict] = {}
    for row in csv_rows + digest_rows:
        url = row["url"]
        if not url or not slug_from_url(url):
            continue
        prev = by_url.get(url)
        if not prev:
            by_url[url] = dict(row)
            continue
        if len(row.get("body") or "") > len(prev.get("body") or ""):
            prev["body"] = row["body"]
        if row.get("digest_file") and not prev.get("digest_file"):
            prev["digest_file"] = row["digest_file"]
        if row.get("title") and (
            not prev.get("title") or prev["title"] == prev["url"]
        ):
            prev["title"] = row["title"]
        if row.get("date") and not prev.get("date"):
            prev["date"] = row["date"]
    return list(by_url.values())


def make_item(row: dict) -> dict:
    slug = slug_from_url(row["url"])
    return {
        "id": f"aigl-{slug}",
        "collection": COL_KEY,
        "collection_name": COL_NAME,
        "slug": slug,
        "title": row["title"],
        "org": "AIGL",
        "category": "AIGL",
        "date": row.get("date") or "",
        "page_url": row["url"],
        "source_urls": [],
        "body": row.get("body") or "",
        "digest_file": row.get("digest_file"),
    }


def catalog_md(items: list[dict]) -> str:
    lines = [
        f"# {COL_NAME}",
        "",
        "- 큐레이터: AI Governance Library (aigl.blog)",
        "- 랜딩은 AIGL 카드 URL. 원문 URL은 아직 비움(중복 허용).",
        f"- 건수: **{len(items)}건**",
        "",
        "| 날짜 | 제목 |",
        "|---|---|",
    ]
    for r in items:
        title = (r.get("title") or "").replace("|", "\\|")
        page = r.get("page_url") or ""
        lines.append(f"| {r.get('date') or ''} | [{title}]({page}) |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--digest-root", type=Path, default=DIGEST_ROOT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    digest_dir = args.digest_root / "daily_digest"
    csv_path = args.digest_root / "global_ai_news_list.csv"
    digest_rows = parse_digest_aigl(digest_dir)
    csv_rows = parse_csv_aigl(csv_path)
    merged = merge_rows(digest_rows, csv_rows)
    items = [make_item(r) for r in merged]
    items.sort(key=lambda it: (it.get("date") or "", it.get("title") or ""), reverse=True)

    data = {
        "collection": COL_KEY,
        "name": COL_NAME,
        "source": {
            "list_url": "https://www.aigl.blog/",
            "note": (
                "거버넌스 문건 카탈로그. Digest에서 이관. "
                "page_url은 AIGL 카드. source_urls는 비움(원문 중복 정리는 나중)."
            ),
        },
        "items": items,
    }
    rebuild_collection_stats(data)

    print(f"Digest AIGL {len(digest_rows)} · CSV {len(csv_rows)} → 고유 {len(items)}")
    if args.dry_run:
        for it in items[:8]:
            print(f"  {it.get('date') or '?'}  {it['title'][:80]}")
        print("(dry-run — 저장 안 함)")
        return 0

    col_dir = ROOT / "collections" / COL_KEY
    col_dir.mkdir(parents=True, exist_ok=True)
    write_json(col_dir / "items.json", data)
    write_json(
        col_dir / "source.json",
        {
            "list_url": "https://www.aigl.blog/",
            "rss": "https://www.aigl.blog/rss/",
            "fetched": "",
            "note": data["source"]["note"],
        },
    )
    (col_dir / "catalog.md").write_text(catalog_md(items), encoding="utf-8")
    print(f"저장: collections/{COL_KEY}/items.json ({data['count']}건)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
