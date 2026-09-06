#!/usr/bin/env python3
"""OECD Policy Navigator 항목의 실제 발표일을 원문·검색으로 추정하는 파일럿.

우선순위:
  1) 원문 HTML 메타 / 명시적 Published 문구
  2) 비-OECD 호스트 PDF CreationDate (startYear와 맞을 때)
  3) DuckDuckGo 검색 스니펫에서 날짜 추출 (startYear 일치 시)

결과: cache/oecd_dates.json
  python3 scripts/resolve_oecd_dates.py --limit 100
  python3 scripts/resolve_oecd_dates.py --limit 100 --apply   # 고신뢰만 items에 반영
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "collections" / "oecd-navigator" / "items.json"
CACHE = ROOT / "cache" / "oecd_dates.json"
UA = (
    "Mozilla/5.0 (compatible; AI-Safety-Library/0.1; "
    "+https://github.com/local; research date resolution)"
)

_META = re.compile(
    r"""<meta[^>]+(?:property|name)=["'](?:article:published_time|og:updated_time|"""
    r"""datePublished|pubdate|publishdate|DC\.date|dc\.date|citation_publication_date)"""
    r"""["'][^>]+content=["']([^"']+)["']"""
    r"""|<meta[^>]+content=["']([^"']+)["'][^>]+(?:property|name)=["'](?:article:published_time|"""
    r"""datePublished|pubdate|DC\.date)["']""",
    re.I,
)
_JSONLD = re.compile(
    r""""(?:datePublished|dateCreated|uploadDate)"\s*:\s*"([^"]+)" """,
    re.I,
)
_PUB_LINE = re.compile(
    r"""(?:published|publication\s*date|released|issued|adopted|posted)"""
    r"""[^0-9]{0,40}"""
    r"""((?:20\d{2}-\d{2}-\d{2})|(?:\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+20\d{2})"""
    r"""|(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20\d{2}))""",
    re.I,
)
_ISO = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")
_PDF_CREATION = re.compile(r"/CreationDate\s*\(D:(\d{4})(\d{2})(\d{2})")
_DDG_DATE = re.compile(
    r"(20\d{2}-\d{2}-\d{2})"
    r"|(?:(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2}))"
    r"|(?:(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s+(20\d{2}))",
    re.I,
)
_MONTH = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_date(raw: str) -> str:
    raw = unescape((raw or "").strip())
    if not raw:
        return ""
    m = _ISO.search(raw[:32])
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1990 <= y <= 2035 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"
    m = re.search(
        r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})",
        raw,
        re.I,
    )
    if m:
        mo = _MONTH[m.group(2)[:3].lower()]
        return f"{int(m.group(3)):04d}-{mo:02d}-{int(m.group(1)):02d}"
    m = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s+(20\d{2})",
        raw,
        re.I,
    )
    if m:
        mo = _MONTH[m.group(1)[:3].lower()]
        return f"{int(m.group(3)):04d}-{mo:02d}-{int(m.group(2)):02d}"
    return ""


def year_ok(resolved: str, start_year) -> bool:
    if not resolved or not start_year:
        return True
    try:
        sy = int(start_year)
    except (TypeError, ValueError):
        return True
    ry = int(resolved[:4])
    # allow ±1 year slack for release vs start
    return abs(ry - sy) <= 1


def is_oecd_storage(url: str) -> bool:
    u = (url or "").lower()
    return "api.oecdai.org/storage" in u or "oecd.ai/storage" in u


