#!/usr/bin/env python3
"""Global AI Regulation Tracker 항목 중 제도 원문을 가리키는 것만 라이브러리 컬렉션으로 받는다.

입력은 다이제스트가 내보낸 knowledge/ai_safety_corpus.jsonl 하나(AI_SAFETY_DIGEST_CORPUS).
다이제스트 코드·내부 CSV는 읽지 않는다. 다이제스트에는 그 보도가 그대로 남는다.

1. 판정 (LLM): 항목이 특정 제도(법·법안·규칙·지침·전략·선언·표준 등)를 다루는지, 링크가 어떤 종류인지.
   link_type = instrument(제도 원문·제도 자체의 공식 페이지) · announcement(발급 기관의 공식 발표·보도자료)
   · media(언론·블로그) · other.
2. 매칭 (LLM): 라이브러리에 이미 같은 제도가 있으면 그 문서에 이력으로 붙인다(same_as).
   개정안은 원법과 다른 제도로 본다.
   - 붙일 때는 instrument·announcement 둘 다 받는다(이력 한 줄). announcement 링크는 대표 링크로 쓰지 않는다.
   - 새 문서는 instrument 링크일 때만 만든다. 보도자료만 있으면 다이제스트에만 남는다
     (라이브러리 큐레이션이 보도자료를 news_press로 범위 밖에 두는 기준과 같다).
3. collections/regtracker/items.json 에 받은 항목만 쓴다. 판정·매칭 결과는
   cache/regtracker_judge.json 에 남겨 같은 링크를 다시 묻지 않는다.

사용:
  python3 scripts/ingest_regtracker.py                 # 새 항목만 (기본 상한 60)
  python3 scripts/ingest_regtracker.py --limit 0       # 상한 없음 (첫 적재)
  python3 scripts/ingest_regtracker.py --dry-run --limit 5
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_ko import llm_json  # noqa: E402
from library_common import (  # noqa: E402
    ROOT,
    normalize_url,
    rebuild_collection_stats,
    write_json,
)
from parse_meta import DOC_KINDS  # noqa: E402

COL_KEY = "regtracker"
COL_NAME = "Global AI Regulation Tracker"
SOURCE_NAME = "GlobalAIRegTracker"  # 다이제스트 코퍼스의 source 값
DIGEST_CORPUS = Path(
    os.environ.get("AI_SAFETY_DIGEST_CORPUS")
    or Path.home() / "Code" / "ai-safety-pipeline" / "knowledge" / "ai_safety_corpus.jsonl"
)
DIGEST_SCHEMA = 1
COL_DIR = ROOT / "collections" / COL_KEY
JUDGE_CACHE = ROOT / "cache" / "regtracker_judge.json"
DOCS_PATH = ROOT / "documents.json"
DEFAULT_MODEL = os.environ.get("LIBRARY_TRACKER_MODEL") or "anthropic/claude-sonnet-5.5"
TODAY = date.today().isoformat()

KINDS = [k for k in DOC_KINDS if k != "뉴스·보도"]
STAGES = {
    "draft": "초안",
    "consultation": "의견수렴",
    "introduced": "발의",
    "passed": "통과",
    "enacted": "공포·시행",
    "adopted": "채택",
    "published": "발표",
    "amended": "개정",
    "other": "기록",
}
LINK_TYPES = ("instrument", "announcement", "media", "other")
_REGION_RE = re.compile(r"^\s*\[[^\]]+\]\s*")

JUDGE_SYSTEM = f"""당신은 AI 안전·거버넌스 라이브러리의 수집 담당이다.
규제 동향 트래커의 한 항목(헤드라인·링크·한국어 요약)을 보고, 라이브러리에 원문으로 둘 제도인지 판정한다.

라이브러리는 제도 자체(법·법안·행정규칙·조약·선언·가이드라인·전략·정책보고서·표준·기구 설립 문서)를
원문 링크로 모은다. 뉴스·연설·회의 소식·인터뷰는 받지 않는다.

