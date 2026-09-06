#!/usr/bin/env python3
"""OpenRouter LLM 큐레이션: 범위·문서종류·토픽·한글·날짜 신뢰도를 한 번에 판정.

뉴스·보도는 doc_kind enum에 두지 않고 in_scope=false + reject_reason 으로 제외.
토픽은 키워드 부분일치 대신 의미 판정(정당 ≠ 정당성).

사용:
  python3 scripts/curate_llm.py --limit 20
  python3 scripts/curate_llm.py --prefer-uncertain --limit 50
  python3 scripts/curate_llm.py --workers 8 --limit 4000
  python3 scripts/curate_llm.py --validate-only
  python3 scripts/build_site.py

캐시: cache/llm_curate.json
날짜 URL/검색 복원은 resolve_oecd_dates.py 와 병행(별도 단계).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_ko import ensure_openrouter_key, llm_json  # noqa: E402
from library_common import write_json  # noqa: E402
from parse_meta import DOC_KINDS  # noqa: E402
from topics import TOPIC_COLORS, TOPIC_ORDER, topic_icon, topic_label  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "cache" / "llm_curate.json"
TODAY = date.today().isoformat()
DEFAULT_MODEL = os.environ.get("OPENROUTER_MODEL") or "openai/gpt-5.6-luna"

CURATED_KINDS = [k for k in DOC_KINDS if k != "뉴스·보도"]
TOPIC_IDS = list(TOPIC_ORDER)
CONF_OK = {"high", "medium"}
REJECT_REASONS = {
    "news_press",
    "weak_ai_link",
    "industry_promo",
    "duplicate",
    "out_of_domain",
    "other",
}

SYSTEM = f"""당신은 AI 안전·거버넌스 라이브러리의 수석 큐레이터입니다.
입력 메타만으로 문서를 분류·검증하고, UI용 한국어 표기를 작성합니다.

절대 규칙
1) 원문에 없는 사실·날짜·기관·조항·법안번호를 만들지 마세요.
2) 키워드 부분일치로 분류하지 마세요. 의미 단위로 판단하세요.
   - "정당성/合法性/legitimacy/justify" ≠ 정당(political party) → politics 금지
   - "party"가 third-party·contracting party이면 politics 금지
   - AI가 부수 언급이면 핵심 주제가 AI 안전·거버넌스인지 구분
3) 불확실하면 confidence를 낮추고 topics는 비우세요.
4) JSON만 출력하세요.

허용 enum
- doc_kind: {" | ".join(CURATED_KINDS)}
  (뉴스·보도·블로그성 기사는 doc_kind를 고르지 말고 in_scope=false,
   reject_reason="news_press")
- topics.id (최대 3개): {" | ".join(TOPIC_IDS)}
- in_scope: AI 안전·리스크·정렬·거버넌스·규제·윤리·평가·권리와 직접 관련된
  정책/규범/기구 문서면 true. 순수 산업진흥·투자·인재·시장동향만이면 false.
- reject_reason (in_scope=false일 때): {" | ".join(sorted(REJECT_REASONS))}
- published_confidence: high | medium | low | none
- confidence: high | medium | low

문서종류 (법 vs 법안)
- rule_status_ko·본문을 보세요. 제정·시행·공포·enacted·signed → 법.
  계류·제출·draft·introduced·proposed → 법안.
- 법률자문·해석지침·advisory는 법/법안이 아니라 가이드라인·원칙 또는 행정규칙.
- 유엔 결의·정상 합의·정치선언은 보통 선언·성명 (조약·협약이 아님).

토픽
- 각 topic에 evidence를 원문에서 고른 짧은 구절로 반드시 채우세요. 근거 없으면 그 토픽은 빼세요.
- 보통 1~2개. 명확히 복합 주제일 때만 3개.
- politics: 선거제도·정당·선거운동·로비·의회 정치과정이 규율 대상의 핵심일 때.
  선거 딥페이크/허위조작 규제는 deepfake_disinfo(+law)를 기본으로 두고,
  선거·정치과정이 규율 대상이면 politics를 함께 둡니다.
  아동 성착취물·일반 딥페이크·소비자 기만만이면 politics 금지.