def expand_urls(raw_urls: list[str]) -> list[str]:
    """OECD 필드에 공백으로 이어붙인 복수 URL을 분리·정리."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_urls or []:
        text = (raw or "").strip()
        if not text:
            continue
        parts = re.findall(r"https?://[^\s<>\"']+", text)
        if not parts and text.startswith("http"):
            parts = [text.split()[0]]
        for p in parts:
            u = re.sub(r"[\x00-\x1f\x7f]", "", p).rstrip(".,);]'\"")
            if not u.startswith("http") or u in seen:
                continue
            seen.add(u)
            out.append(u)
    return out


def fetch(url: str, timeout: int = 22) -> tuple[str, bytes]:
    url = re.sub(r"[\x00-\x1f\x7f]", "", (url or "").strip())
    if " " in url or not url.startswith("http"):
        raise ValueError(f"invalid url: {url[:80]}")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "text/html,application/pdf,application/json,*/*"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return (r.headers.get("Content-Type") or ""), r.read(1_500_000)


def extract_from_html(html: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in _META.finditer(html):
        raw = m.group(1) or m.group(2) or ""
        d = normalize_date(raw)
        if d:
            out.append((d, "html-meta"))
    for m in _JSONLD.finditer(html[:200_000]):
        d = normalize_date(m.group(1))
        if d:
            out.append((d, "html-jsonld"))
    for m in _PUB_LINE.finditer(html[:120_000]):
        d = normalize_date(m.group(1))
        if d:
            out.append((d, "html-published-line"))
    return out


def extract_from_pdf(data: bytes, url: str) -> list[tuple[str, str]]:
    if is_oecd_storage(url):
        return []  # OECD 업로드 시각 — 발표일로 쓰지 않음
    text = data.decode("latin-1", errors="ignore")
    m = _PDF_CREATION.search(text[:50_000])
    if not m:
        return []
    d = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return [(d, "pdf-creation")]


def resolve_from_urls(urls: list[str], start_year) -> dict | None:
    for url in expand_urls(urls)[:6]:
        if not url.startswith("http"):
            continue
        # skip bare search pages
        if "google.com/search" in url or "google.com/url" in url:
            continue
        try:
            ct, data = fetch(url)
        except Exception:
            continue
        hits: list[tuple[str, str]] = []
        if "pdf" in (ct or "").lower() or url.lower().endswith(".pdf"):
            hits = extract_from_pdf(data, url)
        else:
            html = data.decode("utf-8", errors="ignore")
            hits = extract_from_html(html)
        for d, method in hits:
            if year_ok(d, start_year):
                return {"date": d, "method": method, "evidence_url": url, "confidence": "high"}
            # keep near-miss as medium if same decade? skip
    return None


def ddg_search(query: str) -> str:
    q = urllib.parse.urlencode({"q": query})
    url = f"https://html.duckduckgo.com/html/?{q}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "text/html"},
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read(400_000).decode("utf-8", errors="ignore")


def url_score(url: str) -> int:
    u = (url or "").lower()
    if not u.startswith("http"):
        return -1
    if is_oecd_storage(u) or "google.com/" in u:
        return 0
    score = 1
    if u.endswith(".pdf") or ".pdf?" in u:
        score += 3
    for host in (
        "europa.eu",
        "ec.europa.eu",
        "whitehouse.gov",
        "archives.gov",
        "gov.uk",
        "nist.gov",
        "oecd.org",
        "unesco.org",
        "meti.go.jp",
        "digital-strategy.ec.europa.eu",
    ):
        if host in u:
            score += 4
            break
    if re.search(r"\.(gov|go)\.[a-z.]+", u) or ".gov/" in u:
        score += 2
    return score


def candidate_items(items: list[dict], *, bulk_first: bool = True) -> list[dict]:
    scored: list[tuple[int, dict]] = []
    for it in items:
        added = (it.get("added_on") or it.get("date") or "")[:10]
        urls = expand_urls(
            list(it.get("source_urls") or []) + list(it.get("source_files") or [])
        )
        if not urls:
            continue
        best = max((url_score(u) for u in urls), default=-1)
        if best <= 0:
            continue
        spike = 5 if added == "2025-07-09" or added.startswith("2025-07") else 0
        try:
            sy = int(it.get("start_year") or 0)
        except (TypeError, ValueError):
            sy = 0
        freshness = max(0, sy - 2015)
        scored.append((spike * 10 + best * 3 + freshness, it))
    scored.sort(key=lambda x: (-x[0], str(x[1].get("id"))))
    return [it for _, it in scored]


def resolve_from_search(title: str, start_year, country: str = "") -> dict | None:
    year = str(start_year or "").strip()
    if not title or not year:
        return None
    query = f'"{title[:80]}" {country} {year} published OR released OR adopted'.strip()
    try:
        html = ddg_search(query)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return None
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(re.sub(r"\s+", " ", text))
    if "anomaly" in text.lower() or len(text) < 400:
        return None
    cands: list[str] = []
    for m in _DDG_DATE.finditer(text):
        d = normalize_date(m.group(0))
        if d and year_ok(d, start_year):
            cands.append(d)
    if not cands:
        return None
    same = [d for d in cands if d.startswith(str(start_year))]
    pick = Counter(same or cands).most_common(1)[0][0]
    return {
        "date": pick,
        "method": "web-search",
        "evidence_url": "",
        "confidence": "medium",
        "query": query[:160],
    }


def resolve_from_llm(it: dict, *, model: str) -> dict | None:
    """OpenRouter로 원 발표일 추정."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from enrich_ko import ensure_openrouter_key, llm_json
    except Exception:
        return None
    if not ensure_openrouter_key():
        return None
    urls = sorted(
        expand_urls(list(it.get("source_urls") or []) + list(it.get("source_files") or []))[:6],
        key=url_score,
        reverse=True,
    )
    title = it.get("title") or ""
    sy = it.get("start_year")
    country = it.get("country") or ""
    user = (
        "Find the original publication / adoption / release date of this policy initiative.\n"
        'Return JSON only: {"date":"YYYY-MM-DD or empty", "confidence":"high|medium|low|none", '
        '"rationale":"short"}.\n'
        "Use the real document date, NOT the OECD catalog Added-on date.\n"
        "If only the year is known, return YYYY-01-01 with confidence low.\n"
        "If unknown, date=\"\" and confidence=\"none\".\n\n"
        f"Title: {title}\nCountry/org: {country}\nOECD startYear: {sy}\n"
        f"URLs:\n" + "\n".join(urls)
    )
    try:
        out = llm_json(
            model,
            [
                {
                    "role": "system",
                    "content": "You are a careful research librarian. Prefer primary sources. Never invent dates.",
                },
                {"role": "user", "content": user},
            ],
            timeout=60,
        )
    except Exception:
        return None
    d = normalize_date(str(out.get("date") or ""))
    conf = str(out.get("confidence") or "none").lower()
    if conf not in ("high", "medium", "low", "none"):
        conf = "none"
    if not d or conf == "none":
        return None
    try:
        if sy is not None and abs(int(d[:4]) - int(sy)) > 2:
            return None
    except (TypeError, ValueError):
        pass
    return {
        "date": d,
        "method": "llm",
        "evidence_url": urls[0] if urls else "",
        "confidence": conf if conf in ("high", "medium", "low") else "low",
        "rationale": str(out.get("rationale") or "")[:200],
    }


