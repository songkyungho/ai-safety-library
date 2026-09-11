#!/usr/bin/env python3
"""OpenRouter로 문서 제목·핵심내용을 한글로 정리하고 캐시에 저장.

사용:
  python3 scripts/enrich_ko.py --limit 30          # 샘플
  python3 scripts/enrich_ko.py --limit 200         # 배치
  python3 scripts/enrich_ko.py --leftover-titles --force --limit 80
  python3 scripts/enrich_ko.py --english-titles --limit 80
  python3 scripts/build_site.py                    # 캐시 반영 후 사이트 빌드

캐시: cache/ko_enrich.json  (doc id → short_name / summary)
원문 제목은 documents.original_name 에 유지되고, short_name·summary 만 한글로 덮어쓴다.
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
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_documents import build_documents  # noqa: E402
from library_common import write_json  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "cache" / "ko_enrich.json"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.environ.get("OPENROUTER_MODEL") or "openai/gpt-5.6-luna"
TODAY = date.today().isoformat()
_HANGUL = re.compile(r"[가-힣]")
_LATIN = re.compile(r"[A-Za-z]")
_EN_WORD = re.compile(r"\b[A-Za-z][A-Za-z'’-]{2,}\b")
# 약칭에 남아도 되는 짧은 고유명·법안 번호. 일반 영어 명사는 여기 두지 않는다.
_LEFTOVER_KEEP = {
    "the",
    "and",
    "for",
    "of",
    "on",
    "in",
    "to",
    "a",
    "an",
    "or",
    "ai",
    "act",
    "bill",
    "hr",
    "sb",
    "ab",
    "s",
    "scr",
    "acr",
    "eu",
    "un",
    "oecd",
    "unesco",
    "g7",
    "g20",
    "nato",
    "iso",
    "ieee",
    "itu",
    "gpai",
    "who",
    "ilo",
    "wipo",
    "nist",
    "gpt",
    "llm",
    "api",
}
# 프로그램·프레임워크 고유명은 한·영 병기를 유지한다.
_SKIP_PROPER = re.compile(
    r"Defense Innovation Board|Health Data Lab|AI Essentials|Aletheia|"
    r"TechGirls|IBM.?s Principles|Grant Connect|Privacy Act|"
    r"Embedded EthiCS|Copilot|Tampere Pulse|verkstaden|Pax Silica|"
    r"Magnifica Humanitas|DAEDALUS|Tipping Point|GovTech Sandbox|"
    r"Cultural AI Lab|SeCoIA|Regulatory Sandbox|Project Nimbus|"
    r"Project Explain|KI@Polizei|Police AI|INDIAai|Evaluation Sandbox|"
    r"Stakeholder Forum|Source List|Frontier Safety|Miami-Dade|"
    r"Kendall County|Asilomar|Rome Call|Responsible Scaling|Scaling 정책|"
    r"DeepMind|GovAI Chat|AMALIA|ALLiaNCE|Leuven\.AI|AI4Citizens|"
    r"\bSURF\b|xPlain-AI|AI Politeia Lab|fAIr LAC|AiLECS|"
    r"Constitutional AI|TRAIL\(",
    re.I,
)
_EN_TITLE_SIGNAL = re.compile(
    r"\b(Act|NDAA|IAA|AB-|HR\s|Bill|Principles|Authority|Report|"
    r"Faculty|Index|Uzbekistan|Appropriations|Program)\b",
    re.I,
)


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


def ensure_openrouter_key() -> str:
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if key:
        return key
    for p in (
        Path.home() / ".ai_safety_daily_env",
        Path.home() / "ai_safety_daily_env",
        ROOT.parent / "AI Safety" / "ai_safety_daily_env",
        ROOT.parent / "AI Safety" / ".env.local",
    ):
        load_env_file(p)
        key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
        if key:
            return key
    return ""


def hangul_ratio(text: str) -> float:
    text = text or ""
    h = len(_HANGUL.findall(text))
    letters = len(_HANGUL.findall(text)) + len(_LATIN.findall(text))
    return (h / letters) if letters else 1.0


def src_hash(short: str, summary: str, original: str) -> str:
    blob = f"{short}\n{original}\n{summary}".encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def leftover_english_words(text: str) -> list[str]:
    """한글 약칭에 남은 일반 영어 단어. 짧은 대문자 약어는 제외."""
    out: list[str] = []
    for w in _EN_WORD.findall(text or ""):
        if w.lower() in _LEFTOVER_KEEP:
            continue
        if w.isupper() and len(w) <= 6:
            continue
        out.append(w)
    return out


_BILL_HOST = re.compile(r"congress\.gov|legislature\.ca\.gov", re.I)


def leftover_title_needs_rewrite(
    doc: dict, *, min_words: int = 3, bills_only: bool = False
) -> bool:
    """한글이 있는데 일반 영어 단어가 남은 약칭. 고유명 병기는 건너뛴다."""
    short = doc.get("short_name") or doc.get("title") or ""
    original = doc.get("original_name") or ""
    if _SKIP_PROPER.search(short) or _SKIP_PROPER.search(original):
        return False
    if not _HANGUL.search(short):
        return False
    if bills_only:
        urls = [doc.get("canonical_url") or ""]
        for h in doc.get("history") or []:
            if isinstance(h, dict):
                urls.append(h.get("url") or "")
        if not _BILL_HOST.search(" ".join(urls)):
            return False
    return len(leftover_english_words(short)) >= min_words


def english_summary_needs_rewrite(doc: dict) -> bool:
    """한글 약칭인데 핵심내용이 영어인 카드."""
    short = doc.get("short_name") or doc.get("title") or ""
    summary = doc.get("summary") or ""
    if not _HANGUL.search(short):
        return False
    if len(summary) < 40:
        return False
    return hangul_ratio(summary) < 0.2


def english_title_needs_rewrite(doc: dict) -> bool:
    """한글이 없는 약칭. 프로그램·랩 고유명은 건너뛰고 법안·기관명만 옮긴다."""
    short = doc.get("short_name") or doc.get("title") or ""
    original = doc.get("original_name") or ""
    if _HANGUL.search(short):
        return False
    if _SKIP_PROPER.search(short) or _SKIP_PROPER.search(original):
        return False
    if _EN_TITLE_SIGNAL.search(short):
        return True
    urls = [doc.get("canonical_url") or ""]
    for h in doc.get("history") or []:
        if isinstance(h, dict):
            urls.append(h.get("url") or "")
    return bool(_BILL_HOST.search(" ".join(urls)))


def needs_enrich(doc: dict) -> bool:
    short = doc.get("short_name") or doc.get("title") or ""
    summary = doc.get("summary") or ""
    original = doc.get("original_name") or ""
    # 제목: 라틴이 많고 한글이 적으면
    title_needs = bool(_LATIN.search(short)) and hangul_ratio(short) < 0.45
    # 요약: 길이가 있고 한글이 적으면
    summary_needs = len(summary) >= 40 and hangul_ratio(summary) < 0.35
    # 이미 한글 제목인데 요약만 영어인 경우도 포함
    if not title_needs and not summary_needs:
        return False
    # 원문이 한국어뿐이면 스킵
    if hangul_ratio(original or short) > 0.7 and hangul_ratio(summary) > 0.7:
        return False
    return True


def load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_json(CACHE_PATH, cache)


def llm_json(model: str, messages: list[dict], timeout: int = 90) -> dict:
    key = ensure_openrouter_key()
    body = json.dumps(
        {
            "model": model,
            "temperature": 0.2,
            "messages": messages,
            "response_format": {"type": "json_object"},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/songkyungho/ai-safety-library",
            "X-Title": "AI Safety Library KO enrich",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    content = raw["choices"][0]["message"]["content"]
    return json.loads(content)


SYSTEM = """당신은 AI 안전·거버넌스 문서 큐레이터입니다.
주어진 문서의 표시용 한글 약칭과 핵심내용을 작성합니다.

