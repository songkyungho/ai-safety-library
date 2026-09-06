#!/usr/bin/env python3
"""Heuristic Korean glosses for English (and mixed) policy/legal titles."""
from __future__ import annotations

import re
import unicodedata

_HANGUL = re.compile(r"[가-힣]")

# Longest-first phrase replacements (case-insensitive).
_PHRASES: list[tuple[str, str]] = [
    ("artificial intelligence", "인공지능"),
    ("machine learning", "머신러닝"),
    ("generative ai", "생성형 AI"),
    ("general-purpose ai", "범용 AI"),
    ("general purpose ai", "범용 AI"),
    ("frontier ai", "프론티어 AI"),
    ("advanced artificial intelligence", "고도 인공지능"),
    ("advanced ai", "고도 AI"),
    ("national artificial intelligence strategy", "국가 인공지능 전략"),
    ("national ai strategy", "국가 AI 전략"),
    ("ai strategy", "AI 전략"),
    ("ai action plan", "AI 행동계획"),
    ("action plan", "행동계획"),
    ("executive order", "행정명령"),
    ("white paper", "백서"),
    ("code of practice", "실천규범"),
    ("code of conduct", "행동규범"),
    ("framework convention", "기본협약"),
    ("risk management framework", "위험관리 프레임워크"),
    ("risk management", "위험관리"),
    ("impact assessment", "영향평가"),
    ("human rights", "인권"),
    ("national security", "국가안보"),
    ("cybersecurity", "사이버보안"),
    ("data protection", "개인정보보호"),
    ("intellectual property", "지식재산"),
    ("public sector", "공공부문"),
    ("private sector", "민간부문"),
    ("working group", "작업반"),
    ("task force", "태스크포스"),
    ("advisory committee", "자문위원회"),
    ("governing council", "운영이사회"),
    ("pilot program", "시범사업"),
    ("research and development", "연구개발"),
    ("removing barriers", "장벽 제거"),
    ("american leadership", "미국 리더십"),
    ("relating to", "관련"),
    ("with respect to", "관련"),
    ("for the purpose of", "목적의"),
    ("organizations developing", "개발 조직"),
    ("developing advanced", "고도"),
    ("preventing algorithmic collusion", "알고리즘 담합 방지"),
    ("algorithmic collusion", "알고리즘 담합"),
    ("prior authorization", "사전승인"),
    ("health care coverage", "의료보장"),
    ("united states", "미국"),
    ("united kingdom", "영국"),
    ("european union", "EU"),
    ("european commission", "유럽위원회"),
    ("council of europe", "유럽평의회"),
    ("united nations", "유엔"),
    ("south korea", "한국"),
    ("republic of korea", "대한민국"),
    ("new zealand", "뉴질랜드"),
    ("saudi arabia", "사우디아라비아"),
    ("hong kong", "홍콩"),
    ("california", "캘리포니아"),
    ("washington", "워싱턴"),
    ("georgia", "조지아"),
    ("sweden", "스웨덴"),
    ("france", "프랑스"),
    ("germany", "독일"),
    ("japan", "일본"),
    ("china", "중국"),
    ("australia", "호주"),
    ("canada", "캐나다"),
    ("india", "인도"),
    ("brazil", "브라질"),
    ("department of defense", "국방부"),
    ("department of state", "국무부"),
    ("white house", "백악관"),
    ("chief digital and artificial intelligence officer", "최고디지털·인공지능책임자(CDAO)"),
    ("intelligence officer", "정보책임자"),
    ("digital and", "디지털·"),
    ("guidelines", "가이드라인"),
    ("guideline", "가이드라인"),
    ("guidance", "지침"),
    ("principles", "원칙"),
    ("principle", "원칙"),
    ("recommendation", "권고"),
    ("recommendations", "권고"),
    ("declaration", "선언"),
    ("strategy", "전략"),
    ("framework", "프레임워크"),
    ("regulation", "규정"),
    ("directive", "지침"),
    ("standard", "표준"),
    ("standards", "표준"),
    ("policy", "정책"),
    ("policies", "정책"),
    ("report", "보고서"),
    ("roadmap", "로드맵"),
    ("blueprint", "청사진"),
    ("initiative", "이니셔티브"),
    ("programme", "프로그램"),
    ("program", "프로그램"),
    ("process", "프로세스"),
    ("systems", "시스템"),
    ("system", "시스템"),
    ("models", "모델"),
    ("model", "모델"),
    ("technologies", "기술"),
    ("technology", "기술"),
    ("organizations", "기관"),
    ("organization", "기관"),
    ("leadership", "리더십"),
    ("barriers", "장벽"),
    ("removing", "제거"),
    ("preventing", "방지"),
    ("relating", "관련"),
    ("duties of", ""),
    ("duties", "책무 —"),
    ("bill", "법안"),
    ("act", "법"),
    ("law", "법"),
    ("treaty", "조약"),
    ("convention", "협약"),
    ("agreement", "협정"),
    ("memorandum", "양해각서"),
    ("ethics", "윤리"),
    ("ethical", "윤리"),
    ("safety", "안전"),
    ("secure", "보안"),
    ("security", "안보"),
    ("governance", "거버넌스"),
    ("transparency", "투명성"),
    ("accountability", "책무성"),
    ("responsible", "책임 있는"),
    ("trustworthy", "신뢰할 수 있는"),
    ("national", "국가"),
    ("international", "국제"),
    ("federal", "연방"),
    ("amendment", "개정"),
    ("reauthorization", "재승인"),
    ("establishment", "설치"),
    ("requirements", "요건"),
    ("requirement", "요건"),
    ("modification", "수정"),
    ("improvements", "개선"),
    ("improvement", "개선"),
    ("prohibition", "금지"),
    ("notification", "통지"),
    ("assessment", "평가"),
    ("study", "연구"),
    ("education", "교육"),
    ("training", "훈련"),
    ("procurement", "조달"),
    ("acquisition", "획득"),
    ("health care", "의료"),
    ("healthcare", "의료"),
    ("algorithmic", "알고리즘"),
    ("algorithm", "알고리즘"),
    ("collusion", "담합"),
    ("deepfake", "딥페이크"),
    ("biometric", "생체인식"),
    ("autonomous", "자율"),
    ("unmanned", "무인"),
    ("weapons", "무기"),
    ("munition", "탄약"),
    ("intelligence community", "정보공동체"),
    ("officer", "책임자"),
    ("council", "이사회"),
    ("committee", "위원회"),
    ("office", "사무소"),
    ("center", "센터"),
    ("centre", "센터"),
    ("of", ""),
    ("for", ""),
    ("on", ""),
    ("to", ""),
    ("in", ""),
    ("and", "·"),
    ("the", ""),
    ("a", ""),
    ("an", ""),
    ("artificial", "인공"),
    ("intelligence", "지능"),
]