판정 기준
- is_instrument: 항목이 특정한 하나의 제도를 다루면 true. 정책 방향 언급·촉구·행사·인사 소식이면 false.
- link_type: 링크 페이지의 종류.
  instrument = 제도 원문(법안 본문·관보·PDF)이나 제도 자체의 공식 페이지(의안 정보 페이지, 지침·전략 문서 페이지)
  announcement = 발급 기관·의원실·부처가 그 제도를 알리는 공식 보도자료·발표문 (본문은 제도 소개)
  media = 언론사·통신사·블로그·UN News 같은 보도
  other = 연설문·회의 결과·인사 소식 등 그 밖의 페이지
- instrument_name: 제도의 공식 명칭(영문 또는 원어). 헤드라인을 옮기지 말고 제도 이름만.
  확실하지 않으면 헤드라인에서 제도 이름 부분만 뽑는다.
- name_ko: 한국어 약칭. 관할(국가·주)과 고유번호(법안 번호)는 유지.
- doc_kind: {" | ".join(KINDS)}
- stage: {" | ".join(STAGES)} (이 항목이 기록하는 사건)
- country: 관할 국가·지역의 영문 이름(EU, United States 등). 국제기구면 기구 이름.
- country_ko: 관할의 한국어 이름(튀르키예, 미국, 유럽연합, 대한민국 등). 미국 주는 "미국".
- 원문에 없는 사실을 만들지 않는다. JSON만 출력한다.

출력 JSON:
{{"is_instrument": true, "link_type": "instrument", "reason": "한 문장",
  "instrument_name": "", "name_ko": "", "doc_kind": "", "stage": "", "country": "", "country_ko": ""}}
"""

MATCH_SYSTEM = """당신은 AI 안전·거버넌스 라이브러리의 편집자다.
새 항목이 기존 문서 후보 중 하나와 같은 제도인지 판정한다.

- 같은 제도 = 같은 법·법안·전략·지침 그 자체(단계만 다른 기록: 초안→채택, 발의→통과→시행 포함).
- 개정안·시행령·후속 지침은 원법과 다른 제도다. 후보가 바로 그 개정안일 때만 같다.
- 관할이 다르면 다른 제도다. 이름이 비슷한 다른 연도·다른 판도 다른 제도다.
- 확신이 없으면 match_id를 비운다. JSON만 출력한다.

