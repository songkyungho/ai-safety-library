#!/usr/bin/env python3
"""Build the library static site (canonical documents + publish history)."""
from __future__ import annotations

import html as html_lib
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_documents import build_documents  # noqa: E402
from curate_llm import is_hollow_summary  # noqa: E402
from issuer_levels import ISSUER_COLORS, ISSUER_LEVELS  # noqa: E402
from library_common import write_json  # noqa: E402
from ui_common import page_chrome, safe_json  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# GitHub Pages는 저장소의 / 또는 /docs 만 소스로 허용 → 공개 HTML은 docs/
DOCS = ROOT / "docs"
DIST = DOCS  # 하위 호환 이름
DIST_MIRROR = ROOT / "dist"  # 로컬·기존 경로용 미러
TODAY = date.today().isoformat()

FOOTER_HTML = (
    '<footer class="site-footer">'
    "AI 안전 라이브러리 · 만든 사람: 인공지능안전연구소(Korea AISI) 송경호 · "
    '<a href="mailto:songkyungho@etri.re.kr">songkyungho@etri.re.kr</a><br>'
    "원본 랜딩 URL 기준 · 발표 히스토리 · AGORA CC BY-NC 4.0"
    "</footer>"
)
# 문서종류 칩 색 (라이트). 동향 시리즈 톤과 맞추되 헤더 네이비는 슬레이트 계열.
# Digest tokens: navy #474284 · gold #f3b84f · accent #ef3837 · sage #3f5340 · rose #b44a58
KIND_COLORS = {
    "법": ("#1d4ed8", "#93c5fd"),          # topic-law
    "법안": ("#be123c", "#fb7185"),        # topic-politics
    "행정규칙": ("#0369a1", "#7dd3fc"),    # topic-cybersecurity
    "조약·협약": ("#3d3a6e", "#b8b4d0"),  # cat-intl / archive
    "선언·성명": ("#a16207", "#fbbf24"),  # topic-norms / gold
    "가이드라인·원칙": ("#0f766e", "#5eead4"),  # topic-guideline
    "전략·정책": ("#c2410c", "#fdba8c"),  # topic-frontier
    "정책보고서": ("#474284", "#b0acd8"),  # cat-research / navy
    "표준": ("#7c3aed", "#c4b5fd"),        # topic-standards
    "기구·제도": ("#3f5340", "#9bb396"),  # cat-gov / sage
    "뉴스·보도": ("#b44a58", "#ed7787"),  # cat-notice / accent-rose
    "기타": ("#534f4a", "#c4bdb4"),        # cat-other
}
KIND_SLUG = {
    "법": "law",
    "법안": "bill",
    "행정규칙": "admin",
    "조약·협약": "treaty",
    "선언·성명": "declaration",
    "가이드라인·원칙": "guideline",
    "전략·정책": "strategy",
    "정책보고서": "report",
    "표준": "standard",
    "기구·제도": "institution",
    "뉴스·보도": "news",
    "기타": "other",
}

# AI 안전 핵심 키워드 (표시 라벨, 매칭 패턴). 순서 = 우선순위.
# 본문 강조용 전체 목록. 카드 태그는 TAG_* 규칙으로 더 좁힌다.
KEYWORD_RULES: list[tuple[str, list[str]]] = [
    ("AI 안전", [r"ai\s*safety", r"인공지능\s*안전", r"AI\s*안전"]),
    ("안전성", [r"안전성", r"\bsafety\b", r"safe\s*ai"]),
    ("프론티어", [r"프론티어", r"frontier"]),
    ("정렬", [r"\balignment\b", r"정렬"]),
    ("레드팀", [r"red\s*team", r"레드팀"]),
    ("위험관리", [r"위험\s*관리", r"위험관리", r"risk\s*management", r"high[-\s]?risk", r"고위험"]),
    ("거버넌스", [r"governan", r"거버넌스"]),
    ("프레임워크", [r"프레임워크", r"framework"]),
    ("투명성", [r"투명성", r"transpar"]),
    ("설명가능성", [r"설명\s*가능", r"explainab"]),
    ("책무성", [r"책무", r"accountability", r"책임\s*있는\s*AI", r"responsible\s*ai"]),
    ("공정성", [r"공정성", r"fairness", r"편향", r"\bbias\b", r"차별"]),
    ("개인정보", [r"개인정보", r"privacy", r"data\s*protection"]),
    ("평가", [r"영향\s*평가", r"적합성\s*평가", r"평가", r"evaluat", r"audit", r"감사", r"benchmark", r"적합성"]),
    ("가이드라인", [r"가이드라인", r"guideline", r"(?<![a-z])guidance(?![a-z])", r"지침"]),
    ("표준", [r"\bstandard", r"표준", r"iso/?iec"]),
    ("규제", [r"regulat", r"규제"]),
    ("윤리", [r"ethic", r"윤리"]),
    ("보안", [r"\bsecurit", r"보안", r"cybersecurity", r"사이버보안"]),
    ("사고", [r"incident", r"사고"]),
    ("딥페이크", [r"deepfake", r"딥페이크", r"합성\s*미디어"]),
    ("오픈웨이트", [r"open[-\s]?weight", r"오픈\s*웨이트", r"오픈소스\s*모델"]),
    ("가드레일", [r"guardrail", r"가드레일", r"안전장치"]),
    ("인권", [r"human\s*rights", r"인권"]),
    ("신뢰", [r"trustworth", r"신뢰\s*가능", r"신뢰할\s*수\s*있는"]),
    ("의무·금지", [r"의무화", r"금지", r"의무\s*부과", r"사전\s*승인"]),
]

# 분류(doc_kind)·주제 리본과 겹치거나 이 라이브러리에서 너무 흔한 태그 → 카드에 안 씀
TAG_ALWAYS_DROP = {
    "AI 안전",
    "안전성",
    "가이드라인",
    "윤리",
    "평가",
    "프레임워크",
    "거버넌스",
}
# 주제 리본이 있으면 같은 뜻의 태그 숨김
TAG_DROP_IF_TOPIC: dict[str, frozenset[str]] = {
    "프론티어": frozenset({"frontier"}),
    "표준": frozenset({"standards"}),
    "규제": frozenset({"law"}),
    "보안": frozenset({"cybersecurity", "national_security"}),
    "사고": frozenset({"incidents"}),
    "딥페이크": frozenset({"deepfake_disinfo"}),
    "오픈웨이트": frozenset({"open_weight"}),
}
# 문서종류와 겹치면 숨김
TAG_DROP_IF_KIND: dict[str, frozenset[str]] = {
    "표준": frozenset({"표준"}),
    "규제": frozenset({"법", "법안", "행정규칙"}),
    "가이드라인": frozenset({"가이드라인·원칙"}),
}