_PHRASES_SORTED = sorted(_PHRASES, key=lambda p: len(p[0]), reverse=True)

_JURIS_PREFIX = [
    (re.compile(r"^California\s+(AB|SB|HR|ACR|SCR)\s*-?\s*(\d+)", re.I), r"캘리포니아 \1 \2"),
    (re.compile(r"^Georgia\s+(HB|SB)\s*-?\s*(\d+)", re.I), r"조지아 \1 \2"),
    (re.compile(r"^New\s+York\s+(A|S|AB|SB)\s*-?\s*(\d+)", re.I), r"뉴욕 \1 \2"),
    (re.compile(r"^(?:U\.?S\.?\s+)?(?:H\.?R\.?|HR)\s*-?\s*(\d+)", re.I), r"미국 하원법안 HR \1"),
    (re.compile(r"^(?:U\.?S\.?\s+)?(?:S\.?|SB)\s*-?\s*(\d+)", re.I), r"미국 상원법안 S \1"),
]


def has_hangul(s: str) -> bool:
    return bool(_HANGUL.search(s or ""))


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "").strip()


def _replace_phrases(text: str) -> str:
    """Replace known English phrases; leave unmatched tokens mostly intact."""
    if not text:
        return text
    # Protect already-Korean spans and common acronyms by placeholder? Keep simple.
    out = text
    lower_map: list[tuple[int, int, str]] = []
    low = out.lower()
    used = [False] * len(out)
    for en, ko in _PHRASES_SORTED:
        start = 0
        while True:
            i = low.find(en, start)
            if i < 0:
                break
            j = i + len(en)
            # word-ish boundaries
            if i > 0 and (low[i - 1].isalnum() or low[i - 1] == "-"):
                start = i + 1
                continue
            if j < len(low) and (low[j].isalnum() or low[j] == "-"):
                start = i + 1
                continue
            if any(used[i:j]):
                start = i + 1
                continue
            lower_map.append((i, j, ko))
            for k in range(i, j):
                used[k] = True
            start = j
    if not lower_map:
        return out
    lower_map.sort(key=lambda x: x[0])
    parts: list[str] = []
    cursor = 0
    for i, j, ko in lower_map:
        parts.append(out[cursor:i])
        parts.append(ko)
        cursor = j
    parts.append(out[cursor:])
    gloss = "".join(parts)
    gloss = re.sub(r"\s*·\s*", " · ", gloss)
    gloss = re.sub(r"\s{2,}", " ", gloss)
    gloss = re.sub(r"\s+([,.;:)/])", r"\1", gloss)
    gloss = re.sub(r"([(])\s+", r"\1", gloss)
    gloss = re.sub(r"\s+—\s+", " — ", gloss)
    return gloss.strip(" ·")


