"""거버넌스 층위(issuer_level): 문서 종류(doc_kind)와 직교.

doc_kind = 규범 형태 (법, 가이드라인·원칙, …)
issuer_level = 누가·어느 층위에서 냈는지 (국제기구, 국가, 랩, …)

구 `개발사 정책`은 doc_kind가 아니라 issuer_level=lab + 형태 종류로 옮긴다.
"""
from __future__ import annotations

import re
from typing import Any

# id → 한국어 라벨 (필터·배지)
ISSUER_LEVELS: list[tuple[str, str]] = [
    ("international", "국제기구·다자"),
    ("national", "국가"),
    ("subnational", "지방·주"),
    ("ministry", "부처·규제기관"),
    ("lab", "프론티어 랩"),
    ("industry", "산업계·협회"),
    ("civil_society", "시민사회·학계"),
    ("multi", "민관·혼합"),
]

ISSUER_IDS = {i for i, _ in ISSUER_LEVELS}
ISSUER_LABEL = dict(ISSUER_LEVELS)

# UI 색 (라이트, 다크) — 동향 Digest cat/topic 토큰
ISSUER_COLORS: dict[str, tuple[str, str]] = {
    "international": ("#3d3a6e", "#b8b4d0"),  # cat-intl
    "national": ("#1d4ed8", "#93c5fd"),        # topic-law
    "subnational": ("#0369a1", "#7dd3fc"),     # topic-cyber
    "ministry": ("#3f5340", "#9bb396"),        # cat-gov / sage
    "lab": ("#8a5a18", "#f3b84f"),             # cat-company / gold
    "industry": ("#c2410c", "#fdba8c"),        # topic-frontier
    "civil_society": ("#a16207", "#fbbf24"),   # topic-norms
    "multi": ("#474284", "#b0acd8"),           # cat-research / navy
}

LEGACY_LAB_KIND = "개발사 정책"

_LAB_STRATEGY = re.compile(
    r"전략|roadmap|strategy\s*paper|정책\s*보고서|white\s*paper",
    re.I,
)
_INTL = re.compile(
    r"\b(un|unesco|oecd|g7|g20|gpai|council of europe|"
    r"european union|\beu\b|wto|who|iso|iec|itu|"
    r"asean|apec|imf|world bank|"
    r"국제연합|유네스코|유럽연합|유럽의회|유럽이사회|oecd\.ai)\b",
    re.I,
)
_MINISTRY = re.compile(
    r"ministry|department of|agency|commission|authority|regulator|"
    r"\bnist\b|\bntia\b|\bofcom\b|\bico\b|\bcnil\b|\bcisa\b|"
    r"부처|위원회|규제|과학기술정보통신부|과기정통부|"
    r"개인정보보호위원회|방송통신위원회|산업통상자원부|행정안전부",
    re.I,
)
_SUBNAT = re.compile(
    r"\b(state of|province|canton|prefecture|"
    r"california|new york|colorado|illinois|texas)\b|"
    r"조례|\b(SB|AB)\s*\d+",
    re.I,
)
_LAB_ORG = re.compile(
    r"\b(openai|anthropic|google\s*deepmind|deepmind|meta\s*ai|"
    r"microsoft|amazon|xai|inflection|mistral|cohere|"
    r"naver|kakao|samsung|upstage|ncsoft|lg\s*ai|"
    r"skt|sk\s*telecom)\b",
    re.I,
)
_INDUSTRY = re.compile(
    r"\b(association|chamber|\bbsa\b|partnership on ai|"
    r"업계|협회|연맹|컨소시엄)\b",
    re.I,
)
_CIVIL = re.compile(
    r"\b(iaae|metr\b|future of life|\bfli\b|stanford|berkeley|"
    r"university|institute|think\s*tank|\bngo\b|civil\s*society|"
    r"시민|학회|연구소|대학|싱크탱크)\b",
    re.I,
)
_MULTI = re.compile(
    r"민관|합동|public[-\s]?private|multi[-\s]?stakeholder|"
    r"공동\s*(선언|원칙|이니셔티브)",
    re.I,
)


def issuer_label(level_id: str) -> str:
    return ISSUER_LABEL.get(level_id or "", level_id or "")


