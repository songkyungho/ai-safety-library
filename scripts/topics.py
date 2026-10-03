"""AI Safety Digest 주제 분류표를 라이브러리 문서에 재사용.

다이제스트 코드를 import하지 않고, 다이제스트가 내보낸 knowledge/topics.json만 읽는다
(경로: AI_SAFETY_DIGEST_TOPICS, 기본 ~/Code/ai-safety-pipeline/knowledge/topics.json).
읽을 때마다 cache/digest_topics.json에 사본을 남겨, 다이제스트 폴더가 없거나 옮겨져도
마지막 분류표로 빌드한다.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
DIGEST_TOPICS_PATH = Path(
    os.environ.get("AI_SAFETY_DIGEST_TOPICS")
    or Path.home() / "Code" / "ai-safety-pipeline" / "knowledge" / "topics.json"
)
_SNAPSHOT = _ROOT / "cache" / "digest_topics.json"
_SUPPORTED_SCHEMA = 1


def _load_topics() -> dict:
    for path in (DIGEST_TOPICS_PATH, _SNAPSHOT):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("schema_version") != _SUPPORTED_SCHEMA or not data.get("topics"):
            print(f"topics: {path} 스키마 {data.get('schema_version')} — 건너뜀", file=sys.stderr)
            continue
        if path == DIGEST_TOPICS_PATH:
            text = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
            try:
                if not _SNAPSHOT.is_file() or _SNAPSHOT.read_text(encoding="utf-8") != text:
                    _SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
                    _SNAPSHOT.write_text(text, encoding="utf-8")
            except OSError:
                pass
        else:
            print(f"topics: 다이제스트 분류표 없음({DIGEST_TOPICS_PATH}) — 사본 사용", file=sys.stderr)
        return data["topics"]
    raise FileNotFoundError(f"주제 분류표를 찾을 수 없습니다: {DIGEST_TOPICS_PATH}, {_SNAPSHOT}")


_TOPICS = _load_topics()
TOPIC_KEYWORDS: dict[str, list[str]] = {
    tid: list(t.get("keywords") or []) for tid, t in _TOPICS.items() if t.get("keywords")
}
TOPIC_LABELS: dict[str, tuple[str, str]] = {
    tid: (t.get("label") or tid, t.get("icon") or "") for tid, t in _TOPICS.items()
}

# 매칭 규칙은 다이제스트 topic_keywords.match_topics와 같게 둔다(바꾸면 양쪽 함께).
_HANGUL_RE = re.compile(r"[가-힣]")
_REGEX_META_RE = re.compile(r"[(){}\[\]|?*+\\^$.]")
_COMPILE_CACHE: dict[str, re.Pattern[str]] = {}


def _is_korean(pattern: str) -> bool:
    return bool(_HANGUL_RE.search(pattern))


def _compiled(pattern: str) -> re.Pattern[str]:
    """한글은 단어경계 없이, 영어는 단어경계로 감싼다. 메타문자가 없으면 이스케이프."""
    cached = _COMPILE_CACHE.get(pattern)
    if cached is not None:
        return cached
    has_meta = bool(_REGEX_META_RE.search(pattern))
    body = pattern if has_meta else re.escape(pattern)
    if _is_korean(pattern):
        compiled = re.compile(body, re.IGNORECASE)
    else:
        compiled = re.compile(rf"\b(?:{body})\b", re.IGNORECASE)
    _COMPILE_CACHE[pattern] = compiled
    return compiled


def match_topics(text: str, topic_keywords: dict[str, list[str]]) -> list[str]:
    """text 안에서 매칭되는 모든 주제 슬러그(다중 태그). 공백 뺀 문자열에도 한 번 더 본다."""
    if not text:
        return []
    compact = re.sub(r"\s+", "", text)
    matched: list[str] = []
    for topic, patterns in topic_keywords.items():
        for pat in patterns:
            try:
                compiled = _compiled(pat)
                if compiled.search(text) or compiled.search(compact):
                    matched.append(topic)
                    break
                if _is_korean(pat) and not _REGEX_META_RE.search(pat):
                    if re.sub(r"\s+", "", pat) in compact:
                        matched.append(topic)
                        break
            except re.error:
                if pat.lower() in text.lower() or re.sub(r"\s+", "", pat).lower() in compact.lower():
                    matched.append(topic)
                    break
    return matched

# 필터·표시 순서. 종류(doc_kind)와 겹치는 윤리·규범/법/가이드라인/표준은 쓰지 않는다.
KIND_OVERLAP_TOPICS = frozenset({"norms", "law", "guideline", "standards"})
TOPIC_ORDER = [
    "national_security",
    "cybersecurity",
    "politics",
    "sovereign_ai",
    "healthcare",
    "youth",
    "agentic_ai",
    "physical_ai",
    "safety_research",
    "deepfake_disinfo",
    "open_weight",
    "frontier",
    "incidents",
]

# 동향 HTML --topic-* 라이트 팔레트 (export_digest_html.py 와 동일)
TOPIC_COLORS: dict[str, str] = {
    "norms": "#a16207",
    "law": "#1d4ed8",
    "guideline": "#0f766e",
    "standards": "#7c3aed",
    "national_security": "#b45309",
    "cybersecurity": "#0369a1",
    "politics": "#be123c",
    "sovereign_ai": "#4338ca",
    "healthcare": "#059669",
    "youth": "#db2777",
    "aisi_topic": "#16a34a",
    "agentic_ai": "#ea580c",
    "physical_ai": "#4d7c0f",
    "safety_research": "#4f46e5",
    "deepfake_disinfo": "#9f1239",
    "open_weight": "#0d9488",
    "frontier": "#c2410c",
    "incidents": "#334155",
}


def topic_label(slug: str) -> str:
    lab, _icon = TOPIC_LABELS.get(slug, (slug, ""))
    return lab


def topic_icon(slug: str) -> str:
    _lab, icon = TOPIC_LABELS.get(slug, ("", ""))
    return icon or ""


def drop_kind_overlap_topics(topics: list) -> list:
    """종류 리본과 같은 뜻의 주제는 카드·필터에 남기지 않는다."""
    out: list = []
    seen: set[str] = set()
    for t in topics or []:
        tid = str((t.get("id") if isinstance(t, dict) else t) or "")
        if not tid or tid in KIND_OVERLAP_TOPICS or tid in seen:
            continue
        seen.add(tid)
        if isinstance(t, dict):
            out.append(t)
        else:
            out.append(
                {
                    "id": tid,
                    "label": topic_label(tid),
                    "icon": topic_icon(tid),
                    "color": TOPIC_COLORS.get(tid, "#534f4a"),
                }
            )
    return out


def match_doc_topics(doc: dict) -> list[str]:
    hay = "\n".join(
        str(doc.get(k) or "")
        for k in (
            "short_name",
            "full_name",
            "original_name",
            "title",
            "summary",
            "snippet",
            "org",
            "doc_kind",
            "doc_kind_raw",
        )
    )
    matched = [
        s
        for s in match_topics(hay, TOPIC_KEYWORDS)
        if s in TOPIC_ORDER and s not in KIND_OVERLAP_TOPICS
    ]
    order_index = {s: i for i, s in enumerate(TOPIC_ORDER)}
    return sorted(set(matched), key=lambda s: (order_index.get(s, 999), s))


def enrich_topics(docs: list[dict]) -> list[dict]:
    for d in docs:
        # LLM 큐레이션이 이미 토픽을 넣었으면 키워드 매칭으로 덮지 않음
        if d.get("topics_source") == "llm" and isinstance(d.get("topics"), list):
            d["topics"] = drop_kind_overlap_topics(d["topics"])
            continue
        slugs = match_doc_topics(d)
        d["topics"] = [
            {
                "id": s,
                "label": topic_label(s),
                "icon": topic_icon(s),
                "color": TOPIC_COLORS.get(s, "#534f4a"),
                "source": "keyword",
            }
            for s in slugs
        ]
        d["topics_source"] = "keyword"
    return docs
