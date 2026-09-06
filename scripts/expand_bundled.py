#!/usr/bin/env python3
"""Expand bundled curator posts into per-document records.

Example: one IAAE/NIA card lists four AI Basic Act guidelines; the NIA
board page has one PDF attachment per guideline. We emit one derived item
per attachment (or per title segment when attachments are unavailable).
"""
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
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from library_common import (  # noqa: E402
    ROOT,
    as_url_list,
    rebuild_collection_stats,
    write_json,
)

UA = "AI-Safety-Library/0.1 (expand bundled)"
DERIVED = ROOT / "collections" / "derived-splits"
SPLIT_SUFFIX = re.compile(
    r"(가이드라인|지침|가이드|원칙|기준|프레임워크|고시|지침서)\s*$"
)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def title_prefix_and_rest(title: str) -> tuple[str, str]:
    m = re.match(r"^([［\[][^］\]]+[］\]])\s*(.+)$", title.strip())
    if m:
        return m.group(1), m.group(2)
    return "", title.strip()


def split_title_segments(rest: str) -> list[str]:
    """Split 'A 가이드라인, B 가이드라인, …' into segments."""
    # Avoid splitting "「옛것과 새것」, ancient and new"
    if "「" in rest or "Antiqua" in rest:
        return [rest]
    parts = [p.strip() for p in re.split(r",\s*", rest) if p.strip()]
    if len(parts) < 2:
        return [rest]
    if all(SPLIT_SUFFIX.search(p) or len(p) >= 12 for p in parts) and len(parts) >= 2:
        # require at least 2 parts that look like named instruments
        named = sum(1 for p in parts if SPLIT_SUFFIX.search(p))
        if named >= 2:
            return parts
    return [rest]


def normalize_name(s: str) -> str:
    s = unicodedata_fold(s)
    s = re.sub(r"[_\-\s]+", "", s)
    s = re.sub(r"\d+", "", s)  # drop date stamps in filenames
    return s


def unicodedata_fold(s: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"\s+", "", s)


def extract_nia_attachments(page_url: str, html: str) -> list[dict]:
    """NIA board Download.do attachments with display names."""
    base = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"
    out = []
    seen = set()
    # <a href="/common/board/Download.do?...fileNo=14" ...>1._260126_인공지능_투명성_확보_가이드라인.pdf</a>
    for m in re.finditer(
        r'href="([^"]*Download\.do[^"]*)"[^>]*>\s*([^<>]+?\.pdf)\s*<',
        html,
        flags=re.I,
    ):
        href, name = m.group(1), html_mod.unescape(m.group(2)).strip()
        url = urljoin(base, href)
        if url in seen:
            continue
        seen.add(url)
        # Strip leading "1._260126_" style prefixes for display title
        display = re.sub(r"^\d+\._\d+_", "", name)
        display = display.replace("_", " ").replace(".pdf", "").strip()
        out.append({"title": display, "filename": name, "url": url})
    return out


def extract_generic_pdfs(page_url: str, html: str) -> list[dict]:
    base = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"
    out = []
    seen = set()
    for m in re.finditer(
        r'href="([^"]+\.pdf[^"]*)"[^>]*>([^<]{0,120})',
        html,
        flags=re.I,
    ):
        href, label = m.group(1), html_mod.unescape(m.group(2) or "").strip()
        url = urljoin(base, href)
        if url in seen:
            continue
        seen.add(url)
        name = label if label.lower().endswith(".pdf") else (label or url.rsplit("/", 1)[-1])
        display = name.replace("_", " ").replace(".pdf", "").strip()
        out.append({"title": display, "filename": name, "url": url})
    return out


def match_segment_to_attachment(segment: str, attachments: list[dict]) -> dict | None:
    seg_n = normalize_name(segment)
    best = None
    best_score = 0
    for att in attachments:
        cand = normalize_name(att["title"] + att.get("filename", ""))
        if not cand:
            continue
        # mutual containment / overlap
        score = 0
        if seg_n and seg_n in cand:
            score = len(seg_n)
        elif cand and cand in seg_n:
            score = len(cand)
        else:
            # token overlap
            toks = [t for t in re.findall(r"[가-힣a-z]{2,}", segment.lower()) if t not in {"인공", "지능", "인공지능"}]
            hit = sum(1 for t in toks if t in cand)
            score = hit * 3
        if score > best_score:
            best_score = score
            best = att
    if best and best_score >= 6:
        return best
    return None