def migrate_legacy_lab_kind(doc_kind: str, *texts: str) -> tuple[str, str | None]:
    """구 `개발사 정책` → (형태 종류, issuer lab 힌트).

    기본은 가이드라인·원칙. 전략·로드맵성만 전략·정책.
    """
    kind = (doc_kind or "").strip()
    if kind != LEGACY_LAB_KIND:
        return kind, None
    blob = " ".join(str(t) for t in texts if t)
    if _LAB_STRATEGY.search(blob):
        return "전략·정책", "lab"
    return "가이드라인·원칙", "lab"


def _is_lab_member(doc: dict[str, Any]) -> bool:
    for mid in doc.get("member_ids") or []:
        if str(mid).startswith("lab-"):
            return True
    for h in doc.get("history") or []:
        if not isinstance(h, dict):
            continue
        iid = str(h.get("item_id") or "")
        if iid.startswith("lab-"):
            return True
        if h.get("label") in (LEGACY_LAB_KIND, "개발사 게시") or h.get(
            "collection"
        ) == "lab-policies":
            return True
    return False


def infer_issuer_level(doc: dict[str, Any]) -> str:
    """문서 메타로 주 발급 층위 1개 추정."""
    preset = str(doc.get("issuer_level") or "").strip()
    if preset in ISSUER_IDS:
        return preset

    kind = str(doc.get("doc_kind") or "")
    if kind == LEGACY_LAB_KIND or _is_lab_member(doc):
        return "lab"

    org = str(doc.get("org") or "")
    country = str(doc.get("country") or "")
    title = " ".join(
        str(doc.get(k) or "")
        for k in ("title", "short_name", "full_name", "original_name", "summary")
    )
    blob = f"{org} {country} {title} {kind}"

    if _MULTI.search(blob):
        return "multi"
    if _LAB_ORG.search(org) or _LAB_ORG.search(blob):
        return "lab"
    if re.search(r"international|multilateral|supranational|글로벌|다자|국제", country, re.I):
        return "international"
    if _INTL.search(blob):
        return "international"
    if kind == "조약·협약":
        return "international"
    if _SUBNAT.search(blob) and kind in (
        "법",
        "법안",
        "행정규칙",
        "전략·정책",
        "선언·성명",
    ):
        return "subnational"
    if _INDUSTRY.search(blob):
        return "industry"
    if _CIVIL.search(org) and kind in (
        "가이드라인·원칙",
        "정책보고서",
        "선언·성명",
        "기타",
    ):
        if not _MINISTRY.search(org) and not _INTL.search(org):
            return "civil_society"
    if _MINISTRY.search(org) or (
        _MINISTRY.search(blob)
        and kind
        in ("행정규칙", "가이드라인·원칙", "전략·정책", "정책보고서", "기구·제도")
    ):
        return "ministry"
    if kind in ("법", "법안"):
        return "national"
    if kind in ("전략·정책", "선언·성명") and country and not re.search(
        r"international|다자|국제", country, re.I
    ):
        return "national"
    if country and not re.search(r"international|다자|국제", country, re.I):
        return "national"
    if _CIVIL.search(blob):
        return "civil_society"
    return "national"


def apply_issuer_taxonomy(docs: list[dict]) -> dict[str, int]:
    """개발사 정책 이관 + issuer_level 부여. 문서는 삭제하지 않음."""
    stats = {"lab_kind_migrated": 0, "issuer_set": 0}
    for d in docs:
        old_kind = str(d.get("doc_kind") or "")
        new_kind, lab_hint = migrate_legacy_lab_kind(
            old_kind,
            d.get("title") or "",
            d.get("short_name") or "",
            d.get("summary") or "",
            d.get("org") or "",
        )
        if new_kind != old_kind:
            d["doc_kind"] = new_kind
            stats["lab_kind_migrated"] += 1
        if lab_hint and d.get("issuer_level") not in ISSUER_IDS:
            d["issuer_level"] = lab_hint
        level = infer_issuer_level(d)
        d["issuer_level"] = level
        d["issuer_level_ko"] = issuer_label(level)
        stats["issuer_set"] += 1
    return stats
