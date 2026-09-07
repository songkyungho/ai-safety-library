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
from issuer_levels import ISSUER_IDS, ISSUER_LEVELS, migrate_legacy_lab_kind  # noqa: E402
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

# 제목·출처만 반복하고 실질 내용이 없는 LLM 요약 (카드는 유지, summary만 비움)
# 예: 「제목」입니다 / 제목은 ～가이드라인임을 나타냅니다 (따옴표 없음)
_HOLLOW_TITLE = re.compile(
    r"문서\s*제목은\s*"
    r"(?:"
    r"[「『\"“‘'][^」』\"”’']+[」』\"”’']\s*입니다|"
    r"[^\n]{6,100}?(?:입니다|임을\s*나타냅니다|[을를]\s*나타냅니다)"
    r")"
)
_HOLLOW_NO_DETAIL = re.compile(
    r"(제공된|주어진|원문)\s*(메타(데이터)?|정보|본문).{0,64}"
    r"(없|부족|포함되어\s*있지\s*않|확인\s*할\s*수\s*없)|"
    r"(메타|정보)\s*만으로는.{0,64}(없|부족|확인\s*할\s*수\s*없)|"
    r"세부\s*(내용|조항|책무|원칙|권고|기준|적용\s*(범위|대상)).{0,64}"
    r"(없|포함되어\s*있지\s*않|확인\s*할\s*수\s*없)|"
    r"상세\s*내용(은|이|을).{0,24}(첨부|다운로드|웹\s*페이지|원문)|"
    r"첨부\s*자료.{0,24}(다운로드|확인)|"
    r"메타데이터만으로는"
)
_HOLLOW_SOURCE_ONLY = re.compile(
    r"원문\s*메타|"
    r"출처로\s*제시|"
    r"자료로\s*제시|"
    r"홈페이지.{0,40}첨부|"
    r"첨부\s*자료.{0,40}출처|"
    r"홈페이지의\s*게시물"
)
_HOLLOW_SIBLING_LIST = re.compile(
    r"(자료\s*목록|같은\s*(게시물|목록)).{0,100}함께\s*(언급|제시|안내)|"
    r"함께\s*(언급|제시|안내).{0,48}(가이드라인|관련)|"
    r"관련\s*가이드라인도|"
    r"별도\s*가이드라인도"
)


def is_hollow_summary(text: str) -> bool:
    """제목·출처 안내만 있고 규범 내용이 없는 빈 요약 → summary만 삭제 대상."""
    from library_common import is_scrape_chrome

    s = (text or "").strip()
    if not s:
        return False
    if is_scrape_chrome(s):
        return True
    no_detail = bool(_HOLLOW_NO_DETAIL.search(s))
    title_only = bool(_HOLLOW_TITLE.search(s))
    source_only = bool(_HOLLOW_SOURCE_ONLY.search(s))
    sibling_list = bool(_HOLLOW_SIBLING_LIST.search(s))
    if title_only and no_detail:
        return True
    if title_only and source_only:
        return True
    if title_only and sibling_list:
        return True
    if no_detail and (source_only or sibling_list):
        return True
    if no_detail and re.search(r"(홈페이지|자료로\s*제시|출처로\s*제시|원문\s*메타)", s):
        return True
    return False


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
5) 제목·출처 URL·첨부 안내만 있고 규범·책무·조항의 실질 내용이 없으면
   summary="" 로 두세요. 문서를 범위 밖(in_scope=false)으로 빼지 마세요.
   "문서 제목은 ～입니다 / 메타에 세부 내용이 없다 / 첨부 다운로드" 식의
   빈 요약은 쓰지 마세요.

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
- AI 개발사·랩이 공개한 윤리원칙·헌장·책임있는 AI 원칙·프론티어 안전
  프레임워크(RSP/ASF/ASI 등)는 doc_kind=가이드라인·원칙(또는 전략·정책),
  issuer_level=lab 로 두세요. "개발사 정책"이라는 doc_kind는 쓰지 마세요.

층위 (issuer_level, 문서 종류와 별개)
- issuer_level: {" | ".join(i for i, _ in ISSUER_LEVELS)}
  international=국제기구·다자, national=국가, subnational=지방·주,
  ministry=부처·규제기관, lab=프론티어 랩, industry=산업계·협회,
  civil_society=시민사회·학계, multi=민관·혼합.
- 시·도 교육청, 광역시·특별자치도, 주 정부/주 의회, City of·County of 문서는
  subnational. 중앙부처(교육부·Ministry of Local Government 등)는 ministry.