- law: 구속력 있는 법령·법안이 핵심. 가이드라인·자문은 guideline 또는 norms.
- cybersecurity: AI/모델/선거 인프라 보안이 핵심일 때. 일반 IT만이면 신중히.

날짜 (published)
- catalog Added-on / OECD 등록일 / 크롤 시각은 쓰지 마세요 → published="" ,
  published_confidence="none", published_note에 사유.
- 연도만 알면 published="" 또는 YYYY-01-01 + confidence=low. 일자·월을 추측하지 마세요.
- 원문에 명시된 채택·공포·발표일만 high/medium.

한글 표기
- short_name: 한국어 약칭. 관할(캘리포니아·EU 등)·고유번호(AB 410, SB 9)는 유지.
- summary: 사실만 3~6문장. 마케팅·추측 금지.
"""


def load_cache() -> dict:
    if CACHE_PATH.exists():
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_json(CACHE_PATH, cache)


def src_hash(doc: dict) -> str:
    blob = "\n".join(
        [
            str(doc.get("short_name") or doc.get("title") or ""),
            str(doc.get("original_name") or ""),
            str(doc.get("summary") or "")[:2000],
            str(doc.get("doc_kind") or ""),
            str(doc.get("published") or ""),
            str(doc.get("canonical_url") or doc.get("url") or ""),
        ]
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def expand_urls(raw_urls) -> list[str]:
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
            if u.startswith("http") and u not in seen:
                seen.add(u)
                out.append(u)
    return out


def normalize_entry(raw: dict) -> dict:
    in_scope = bool(raw.get("in_scope"))
    kind = str(raw.get("doc_kind") or "").strip()
    if kind == "뉴스·보도":
        in_scope = False
        kind = ""
        raw.setdefault("reject_reason", "news_press")
    if kind not in CURATED_KINDS:
        kind = ""

    topics = []
    for t in raw.get("topics") or []:
        if isinstance(t, str):
            tid, ev = t, ""
        else:
            tid = str((t or {}).get("id") or "").strip()
            ev = str((t or {}).get("evidence") or (t or {}).get("evidence") or "")[:160]
        if tid in TOPIC_IDS and ev.strip():
            topics.append({"id": tid, "evidence": ev.strip()})
    topics = topics[:3]

    conf = str(raw.get("confidence") or "low").lower()
    if conf not in ("high", "medium", "low"):
        conf = "low"
    pconf = str(raw.get("published_confidence") or "none").lower()
    if pconf not in ("high", "medium", "low", "none"):
        pconf = "none"
    published = str(raw.get("published") or "").strip()[:10]
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", published or ""):
        published = ""
        if pconf != "none":
            pconf = "none"
    note = str(raw.get("published_note") or "").lower()
    # catalog/등록일·순수 추정은 버림
    if published and (
        "catalog" in note
        or "added-on" in note
        or "added on" in note
        or "등록" in note
        or "추측" in note
        or "추정" in note
    ):
        published = ""
        pconf = "none"
    # 연초 플레이스홀더인데 high/medium이면 low로 강등
    if published.endswith("-01-01") and pconf in ("high", "medium"):
        pconf = "low"

    reject = str(raw.get("reject_reason") or "").strip()
    # 프롬프트에 쓴 별칭도 수용
    alias = {
        "news_press": "news_press",
        "weak_ai_link": "weak_ai_link",
        "industry_promo": "industry_promo",
        "out_of_domain": "out_of_domain",
    }
    reject = alias.get(reject, reject)
    if not in_scope:
        if reject not in REJECT_REASONS:
            reject = "other"
    else:
        reject = ""

    return {
        "in_scope": in_scope,
        "in_scope_reason": str(raw.get("in_scope_reason") or "")[:240],
        "reject_reason": reject,
        "doc_kind": kind,
        "topics": topics,
        "published": published,
        "published_confidence": pconf,
        "published_note": str(raw.get("published_note") or "")[:240],
        "short_name": str(raw.get("short_name") or "").strip()[:200],
        "summary": str(raw.get("summary") or "").strip()[:4000],
        "corrections": [str(c) for c in (raw.get("corrections") or []) if c][:12],
        "confidence": conf,
        "flags": [str(f) for f in (raw.get("flags") or []) if f][:12],
    }


def validate_entry(entry: dict) -> list[str]:
    errs: list[str] = []
    if not isinstance(entry, dict):
        return ["not a dict"]
    if entry.get("doc_kind") and entry["doc_kind"] not in CURATED_KINDS:
        errs.append(f"bad doc_kind {entry.get('doc_kind')}")
    if entry.get("doc_kind") == "뉴스·보도":
        errs.append("news must not be doc_kind")
    for t in entry.get("topics") or []:
        tid = t.get("id") if isinstance(t, dict) else t
        if tid not in TOPIC_IDS:
            errs.append(f"bad topic {tid}")
    if entry.get("confidence") not in ("high", "medium", "low"):
        errs.append("bad confidence")
    if entry.get("in_scope") is False and not entry.get("reject_reason"):
        errs.append("missing reject_reason")
    return errs


def curate_one(doc: dict, *, model: str) -> dict:
    urls = expand_urls(
        [doc.get("canonical_url") or ""]
        + list(doc.get("source_urls") or [])
        + list(doc.get("urls") or [])
    )[:6]
    rule_topics = []
    for t in doc.get("topics") or []:
        if isinstance(t, dict) and t.get("id"):
            rule_topics.append(t["id"])
        elif isinstance(t, str):
            rule_topics.append(t)

    user = f"""다음 문서를 큐레이션하세요.