# 상세 본문 강조: 종류·주체 → 밑줄(name), 주제 → 볼드(em).
# 약어는 영숫자 경계만 막아 한국어 조사(에/을 등)와도 매칭되게 한다.
_ACRO = r"(?<![A-Za-z0-9]){0}(?![A-Za-z0-9])"
# 고유 문건명(종류에 가깝게 밑줄).
EMPHASIS_INSTRUMENT_PATTERNS: list[str] = [
    r"EU\s*AI\s*Act",
    r"AI\s*Act",
    r"AI\s*기본법",
    r"인공지능\s*기본법",
    r"Responsible\s*Scaling\s*Policy",
    _ACRO.format(r"RSP"),
    r"Preparedness\s*Framework",
    r"Frontier\s*Safety\s*Framework",
    _ACRO.format(r"FSF"),
    r"AI\s*Safety\s*Framework",
    _ACRO.format(r"ASF"),
    r"Kakao\s*ASI|Kakao\s*AI\s*Safety\s*Initiative",
    _ACRO.format(r"ASTRI"),
    r"NIST\s*AI\s*RMF",
    r"Hiroshima\s*Process|히로시마\s*프로세스",
    r"Bletchley|블레츨리|블레출리",
    _ACRO.format(r"GPAI"),
    r"ASL[-\s]?\d",
    r"CCL[-\s]?\d?",
]
# 문서 종류 키워드 → 밑줄. 긴 표현이 앞에 오도록 둔다.
EMPHASIS_KIND_PATTERNS: list[str] = [
    r"정책보고서",
    r"행정규칙",
    r"시행규칙",
    r"시행령",
    r"법률안",
    r"기본법",
    r"가이드라인",
    r"가이드북",
    r"권고안",
    r"모범사례",
    r"규제샌드박스",
    r"법제화",
    r"제정안",
    r"개정안",
    r"법령",
    r"법률",
    r"법안",
    r"조약",
    r"협약",
    r"선언문",
    r"선언",
    r"성명",
    r"지침",
    r"전략",
    r"표준화",
    r"표준",
    r"규제",
    r"입법",
    r"정책",
    r"(?<![가-힣])법(?![가-힣])",
    r"guidelines?",
    r"code of (?:practice|conduct)",
    r"executive orders?",
    r"regulatory framework",
    r"legislation",
    r"regulations?",
    r"statutes?",
    r"(?<![A-Za-z])bills?(?![A-Za-z])",
    r"treat(?:y|ies)",
    r"conventions?",
    r"declarations?",
    r"strateg(?:y|ies)",
    r"polic(?:y|ies)",
    r"standards?",
]
# 지방·규제기관 등 주체 고유명(국가명은 emphasis_rules_for_js에서 합친다).
EMPHASIS_SUBJECT_EXTRA: list[str] = [
    r"과학기술정보통신부",
    r"개인정보보호위원회",
    r"한국지능정보사회진흥원",
    r"국가인공지능위원회",
    r"유럽연합\s*집행위원회",
    r"방송통신위원회",
    r"산업통상자원부",
    r"공정거래위원회",
    r"행정안전부",
    r"보건복지부",
    r"국가정보원",
    r"과기정통부",
    r"규제당국",
    r"규제기관",
    r"감독기관",
    r"집행위원회",
    r"유럽의회",
    r"유럽연합",
    r"유럽평의회",
    r"인공지능안전연구소",
    r"외교부",
    r"교육부",
    r"국방부",
    r"과기부",
    r"개보위",
    r"방통위",
    r"산업부",
    r"행안부",
    r"내각부",
    r"헌법재판소",
    r"대법원",
    r"국회",
    r"의회",
    r"캘리포니아",
    r"콜로라도",
    r"일리노이",
    r"텍사스",
    r"뉴욕주",
    r"워싱턴주",
    r"경기도",
    r"서울시",
    r"베이징",
    r"상하이",
    r"도쿄",
    r"오사카",
    r"부산",
    r"서울",
    r"뉴욕",
    r"European Commission",
    r"Council of Europe",
    r"EU AI Office",
    r"AI Office",
    r"State of California",
    r"New York",
    r"California",
    r"Colorado",
    r"Illinois",
    r"Texas",
    r"Congress",
    _ACRO.format(r"NIST"),
    _ACRO.format(r"NTIA"),
    _ACRO.format(r"CISA"),
    _ACRO.format(r"FTC"),
    _ACRO.format(r"FCC"),
    _ACRO.format(r"FDA"),
    _ACRO.format(r"ICO"),
    _ACRO.format(r"CNIL"),
    r"(?<![A-Za-z])Ofcom(?![A-Za-z])",
]
# 주제 키워드 → 볼드. 종류·주체와 겹치는 법/가이드라인/표준/국가명은 넣지 않는다.
EMPHASIS_TOPIC_EXTRA: list[str] = [
    r"딥페이크\s*성범죄",
    r"딥페이크",
    r"허위조작정보",
    r"허위정보",
    r"가짜뉴스",
    r"합성미디어",
    r"합성\s*미디어",
    r"음성복제",
    r"피지컬\s*AI",
    r"피지컬AI",
    r"물리적\s*AI",
    r"소버린\s*AI",
    r"소버린AI",
    r"주권\s*AI",
    r"주권AI",
    r"데이터주권",
    r"디지털주권",
    r"에이전틱\s*AI",
    r"에이전틱AI",
    r"에이전틱",
    r"AI\s*에이전트",
    r"자율\s*에이전트",
    r"멀티에이전트",
    r"휴머노이드",
    r"로보틱스",
    r"자율주행",
    r"오픈소스\s*AI",
    r"오픈소스\s*모델",
    r"오픈웨이트",
    r"오픈모델",
    r"사이버안보",
    r"사이버보안",
    r"국가안보",
    r"윤리\s*원칙",
    r"윤리\s*규범",
    r"AI\s*윤리",
    r"프론티어\s*모델",
    r"프론티어\s*AI",
    r"레드티밍",
    r"의료AI",
    r"헬스케어",
    r"deepfakes?",
    r"disinformation",
    r"misinformation",
    r"synthetic media",
    r"physical AI",
    r"embodied AI",
    r"sovereign AI",
    r"AI sovereignty",
    r"digital sovereignty",
    r"agentic AI",
    r"AI agents?",
    r"humanoid",
    r"\brobotics\b",
    r"open[-\s]?weight",
    r"cybersecurity",
    r"national security",
]
# 카드 태그용 개념어 중 종류 키워드는 본문에서 밑줄로 돌린다.
_KEYWORD_AS_KIND = {"가이드라인", "표준", "규제"}

_KEYWORD_COMPILED = [
    (label, [re.compile(p, re.I) for p in pats]) for label, pats in KEYWORD_RULES
]


def _country_subject_patterns() -> list[str]:
    """국가·국제기구 표기 → 밑줄. 짧은 한국어 오탐은 후방/전방 탐색으로 막는다."""
    from library_common import COUNTRY_KO, ORG_FLAGS, TITLE_COUNTRY

    special = {
        "한국": r"한국(?!어)",
        "인도": r"인도(?![적주의화하네])",
        "오만": r"오만(?![한함])",
        "가나": r"가나(?![능히])",
        "이란": r"이란(?![가-힣])",
        "멕시코": r"(?<!뉴)멕시코",
        "아일랜드": r"(?<!로드)아일랜드",
    }
    ko_names: list[str] = []
    en_lits: list[str] = []
    en_acro: list[str] = []
    seen: set[str] = set()

    def _add_en(name: str) -> None:
        if not name or name in seen or name == "International":
            return
        seen.add(name)
        if re.fullmatch(r"[A-Z0-9]{2,5}", name):
            en_acro.append(re.escape(name))
        else:
            en_lits.append(re.escape(name))

    for name in list(TITLE_COUNTRY.keys()) + list(COUNTRY_KO.values()):
        name = (name or "").strip()
        if not name or name in seen:
            continue
        if re.fullmatch(r"[A-Za-z0-9 .'-]+", name):
            _add_en(name)
            continue
        seen.add(name)
        ko_names.append(special.get(name, re.escape(name)))
    ko_names.sort(key=len, reverse=True)

    for name in list(COUNTRY_KO.keys()) + list(ORG_FLAGS.keys()):
        _add_en((name or "").strip())
    en_lits.sort(key=len, reverse=True)
    out: list[str] = []
    if ko_names:
        out.append("(?:%s)" % "|".join(ko_names))
    if en_lits:
        out.append(rf"(?<![A-Za-z])(?:{'|'.join(en_lits)})(?![A-Za-z])")
    if en_acro:
        out.append(_ACRO.format("(?:%s)" % "|".join(en_acro)))
    return out


def emphasis_rules_for_js() -> list[dict]:
    """프론트엔드 본문 강조용. 종류·주체(name/밑줄)가 주제(em/볼드)보다 우선."""
    rules: list[dict] = []
    for pat in EMPHASIS_INSTRUMENT_PATTERNS:
        rules.append({"re": pat, "style": "name"})
    rules.append({"re": "(?:%s)" % "|".join(EMPHASIS_KIND_PATTERNS), "style": "name"})
    rules.append({"re": "(?:%s)" % "|".join(EMPHASIS_SUBJECT_EXTRA), "style": "name"})
    for pat in _country_subject_patterns():
        rules.append({"re": pat, "style": "name"})
    for label, pats in KEYWORD_RULES:
        if label in _KEYWORD_AS_KIND:
            continue
        for pat in pats:
            rules.append({"re": pat, "style": "em"})
    rules.append({"re": "(?:%s)" % "|".join(EMPHASIS_TOPIC_EXTRA), "style": "em"})
    return rules


def extract_keywords(*parts: str, limit: int = 8) -> list[str]:
    hay = " ".join(p for p in parts if p)
    if not hay:
        return []
    out: list[str] = []
    for label, regs in _KEYWORD_COMPILED:
        if any(r.search(hay) for r in regs):
            out.append(label)
            if len(out) >= limit:
                break
    return out


def _topic_ids(doc: dict) -> set[str]:
    ids: set[str] = set()
    for t in doc.get("topics") or []:
        if isinstance(t, dict) and t.get("id"):
            ids.add(str(t["id"]))
        elif isinstance(t, str):
            ids.add(t)
    return ids


def select_tag_keywords(doc: dict, *, limit: int = 5) -> list[str]:
    """카드용 태그: 분류·주제 리본과 겹치지 않는 신호만."""
    # doc_kind는 매칭 원문에 넣지 않음(종류명이 태그로 새는 것 방지)
    found = extract_keywords(
        doc.get("summary") or "",
        doc.get("snippet") or "",
        doc.get("short_name") or "",
        doc.get("full_name") or "",
        doc.get("original_name") or "",
        doc.get("title") or "",
        doc.get("org") or "",
        limit=24,
    )
    topics = _topic_ids(doc)
    kind = (doc.get("doc_kind") or "").strip()
    out: list[str] = []
    for label in found:
        if label in TAG_ALWAYS_DROP:
            continue
        drop_topics = TAG_DROP_IF_TOPIC.get(label)
        if drop_topics and topics & drop_topics:
            continue
        drop_kinds = TAG_DROP_IF_KIND.get(label)
        if drop_kinds and kind in drop_kinds:
            continue
        out.append(label)
        if len(out) >= limit:
            break
    return out


def enrich_keywords(docs: list[dict]) -> list[dict]:
    for d in docs:
        d["keywords"] = select_tag_keywords(d)
    return docs