- 한 문서에 주 발급 층위 하나만. 형태(doc_kind)와 층위(issuer_level)를 동시에 채우세요.

토픽
- 각 topic에 evidence를 원문에서 고른 짧은 구절로 반드시 채우세요. 근거 없으면 그 토픽은 빼세요.
- 보통 1~2개. 명확히 복합 주제일 때만 3개.
- norms, law, guideline, standards 는 쓰지 마세요. 그건 doc_kind(종류)입니다.
- politics: 선거제도·정당·선거운동·로비·의회 정치과정이 규율 대상의 핵심일 때.
  선거 딥페이크/허위조작 규제는 deepfake_disinfo를 기본으로 두고,
  선거·정치과정이 규율 대상이면 politics를 함께 둡니다.
  아동 성착취물·일반 딥페이크·소비자 기만만이면 politics 금지.
- cybersecurity: AI/모델/선거 인프라 보안이 핵심일 때. 일반 IT만이면 신중히.

날짜 (published)
- catalog Added-on / OECD 등록일 / 크롤 시각은 쓰지 마세요 → published="" ,
  published_confidence="none", published_note에 사유.
- 연도만 알면 published="" 또는 YYYY-01-01 + confidence=low. 일자·월을 추측하지 마세요.
- 원문에 명시된 채택·공포·발표일만 high/medium.

한글 표기
- short_name: 한국어 약칭. 관할(캘리포니아·EU 등)·고유번호(AB 410, SB 9)는 유지.
- summary: 사실만 3~6문장. 마케팅·추측 금지. 내용이 없으면 빈 문자열.
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
    kind, lab_hint = migrate_legacy_lab_kind(kind)
    if kind not in CURATED_KINDS:
        kind = ""

    issuer = str(raw.get("issuer_level") or "").strip()
    if issuer not in ISSUER_IDS:
        issuer = lab_hint or ""

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

    summary = str(raw.get("summary") or "").strip()[:4000]
    # 제목·출처만 있는 빈 요약 → 설명만 비움 (카드·범위는 유지)
    if is_hollow_summary(summary):
        summary = ""

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
        "issuer_level": issuer,
        "topics": topics,
        "published": published,
        "published_confidence": pconf,
        "published_note": str(raw.get("published_note") or "")[:240],
        "short_name": str(raw.get("short_name") or "").strip()[:200],
        "summary": summary,
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
  "issuer_level": "<enum>",
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
            # 저신뢰여도 LLM이 요약을 비웠으면 원문 폴백을 남기지 않는다.
            if "summary" in body:
                s = str(body.get("summary") or "").strip()
                if not s or is_hollow_summary(s):
                    d["summary"] = ""
                    d["snippet"] = ""
                    stats["summary_cleared"] += 1
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
        if body.get("issuer_level") in ISSUER_IDS:
            d["issuer_level"] = body["issuer_level"]
            d["issuer_level_ko"] = dict(ISSUER_LEVELS).get(body["issuer_level"], "")

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
        if "summary" in body:
            summary = str(body.get("summary") or "").strip()
            if is_hollow_summary(summary):
                summary = ""
            d["summary"] = summary
            d["snippet"] = summary[:500] if summary else ""
            stats["summary"] += 1
            if not summary:
                stats["summary_cleared"] = stats.get("summary_cleared", 0) + 1

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
    ap.add_argument(
        "--collection",
        action="append",
        default=[],
        help="이 컬렉션 문서만 (반복 가능). 예: --collection lab-policies",
    )
    args = ap.parse_args()
    workers = max(1, int(args.workers))
    collection_filter = {c.strip() for c in (args.collection or []) if c.strip()}
    filter_member_ids: set[str] = set()
    if collection_filter:
        from library_common import load_collection

        for key in collection_filter:
            for it in (load_collection(key).get("items") or []):
                mid = it.get("id") or ""
                if mid:
                    filter_member_ids.add(mid)
        print(
            f"collection filter={sorted(collection_filter)} "
            f"members={len(filter_member_ids)}",
            flush=True,
        )

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
        if filter_member_ids:
            mids = {m for m in (d.get("member_ids") or []) if m}
            if not (mids & filter_member_ids):
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
    run_path = ROOT / "cache" / "curate_last_run.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text(
        json.dumps(
            {
                "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "batch": total,
                "ok": ok,
                "fail": fail,
                "elapsed_sec": round(elapsed, 1),
                "model": args.model,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
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