def expand_item(item: dict, html_cache: dict[str, str], sleep: float) -> list[dict]:
    title = item.get("title") or ""
    prefix, rest = title_prefix_and_rest(title)
    segments = split_title_segments(rest)
    if len(segments) < 2:
        return []

    sources = as_url_list(item.get("source_urls"))
    page = sources[0] if sources else (item.get("page_url") or "")
    attachments: list[dict] = []
    if page.startswith("http"):
        if page not in html_cache:
            try:
                html_cache[page] = fetch(page)
                time.sleep(sleep)
            except Exception as e:
                print(f"  fetch fail {page}: {e}")
                html_cache[page] = ""
        html = html_cache[page]
        if "nia.or.kr" in page:
            attachments = extract_nia_attachments(page, html)
        if not attachments:
            attachments = extract_generic_pdfs(page, html)

    children = []
    for i, seg in enumerate(segments, 1):
        att = match_segment_to_attachment(seg, attachments) if attachments else None
        child_title = f"{prefix} {seg}".strip() if prefix else seg
        canon = att["url"] if att else page
        child = {
            "id": f"derived-split-{item['id']}-{i}",
            "collection": "derived-splits",
            "collection_name": "묶음 분리",
            "parent_id": item["id"],
            "title": child_title,
            "org": item.get("org") or "",
            "category": item.get("category") or "",
            "date": item.get("date") or "",
            "page_url": page or item.get("page_url") or "",
            "source_urls": [canon] if canon else [],
            "source_files": [att["url"]] if att else [],
            "body": (item.get("body") or "")[:800],
            "bundle_index": i,
            "bundle_total": len(segments),
            "bundle_parent_title": title,
        }
        children.append(child)
        print(f"  [{i}/{len(segments)}] {child_title[:70]}")
        print(f"       → {canon[:90]}")
    return children


def find_candidates() -> list[dict]:
    """IAAE (and later others) whose titles look like multi-instrument bundles."""
    out = []
    for key in ("iaae-ethics", "mofa-country-policy", "mofa-governance"):
        path = ROOT / "collections" / key / "items.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for it in data.get("items") or []:
            _, rest = title_prefix_and_rest(it.get("title") or "")
            if len(split_title_segments(rest)) >= 2:
                out.append(it)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=0.4)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    cands = find_candidates()
    if args.limit:
        cands = cands[: args.limit]
    print(f"bundle candidates: {len(cands)}")

    html_cache: dict[str, str] = {}
    children: list[dict] = []
    parents: list[str] = []
    for it in cands:
        print(it.get("id"), (it.get("title") or "")[:80])
        kids = expand_item(it, html_cache, args.sleep)
        if kids:
            children.extend(kids)
            parents.append(it["id"])

    DERIVED.mkdir(parents=True, exist_ok=True)
    pack = {
        "collection": "derived-splits",
        "name": "묶음 분리",
        "count": len(children),
        "parent_ids": parents,
        "items": children,
        "note": "큐레이터 한 카드에 여러 지침이 묶인 경우, 원본 첨부(PDF) 기준으로 건을 나눈 파생 레코드",
    }
    rebuild_collection_stats(pack)
    write_json(DERIVED / "items.json", pack)

    fields = [
        "id",
        "parent_id",
        "date",
        "org",
        "title",
        "page_url",
        "source_urls",
        "bundle_index",
        "bundle_total",
    ]
    with (DERIVED / "items.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in children:
            row = dict(r)
            row["source_urls"] = " | ".join(as_url_list(r.get("source_urls")))
            w.writerow(row)

    write_json(DERIVED / "parents.json", {"parent_ids": parents, "count": len(parents)})
    print(f"wrote {len(children)} children from {len(parents)} parents → {DERIVED}")


if __name__ == "__main__":
    main()