def resolve_one(it: dict, *, use_search: bool, use_llm: bool = False, model: str = "") -> dict:
    urls = expand_urls(
        list(it.get("source_urls") or []) + list(it.get("source_files") or [])
    )
    urls = sorted(urls, key=url_score, reverse=True)
    hit = resolve_from_urls(urls, it.get("start_year"))
    if hit:
        return hit
    if use_search:
        hit = resolve_from_search(
            it.get("title") or "",
            it.get("start_year"),
            it.get("country") or "",
        )
        if hit:
            return hit
    if use_llm:
        hit = resolve_from_llm(it, model=model or "openai/gpt-5.6-luna")
        if hit:
            return hit
    return {
        "date": "",
        "method": "none",
        "confidence": "none",
        "evidence_url": "",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--sleep", type=float, default=0.05)
    ap.add_argument("--workers", type=int, default=8, help="병렬 워커 수")
    ap.add_argument("--search", action="store_true", help="원문 실패 시 DDG 검색")
    ap.add_argument("--no-search", action="store_true")
    ap.add_argument("--llm", action="store_true", help="원문/검색 실패 시 OpenRouter로 추정")
    ap.add_argument("--model", default="openai/gpt-5.6-luna")
    ap.add_argument("--apply", action="store_true", help="high 신뢰 결과를 items.json date에 반영")
    ap.add_argument("--force", action="store_true", help="캐시 있어도 재시도")
    args = ap.parse_args()
    use_search = args.search or not args.no_search
    workers = max(1, int(args.workers))

    blob = load_json(ITEMS)
    items = blob.get("items") or []
    cache = load_json(CACHE) if CACHE.exists() else {}
    if not isinstance(cache, dict):
        cache = {}

    queue = candidate_items(items, bulk_first=True)
    # skip already resolved unless force
    todo = []
    for it in queue:
        iid = it.get("id") or ""
        if not iid:
            continue
        prev = cache.get(iid)
        if not args.force and prev and prev.get("date") and prev.get("confidence") in ("high", "medium"):
            continue
        # also skip recent hard-none? no — retry with better methods via --force
        if not args.force and prev and prev.get("confidence") == "none" and prev.get("method") == "none":
            # allow retry when upgrading to llm
            if not args.llm:
                continue
        todo.append(it)
        if len(todo) >= args.limit:
            break

    print(
        f"pilot queue={len(todo)} workers={workers} search={use_search} llm={args.llm} "
        f"cache={len(cache)} pool={len(queue)}",
        flush=True,
    )

    stats = Counter()
    lock = threading.Lock()
    done = 0
    total = len(todo)
    t0 = time.time()

    def _work(it: dict) -> tuple[dict, dict]:
        if args.sleep > 0:
            time.sleep(args.sleep)
        try:
            hit = resolve_one(
                it,
                use_search=use_search,
                use_llm=args.llm,
                model=args.model,
            )
        except Exception as e:
            hit = {"date": "", "method": "error", "confidence": "none", "error": str(e)[:120]}
        hit.update(
            {
                "id": it["id"],
                "title": it.get("title") or "",
                "start_year": it.get("start_year"),
                "added_on": it.get("added_on") or it.get("date") or "",
                "resolved": date.today().isoformat(),
            }
        )
        return it, hit

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_work, it) for it in todo]
        for fut in as_completed(futs):
            it, hit = fut.result()
            iid = it["id"]
            with lock:
                cache[iid] = hit
                stats[hit.get("confidence") or "none"] += 1
                stats[f"method:{(hit.get('method') or 'none')}"] += 1
                done += 1
                if done % 20 == 0:
                    save_json(CACHE, cache)
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed else 0
            eta = (total - done) / rate / 60 if rate else 0
            title = (it.get("title") or "")[:50]
            if hit.get("date"):
                print(
                    f"[{done}/{total}] {iid} → {hit['date']} "
                    f"[{hit.get('confidence')}/{hit.get('method')}] {title} "
                    f"| {rate:.2f}/s ETA {eta:.0f}m",
                    flush=True,
                )
            else:
                print(
                    f"[{done}/{total}] {iid} → (none) {title} | {rate:.2f}/s ETA {eta:.0f}m",
                    flush=True,
                )

    save_json(CACHE, cache)
    print("\n=== pilot summary ===")
    for k, v in stats.most_common():
        print(f"  {k}: {v}")
    resolved_n = sum(
        1
        for it in todo
        if (cache.get(it["id"]) or {}).get("date")
        and (cache.get(it["id"]) or {}).get("confidence") in ("high", "medium")
    )
    print(f"resolved {resolved_n}/{len(todo)} ({100 * resolved_n / max(1, len(todo)):.1f}%)")
    print(f"cache → {CACHE}")

    if args.apply:
        usable = {
            k: v
            for k, v in cache.items()
            if v.get("date") and v.get("confidence") in ("high", "medium")
        }
        n = 0
        for it in items:
            iid = it.get("id") or ""
            if iid in usable:
                it["date"] = usable[iid]["date"]
                it["date_source"] = usable[iid].get("method") or "resolved"
                it["date_resolved"] = usable[iid]["date"]
                n += 1
        blob["items"] = items
        blob["updated"] = date.today().isoformat()
        save_json(ITEMS, blob)
        print(f"applied high/medium dates to {n} items")


if __name__ == "__main__":
    main()
