#!/usr/bin/env python3
"""OpenRouter로 문서 제목·핵심내용을 한글로 정리하고 캐시에 저장.

사용:
  python3 scripts/enrich_ko.py --limit 30          # 샘플
  python3 scripts/enrich_ko.py --limit 200         # 배치
  python3 scripts/enrich_ko.py --missing-only      # 미번역만
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
3) 이미 한글이 충분하면 다듬기만 하고, 영문이면 번역·요약합니다.
4) JSON만 출력: {"short_name":"...","summary":"..."}
"""


def enrich_one(doc: dict, *, model: str) -> dict:
    short = doc.get("short_name") or doc.get("title") or ""
    original = doc.get("original_name") or ""
    summary = (doc.get("summary") or "")[:3500]
    org = doc.get("org") or ""
    kind = doc.get("doc_kind") or ""
    country = doc.get("country_ko") or doc.get("country") or ""
    user = (
        f"국가/기구: {country}\n기관: {org}\n문서종류: {kind}\n"
        f"표시 제목: {short}\n원문 제목: {original}\n\n핵심내용(원문):\n{summary}"
    )
    return llm_json(
        model,
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
    )


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
        if not did or not needs_enrich(d):
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
            out = enrich_one(d, model=args.model)
            short = (out.get("short_name") or "").strip()
            summary = (out.get("summary") or "").strip()
            if not short or not summary:
                raise ValueError(f"empty fields: {out!r}")
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