def render_kind_trend(docs: list[dict], *, from_year: int = 2017) -> str:
    """문서종류별 연간 건수 누적 막대. from_year 미만은 한 막대로 묶음."""
    from parse_meta import DOC_KINDS

    by_key: dict[str, Counter] = {}
    kind_totals: Counter = Counter()
    pre_label = f"{from_year} 이전"
    year_hi = 0
    for d in docs:
        pub = (d.get("published") or "").strip()
        y = pub[:4]
        if len(y) != 4 or not y.isdigit():
            continue
        yi = int(y)
        kind = d.get("doc_kind") or "기타"
        if yi < from_year:
            key = pre_label
        else:
            key = y
            if yi > year_hi:
                year_hi = yi
        by_key.setdefault(key, Counter())[kind] += 1
        kind_totals[kind] += 1
    if not by_key:
        return ""

    keys: list[str] = []
    if pre_label in by_key:
        keys.append(pre_label)
    if year_hi:
        keys.extend(f"{y:04d}" for y in range(from_year, year_hi + 1))
    elif not keys:
        return ""

    series = [k for k in DOC_KINDS if kind_totals.get(k)]
    if not series:
        return ""

    pad_l, pad_r, pad_t, pad_b = 42, 6, 10, 24
    plot_h = 200
    n = len(keys)
    slot = 48 if n <= 14 else (36 if n <= 20 else 28)
    plot_w = max(560, int(n * slot))
    w, h = pad_l + plot_w + pad_r, pad_t + plot_h + pad_b
    peak = max((sum(by_key.get(k, Counter()).values()) for k in keys), default=1)
    y_max = max(1, int(((peak + 4) // 5) * 5))
    if y_max < peak:
        y_max = peak
    slot_w = plot_w / n
    bar_w = max(12.0, slot_w * 0.62)

    def y_of(v: float) -> float:
        return pad_t + plot_h - (v / y_max) * plot_h

    parts: list[str] = [
        f'<svg class="trend-svg" viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="문서종류별 연간 발표 건수">'
    ]
    for g in range(5):
        gy = pad_t + plot_h * g / 4
        val = y_max * (4 - g) / 4
        parts.append(
            f'<line x1="{pad_l}" x2="{w - pad_r}" y1="{gy:.1f}" y2="{gy:.1f}" '
            f'class="trend-grid" />'
            f'<text x="{pad_l - 6}" y="{gy + 3:.1f}" class="trend-axis" '
            f'text-anchor="end">{val:.0f}</text>'
        )

    for i, key in enumerate(keys):
        x = pad_l + i * slot_w + (slot_w - bar_w) / 2
        counts = by_key.get(key, Counter())
        cum = 0
        for kind in series:
            v = int(counts.get(kind) or 0)
            if v <= 0:
                continue
            y1, y2 = y_of(cum + v), y_of(cum)
            color = KIND_COLORS.get(kind, KIND_COLORS["기타"])[0]
            tip = f"{key} · {kind}: {v}건"
            parts.append(
                f'<rect x="{x:.1f}" y="{y1:.1f}" width="{bar_w:.1f}" '
                f'height="{max(0.5, y2 - y1):.1f}" '
                f'fill="{html_lib.escape(color, quote=True)}">'
                f"<title>{html_lib.escape(tip)}</title>"
                f"</rect>"
            )
            cum += v

        parts.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{h - 4}" class="trend-axis" '
            f'text-anchor="middle">{html_lib.escape(key)}</text>'
        )
    parts.append("</svg>")

    legend = []
    for kind in series:
        color = KIND_COLORS.get(kind, KIND_COLORS["기타"])[0]
        legend.append(
            f'<span class="trend-legend-item">'
            f'<span class="trend-swatch" style="background:{html_lib.escape(color, quote=True)}"></span>'
            f"{html_lib.escape(kind)}"
            f'<span class="n">{kind_totals[kind]}</span></span>'
        )
    if pre_label in keys and year_hi:
        span = f"{pre_label} + {from_year}–{year_hi}"
    elif year_hi:
        span = f"{from_year}–{year_hi}"
    else:
        span = pre_label
    return f"""<section class="trend-section">
  <h2 class="trend-title">문서종류별 연간 추이</h2>
  <div class="trend-sub">{html_lib.escape(span)} · 연별 누적 건수</div>
  <div class="trend-chart-wrap">{"".join(parts)}</div>
  <div class="trend-legend">{"".join(legend)}</div>
</section>"""


EXTRA_CSS = """
/* 지면 토큰은 ui_common.NAV_CSS(:root) — 라이트 전용, 동향과 같은 시리즈·살짝 식힌 팔레트 */
.viz-root {
  background: var(--plane);
  color: var(--ink);
  font-family: "IBM Plex Sans KR", "IBM Plex Sans", -apple-system, BlinkMacSystemFont,
    "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
}
a { color: var(--sage, #3f5340); }
a:hover { color: var(--accent); }
.timeline { position: relative; padding-left: 20px; }
.timeline::before { content: ""; position: absolute; left: 4px; top: 6px; bottom: 6px; width: 2px; background: var(--baseline); }
.year-group { margin-bottom: 8px; scroll-margin-top: 56px; }
.year-header {
  cursor: pointer; font: inherit; font-weight: 600; font-size: 17px; letter-spacing: -0.37px;
  padding: 8px 0; color: var(--ink); user-select: none;
  background: transparent; border: 0; width: 100%; text-align: left;
}
.year-header .muted { font-weight: 400; margin-left: 4px; color: var(--text-muted); }
.event-card, .year-header, .dir-row, .year-nav-item { font: inherit; color: inherit; }
.event-card { background: var(--surface-1); }
button.dir-row { cursor: pointer; background: var(--surface-1); }
.event-card { border: 1px solid var(--hairline); border-radius: 14px; display: block; }
button.back-link { font: inherit; background: none; border: 0; padding: 0; }
.year-nav {
  position: fixed; right: 16px; top: 50%;
  transform: translateY(-50%); z-index: 40;
  display: flex; flex-direction: column; gap: 2px;
  max-height: 70vh; overflow-y: auto; padding: 8px 6px;
  border: 1px solid var(--hairline); border-radius: 12px;
  background: color-mix(in srgb, var(--surface-1) 92%, transparent);
  backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
  box-shadow: 0 4px 20px color-mix(in srgb, var(--ink) 8%, transparent);
}
.year-nav.hidden { display: none; }
.year-nav-item {
  appearance: none; border: 0; background: transparent; cursor: pointer;
  padding: 4px 8px; border-radius: 8px; font-size: 12px;
  font-variant-numeric: tabular-nums; color: var(--text-muted);
  text-align: center; line-height: 1.2;
}
.year-nav-item:hover { color: var(--ink); background: color-mix(in srgb, var(--ink) 6%, transparent); }
.year-nav-item.active { color: var(--ink); font-weight: 600; }
@media (max-width: 960px) {
  .year-nav { right: 10px; padding: 6px 4px; }
  .year-nav-item { padding: 3px 6px; font-size: 11px; }
}
@media (max-width: 720px) {
  .year-nav { display: none; }
}
.event-card { position: relative; padding: 16px 18px; margin-bottom: 12px; }
.event-card::before { content: ""; position: absolute; left: -20px; top: 18px; width: 10px; height: 10px; border-radius: 50%; background: var(--c-l); border: 2px solid var(--plane); }
.event-head { display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; margin-bottom: 4px; }
.event-date { font-variant-numeric: tabular-nums; color: var(--text-muted); font-size: 12px; }
.event-summary { margin: 6px 0; font-size: 17px; line-height: 1.47; letter-spacing: -0.37px; }
.event-summary .event-title {
  font-weight: 700;
}
.event-summary a.event-title {
  color: #1d4ed8;
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 3px;
}
.event-summary a.event-title:hover,
.event-summary a.event-title:focus-visible {
  color: #1e40af;
}
.event-body { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--hairline); }
.event-body p { margin: 0; font-size: 14px; line-height: 1.55; color: var(--text-secondary); white-space: pre-wrap; }
.event-body .term-em {
  font-weight: 650; color: var(--ink);
}
.event-body .term-name {
  font-weight: inherit; color: inherit;
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 3px;
  text-decoration-color: color-mix(in srgb, var(--c-l, var(--ink)) 55%, transparent);
}
a.stat-tile, a.dir-row, a.filter-chip { text-decoration: none; color: inherit; }
.dir-row .org { min-width: 0; flex: 1 1 240px; }
#listControls {
  margin: 0 0 20px;
}
.filter-toolbar {
  display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
  margin: 0;
  padding: 10px 0;
  border-bottom: 1px solid var(--hairline);
}
#listControls .filter-toolbar:last-child { border-bottom: 0; padding-bottom: 0; }
#listControls .filter-toolbar:first-child { padding-top: 0; }
.filter-label {
  flex: 0 0 auto;
  min-width: 2.4em;
  margin-right: 4px;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  letter-spacing: -0.02em;
  white-space: nowrap;
}
a.filter-chip, button.filter-chip {
  display: inline-flex; align-items: center; gap: 5px;
  border: 1px solid var(--hairline); background: transparent;
  color: var(--text-secondary); border-radius: 999px;
  padding: 3px 10px; font: inherit; font-size: 12px; line-height: 1.35;
  cursor: pointer; white-space: nowrap;
}
a.filter-chip:hover, button.filter-chip:hover { color: var(--ink); border-color: var(--text-muted); }
a.filter-chip .n, button.filter-chip .n {
  font-variant-numeric: tabular-nums; color: var(--text-muted); font-size: 11px;
}
a.filter-chip.kind-badge, button.filter-chip.kind-badge {
  background: color-mix(in srgb, var(--chip) 14%, var(--surface-1));
  color: var(--chip);
  border-color: color-mix(in srgb, var(--chip) 32%, var(--hairline));
  font-weight: 600;
}
a.filter-chip.kind-badge .n, button.filter-chip.kind-badge .n {
  color: color-mix(in srgb, var(--chip) 65%, var(--text-muted));
}
button.filter-more {
  border: 1px dashed var(--hairline); background: transparent;
  color: var(--text-muted); border-radius: 999px;
  padding: 3px 10px; font: inherit; font-size: 12px; cursor: pointer;
}
button.filter-more:hover { color: var(--ink); border-color: var(--text-muted); }
.filter-toolbar .filter-more-wrap { display: contents; }
.filter-toolbar .filter-more-wrap.hidden { display: none; }
.sort-toggle.filter-toolbar { display: flex; }
.sort-toggle.filter-toolbar button.filter-chip,
.sort-toggle.filter-toolbar button.filter-more {
  border-radius: 999px; padding: 3px 10px; font-size: 12px;
  background: transparent;
}
.sort-toggle.filter-toolbar button.filter-chip.kind-badge {
  background: color-mix(in srgb, var(--chip) 14%, var(--surface-1));
}
.sort-toggle.filter-toolbar button.active {
  border-color: var(--navy, var(--accent-focus));
  color: var(--navy, var(--accent-focus));
  font-weight: 600;
  background: color-mix(in srgb, var(--gold, #f3b84f) 22%, var(--surface-1));
}
.badge.kind-badge {
  font-size: 11px; font-weight: 600; border-radius: 999px; padding: 2px 8px;
  background: color-mix(in srgb, var(--chip) 14%, var(--surface-1));
  color: var(--chip);
  border: 1px solid color-mix(in srgb, var(--chip) 32%, var(--hairline));
}
.event-summary .status-badge {
  display: inline-block; vertical-align: middle; margin-left: 8px;
  font-size: 11px; font-weight: 500; letter-spacing: -0.02em;
  padding: 1px 7px; border-radius: 6px; white-space: nowrap;
  border: 1px solid var(--hairline); color: var(--text-secondary); background: var(--surface-1);
}
.event-summary .status-badge.status-enacted {
  color: #1d4ed8; border-color: color-mix(in srgb, #1d4ed8 28%, var(--hairline));
  background: color-mix(in srgb, #1d4ed8 8%, var(--surface-1));
}
.event-summary .status-badge.status-amended {
  color: #a16207; border-color: color-mix(in srgb, #a16207 28%, var(--hairline));
  background: color-mix(in srgb, #a16207 8%, var(--surface-1));
}
.event-summary .status-badge.status-pending {
  color: #be123c; border-color: color-mix(in srgb, #be123c 28%, var(--hairline));
  background: color-mix(in srgb, #be123c 8%, var(--surface-1));
}
.event-summary .status-badge.status-defunct {
  color: #6b7280; border-color: color-mix(in srgb, #6b7280 28%, var(--hairline));
  background: color-mix(in srgb, #6b7280 8%, var(--surface-1));
}
.badge.kind-law, .filter-chip.kind-law { --chip: #1d4ed8; }
.badge.kind-bill, .filter-chip.kind-bill { --chip: #be123c; }
.badge.kind-admin, .filter-chip.kind-admin { --chip: #0369a1; }
.badge.kind-treaty, .filter-chip.kind-treaty { --chip: #3d3a6e; }
.badge.kind-declaration, .filter-chip.kind-declaration { --chip: #a16207; }
.badge.kind-guideline, .filter-chip.kind-guideline { --chip: #0f766e; }
.badge.kind-strategy, .filter-chip.kind-strategy { --chip: #c2410c; }
.badge.kind-report, .filter-chip.kind-report { --chip: #474284; }
.badge.kind-standard, .filter-chip.kind-standard { --chip: #7c3aed; }
.badge.kind-institution, .filter-chip.kind-institution { --chip: #3f5340; }
.badge.kind-news, .filter-chip.kind-news { --chip: #b44a58; }
.badge.kind-other, .filter-chip.kind-other { --chip: #534f4a; }
.thread-item { border-left: 2px solid var(--gridline); padding: 4px 0 14px 14px; margin-bottom: 4px; position: relative; }
.thread-item::before { content: ""; position: absolute; left: -5px; top: 6px; width: 8px; height: 8px; border-radius: 50%; background: var(--text-muted); }
.thread-date { font-size: 12px; color: var(--text-muted); font-variant-numeric: tabular-nums; }
.thread-summary { margin: 4px 0; font-size: 14px; }
.detail .sub { color: var(--text-secondary); font-size: 14px; margin-bottom: 18px; }
.flag-inline { margin-right: 6px; }
.country-chip { font-size: 12px; color: var(--text-secondary); }
.event-full { margin-top: 2px; font-size: 13px; line-height: 1.4; }
.original-name { font-style: normal; opacity: 0.85; }
.meta-table th { width: 7em; vertical-align: top; color: var(--text-secondary); font-weight: 500; }
.meta-table td { white-space: pre-wrap; }

.trend-section { margin: 0 0 24px; padding-bottom: 16px; border-bottom: 1px solid var(--hairline); }
.trend-title { font-size: 1.05rem; letter-spacing: -0.3px; margin: 0 0 2px; color: var(--ink); }
.trend-sub { color: var(--text-muted); font-size: 0.82rem; margin-bottom: 10px; }
.trend-legend {
  display: flex; flex-wrap: wrap; gap: 8px 14px; margin-top: 10px;
  font-size: 0.75rem; color: var(--text-muted);
}
.trend-legend-item { display: inline-flex; align-items: center; gap: 6px; }
.trend-legend-item .n { font-variant-numeric: tabular-nums; opacity: 0.8; }
.trend-swatch { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.trend-chart-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
.trend-svg { display: block; width: 100%; min-width: 640px; height: auto; }
.trend-grid { stroke: var(--baseline); stroke-width: 1; }
.trend-axis { fill: var(--text-muted); font-size: 9px; font-family: inherit; }
.trend-svg rect { rx: 2; }
.sort-toggle.filter-toolbar button.filter-chip.active {
  border-color: var(--navy, var(--accent-focus));
  color: var(--navy, var(--accent-focus));
  background: color-mix(in srgb, var(--gold, #f3b84f) 22%, var(--surface-1));
}
.ribbon-row {
  display: flex; flex-wrap: nowrap; gap: 5px; margin-top: 8px; align-items: center;
  overflow-x: auto; -webkit-overflow-scrolling: touch;
}
.ribbon-row > * { flex-shrink: 0; }
.kw-tag {
  display: inline-flex; align-items: center;
  border: 1px solid var(--hairline); border-radius: 999px;
  padding: 2px 8px; font-size: 11px; color: var(--text-secondary);
  background: color-mix(in srgb, var(--surface-2, var(--surface-1)) 80%, transparent);
}
.topic-tag {
  display: inline-flex; align-items: center; gap: 3px;
  border-radius: 999px; padding: 2px 8px; font-size: 11px; font-weight: 600;
  color: var(--topic); border: 1px solid color-mix(in srgb, var(--topic) 35%, var(--hairline));
  background: color-mix(in srgb, var(--topic) 12%, var(--surface-1));
}

.filter-chip.issuer-chip {
  color: var(--issuer); border-color: color-mix(in srgb, var(--issuer) 35%, var(--hairline));
  background: color-mix(in srgb, var(--issuer) 12%, var(--surface-1)); font-weight: 600;
}
.filter-chip.issuer-chip .n {
  color: color-mix(in srgb, var(--issuer) 65%, var(--text-muted));
}
.sort-toggle.filter-toolbar button.filter-chip.issuer-chip.active {
  border-color: var(--issuer); color: var(--issuer);
}
.issuer-badge {
  display: inline-flex; align-items: center;
  border-radius: 999px; padding: 2px 8px; font-size: 11px; font-weight: 600;
  color: var(--issuer); border: 1px solid color-mix(in srgb, var(--issuer) 35%, var(--hairline));
  background: color-mix(in srgb, var(--issuer) 12%, var(--surface-1));
}

button.filter-chip.topic-chip {
  color: var(--topic); border-color: color-mix(in srgb, var(--topic) 32%, var(--hairline));
  background: color-mix(in srgb, var(--topic) 12%, var(--surface-1)); font-weight: 600;
}
button.filter-chip.topic-chip .n {
  color: color-mix(in srgb, var(--topic) 65%, var(--text-muted));
}
.sort-toggle.filter-toolbar button.filter-chip.topic-chip.active {
  border-color: var(--topic); color: var(--topic);
}
"""


def kind_slug(kind: str) -> str:
    return KIND_SLUG.get(kind or "", "other")


def strip_hollow_summaries(docs: list[dict]) -> int:
    """의미 없는 설명만 비움. 카드·in_scope는 유지."""
    n = 0
    for d in docs:
        cleared = False
        for key in ("summary", "snippet"):
            val = str(d.get(key) or "")
            if val and is_hollow_summary(val):
                d[key] = ""
                cleared = True
        if cleared:
            n += 1
            if not (d.get("summary") or "").strip():
                d["snippet"] = ""
    return n


def load_docs(*, scoped: bool = True) -> list[dict]:
    path = ROOT / "documents.json"
    if path.exists():
        blob = json.loads(path.read_text(encoding="utf-8"))
        docs = blob.get("documents") or []
        if docs:
            strip_hollow_summaries(docs)
            if scoped:
                return [d for d in docs if d.get("in_scope", True)]
            return docs
    docs = build_documents()
    strip_hollow_summaries(docs)
    write_json(
        ROOT / "documents.json",
        {
            "name": "AI 안전 라이브러리 문서",
            "updated": TODAY,
            "count": len(docs),
            "in_scope_count": sum(1 for d in docs if d.get("in_scope")),
            "out_of_scope_count": sum(1 for d in docs if not d.get("in_scope")),
            "documents": docs,
        },
    )
    if scoped:
        return [d for d in docs if d.get("in_scope", True)]
    return docs


def search_index(docs: list[dict]) -> dict:
    return {
        "docs": [
            {
                "id": d["id"],
                "title": (d.get("short_name") or d.get("title") or "")[:120],
                "org": d.get("org") or "",
                "country": d.get("country_ko") or d.get("country") or "",
                "flag": d.get("flag") or "",
                "date": d.get("published") or "",
                "kind": d.get("doc_kind") or "",
                "original": (d.get("original_name") or "")[:120],
            }
            for d in docs[:4000]
        ]
    }


def page(
    current: str,
    title: str,
    extra_css: str,
    body: str,
    page_js: str,
    index: dict,
    *,
    head_count: int | None = None,
    rel_prefix: str = "",
) -> str:
    chrome = page_chrome(
        current, index, title=title, head_count=head_count, rel_prefix=rel_prefix
    )
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {{ color-scheme: light; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; }}
{chrome["nav_css"]}
{EXTRA_CSS}
{extra_css}
</style>
</head>
<body>
<div class="viz-root">
{chrome["shell"]}
<div class="wrap">
{body}
{FOOTER_HTML}
</div>
</div>
{page_js}
{chrome["omni_js"]}
</body>
</html>
"""


def _esc(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def flag_emoji_safe(country: str) -> str:
    from library_common import flag_emoji

    return flag_emoji(country) or ""


def render_index(docs: list[dict], index: dict, *, total_raw: int = 0, out_count: int = 0) -> str:
    from parse_meta import DOC_KINDS

    from library_common import country_label_ko

    country_counts = Counter(d["country"] for d in docs if d.get("country"))
    countries = sorted(
        country_counts.keys(),
        key=lambda c: (-country_counts[c], country_label_ko(c) or c),
    )
    primary = countries[:20]
    extra = countries[20:]

    def _country_btn(c: str) -> str:
        fl = flag_emoji_safe(c)
        label = country_label_ko(c) or c
        n = country_counts[c]
        return (
            f'<button class="filter-chip" data-country="{_esc(c)}" type="button">'
            f"{fl} {_esc(label)}<span class=\"n\">{n}</span></button>"
        )

    country_btns = ['<button class="filter-chip active" data-country="" type="button">전체</button>']
    country_btns.extend(_country_btn(c) for c in primary)
    if extra:
        more_chips = "".join(_country_btn(c) for c in extra)
        country_btns.append(
            f'<button type="button" class="filter-more" id="countryMoreBtn" '
            f'aria-expanded="false">더보기 +{len(extra)}</button>'
            f'<span class="filter-more-wrap hidden" id="countryMoreWrap">{more_chips}</span>'
        )

    kind_counts = Counter(d.get("doc_kind") or "기타" for d in docs)
    kind_btns = ['<button class="filter-chip active" data-kind="" type="button">전체</button>']
    for k in DOC_KINDS:
        n = kind_counts.get(k, 0)
        if n:
            kind_btns.append(
                f'<button class="filter-chip kind-badge kind-{kind_slug(k)}" data-kind="{_esc(k)}" type="button">'
                f'{_esc(k)}<span class="n">{n}</span></button>'
            )
    issuer_counts = Counter(d.get("issuer_level") or "" for d in docs if d.get("issuer_level"))
    issuer_btns = ['<button class="filter-chip active" data-issuer="" type="button">전체</button>']
    issuer_color_json = safe_json(
        {i: {"l": c[0], "d": c[1], "label": lab} for i, lab in ISSUER_LEVELS for c in [ISSUER_COLORS[i]]}
    )
    for iid, lab in ISSUER_LEVELS:
        n = issuer_counts.get(iid, 0)
        if not n:
            continue
        light, dark = ISSUER_COLORS[iid]
        issuer_btns.append(
            f'<button class="filter-chip issuer-chip" data-issuer="{_esc(iid)}" type="button" '
            f'style="--issuer:{_esc(light)}">{_esc(lab)}'
            f'<span class="n">{n}</span></button>'
        )
    kind_color_json = safe_json(
        {k: {"l": v[0], "d": v[1], "slug": KIND_SLUG[k]} for k, v in KIND_COLORS.items()}
    )
    emphasis_json = safe_json(emphasis_rules_for_js())
    from topics import TOPIC_ORDER, enrich_topics, topic_icon, topic_label, TOPIC_COLORS

    enrich_topics(docs)
    # 주제 리본 확정 뒤 태그 선별(주제·종류와 겹치는 표현 제거)
    enrich_keywords(docs)
    topic_counts: Counter = Counter()
    for d in docs:
        for t in d.get("topics") or []:
            topic_counts[t["id"]] += 1
    topic_btns = ['<button class="filter-chip active" data-topic="" type="button">전체</button>']
    for slug in TOPIC_ORDER:
        n = topic_counts.get(slug, 0)
        if not n:
            continue
        color = TOPIC_COLORS.get(slug, "#534f4a")
        icon = topic_icon(slug)
        lab = topic_label(slug)
        prefix = f"{icon} " if icon else ""
        topic_btns.append(
            f'<button class="filter-chip topic-chip" data-topic="{_esc(slug)}" type="button" '
            f'style="--topic:{_esc(color)}">{prefix}{_esc(lab)}'
            f'<span class="n">{n}</span></button>'
        )
    trend_html = render_kind_trend(docs)
    from ui_common import omnibox_html

    body = f"""
  {trend_html}
  <div class="controls" id="listControls">
    <div class="sort-toggle filter-toolbar" id="kindToggle"><span class="filter-label">종류</span>{"".join(kind_btns)}</div>
    <div class="sort-toggle filter-toolbar" id="issuerToggle"><span class="filter-label">주체</span>{"".join(issuer_btns)}</div>
    <div class="sort-toggle filter-toolbar" id="topicToggle"><span class="filter-label">주제</span>{"".join(topic_btns)}</div>
    <div class="sort-toggle filter-toolbar" id="countryToggle"><span class="filter-label">국가</span>{"".join(country_btns)}</div>
  </div>
  {omnibox_html()}
  <div id="listView"></div>
  <nav class="year-nav hidden" id="yearNav" aria-label="연도 바로가기"></nav>
"""
    more_js = ""
    if extra:
        more_js = """
(function(){
  const btn = document.getElementById('countryMoreBtn');
  const wrap = document.getElementById('countryMoreWrap');
  if (!btn || !wrap) return;
  btn.addEventListener('click', () => {
    const nowHidden = wrap.classList.toggle('hidden');
    const open = !nowHidden;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    btn.textContent = open ? '접기' : ('더보기 +' + wrap.querySelectorAll('button.filter-chip').length);
  });
})();
"""
    js = f"""
<script id="docs-data" type="application/json">{safe_json(docs)}</script>
<script>
const DOCS = JSON.parse(document.getElementById('docs-data').textContent);
const KIND_COLORS = {kind_color_json};
const ISSUER_COLORS = {issuer_color_json};
const EMPHASIS_RULES = {emphasis_json};
const state = {{ q: '', country: '', kind: '', issuer: '', topic: '', yearOpen: {{}}, yearKeys: [] }};
const byId = Object.fromEntries(DOCS.map(d => [d.id, d]));

function escapeHtml(s) {{
  return String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
}}
/** 상세 요약: 종류·주체(국가·기관명)는 밑줄, 주제 키워드는 볼드. 최장·비겹침, 밑줄 우선. */
function emphasizeSummary(raw) {{
  const text = String(raw || '');
  if (!text.trim()) return '';
  const hits = [];
  for (const rule of EMPHASIS_RULES) {{
    let re;
    try {{ re = new RegExp(rule.re, 'gi'); }}
    catch (_) {{ continue; }}
    let m;
    while ((m = re.exec(text)) !== null) {{
      if (!m[0]) {{ re.lastIndex++; continue; }}
      hits.push({{
        start: m.index,
        end: m.index + m[0].length,
        style: rule.style === 'name' ? 'name' : 'em',
      }});
      if (!re.global) break;
    }}
  }}
  hits.sort((a, b) =>
    a.start - b.start ||
    (b.end - b.start) - (a.end - a.start) ||
    (a.style === 'name' ? -1 : 1)
  );
  const kept = [];
  for (const h of hits) {{
    if (kept.some(k => !(h.end <= k.start || h.start >= k.end))) continue;
    kept.push(h);
  }}
  kept.sort((a, b) => a.start - b.start);
  let out = '', i = 0;
  for (const h of kept) {{
    out += escapeHtml(text.slice(i, h.start));
    const frag = escapeHtml(text.slice(h.start, h.end));
    out += h.style === 'name'
      ? `<span class="term-name">${{frag}}</span>`
      : `<strong class="term-em">${{frag}}</strong>`;
    i = h.end;
  }}
  out += escapeHtml(text.slice(i));
  return out;
}}
function yearKey(d) {{
  const y = (d.published || '').slice(0, 4);
  return /^\\d{{4}}$/.test(y) ? y : 'undated';
}}
function yearLabel(y) {{
  return y === 'undated' ? '날짜 없음' : (y + '년');
}}
function isYearOpen(y, index) {{
  if (Object.prototype.hasOwnProperty.call(state.yearOpen, y)) return !!state.yearOpen[y];
  // 기본: 올해만 펼침, 그 이전·미상은 접힘
  return y === {TODAY[:4]!r};
}}
function hay(d) {{
  const topics = (d.topics || []).map(t => t.label + ' ' + t.id).join(' ');
  return [d.title, d.short_name, d.full_name, d.original_name, d.org, d.country, d.country_ko, d.doc_kind, d.issuer_level, d.issuer_level_ko, d.status_ko, d.summary, d.snippet, (d.keywords || []).join(' '), topics]
    .join(' ').toLowerCase();
}}
function hasTopic(d, topic) {{
  return (d.topics || []).some(t => t.id === topic);
}}
function visible() {{
  const q = state.q.trim().toLowerCase();
  return DOCS.filter(d => {{
    if (state.country && d.country !== state.country) return false;
    if (state.kind && (d.doc_kind || '기타') !== state.kind) return false;
    if (state.issuer && (d.issuer_level || '') !== state.issuer) return false;
    if (state.topic && !hasTopic(d, state.topic)) return false;
    if (!q) return true;
    return hay(d).includes(q);
  }});
}}
function flagHtml(d) {{
  return d.flag ? `<span class="org-flag flag-inline" title="${{escapeHtml(d.country_ko || d.country || '')}}">${{d.flag}}</span>` : '';
}}
function kindStyle(kind) {{
  const c = KIND_COLORS[kind] || KIND_COLORS['기타'];
  return `--c-l:${{c.l}};--c-d:${{c.d}}`;
}}
function kindBadge(kind) {{
  if (!kind) return '';
  const c = KIND_COLORS[kind] || KIND_COLORS['기타'];
  return `<span class="badge kind-badge kind-${{c.slug}}">${{escapeHtml(kind)}}</span>`;
}}
function issuerBadge(d) {{
  const id = d.issuer_level || '';
  if (!id || !ISSUER_COLORS[id]) return '';
  const c = ISSUER_COLORS[id];
  const lab = d.issuer_level_ko || c.label || id;
  return `<span class="issuer-badge" style="--issuer:${{c.l}}">${{escapeHtml(lab)}}</span>`;
}}
function statusBadge(d) {{
  const label = d.status_ko || '';
  if (!label) return '';
  let cls = 'status-pending';
  if (label === '제정') cls = 'status-enacted';
  else if (label === '개정' || label === '개정안') cls = 'status-amended';
  else if (label === '폐기') cls = 'status-defunct';
  else if (label === '계류') cls = 'status-pending';
  return `<span class="badge status-badge ${{cls}}">${{escapeHtml(label)}}</span>`;
}}
function ribbonHtml(d) {{
  const issuer = issuerBadge(d);
  const kind = kindBadge(d.doc_kind);
  const topics = d.topics || [];
  const kws = d.keywords || [];
  const topicHtml = topics.map(t =>
    `<span class="topic-tag" data-topic="${{escapeHtml(t.id)}}" style="--topic:${{escapeHtml(t.color || '#534f4a')}}">${{escapeHtml((t.icon ? t.icon + ' ' : '') + (t.label || t.id))}}</span>`
  ).join('');
  const kwHtml = kws.map(k => `<span class="kw-tag">${{escapeHtml(k)}}</span>`).join('');
  const inner = issuer + kind + topicHtml + kwHtml;
  if (!inner) return '';
  return `<div class="ribbon-row">${{inner}}</div>`;
}}
function cardHtml(d) {{
  const place = d.country_ko
    ? `${{flagHtml(d)}}<span class="country-chip">${{escapeHtml(d.country_ko)}}</span>`
    : flagHtml(d);
  const short = d.short_name || d.title || '';
  const original = d.original_name || '';
  const full = d.full_name || '';
  const under = original || (full && full !== short ? full : '');
  const underHtml = (under && under !== short)
    ? `<div class="event-full muted">${{escapeHtml(under)}}</div>` : '';
  const summary = emphasizeSummary(d.summary || d.snippet || '');
  const bodyHtml = summary ? `<p>${{summary}}</p>` : '';
  const title = d.canonical_url
    ? `<a class="event-title" href="${{escapeHtml(d.canonical_url)}}" target="_blank" rel="noopener noreferrer">${{escapeHtml(short)}}</a>`
    : `<span class="event-title">${{escapeHtml(short)}}</span>`;
  const life = statusBadge(d);
  return `<div class="event-card" data-id="${{escapeHtml(d.id)}}" style="${{kindStyle(d.doc_kind)}}">
    <div class="event-head"><span class="event-date">${{escapeHtml(d.published||'')}}</span>${{place}}</div>
    <div class="event-summary">${{title}}${{life}}</div>
    ${{underHtml}}
    ${{ribbonHtml(d)}}
    <div class="event-body">${{bodyHtml}}</div>
  </div>`;
}}
function renderYearNav(keys) {{
  const nav = document.getElementById('yearNav');
  if (!nav) return;
  state.yearKeys = keys;
  if (keys.length < 2) {{
    nav.classList.add('hidden');
    nav.innerHTML = '';
    return;
  }}
  nav.classList.remove('hidden');
  nav.innerHTML = keys.map(y =>
    `<button type="button" class="year-nav-item" data-year="${{escapeHtml(y)}}">${{escapeHtml(y === 'undated' ? '—' : y)}}</button>`
  ).join('');
}}
function renderList() {{
  const rows = visible();
  const headCount = document.getElementById('headCount');
  if (headCount) headCount.textContent = rows.length.toLocaleString('ko-KR');
  if (!rows.length) {{
    document.getElementById('listView').innerHTML = '<div class="empty">해당하는 문서가 없습니다.</div>';
    renderYearNav([]);
    return;
  }}
  const groups = {{}};
  rows.forEach(d => {{
    const y = yearKey(d);
    (groups[y] || (groups[y] = [])).push(d);
  }});
  const keys = Object.keys(groups).sort((a, b) => {{
    if (a === 'undated') return 1;
    if (b === 'undated') return -1;
    return b.localeCompare(a);
  }});
  let html = '<div class="timeline">';
  keys.forEach((y, i) => {{
    const open = isYearOpen(y, i);
    html += `<div class="year-group" id="year-${{escapeHtml(y)}}">
      <button type="button" class="year-header" data-year="${{escapeHtml(y)}}" aria-expanded="${{open ? 'true' : 'false'}}">
        ${{escapeHtml(yearLabel(y))}} <span class="muted">${{groups[y].length}}</span>
      </button>
      <div class="year-body${{open ? '' : ' hidden'}}">${{groups[y].map(cardHtml).join('')}}</div>
    </div>`;
  }});
  html += '</div>';
  document.getElementById('listView').innerHTML = html;
  renderYearNav(keys);
}}
function jumpYear(y) {{
  state.yearOpen[y] = true;
  renderList();
  const el = document.getElementById('year-' + y);
  if (el) el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
  document.querySelectorAll('.year-nav-item').forEach(b => {{
    b.classList.toggle('active', b.dataset.year === y);
  }});
}}
(function bindOmniFilter() {{
  const omni = document.getElementById('omniBox');
  if (!omni) return;
  omni.addEventListener('input', () => {{ state.q = omni.value; renderList(); }});
}})();
function bindFilter(id, key) {{
  document.getElementById(id).querySelectorAll('button[data-' + key + ']').forEach(btn => {{
    btn.addEventListener('click', () => {{
      document.getElementById(id).querySelectorAll('button[data-' + key + ']').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state[key] = btn.dataset[key] || '';
      renderList();
    }});
  }});
}}
bindFilter('countryToggle', 'country');
bindFilter('kindToggle', 'kind');
bindFilter('issuerToggle', 'issuer');
bindFilter('topicToggle', 'topic');
document.getElementById('listView').addEventListener('click', ev => {{
  if (ev.target.closest('a')) return;
  const ttag = ev.target.closest('.topic-tag[data-topic]');
  if (ttag && ttag.dataset.topic) {{
    ev.preventDefault();
    state.topic = ttag.dataset.topic;
    document.getElementById('topicToggle').querySelectorAll('button[data-topic]').forEach(b => {{
      b.classList.toggle('active', (b.dataset.topic || '') === state.topic);
    }});
    renderList();
    return;
  }}
  const head = ev.target.closest('.year-header');
  if (head && head.dataset.year) {{
    const y = head.dataset.year;
    const idx = state.yearKeys.indexOf(y);
    const now = isYearOpen(y, idx < 0 ? 99 : idx);
    state.yearOpen[y] = !now;
    renderList();
    return;
  }}
}});
document.getElementById('yearNav').addEventListener('click', ev => {{
  const btn = ev.target.closest('.year-nav-item');
  if (btn && btn.dataset.year) jumpYear(btn.dataset.year);
}});
{more_js}
(function boot() {{
  const params = new URLSearchParams(location.search);
  if (params.get('country')) {{
    state.country = params.get('country');
    document.getElementById('countryToggle').querySelectorAll('button[data-country]').forEach(b => {{
      b.classList.toggle('active', (b.dataset.country || '') === state.country);
    }});
    const wrap = document.getElementById('countryMoreWrap');
    const btn = document.getElementById('countryMoreBtn');
    if (wrap && btn && state.country) {{
      const hit = Array.from(wrap.querySelectorAll('button[data-country]')).find(b => b.dataset.country === state.country);
      if (hit) {{
        wrap.classList.remove('hidden');
        btn.setAttribute('aria-expanded', 'true');
        btn.textContent = '접기';
      }}
    }}
  }}
  if (params.get('kind')) {{
    state.kind = params.get('kind');
    document.getElementById('kindToggle').querySelectorAll('button[data-kind]').forEach(b => {{
      b.classList.toggle('active', (b.dataset.kind || '') === state.kind);
    }});
  }}
  if (params.get('issuer')) {{
    state.issuer = params.get('issuer');
    document.getElementById('issuerToggle').querySelectorAll('button[data-issuer]').forEach(b => {{
      b.classList.toggle('active', (b.dataset.issuer || '') === state.issuer);
    }});
  }}
  if (params.get('topic')) {{
    state.topic = params.get('topic');
    document.getElementById('topicToggle').querySelectorAll('button[data-topic]').forEach(b => {{
      b.classList.toggle('active', (b.dataset.topic || '') === state.topic);
    }});
  }}
  const hash = decodeURIComponent((location.hash || '').slice(1));
  if (hash && byId[hash]) {{
    state.yearOpen[yearKey(byId[hash])] = true;
  }}
  renderList();
  if (hash && byId[hash]) {{
    const el = document.querySelector('.event-card[data-id="' + CSS.escape(hash) + '"]');
    if (el) el.scrollIntoView({{ block: 'nearest' }});
  }}
}})();
</script>
"""
    return page(
        "index.html",
        "AI 안전 라이브러리",
        "",
        body,
        js,
        index,
        head_count=len(docs),
    )


PIPELINE_SVG = """<svg viewBox="0 0 720 700" class="pipe-svg" role="img"
aria-label="수집, 규칙 후보, LLM 큐레이션, 병합 분석, 통합 합성, 사이트 빌드 파이프라인">
<defs>
  <marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="currentColor"/>
  </marker>
</defs>
<rect x="40" y="28" width="200" height="56" rx="12" fill="var(--surface, #f5f3ef)" stroke="currentColor" stroke-opacity=".25"/>
<text x="140" y="52" text-anchor="middle" font-size="13" font-weight="700">1 · 수집</text>
<text x="140" y="70" text-anchor="middle" font-size="11" opacity=".7">AGORA · OECD · 외교부 · IAAE</text>
<line x1="140" y1="84" x2="140" y2="112" stroke="currentColor" stroke-opacity=".45" marker-end="url(#arr)"/>

<rect x="40" y="116" width="200" height="56" rx="12" fill="var(--surface, #f5f3ef)" stroke="currentColor" stroke-opacity=".25"/>
<text x="140" y="140" text-anchor="middle" font-size="13" font-weight="700">2 · 규칙 후보</text>
<text x="140" y="158" text-anchor="middle" font-size="11" opacity=".7">모법 URL · 조항 · cluster</text>
<line x1="140" y1="172" x2="140" y2="200" stroke="currentColor" stroke-opacity=".45" marker-end="url(#arr)"/>

<rect x="40" y="204" width="200" height="72" rx="12" fill="var(--surface, #f5f3ef)" stroke="currentColor" stroke-opacity=".35" stroke-width="1.6"/>
<text x="140" y="230" text-anchor="middle" font-size="13" font-weight="700">3 · LLM 큐레이션</text>
<text x="140" y="248" text-anchor="middle" font-size="11" opacity=".7">문서별 범위·종류·토픽·한글</text>
<text x="140" y="264" text-anchor="middle" font-size="11" opacity=".7">OpenRouter · 고·중신뢰만 반영</text>
<line x1="140" y1="276" x2="140" y2="304" stroke="currentColor" stroke-opacity=".45" marker-end="url(#arr)"/>

<rect x="40" y="308" width="200" height="64" rx="12" fill="var(--surface, #f5f3ef)" stroke="currentColor" stroke-opacity=".35" stroke-width="1.6"/>
<text x="140" y="332" text-anchor="middle" font-size="13" font-weight="700">4 · 병합 분석</text>
<text x="140" y="350" text-anchor="middle" font-size="11" opacity=".7">멤버 식별 · 같은 제도인지</text>
<line x1="140" y1="372" x2="140" y2="400" stroke="currentColor" stroke-opacity=".45" marker-end="url(#arr)"/>

<rect x="40" y="404" width="200" height="64" rx="12" fill="var(--surface, #f5f3ef)" stroke="currentColor" stroke-opacity=".35" stroke-width="1.6"/>
<text x="140" y="428" text-anchor="middle" font-size="13" font-weight="700">5 · 통합 합성</text>
<text x="140" y="446" text-anchor="middle" font-size="11" opacity=".7">합의된 그룹만 약칭·요약</text>

<rect x="300" y="404" width="200" height="64" rx="12" fill="var(--surface, #f5f3ef)" stroke="currentColor" stroke-opacity=".25" stroke-dasharray="4 3"/>
<text x="400" y="428" text-anchor="middle" font-size="13" font-weight="700">5b · 날짜 복원</text>
<text x="400" y="446" text-anchor="middle" font-size="11" opacity=".7">원문 URL · 검색 · LLM</text>
<line x1="240" y1="436" x2="300" y2="436" stroke="currentColor" stroke-opacity=".45" marker-end="url(#arr)"/>

<line x1="140" y1="468" x2="140" y2="504" stroke="currentColor" stroke-opacity=".45" marker-end="url(#arr)"/>
<line x1="400" y1="468" x2="400" y2="492" stroke="currentColor" stroke-opacity=".35"/>
<line x1="140" y1="492" x2="400" y2="492" stroke="currentColor" stroke-opacity=".35"/>

<rect x="40" y="508" width="200" height="56" rx="12" fill="var(--surface, #f5f3ef)" stroke="currentColor" stroke-opacity=".25"/>
<text x="140" y="532" text-anchor="middle" font-size="13" font-weight="700">6 · 사이트 빌드</text>
<text x="140" y="550" text-anchor="middle" font-size="11" opacity=".7">build_site.py → docs/</text>

<rect x="300" y="508" width="380" height="120" rx="12" fill="var(--surface, #f5f3ef)" stroke="currentColor" stroke-opacity=".2"/>
<text x="320" y="536" font-size="12" font-weight="700">설계 원칙</text>
<text x="320" y="558" font-size="11" opacity=".8">· 문서별 분석(큐레이션) 후에야 통합</text>
<text x="320" y="578" font-size="11" opacity=".8">· 규칙은 후보만, 확정은 LLM 분석</text>
<text x="320" y="598" font-size="11" opacity=".8">· 날짜는 발표일 ≠ 카탈로그 등록일</text>
<text x="320" y="618" font-size="11" opacity=".8">· low confidence는 UI에 자동 반영하지 않음</text>
</svg>"""


def render_about(docs: list[dict], index: dict, *, total_raw: int = 0, out_count: int = 0) -> str:
    from curate_llm import CACHE_PATH, CURATED_KINDS, TOPIC_IDS, load_cache

    cache = load_cache()
    n_curated = sum(
        1
        for v in cache.values()
        if isinstance(v, dict)
        and ((v.get("result") or v).get("confidence") in ("high", "medium"))
    )
    n_llm_topics = sum(1 for d in docs if d.get("topics_source") == "llm")
    css = """
.about-wrap { max-width: 820px; margin: 0 auto; padding: 8px 4px 48px; }
.about-wrap h2 { font-size: 1.25rem; margin: 1.6rem 0 .55rem; font-weight: 650; }
.about-wrap p, .about-wrap li { line-height: 1.55; font-size: 1rem; opacity: .92; }
.about-meta { opacity: .65; font-size: .92rem; margin-bottom: 1rem; }
.pipe-scroll { overflow-x: auto; border: 1px solid color-mix(in srgb, currentColor 14%, transparent);
  border-radius: 16px; padding: 12px; background: color-mix(in srgb, currentColor 3%, transparent); }
.pipe-svg { display: block; width: 100%; min-width: 640px; height: auto; color: inherit; }
.principles { border: 1px solid color-mix(in srgb, currentColor 14%, transparent);
  border-radius: 16px; padding: .4rem 1.1rem; background: color-mix(in srgb, currentColor 3%, transparent); }
.tool-panel { border: 1px solid color-mix(in srgb, currentColor 14%, transparent);
  border-radius: 16px; padding: 14px 16px; margin: 12px 0 20px;
  background: color-mix(in srgb, currentColor 3%, transparent); }
.tool-item { margin-bottom: 12px; font-size: .95rem; }
.tool-item:last-child { margin-bottom: 0; }
.tool-item b { display: block; margin-bottom: 2px; }
.tool-item code { display: block; font-size: .78rem; opacity: .85; overflow-wrap: anywhere; margin: 2px 0; }
.tool-item span { opacity: .65; font-size: .88rem; }
.kind-list { font-size: .92rem; opacity: .85; }
"""
    kinds = " · ".join(CURATED_KINDS)
    issuers = " · ".join(f"{lab}({iid})" for iid, lab in ISSUER_LEVELS)
    topics = " · ".join(TOPIC_IDS)
    body = f"""
<div class="about-wrap">
  <p class="about-meta">표시 문서 {len(docs):,}건 · 원천 {total_raw:,}건 · 범위 밖 {out_count:,}건 ·
  LLM 큐레이션 캐시 {len(cache):,}건(고·중신뢰 {n_curated:,}) · 토픽 LLM 반영 {n_llm_topics:,}건</p>

  <p>AI 안전·거버넌스 관련 법·정책·표준·기구 문서를 모아, 종류·주제·날짜·한글 표기를
  정리해 한 화면에서 훑을 수 있게 한 라이브러리입니다.
  <b>문서별 LLM 큐레이션(분석)을 먼저</b> 한 뒤, 같은 법령·정책 후보를 확인하고
  합의된 그룹만 통합 약칭·핵심내용을 합성합니다. 고·중신뢰만 사이트에 반영합니다.</p>

  <h2>파이프라인</h2>
  <div class="pipe-scroll">{PIPELINE_SVG}</div>
  <p>키워드 태그는 초안용입니다. LLM이 토픽을 확정하면
  (<code>topics_source=llm</code>) 키워드 매칭으로 덮어쓰지 않습니다.
  예: 제목의 「정당성」만으로 <code>politics</code>를 붙이지 않습니다.</p>

  <h2>데이터 원칙</h2>
  <ul class="principles">
    <li><b>형태 × 층위 × 주제</b> — <code>doc_kind</code>는 규범 형태,
      <code>issuer_level</code>은 발급 층위(국제·국가·부처·랩·시민사회 등),
      <code>topics</code>는 주제. 구「개발사 정책」은 층위 <code>lab</code> + 형태
      (대개 가이드라인·원칙)로 나눕니다.</li>
    <li><b>뉴스·보도는 종류가 아니라 제외</b> — UI <code>doc_kind</code> enum에 두지 않고
      <code>in_scope=false</code> + <code>reject_reason=news_press</code>로 뺍니다.</li>
    <li><b>토픽은 의미 판정</b> — 부분문자열 함정(정당성≠정당, party≠정당)을 프롬프트·검증으로 막습니다.</li>
    <li><b>날짜는 발표일</b> — OECD catalog Added-on·업로드 시각은 차트용 발표일로 쓰지 않습니다.
      불확실하면 URL·검색·LLM으로 복원합니다 (<code>resolve_oecd_dates.py</code>).</li>
    <li><b>저신뢰는 자동 반영 안 함</b> — <code>confidence=low</code>는 캐시에만 두고 UI 필드를 바꾸지 않습니다.</li>
    <li><b>원문 제목 보존</b> — 한글 약칭을 쓸 때 영문 원제는 <code>original_name</code>에 남깁니다.</li>
    <li><b>동일 법령은 한 카드</b> — 규칙으로 후보만 묶고, 큐레이션·병합 분석 후
      같은 제도로 합의된 경우만 통합 요약·조항 목록을 씁니다
      (<code>merge_instruments.py --analyze</code> → <code>--synthesize</code>).
      다른 법이 섞이면 분할 플래그만 남깁니다.</li>
  </ul>

  <h2>허용 문서종류 · 토픽</h2>
  <p class="kind-list"><b>doc_kind</b> (형태) {kinds}</p>
  <p class="kind-list"><b>issuer_level</b> (층위) {issuers}</p>
  <p class="kind-list"><b>topics</b> (주제) {topics}</p>

  <h2>수동 도구</h2>
  <div class="tool-panel">
    <div class="tool-item">
      <b>LLM 큐레이션 (문서별 분석 — 먼저)</b>
      <code>python3 scripts/curate_llm.py --limit 200</code>
      <code>python3 scripts/curate_llm.py --validate-only</code>
      <span>캐시 <code>cache/llm_curate.json</code>. 고·중신뢰만 build 시 반영.</span>
    </div>
    <div class="tool-item">
      <b>병합 분석 → 후보 → 통합 합성</b>
      <code>python3 scripts/merge_instruments.py --analyze --limit 30</code>
      <code>python3 scripts/merge_instruments.py --propose</code>
      <code>python3 scripts/merge_instruments.py --synthesize --limit 30</code>
      <span>캐시 <code>cache/instrument_analyze.json</code> · <code>cache/instrument_merge.json</code>.</span>
    </div>
    <div class="tool-item">
      <b>한글 약칭·요약 (레거시 배치)</b>
      <code>python3 scripts/enrich_ko.py --limit 100</code>
      <span>큐레이션이 short_name/summary를 채우면 점차 대체됩니다.</span>
    </div>
    <div class="tool-item">
      <b>OECD 발표일 복원</b>
      <code>python3 scripts/resolve_oecd_dates.py --limit 300 --llm --no-search --apply</code>
      <span>원문 메타 우선, 실패 시 LLM. 캐시 <code>cache/oecd_dates.json</code>.</span>
    </div>
    <div class="tool-item">
      <b>사이트 재생성</b>
      <code>python3 scripts/build_site.py</code>
      <span>후보 그룹 → 큐레이션 → 분석/합성 캐시 → docs/</span>
    </div>
  </div>

  <p class="about-meta">캐시: <code>cache/llm_curate.json</code> · <code>cache/instrument_analyze.json</code> · <code>cache/instrument_merge.json</code></p>
</div>
"""
    return page("about.html", "소개 · 파이프라인", css, body, "", index)


def render_about_log(index: dict) -> str:
    from library_changelog import changelog_months

    css = """
.about-wrap { max-width: 820px; margin: 0 auto; padding: 8px 4px 48px; }
.about-wrap h2 { font-size: 1.15rem; margin: 1.6rem 0 .55rem; font-weight: 650; }
.about-wrap p { line-height: 1.55; font-size: 1rem; opacity: .92; }
.log-intro { opacity: .75; font-size: .95rem; margin-bottom: 1.4rem; }
.log-entry {
  border-bottom: 1px solid var(--hairline); padding: 14px 0;
}
.log-entry:last-child { border-bottom: 0; }
.log-meta { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 6px; }
.log-date { font-variant-numeric: tabular-nums; font-size: 12px; color: var(--text-muted); }
.log-tag {
  font-size: 11px; color: var(--text-muted);
  border: 1px solid var(--hairline); border-radius: 999px; padding: 1px 8px;
}
.log-entry h3 { font-size: 1rem; margin: 0 0 6px; font-weight: 700; }
.log-entry p { margin: 0; font-size: 0.92rem; }
"""
    sections: list[str] = []
    for _ym, month_label, items in changelog_months():
        rows: list[str] = []
        for item in items:
            tags = "".join(
                f'<span class="log-tag">{html_lib.escape(t)}</span>' for t in item["tags"]
            )
            rows.append(
                '<article class="log-entry">'
                '<div class="log-meta">'
                f'<time class="log-date" datetime="{html_lib.escape(item["date"])}">'
                f'{html_lib.escape(item["date"])}</time>'
                f"{tags}"
                "</div>"
                f'<h3>{html_lib.escape(item["title"])}</h3>'
                f'<p>{html_lib.escape(item["body"])}</p>'
                "</article>"
            )
        sections.append(
            f'<section><h2>{html_lib.escape(month_label)}</h2>'
            + "".join(rows)
            + "</section>"
        )
    body = (
        '<div class="about-wrap">'
        '<p class="log-intro">수집이 매일 쌓인 기록은 빼고, 사이트 구조·분류·파이프라인이 '
        "바뀐 지점만 적습니다. 최신 달이 위입니다.</p>"
        + "".join(sections)
        + "</div>"
    )
    return page(
        "about/log.html",
        "업데이트",
        css,
        body,
        "",
        index,
        rel_prefix="../",
    )


def redirect_html(target: str = "index.html") -> str:
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0;url={target}">
<title>이동 중…</title>
<script>location.replace('{target}' + location.search + location.hash);</script>
</head>
<body><p><a href="{target}">라이브러리로 이동</a></p></body>
</html>
"""



def main() -> None:
    print("building documents…")
    all_docs = build_documents()
    cleared = strip_hollow_summaries(all_docs)
    if cleared:
        print(f"cleared hollow summaries on {cleared} docs (cards kept)")
    write_json(
        ROOT / "documents.json",
        {
            "name": "AI 안전 라이브러리 문서",
            "updated": TODAY,
            "count": len(all_docs),
            "in_scope_count": sum(1 for d in all_docs if d.get("in_scope")),
            "out_of_scope_count": sum(1 for d in all_docs if not d.get("in_scope")),
            "documents": all_docs,
        },
    )
    docs = [d for d in all_docs if d.get("in_scope")]
    out_count = len(all_docs) - len(docs)
    print("documents", len(all_docs), "in_scope", len(docs), "out", out_count)
    import csv

    report_dir = ROOT / "reports" / f"audit-{TODAY}"
    report_dir.mkdir(parents=True, exist_ok=True)
    with (report_dir / "out_of_scope.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["id", "title", "safety_score", "published", "canonical_url", "safety_reasons"],
            extrasaction="ignore",
        )
        w.writeheader()
        for d in all_docs:
            if d.get("in_scope"):
                continue
            row = dict(d)
            row["safety_reasons"] = ";".join(d.get("safety_reasons") or [])
            w.writerow(row)

    index = {"docs": []}  # 상단 검색은 목록 필터만 사용
    DOCS.mkdir(parents=True, exist_ok=True)
    DIST_MIRROR.mkdir(parents=True, exist_ok=True)
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    pages = {
        "index.html": render_index(docs, index, total_raw=len(all_docs), out_count=out_count),
        "documents.html": redirect_html("index.html"),
        "clusters.html": redirect_html("index.html"),
        "about.html": render_about(docs, index, total_raw=len(all_docs), out_count=out_count),
        "about/log.html": render_about_log(index),
    }
    for name, html in pages.items():
        for root in (DOCS, DIST_MIRROR):
            out = root / name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(html, encoding="utf-8")
        print(name, f"{(DOCS / name).stat().st_size / 1024:.0f} KB")
    print("wrote", DOCS, "(mirror", DIST_MIRROR, ")")


if __name__ == "__main__":
    main()
