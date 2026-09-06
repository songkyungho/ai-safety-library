"""AI Safety Digest 주제 키워드를 라이브러리 문서에 재사용."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_DIGEST_TOPICS = (
    Path(__file__).resolve().parents[2] / "AI Safety" / "topic_keywords.py"
)


def _load_digest_topics():
    if not _DIGEST_TOPICS.exists():
        raise FileNotFoundError(f"동향 주제 모듈을 찾을 수 없습니다: {_DIGEST_TOPICS}")
    spec = importlib.util.spec_from_file_location("digest_topic_keywords", _DIGEST_TOPICS)
    if spec is None or spec.loader is None:
        raise ImportError(str(_DIGEST_TOPICS))
    mod = importlib.util.module_from_spec(spec)
    # match_topics 등 상대 import 없이 단독 모듈
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_MOD = _load_digest_topics()
TOPIC_KEYWORDS = _MOD.TOPIC_KEYWORDS
TOPIC_LABELS = _MOD.TOPIC_LABELS
match_topics = _MOD.match_topics

# 필터·표시 순서 (동향 TOPIC_LABELS 순서, 한국 locus·안전연구소 카테고리 전용은 제외)
TOPIC_ORDER = [
    "norms",
    "law",
    "guideline",
    "standards",
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

# 동향 HTML --topic-* 라이트 팔레트
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
    matched = match_topics(hay, TOPIC_KEYWORDS)
    # TOPIC_ORDER 우선, 그 외 슬러그는 뒤에
    order_index = {s: i for i, s in enumerate(TOPIC_ORDER)}
    return sorted(set(matched), key=lambda s: (order_index.get(s, 999), s))


def enrich_topics(docs: list[dict]) -> list[dict]:
    for d in docs:
        # LLM 큐레이션이 이미 토픽을 넣었으면 키워드 매칭으로 덮지 않음
        if d.get("topics_source") == "llm" and isinstance(d.get("topics"), list):
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
