#!/usr/bin/env python3
"""DPA *Regulating Artificial Intelligence* 스레드(issue 42) → collections/dpa-ai.

범위 필터는 ingest에서 하지 않는다. OECD·외교부·AGORA와 같이 원천은 두고
build_documents의 classify_safety + LLM 큐레이션이 in_scope를 가른다.

  python3 scripts/ingest_dpa_ai_thread.py --limit 250
  python3 scripts/ingest_dpa_ai_thread.py --full
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from library_common import ROOT, load_collection, rebuild_collection_stats, write_json  # noqa: E402

ISSUE_ID = 42
ISSUE_SLUG = "regulating-artificial-intelligence"
API_HOST = "https://api.globaltradealert.org"
PAGE_SIZE = 100
COL_KEY = "dpa-ai"
COL_NAME = "DPA Regulating AI"
UA = "AI-Safety-Library/0.1 (research archive; ingest dpa thread)"
TODAY = date.today().isoformat()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = val


def dpa_api_key() -> str:
    key = (os.environ.get("DPA_API") or "").strip()
    if key:
        return key
    for p in (
        Path.home() / ".ai_safety_daily_env",
        ROOT.parent / "AI Safety" / "ai_safety_daily_env",
        ROOT / "ai_safety_library_env",
    ):
        load_env_file(p)
        key = (os.environ.get("DPA_API") or "").strip()
        if key:
            return key
    return ""


def get_json(url: str, key: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"APIKey {key}",
            "Accept": "application/json",
            "User-Agent": UA,
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def status_name(raw) -> str:
    if isinstance(raw, dict):
        return str(raw.get("name") or "").strip()
    return str(raw or "").strip()


def compact_events(events: list) -> list[dict]:
    out = []
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        action = ev.get("action_type") if isinstance(ev.get("action_type"), dict) else {}
        impls = []
        for impl in ev.get("implementers") or []:
            if isinstance(impl, dict) and impl.get("name"):
                impls.append(impl["name"])
        out.append(
            {
                "id": ev.get("id"),
                "slug": ev.get("slug") or "",
                "title": ev.get("title") or "",
                "description": ev.get("description") or "",
                "date": (ev.get("date") or "")[:10],
                "action": action.get("name") or "",
                "status": status_name(action.get("current_status")),
                "implementers": impls,
                "event_url": (
                    f"https://digitalpolicyalert.org/event/{ev['slug']}"
                    if ev.get("slug")
                    else ""
                ),
            }
        )
    return out


def event_body(events: list[dict]) -> str:
    parts = []
    for ev in events:
        title = (ev.get("title") or "").strip()
        desc = (ev.get("description") or "").strip()
        date = (ev.get("date") or "").strip()
        head = " · ".join(p for p in (date, title) if p)
        if head:
            parts.append(head)
        if desc and desc != title:
            parts.append(desc)
    return "\n\n".join(parts).strip()


def record_from_intervention(it: dict) -> dict:
    iid = it.get("id")
    slug = it.get("slug") or str(iid)
    events = compact_events(it.get("events") or [])
    latest = events[0] if events else {}
    impls = latest.get("implementers") or []
    country = it.get("country") or ""
    if isinstance(country, dict):
        country = country.get("name") or ""
    org = impls[0] if impls else country
    st = status_name(it.get("status"))
    date_cur = (it.get("date_current") or "")[:10]
    if not date_cur and events:
        date_cur = events[0].get("date") or ""
    return {
        "id": f"dpa-ai-{iid}",
        "collection": COL_KEY,
        "collection_name": COL_NAME,
        "dpa_id": iid,
        "title": it.get("title") or slug,
        "org": org or "",
        "category": st or "기타",
        "status": st,
        "date": date_cur,
        "country": country,
        "page_url": f"https://digitalpolicyalert.org/intervention/{slug}",
        "source_urls": [],
        "body": event_body(events),
        "events": events,
        "slug": slug,
        "issue_id": ISSUE_ID,
    }


def fetch_event_list(key: str, *, limit: int | None, sleep: float) -> list[dict]:
    out: list[dict] = []
    offset = 0
    total = None
    while True:
        url = (
            f"{API_HOST}/dpa/issue/{ISSUE_ID}/event-list/"
            f"?limit={PAGE_SIZE}&offset={offset}"
        )
        data = get_json(url, key)
        if total is None:
            total = int(data.get("count") or 0)
            print(f"dpa issue {ISSUE_ID} event-list count {total}")
        batch = data.get("results") or []
        out.extend(batch)
        print(f"  offset {offset} got {len(batch)} total {len(out)}")
        if limit is not None and len(out) >= limit:
            out = out[:limit]
            break
        if not batch or not data.get("next"):
            break
        offset += PAGE_SIZE
        time.sleep(sleep)
    seen: dict[int, dict] = {}
    for it in out:
        iid = it.get("id")
        if iid is None:
            continue
        seen[int(iid)] = it
    return list(seen.values())


def catalog_md(rows: list[dict]) -> str:
    lines = [
        f"# {COL_NAME}",
        "",
        f"Digital Policy Alert 스레드 "
        f"[Regulating Artificial Intelligence](https://digitalpolicyalert.org/threads/{ISSUE_SLUG}).",
        "랜딩은 DPA intervention 페이지. 원문 URL은 이후 보강.",
        "",
        f"수집일 {TODAY} · {len(rows)}건",
        "",
        "| 날짜 | 관할 | 상태 | 제목 |",
        "|---|---|---|---|",
    ]
    for r in rows:
        title = (r.get("title") or "").replace("|", "｜")
        url = r.get("page_url") or ""
        cell = f"[{title}]({url})" if url else title
        lines.append(
            f"| {r.get('date') or ''} | {r.get('country') or ''} | "
            f"{r.get('status') or ''} | {cell} |"
        )
    return "\n".join(lines) + "\n"


def csv_row(r: dict) -> dict:
    return {
        "id": r.get("id"),
        "collection": r.get("collection"),
        "date": r.get("date"),
        "category": r.get("category"),
        "org": r.get("org"),
        "title": r.get("title"),
        "page_url": r.get("page_url"),
        "country": r.get("country"),
        "status": r.get("status"),
        "body": (r.get("body") or "")[:8000],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=250, help="최근 N건 (파일럿 기본 250)")
    ap.add_argument("--full", action="store_true", help="스레드 전체")
    ap.add_argument("--sleep", type=float, default=0.15)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    key = dpa_api_key()
    if not key:
        raise SystemExit("DPA_API 없음. ~/.ai_safety_daily_env 또는 AI Safety/ai_safety_daily_env")

    cap = None if args.full else args.limit
    raw = fetch_event_list(key, limit=cap, sleep=args.sleep)
    rows = [record_from_intervention(it) for it in raw]
    rows.sort(key=lambda r: (r.get("date") or "", r.get("title") or ""), reverse=True)
    print("records", len(rows), "status", dict(Counter(r.get("status") or "" for r in rows)))

    if args.dry_run:
        for r in rows[:8]:
            print(" ", r["date"], r["country"], r["title"][:70])
        return

    existing: dict[str, dict] = {}
    path = ROOT / "collections" / COL_KEY / "items.json"
    if path.exists():
        try:
            for it in load_collection(COL_KEY).get("items") or []:
                if it.get("id"):
                    existing[it["id"]] = it
        except (OSError, json.JSONDecodeError):
            existing = {}
    for r in rows:
        existing[r["id"]] = r
    merged = list(existing.values())
    merged.sort(key=lambda r: (r.get("date") or "", r.get("title") or ""), reverse=True)

    pack = {
        "collection": COL_KEY,
        "name": COL_NAME,
        "source": {
            "thread": "Regulating Artificial Intelligence",
            "issue_id": ISSUE_ID,
            "slug": ISSUE_SLUG,
            "list_url": f"https://digitalpolicyalert.org/threads/{ISSUE_SLUG}",
            "api": f"{API_HOST}/dpa/issue/{ISSUE_ID}/event-list/",
            "fetched": TODAY,
            "note": "큐레이터 랜딩. 원문 URL은 API에 없음. CC BY-NC 4.0.",
        },
        "items": merged,
    }
    rebuild_collection_stats(pack)
    col_dir = ROOT / "collections" / COL_KEY
    col_dir.mkdir(parents=True, exist_ok=True)
    write_json(col_dir / "items.json", pack)
    write_json(col_dir / "source.json", pack["source"])
    (col_dir / "catalog.md").write_text(catalog_md(merged), encoding="utf-8")
    with (col_dir / "items.csv").open("w", encoding="utf-8-sig", newline="") as f:
        fields = [
            "id",
            "collection",
            "date",
            "category",
            "org",
            "title",
            "page_url",
            "country",
            "status",
            "body",
        ]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in merged:
            w.writerow(csv_row(r))
    print(f"저장: collections/{COL_KEY}/items.json (총 {pack['count']}건)")


if __name__ == "__main__":
    main()