규칙:
1) short_name: 한국어 약칭. 고유명(법안 번호 AB 682, AI Act, UNESCO 등)은 원형 유지.
   불필요한 영문 부제·괄호 설명은 줄이되, 식별에 필요한 약어·연도는 남깁니다.
2) summary: 한국어 핵심내용. 3~6문장 또는 번호 목록(1 2 3…)으로 사실만 요약.
   서론·마케팅 문구 금지. 원문에 없는 사실 추가 금지.
   핵심 결론·사실은 **이렇게**, 중요한 용어나 구체 수치는 __이렇게__ 감싼다. 카드당 많아야 1~2곳. HTML 태그는 쓰지 않는다.
3) 이미 한글이 충분하면 다듬기만 하고, 영문이면 번역·요약합니다.
4) JSON만 출력: {"short_name":"...","summary":"..."}
"""

SYSTEM_LEFTOVER = """당신은 AI 안전·거버넌스 문서 큐레이터입니다.
표시 제목에 한글과 영어가 섞여 있습니다. 원문 제목을 보고 한국어 약칭을 새로 씁니다.

규칙:
1) short_name은 한국어. amend, direct, Secretary, require, relating, establish 같은
   일반 영어 단어는 쓰지 않습니다. 영어는 법안 번호(HR 1142, S 1974, AB 682)와
   공식 약어(AI, OECD, NIST 등)만 허용합니다.