[식별]
id: {doc.get("id")}
urls: {urls or ["(없음)"]}

[규칙 초안 — 참고만, 틀릴 수 있음]
rule_doc_kind: {doc.get("doc_kind") or ""}
rule_status_ko: {doc.get("status_ko") or ""}
rule_in_scope: {doc.get("in_scope")}
rule_safety_score: {doc.get("safety_score")}
rule_topics: {rule_topics}
rule_published: {doc.get("published") or ""}
added_on: {doc.get("added_on") or ""}
start_year: {doc.get("start_year") or ""}

[원문 메타]
country/org: {doc.get("country_ko") or doc.get("country") or ""} / {doc.get("org") or ""}
title: {doc.get("short_name") or doc.get("title") or ""}
original_title: {doc.get("original_name") or ""}
category_raw: {doc.get("doc_kind_raw") or ""}
body/summary:
{(doc.get("summary") or doc.get("snippet") or "")[:3500]}

출력 JSON:
{{
  "in_scope": true,
  "in_scope_reason": "한 문장",
  "reject_reason": "",
  "doc_kind": "<enum>",
  "topics": [{{"id":"<enum>", "evidence":"원문 근거 구절(필수)"}}],
  "published": "YYYY-MM-DD or empty",
  "published_confidence": "high|medium|low|none",
  "published_note": "날짜 출처. catalog Added-on/추측이면 비우고 confidence none",
  "short_name": "한국어 약칭",
  "summary": "한국어 핵심 3~6문장 또는 번호 목록",
  "corrections": ["규칙 초안 대비 고친 점"],
  "confidence": "high|medium|low",
  "flags": []
}}
reject_reason 후보: news_press | weak_ai_link | industry_promo | duplicate | out_of_domain | other
뉴스면 in_scope=false, reject_reason=news_press, doc_kind="" .
added_on·start_year만 있고 원문 발표일이 없으면 published를 비우세요.
topics.evidence가 비면 그 토픽은 넣지 마세요.
"""
    raw = llm_json(
        model,
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
        timeout=90,
    )
    return normalize_entry(raw if isinstance(raw, dict) else {})


def apply_cache_to_docs(docs: list[dict], cache: dict | None = None) -> dict:
    """고·중신뢰 큐레이션을 문서에 반영."""
    cache = cache if cache is not None else load_cache()
    stats: Counter = Counter()
    for d in docs:
        did = d.get("id") or ""
        entry = cache.get(did)
        if not entry:
            continue
        body = entry.get("result") or entry
        if not isinstance(body, dict):
            continue
        conf = body.get("confidence") or "low"
        if conf not in CONF_OK:
            stats["skip_low_conf"] += 1
            continue

        stats["applied"] += 1
        d["llm_curated"] = True
        d["llm_confidence"] = conf
        d["llm_flags"] = list(body.get("flags") or [])

        if "in_scope" in body:
            d["in_scope"] = bool(body["in_scope"])
            d["in_scope_reason"] = body.get("in_scope_reason") or ""
            if body.get("reject_reason"):
                d["reject_reason"] = body["reject_reason"]

        if body.get("doc_kind") in CURATED_KINDS:
            d["doc_kind"] = body["doc_kind"]

        topic_objs = []
        for t in body.get("topics") or []:
            tid = t.get("id") if isinstance(t, dict) else t
            if tid not in TOPIC_IDS:
                continue
            topic_objs.append(
                {
                    "id": tid,
                    "label": topic_label(tid),
                    "icon": topic_icon(tid),
                    "color": TOPIC_COLORS.get(tid, "#534f4a"),
                    "evidence": (t.get("evidence") if isinstance(t, dict) else "") or "",
                    "source": "llm",
                }
            )
        if topic_objs or body.get("topics") == []:
            d["topics"] = topic_objs
            d["topics_source"] = "llm"
            stats["topics"] += 1

        if body.get("short_name"):
            if not (d.get("original_name") or "").strip():
                prev = d.get("short_name") or d.get("title") or ""
                if prev:
                    d["original_name"] = prev
            d["short_name"] = body["short_name"]
            d["title"] = body["short_name"]
            stats["short_name"] += 1
        if body.get("summary"):
            d["summary"] = body["summary"]
            d["snippet"] = body["summary"][:500]
            stats["summary"] += 1

        pconf = body.get("published_confidence") or "none"
        if body.get("published") and pconf in CONF_OK:
            note = (body.get("published_note") or "").lower()
            if "catalog" in note or "added-on" in note or "added on" in note:
                stats["date_skipped_catalog"] += 1
            else:
                d["published"] = body["published"]
                d["published_source"] = "llm_curate"
                stats["published"] += 1

    return dict(stats)


def run_validate(cache: dict) -> int:
    bad = 0
    for did, entry in cache.items():
        body = entry.get("result") if isinstance(entry, dict) and "result" in entry else entry
        errs = validate_entry(body or {})
        if errs:
            bad += 1
            print(f"INVALID {did}: {', '.join(errs)}")
    print(f"validate entries={len(cache)} invalid={bad}")
    return bad


def curate_with_retries(doc: dict, *, model: str, retries: int = 3) -> dict:
    """429/5xx는 짧게 백오프 후 재시도."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            result = curate_one(doc, model=model)
            errs = validate_entry(result)
            if errs:
                raise ValueError("; ".join(errs))
            return result
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504) and attempt + 1 < retries:
                time.sleep(1.5 * (2**attempt))
                continue
            raise
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
            last = e
            if attempt + 1 < retries:
                time.sleep(1.2 * (2**attempt))
                continue
            raise
    raise last or RuntimeError("curate failed")