def _translate_quoted(quote: str) -> str:
    q = _replace_phrases(quote.strip())
    return q


def title_to_ko(title: str) -> str:
    """Return a Korean display gloss. If already Hangul-heavy, return cleaned title."""
    t = _fold(title)
    if not t:
        return ""
    if has_hangul(t):
        # Strip curator bracket tags for display short names
        t = re.sub(r"^[［\[][^］\]]+[］\]]\s*", "", t).strip()
        return t

    # NDAA / compact act short names already produced upstream
    m = re.match(
        r"^(NDAA FY\d{4}|IIJA|OBBB Act(?: \d{4})?|CHIPS/R&D Act|CAA \d{4}|IAA FY\d{4}|NDAA)"
        r"(.*)$",
        t,
    )
    if m:
        head, rest = m.group(1), m.group(2)
        # Translate after em-dash quote / section descriptor
        mq = re.match(r"^(\s*§[\w\-()]+(?:\s*[—–-]\s*)?)(.*)$", rest)
        if mq:
            return f"{head}{mq.group(1)}{_translate_quoted(mq.group(2))}".strip()
        return f"{head}{_replace_phrases(rest)}".strip()

    # Bill prefixes
    for rx, repl in _JURIS_PREFIX:
        m = rx.match(t)
        if m:
            head = rx.sub(repl, t[: m.end()])
            tail = t[m.end() :]
            # "(Full Act Name)" → translate inside
            def _paren(mm: re.Match[str]) -> str:
                inner = mm.group(1)
                return f"({_replace_phrases(inner)})"

            tail = re.sub(r"\(([^)]{3,})\)", _paren, tail)
            tail = _replace_phrases(tail)
            return f"{head}{tail}".strip()

    # Section / Title patterns with leading act name
    m = re.match(
        r"^(.+?)(,\s*(?:Section|Sec\.|Title|Division)\b.*)$",
        t,
        re.I,
    )
    if m and len(m.group(1)) < 120:
        return f"{_replace_phrases(m.group(1))}{_replace_phrases(m.group(2))}".strip()

    return _replace_phrases(t)


def pick_original_title(candidates: list[str], korean_title: str = "") -> str:
    """Choose a source-language full title distinct from the Korean display name."""
    ko = _fold(korean_title)
    seen = set()
    best_en = ""
    best_other = ""
    for raw in candidates:
        t = _fold(raw)
        if not t or t in seen:
            continue
        seen.add(t)
        if ko and (t == ko or t in ko or ko in t):
            continue
        if has_hangul(t):
            continue
        # Prefer Latin/English-looking titles as "원문"
        if re.search(r"[A-Za-z]{3}", t):
            if not best_en or len(t) > len(best_en):
                best_en = t
        elif not best_other:
            best_other = t
    return best_en or best_other


def resolve_display_titles(
    *,
    short_hint: str,
    full_hint: str,
    member_titles: list[str],
    original_names: list[str],
) -> tuple[str, str, str]:
    """Return (short_ko, full_ko, original).

    short_ko: primary Korean card title
    full_ko: optional longer Korean name (empty if redundant)
    original: source-language full title shown underneath
    """
    short = _fold(short_hint)
    full = _fold(full_hint)
    hangul_candidates = [t for t in [short, full, *member_titles] if has_hangul(t)]
    if hangul_candidates:
        hangul_candidates.sort(key=lambda s: (len(s), s))
        short_ko = hangul_candidates[0]
        full_ko = ""
        for t in sorted(set(hangul_candidates), key=len, reverse=True):
            if t == short_ko:
                continue
            if len(t) > len(short_ko) + 6:
                full_ko = t
                break
    else:
        base = short or full or next((t for t in member_titles if t), "")
        short_ko = title_to_ko(base)
        full_ko = ""
        if full and full != short:
            full_try = title_to_ko(full)
            if has_hangul(full_try) and full_try != short_ko:
                full_ko = full_try

    original = pick_original_title(
        [*original_names, *member_titles, full_hint, short_hint],
        korean_title=short_ko,
    )
    # Never treat non-Hangul as Korean full name
    if full_ko and not has_hangul(full_ko):
        if not original:
            original = full_ko
        full_ko = ""
    if full_ko and (full_ko == short_ko or full_ko in short_ko or short_ko in full_ko):
        full_ko = ""
    if original and (original == short_ko or original == full_ko):
        original = ""
    # If short still has little Hangul, keep it but ensure original is the English source
    if short_ko and not has_hangul(short_ko) and not original:
        original = short or full or next((t for t in member_titles if t), "")
        if original == short_ko:
            original = ""
    return short_ko, full_ko, original