2) 법의 대상과 목적을 짧게 한국어로 쓰고, 원문 제목을 직역해 영어 단어를 남기지 않습니다.
3) summary: 한국어 핵심내용. 3~6문장. 원문에 없는 사실 금지.
   핵심 사실은 **굵게**, 중요 용어·수치는 __밑줄__. 카드당 1~2곳.
4) JSON만 출력: {"short_name":"...","summary":"..."}
"""

SYSTEM_SUMMARY = """당신은 AI 안전·거버넌스 문서 큐레이터입니다.
표시 제목은 이미 한국어입니다. short_name은 입력과 똑같이 두고, summary만 한국어로 씁니다.

규칙:
1) short_name은 받은 표시 제목을 그대로 반환합니다. 바꾸지 않습니다.
2) summary: 한국어 핵심내용. 3~6문장. 원문에 없는 사실 금지.
   서론·마케팅 문구 금지.
   핵심 사실은 **굵게**, 중요 용어·수치는 __밑줄__. 카드당 1~2곳.
3) JSON만 출력: {"short_name":"...","summary":"..."}
"""


def enrich_one(
    doc: dict, *, model: str, leftover: bool = False, summary_only: bool = False
) -> dict:
    short = doc.get("short_name") or doc.get("title") or ""
    original = doc.get("original_name") or ""
    summary = (doc.get("summary") or "")[:3500]
    org = doc.get("org") or ""
    kind = doc.get("doc_kind") or ""
    country = doc.get("country_ko") or doc.get("country") or ""
    user = (
        f"국가/기구: {country}\n기관: {org}\n문서종류: {kind}\n"
        f"표시 제목(참고): {short}\n원문 제목(이것을 번역): {original}\n\n"
        f"핵심내용(원문):\n{summary}"
    )
    if summary_only:
        system = SYSTEM_SUMMARY
    elif leftover:
        system = SYSTEM_LEFTOVER
    else:
        system = SYSTEM
    out = llm_json(
        model,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    if summary_only:
        out["short_name"] = short
    return out


def apply_cache_to_docs(docs: list[dict], cache: dict | None = None) -> int:
    """캐시 한글본을 문서에 반영. 소스 해시가 맞거나, 아직 미번역인데 캐시가 있으면 적용."""
    cache = cache if cache is not None else load_cache()
    n = 0
    dirty = False
    for d in docs:
        did = d.get("id") or ""
        entry = cache.get(did)
        if not entry or not entry.get("short_name") or not entry.get("summary"):
            continue
        h = src_hash(
            d.get("short_name") or "",
            d.get("summary") or "",
            d.get("original_name") or "",
        )
        hash_ok = entry.get("src_hash") == h
        cache_ready = hangul_ratio(entry.get("summary") or "") >= 0.35
        if not hash_ok and not (needs_enrich(d) and cache_ready):
            continue
        if not hash_ok and cache_ready:
            # 소스 문구가 조금 바뀌어도 기존 한글 캐시를 쓰고, 해시를 현재 소스에 맞춤
            entry["src_hash"] = h
            dirty = True
        if not (d.get("original_name") or "").strip():
            prev = d.get("short_name") or d.get("title") or ""
            if prev and hangul_ratio(prev) < 0.45:
                d["original_name"] = prev
        d["short_name"] = entry["short_name"]
        d["title"] = entry["short_name"]
        d["summary"] = entry["summary"]
        d["snippet"] = entry["summary"][:500]
        d["ko_enriched"] = True
        n += 1
    if dirty:
        save_cache(cache)
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="문서 제목·핵심내용 한글화 (OpenRouter)")
    ap.add_argument("--limit", type=int, default=50, help="이번에 번역할 최대 건수")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--sleep", type=float, default=0.4)
    ap.add_argument("--force", action="store_true", help="캐시 무시하고 재번역")
    ap.add_argument(
        "--leftover-titles",
        action="store_true",
        help="한글·영어가 섞인 약칭만 원문 제목 기준으로 다시 쓴다",
    )
    ap.add_argument(
        "--min-words",
        type=int,
        default=3,
        help="leftover-titles일 때 남은 영어 단어 최소 개수",
    )
    ap.add_argument(
        "--bills-only",
        action="store_true",
        help="미국·캘리포니아 법안 주소만 leftover 대상으로",
    )
    ap.add_argument(
        "--english-summaries",
        action="store_true",
        help="한글 약칭인데 핵심내용이 영어인 카드만 요약 번역",
    )
    ap.add_argument(
        "--english-titles",
        action="store_true",
        help="영어 약칭만 한글로 옮긴다. 프로그램·랩 고유명은 건너뛴다",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    key = ensure_openrouter_key()
    if not key and not args.dry_run:
        raise SystemExit("OPENROUTER_API_KEY 없음. ~/.ai_safety_daily_env 등을 확인하세요.")

    print("building documents…")
    docs = [d for d in build_documents() if d.get("in_scope")]
    cache = load_cache()
    # 이미 캐시 적용된 상태에서도 원문 해시 비교를 위해, 캐시 미적용 raw 기준으로
    # needs를 보려면 캐시 없는 필드만 보면 됨. force가 아니면 캐시 hit 스킵.
    candidates = []
    for d in docs:
        did = d.get("id") or ""
        if not did:
            continue
        if args.leftover_titles:
            if not leftover_title_needs_rewrite(
                d, min_words=args.min_words, bills_only=args.bills_only
            ):
                continue
        elif args.english_summaries:
            if not english_summary_needs_rewrite(d):
                continue
        elif args.english_titles:
            if not english_title_needs_rewrite(d):
                continue
        elif not needs_enrich(d):
            continue
        h = src_hash(d.get("short_name") or "", d.get("summary") or "", d.get("original_name") or "")
        prev = cache.get(did)
        if not args.force and prev and prev.get("short_name") and prev.get("summary"):
            if prev.get("src_hash") == h:
                continue
            # 해시가 어긋나도 캐시에 쓸 만한 한글 요약이 있으면 API 재호출하지 않음
            if hangul_ratio(prev.get("summary") or "") >= 0.35:
                continue
        candidates.append(d)

    # 최근 발표 우선, id 중복 제거
    candidates.sort(key=lambda d: d.get("published") or "", reverse=True)
    seen_ids: set[str] = set()
    uniq: list[dict] = []
    for d in candidates:
        did = d.get("id") or ""
        if not did or did in seen_ids:
            continue
        seen_ids.add(did)
        uniq.append(d)
    batch = uniq[: max(0, args.limit)]
    print(f"need≈{len(candidates)} batch={len(batch)} model={args.model} cache={len(cache)}")

    ok = fail = 0
    for i, d in enumerate(batch, 1):
        did = d["id"]
        h = src_hash(d.get("short_name") or "", d.get("summary") or "", d.get("original_name") or "")
        print(f"[{i}/{len(batch)}] {did} {(d.get('short_name') or '')[:60]}")
        if args.dry_run:
            continue
        try:
            out = enrich_one(
                d,
                model=args.model,
                leftover=args.leftover_titles or args.english_titles,
                summary_only=args.english_summaries,
            )
            short = (out.get("short_name") or "").strip()
            summary = (out.get("summary") or "").strip()
            if not short or not summary:
                raise ValueError(f"empty fields: {out!r}")
            min_left = args.min_words if args.leftover_titles else 3
            still_en = args.english_titles and not _HANGUL.search(short)
            leftover_retry = args.leftover_titles and len(leftover_english_words(short)) >= min_left
            if leftover_retry or still_en:
                print(f"  retry leftover EN: {short[:70]}")
                out = enrich_one(d, model=args.model, leftover=True)
                short = (out.get("short_name") or "").strip()
                summary = (out.get("summary") or "").strip()
                if not short or not summary:
                    raise ValueError(f"empty fields: {out!r}")
            if args.leftover_titles and len(leftover_english_words(short)) >= min_left:
                print(f"  still leftover: {short[:70]}")
            if args.english_titles and not _HANGUL.search(short):
                print(f"  still English title: {short[:70]}")
            cache[did] = {
                "src_hash": h,
                "short_name": short,
                "summary": summary,
                "model": args.model,
                "updated": TODAY,
            }
            ok += 1
            if i % 5 == 0:
                save_cache(cache)
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, ValueError, KeyError) as e:
            fail += 1
            print("  FAIL", e)
        time.sleep(args.sleep)

    if not args.dry_run:
        save_cache(cache)
    print(f"done ok={ok} fail={fail} cache={len(cache)} → {CACHE_PATH}")
    print("다음: python3 scripts/build_site.py")


if __name__ == "__main__":
    main()