def main() -> None:
    ap = argparse.ArgumentParser(description="LLM 문서 큐레이션 (OpenRouter)")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--sleep", type=float, default=0.05, help="워커당 제출 간격(초)")
    ap.add_argument(
        "--workers",
        type=int,
        default=8,
        help="병렬 워커 수 (OpenRouter 한도 보며 4~16 권장)",
    )
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--validate-only", action="store_true")
    ap.add_argument(
        "--prefer-uncertain",
        action="store_true",
        help="규칙 토픽·종류가 애매한 문서 우선",
    )
    args = ap.parse_args()
    workers = max(1, int(args.workers))

    cache = load_cache()
    if args.validate_only:
        raise SystemExit(run_validate(cache))

    if not args.dry_run:
        key = ensure_openrouter_key()
        if not key:
            raise SystemExit(
                "OPENROUTER_API_KEY 없음. AI Safety/ai_safety_daily_env 등을 확인하세요."
            )

    from build_documents import build_documents
    from topics import enrich_topics

    print("building documents…")
    docs = build_documents()
    enrich_topics(docs)

    candidates = []
    for d in docs:
        did = d.get("id") or ""
        if not did:
            continue
        h = src_hash(d)
        prev = cache.get(did) or {}
        prev_body = prev.get("result") or prev
        if (
            not args.force
            and prev.get("src_hash") == h
            and (prev_body.get("confidence") in CONF_OK)
        ):
            continue
        score = 0
        if (d.get("doc_kind") or "") in ("기타", "뉴스·보도", ""):
            score += 3
        if any(
            (t.get("id") if isinstance(t, dict) else t) == "politics"
            for t in (d.get("topics") or [])
        ):
            score += 5
        if not d.get("in_scope"):
            score += 1
        candidates.append((score if args.prefer_uncertain else 0, d))

    if args.prefer_uncertain:
        candidates.sort(key=lambda x: -x[0])
    batch = [d for _, d in candidates[: max(0, args.limit)]]
    print(
        f"need≈{len(candidates)} batch={len(batch)} workers={workers} "
        f"model={args.model} cache={len(cache)}",
        flush=True,
    )

    if args.dry_run:
        for i, d in enumerate(batch, 1):
            title = (d.get("short_name") or d.get("title") or "")[:56]
            print(f"[{i}/{len(batch)}] {d['id']} {title}", flush=True)
        print("dry-run done")
        return

    cache_lock = threading.Lock()
    ok = fail = 0
    done = 0
    total = len(batch)
    t0 = time.time()
    by_id = {d["id"]: d for d in batch}

    def _work(doc: dict) -> tuple[str, dict | None, str]:
        did = doc["id"]
        title = (doc.get("short_name") or doc.get("title") or "")[:56]
        if args.sleep > 0:
            time.sleep(args.sleep)
        try:
            result = curate_with_retries(doc, model=args.model)
            return did, result, title
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            json.JSONDecodeError,
            ValueError,
            KeyError,
            TypeError,
            TimeoutError,
            RuntimeError,
        ) as e:
            return did, None, f"{title} | {e}"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_work, d): d["id"] for d in batch}
        for fut in as_completed(futures):
            did, result, info = fut.result()
            done += 1
            if result is None:
                fail += 1
                print(f"[{done}/{total}] FAIL {did} {info}", flush=True)
            else:
                with cache_lock:
                    cache[did] = {
                        "src_hash": src_hash(by_id[did]),
                        "model": args.model,
                        "updated": TODAY,
                        "result": result,
                    }
                    ok += 1
                    if ok % 10 == 0:
                        save_cache(cache)
                kind = result.get("doc_kind") or (
                    "∅" if not result.get("in_scope") else "?"
                )
                tops = ",".join(t["id"] for t in result.get("topics") or []) or "-"
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                eta = (total - done) / rate / 60 if rate > 0 else 0
                print(
                    f"[{done}/{total}] {did} scope={result.get('in_scope')} "
                    f"kind={kind} topics={tops} conf={result.get('confidence')} "
                    f"| {rate:.2f}/s ETA {eta:.0f}m",
                    flush=True,
                )

    save_cache(cache)
    elapsed = time.time() - t0
    print(
        f"done ok={ok} fail={fail} cache={len(cache)} "
        f"elapsed={elapsed/60:.1f}m → {CACHE_PATH}"
    )
    bad = run_validate(cache)
    if bad:
        print(f"warning: {bad} invalid cache entries")
    print("다음: python3 scripts/build_site.py")


if __name__ == "__main__":
    main()
