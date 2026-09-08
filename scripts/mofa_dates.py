"""외교부 카드의 연도·월만 있는 발표일을 원문 URL에서 보강.

발표시점이 「2026년」뿐이면 원문 HTML 메타·PDF·주소 경로(/2025/11/)를 본다.
고·중신뢰만 캐시. 결과: cache/mofa_dates.json
  python3 scripts/mofa_dates.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_meta import normalize_date_ko  # noqa: E402
from resolve_oecd_dates import resolve_from_urls, year_ok  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "mofa_dates.json"
MOFA_KEYS = ("mofa-governance", "mofa-country-policy")
USABLE = ("high", "medium")

_PATH_DATE = re.compile(
    r"/(20\d{2})/(\d{2})(?:/(\d{2}))?(?:/|$)",
)


def load_cache() -> dict:
    if not CACHE.exists():
        return {}
    try:
        blob = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return blob if isinstance(blob, dict) else {}


def save_cache(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def hint_year(item: dict) -> int | None:
    raw = (item.get("published") or "") + " " + (item.get("date") or "")
    m = re.search(r"(20\d{2})", raw)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def body_date(item: dict) -> str:
    return normalize_date_ko(item.get("published") or "") or ""


def date_from_url_path(url: str, start_year=None) -> str:
    """oecd.org/.../2025/11/title 같은 출판 경로. 쿼리스트링은 보지 않음."""
    path = urlparse(url or "").path or ""
    m = _PATH_DATE.search(path)
    if not m:
        return ""
    y, mo = int(m.group(1)), int(m.group(2))
    if not (1990 <= y <= 2035 and 1 <= mo <= 12):
        return ""
    if m.group(3):
        day = int(m.group(3))
        if 1 <= day <= 31:
            d = f"{y:04d}-{mo:02d}-{day:02d}"
        else:
            d = f"{y:04d}-{mo:02d}"
    else:
        d = f"{y:04d}-{mo:02d}"
    iso = d if len(d) == 10 else f"{d}-01"
    if start_year is not None and not year_ok(iso, start_year):
        return ""
    return d


def _precision(d: str) -> int:
    d = (d or "").strip()
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", d) and not d.endswith("-01-01"):
        return 3
    if re.fullmatch(r"20\d{2}-\d{2}", d):
        return 2
    if re.fullmatch(r"20\d{2}", d):
        return 1
    return 0


def needs_resolve(item: dict) -> bool:
    d = body_date(item)
    p = _precision(d)
    if p >= 3:
        return False
    board = (item.get("date") or "")[:10]
    if p == 0 and re.fullmatch(r"20\d{2}-\d{2}-\d{2}", board) and not board.endswith("-01-01"):
        return False
    urls = [u for u in (item.get("source_urls") or []) if isinstance(u, str) and u.startswith("http")]
    return bool(urls)


def resolve_item(item: dict) -> dict | None:
    urls = [u for u in (item.get("source_urls") or []) if isinstance(u, str) and u.startswith("http")]
    if not urls:
        return None
    sy = hint_year(item)
    hit = resolve_from_urls(urls, sy)
    if hit and hit.get("date") and not str(hit["date"]).endswith("-01-01"):
        return hit
    for url in urls:
        d = date_from_url_path(url, sy)
        if _precision(d) >= 2:
            return {
                "date": d,
                "method": "url-path",
                "evidence_url": url,
                "confidence": "medium",
            }
    return None


def mofa_card_date(item: dict, cache: dict | None = None) -> str:
    """발표시점 일자 > 원문 복원 > 발표시점 월/연도 > 게시일(1월 1일은 연도)."""
    cache = cache if cache is not None else load_cache()
    body = body_date(item)
    best = body
    best_p = _precision(body)
    hit = cache.get(item.get("id") or "") or {}
    if hit.get("confidence") in USABLE:
        cd = str(hit.get("date") or "").strip()
        if cd.endswith("-01-01") and len(cd) == 10:
            cd = cd[:4]
        if _precision(cd) > best_p:
            best, best_p = cd, _precision(cd)
    if best_p >= 2:
        return best
    board = (item.get("date") or "")[:10]
    if best_p == 1:
        return best
    if board.endswith("-01-01"):
        return board[:4]
    return board or best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    cache = load_cache()
    todo: list[dict] = []
    for key in MOFA_KEYS:
        path = ROOT / "collections" / key / "items.json"
        if not path.exists():
            continue
        blob = json.loads(path.read_text(encoding="utf-8"))
        for it in blob.get("items") or []:
            if not needs_resolve(it):
                continue
            prev = cache.get(it.get("id") or "")
            if prev and prev.get("confidence") in USABLE and not args.force:
                continue
            if prev and prev.get("method") == "none" and not args.force:
                continue
            todo.append(it)
            if len(todo) >= args.limit:
                break
        if len(todo) >= args.limit:
            break

    print(f"mofa date resolve todo={len(todo)} cache={len(cache)}", flush=True)
    ok = 0
    for i, it in enumerate(todo, 1):
        title = (it.get("title") or "")[:50]
        hit = resolve_item(it)
        if hit and hit.get("date"):
            cache[it["id"]] = {
                **hit,
                "id": it["id"],
                "title": it.get("title") or "",
                "resolved": date.today().isoformat(),
            }
            ok += 1
            print(f"[{i}/{len(todo)}] {it['id']} → {hit['date']} [{hit.get('method')}] {title}", flush=True)
        else:
            cache[it["id"]] = {
                "id": it["id"],
                "date": "",
                "method": "none",
                "confidence": "none",
                "title": it.get("title") or "",
                "resolved": date.today().isoformat(),
            }
            print(f"[{i}/{len(todo)}] {it['id']} → (none) {title}", flush=True)
        if i % 10 == 0:
            save_cache(cache)
    save_cache(cache)
    print(f"resolved {ok}/{len(todo)} cache → {CACHE}")


if __name__ == "__main__":
    main()