출력 JSON: {"match_id": "doc-… 또는 빈 문자열", "confidence": "high|medium|low", "reason": "한 문장"}
"""


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def check_digest_schema() -> None:
    manifest = load_json(DIGEST_CORPUS.parent / "manifest.json", {})
    ver = manifest.get("schema_version")
    if ver is not None and ver != DIGEST_SCHEMA:
        raise SystemExit(f"다이제스트 코퍼스 스키마 {ver} — 이 스크립트는 {DIGEST_SCHEMA}만 읽는다")


def tracker_rows() -> list[dict]:
    check_digest_schema()
    rows: dict[str, dict] = {}
    with DIGEST_CORPUS.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("source") != SOURCE_NAME:
                continue
            url = (r.get("url") or "").strip()
            key = normalize_url(url)
            if key and key not in rows:
                rows[key] = r
    return sorted(rows.values(), key=lambda r: r.get("article_date") or "", reverse=True)


# ── 기존 문서 후보 검색 (어휘 겹침) ─────────────────────────────

_STOP = {
    "the", "of", "and", "on", "for", "to", "in", "a", "an", "act", "bill", "law", "ai",
    "artificial", "intelligence", "national", "policy", "strategy", "framework", "guidelines",
    "guidance", "regulation", "new", "draft", "amendment", "법", "법안", "인공지능", "ai",
}


def _tokens(text: str) -> set[str]:
    text = (text or "").lower()
    words = {w for w in re.findall(r"[a-z0-9]{3,}", text) if w not in _STOP}
    ko = re.sub(r"[^가-힣]", "", text)
    bigrams = {ko[i : i + 2] for i in range(len(ko) - 1)}
    return words | {b for b in bigrams if b not in _STOP}


def load_doc_index() -> list[dict]:
    blob = load_json(DOCS_PATH, {})
    docs = blob.get("documents") if isinstance(blob, dict) else blob
    out = []
    for d in docs or []:
        names = " ".join(str(d.get(k) or "") for k in ("short_name", "original_name", "full_name", "title"))
        urls = {normalize_url(d.get("canonical_url") or "")}
        urls |= {normalize_url(h.get("url") or "") for h in d.get("history") or []}
        out.append({"doc": d, "tokens": _tokens(names), "urls": {u for u in urls if u}})
    return out


def _days_apart(a: str, b: str) -> int:
    try:
        return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)
    except ValueError:
        return 10_000


_KO_ALIASES = {"한국": "대한민국", "south korea": "대한민국", "us": "미국", "eu": "유럽연합"}


def _same_country(judge: dict, doc: dict) -> bool:
    jk = (judge.get("country_ko") or "").strip()
    jk = _KO_ALIASES.get(jk.lower(), jk)
    dk = (doc.get("country_ko") or "").strip()
    dk = _KO_ALIASES.get(dk.lower(), dk)
    if jk and dk and (jk == dk or jk in dk or dk in jk):
        return True
    je = (judge.get("country") or "").lower()
    de = (doc.get("country") or "").lower()
    return bool(je and de and (je == de or je[:5] == de[:5]))


def candidates_for(judge: dict, url: str, event_date: str, index: list[dict]) -> list[dict]:
    """같은 원문 링크가 있으면 그것 하나. 아니면 이름이 겹치는 문서 상위 8건 +
    같은 관할에서 이름 겹침·날짜 근접 순 상위 20건."""
    nu = normalize_url(url)
    self_id = item_id_for(url)
    q = _tokens(" ".join([judge.get("instrument_name") or "", judge.get("name_ko") or ""]))
    lexical, local = [], []
    for e in index:
        d = e["doc"]
        if self_id in (d.get("member_ids") or []):
            continue  # 자기 자신(이전 실행에서 만든 카드)
        if nu and nu in e["urls"]:
            return [d]
        inter = len(q & e["tokens"]) if q and e["tokens"] else 0
        score = inter / (len(q) ** 0.5 * len(e["tokens"]) ** 0.5) if inter else 0.0
        if score:
            lexical.append((score, d))
        if _same_country(judge, d):
            local.append((-score, _days_apart(event_date, d.get("published") or ""), d))
    lexical.sort(key=lambda x: x[0], reverse=True)
    local.sort(key=lambda x: (x[0], x[1]))
    out, seen = [], set()
    for d in [d for _, d in lexical[:8]] + [d for *_, d in local[:20]]:
        if d["id"] not in seen:
            seen.add(d["id"])
            out.append(d)
    return out


# ── LLM ────────────────────────────────────────────────────────

def _llm(model: str, system: str, user: str, retries: int = 3) -> dict:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            out = llm_json(model, [{"role": "system", "content": system}, {"role": "user", "content": user}], timeout=120)
            if isinstance(out, dict):
                return out
            raise ValueError("not a JSON object")
        except (urllib.error.URLError, ValueError, KeyError, TimeoutError) as e:
            last = e
            time.sleep(1.5 * (2**attempt))
    raise RuntimeError(f"LLM 실패: {last}")


def judge_one(row: dict, model: str) -> dict:
    user = (
        f"헤드라인: {row.get('title') or ''}\n"
        f"링크: {row.get('url') or ''}\n"
        f"날짜: {row.get('article_date') or ''}\n"
        f"한국어 요약:\n{(row.get('summary') or '')[:2500]}"
    )
    out = _llm(model, JUDGE_SYSTEM, user)
    link_type = out.get("link_type") if out.get("link_type") in LINK_TYPES else "other"
    is_instr = bool(out.get("is_instrument"))
    res = {
        # 붙일 수 있는 항목(매칭 대상). 새 문서는 link_type == instrument 일 때만.
        "accept": is_instr and link_type in ("instrument", "announcement"),
        "is_instrument": is_instr,
        "link_type": link_type,
        "reason": str(out.get("reason") or "")[:300],
        "instrument_name": str(out.get("instrument_name") or "").strip()[:300],
        "name_ko": str(out.get("name_ko") or "").strip()[:200],
        "doc_kind": out.get("doc_kind") if out.get("doc_kind") in KINDS else "기타",
        "stage": out.get("stage") if out.get("stage") in STAGES else "other",
        "country": str(out.get("country") or "").strip()[:80],
        "country_ko": str(out.get("country_ko") or "").strip()[:40],
    }
    return res


def match_one(row: dict, judge: dict, cands: list[dict], model: str) -> dict:
    if not cands:
        return {"match_id": "", "confidence": "", "reason": "후보 없음"}
    lines = []
    for d in cands:
        urls = [d.get("canonical_url") or ""] + [h.get("url") or "" for h in (d.get("history") or [])[:3]]
        lines.append(
            f"- id={d.get('id')} | {d.get('short_name') or ''} | 원제: {d.get('original_name') or ''} | "
            f"{d.get('country_ko') or d.get('country') or ''} | {d.get('doc_kind') or ''} | "
            f"{d.get('status_ko') or ''} | 발표 {d.get('published') or ''} | {' '.join(u for u in urls if u)[:300]}"
        )
    user = (
        f"[새 항목]\n헤드라인: {row.get('title') or ''}\n링크: {row.get('url') or ''}\n"
        f"제도 이름: {judge.get('instrument_name')} / {judge.get('name_ko')}\n"
        f"관할: {judge.get('country')} · 종류: {judge.get('doc_kind')} · 단계: {judge.get('stage')}\n"
        f"요약: {(row.get('summary') or '')[:1200]}\n\n[기존 문서 후보]\n" + "\n".join(lines)
    )
    out = _llm(model, MATCH_SYSTEM, user)
    mid = str(out.get("match_id") or "").strip()
    valid = {d.get("id") for d in cands}
    conf = out.get("confidence") if out.get("confidence") in ("high", "medium", "low") else "low"
    if mid not in valid or conf == "low":
        mid = ""
    member = ""
    if mid:
        target = next(d for d in cands if d.get("id") == mid)
        member = next((x for x in target.get("member_ids") or [] if not x.startswith(f"{COL_KEY}-")),
                      (target.get("member_ids") or [""])[0])
    return {"match_id": mid, "match_member": member, "confidence": conf,
            "reason": str(out.get("reason") or "")[:300]}


def included(entry: dict) -> bool:
    """컬렉션에 넣을지: 기존 문서에 붙거나, 새 문서가 될 만한 원문 링크일 때."""
    j = entry.get("judge") or {}
    m = entry.get("match") or {}
    if not j.get("accept"):
        return False
    return bool(m.get("match_member")) or j.get("link_type") == "instrument"


# ── 컬렉션 ─────────────────────────────────────────────────────

def item_id_for(url: str) -> str:
    return f"{COL_KEY}-" + hashlib.sha1(normalize_url(url).encode("utf-8")).hexdigest()[:12]


def build_item(row: dict, entry: dict) -> dict:
    j = entry["judge"]
    m = entry.get("match") or {}
    url = row.get("url") or ""
    headline = _REGION_RE.sub("", row.get("title") or "").strip()
    region = (_REGION_RE.match(row.get("title") or "") or [""])[0].strip(" []")
    item = {
        "id": item_id_for(url),
        "collection": COL_KEY,
        "collection_name": COL_NAME,
        "title": j.get("name_ko") or j.get("instrument_name") or headline,
        "original_name": j.get("instrument_name") or "",
        "headline": headline,
        "region": region,
        "country": j.get("country") or "",
        "org": "",
        "category": STAGES.get(j.get("stage") or "other", "기록"),
        "stage": j.get("stage") or "other",
        "doc_kind": j.get("doc_kind") or "기타",
        "date": (row.get("article_date") or "")[:10],
        "page_url": url,
        "source_urls": [url],
        "body": (row.get("summary") or "").strip(),
        "link_type": j.get("link_type") or "",
    }
    if item["doc_kind"] in ("법", "법안"):
        stage = item["stage"]
        item["status"] = "Enacted" if stage == "enacted" else (
            "Proposed" if stage in ("draft", "consultation", "introduced", "passed") else "")
    if m.get("match_member"):
        item["same_as"] = m["match_member"]
        item["same_as_doc"] = m.get("match_id") or ""
    return item


def main() -> None:
    ap = argparse.ArgumentParser(description="Global AI Regulation Tracker → 라이브러리 컬렉션")
    ap.add_argument("--limit", type=int, default=60, help="이번에 새로 판정할 최대 건수 (0=무제한)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true", help="판정만 출력하고 파일은 쓰지 않는다")
    ap.add_argument("--rematch", action="store_true", help="받은 항목의 매칭만 다시 한다")
    args = ap.parse_args()

    if not DIGEST_CORPUS.is_file():
        print(f"다이제스트 코퍼스 없음({DIGEST_CORPUS}) — 건너뜀")
        return
    rows = tracker_rows()
    cache: dict = load_json(JUDGE_CACHE, {})
    todo = [r for r in rows if normalize_url(r["url"]) not in cache]
    if args.rematch:
        todo = [r for r in rows if (cache.get(normalize_url(r["url"])) or {}).get("judge", {}).get("accept")]
    if args.limit > 0:
        todo = todo[: args.limit]
    print(f"트래커 {len(rows)}건 · 판정 캐시 {len(cache)}건 · 이번 대상 {len(todo)}건 · model={args.model}")

    index = load_doc_index()

    def work(row: dict) -> tuple[dict, dict | None, str]:
        key = normalize_url(row["url"])
        try:
            prev = cache.get(key) or {}
            j = prev.get("judge") if args.rematch and prev.get("judge") else judge_one(row, args.model)
            m = {}
            if j["accept"]:
                cands = candidates_for(j, row["url"], row.get("article_date") or "", index)
                m = match_one(row, j, cands, args.model)
            return row, {"judge": j, "match": m, "model": args.model, "judged": TODAY}, ""
        except RuntimeError as e:
            return row, None, str(e)

    ok = fail = acc = matched = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futs = [pool.submit(work, r) for r in todo]
        for fut in as_completed(futs):
            row, entry, err = fut.result()
            if entry is None:
                fail += 1
                print(f"  FAIL {row['url'][:80]} | {err}", flush=True)
                continue
            ok += 1
            j, m = entry["judge"], entry["match"]
            inc = included(entry)
            acc += inc
            matched += bool(m.get("match_member"))
            mark = ("붙임" if m.get("match_member") else "새 문서") if inc else "제외"
            link = f" → {m['match_id']}" if m.get("match_id") else ""
            print(f"  [{mark}] {(row.get('title') or '')[:70]} | {j['link_type']} | {j['reason'][:50]}{link}", flush=True)
            if not args.dry_run:
                cache[normalize_url(row["url"])] = entry
    print(f"판정 {ok}건 (받음 {acc} · 기존 문서에 붙임 {matched}) · 실패 {fail}건")
    if args.dry_run:
        return
    write_json(JUDGE_CACHE, cache)

    items = []
    for r in rows:
        entry = cache.get(normalize_url(r["url"])) or {}
        if included(entry):
            items.append(build_item(r, entry))
    data = {
        "collection": COL_KEY,
        "name": COL_NAME,
        "source": {
            "list_url": "https://www.techieray.com/GlobalAIRegulationTracker",
            "via": "AI Safety Digest knowledge/ai_safety_corpus.jsonl",
            "fetched": TODAY,
        },
        "items": items,
    }
    rebuild_collection_stats(data)
    write_json(COL_DIR / "items.json", data)
    write_json(
        COL_DIR / "source.json",
        {
            "list_url": "https://www.techieray.com/GlobalAIRegulationTracker",
            "via": "AI Safety Digest가 내보낸 knowledge/ai_safety_corpus.jsonl (source=GlobalAIRegTracker)",
            "fetched": TODAY,
            "note": "트래커 항목 중 제도 원문(1차 출처)을 가리키는 것만. 판정·매칭은 cache/regtracker_judge.json.",
        },
    )
    print(f"→ {COL_DIR / 'items.json'} ({len(items)}건)")


if __name__ == "__main__":
    main()
