#!/usr/bin/env python3
"""Parse structured metadata (기관·문서종류·문서명·약칭·핵심내용·발표시점)."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

# Canonical document-kind labels (성격).
DOC_KINDS = [
    "법",
    "법안",
    "행정규칙",
    "조약·협약",
    "선언·성명",
    "가이드라인·원칙",
    "전략·정책",
    "정책보고서",
    "표준",
    "기구·제도",
    "뉴스·보도",
    "기타",
]
# 구 라벨 → (형태 종류). 층위는 issuer_level=lab 로 분리.
LEGACY_KIND_ALIASES = {
    "개발사 정책": "가이드라인·원칙",
}

# OECD Policy Navigator category → kind
_OECD_CAT = {
    "regulations, guidelines and standards": "가이드라인·원칙",
    "national – strategy": "전략·정책",
    "national – ai governance bodies or mechanisms": "기구·제도",
    "ai governance bodies and mechanisms (intergovernmental or supranational)": "기구·제도",
    "ai policy frameworks and initiatives (intergovernmental or supranational)": "전략·정책",
    "ai policy initiatives, programmes and projects": "전략·정책",
}

# AGORA collection tags → kind
_AGORA_CAT = [
    (re.compile(r"federal laws|state and local|chinese law", re.I), "법"),
    (re.compile(r"regulations, executive orders|agency policies", re.I), "행정규칙"),
    (re.compile(r"corporate policies", re.I), "가이드라인·원칙"),
    (re.compile(r"multinational", re.I), "조약·협약"),
]

_AMEND_RX = re.compile(
    r"amend|amended|amendment|revis(?:e|ed|ion)|re-?authoriz|"
    r"부분\s*개정|(?<![가-힣])개정(?![가-힣])|수정\s*법",
    re.I,
)


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "").strip()


def lifecycle_label(status: str = "", *texts: str, doc_kind: str = "") -> str:
    """Korean lifecycle tag beside 법/법안 titles: 제정·개정·계류·폐기."""
    kind = (doc_kind or "").strip()
    st = _fold(status).lower()
    blob = " / ".join(t for t in texts if t)
    is_amend = bool(_AMEND_RX.search(blob))

    if st == "defunct":
        return "폐기"
    if st == "proposed":
        return "개정안" if is_amend else "계류"
    if st == "enacted":
        return "개정" if is_amend else "제정"

    if kind == "법안":
        return "개정안" if is_amend else "계류"
    if kind == "법":
        return "개정" if is_amend else "제정"
    return ""


def parse_bullet_fields(body: str) -> dict[str, str]:
    """Parse 『●키: 값』 lines from MOFA-style bodies."""
    text = _fold(body)
    if not text:
        return {}
    parts = re.split(r"\n?\s*●\s*", text)
    out: dict[str, str] = {}
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^([^:：\n]{1,40})\s*[:：]\s*([\s\S]*)$", part)
        if not m:
            continue
        out[m.group(1).strip()] = m.group(2).strip()
    return out


def pick_date_field(fields: dict[str, str]) -> str:
    for key in (
        "발표시점",
        "발표시점/채택시점",
        "발표시점/배포시점",
        "발표시점/시행시점",
        "채택시점",
        "제정시점",
        "시행시점",
        "발효시점",
        "공표시점",
        "게시시점",
        "배포시점",
        "개최시점",
        "성립시점",
    ):
        if fields.get(key):
            return fields[key]
    for k, v in fields.items():
        if "시점" in k or "발표" in k:
            return v
    return ""


def normalize_date_ko(raw: str) -> str:
    if not raw:
        return ""
    m = re.search(r"(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(20\d{2})\s*년\s*(\d{1,2})\s*월", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-01"
    m = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(20\d{2})[./-](\d{1,2})\b", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-01"
    m = re.search(r"(20\d{2})\s*년", raw)
    if m:
        return f"{m.group(1)}-01-01"
    return ""


def classify_doc_kind(*texts: str, category: str = "", status: str = "") -> str:
    blob = " / ".join(t for t in texts if t)
    cat = _fold(category).lower()
    st = _fold(status).lower()

    # Numbered ISO/IEC (and similar) standards beat OECD policy-framework buckets.
    if re.search(r"\bISO(?:/IEC)?\s*\d{4,5}\b|\bIEC\s*\d{4,5}\b|\bKS\s*[A-Z]?\s*\d", blob, re.I):
        return "표준"

    if cat:
        for key, kind in _OECD_CAT.items():
            if key in cat:
                # programmes/projects that are clearly institutes
                if kind == "전략·정책" and re.search(
                    r"\b(institute|office|centre|center|committee|board|agency|authority|portal)\b",
                    blob,
                    re.I,
                ):
                    return "기구·제도"
                return kind
        for rx, kind in _AGORA_CAT:
            if rx.search(cat):
                # AGORA tags bills and statutes together under "federal/state/chinese law".
                # Prefer the explicit lifecycle status when present.
                if kind == "법" and st:
                    if st in ("proposed", "defunct"):
                        return "법안"
                    if st == "enacted":
                        return "법"
                return kind

    if re.search(r"법안|bill\b|의회\s*제출|개정안|omnibus|draft\s*(act|law|bill)", blob, re.I):
        if not re.search(r"연방법률|공포·|발효|enacted|signed into law", blob, re.I):
            return "법안"

    rules: list[tuple[str, re.Pattern[str]]] = [
        (
            "기구·제도",
            re.compile(
                r"task\s*force|task\s*team|태스크포스|태스크팀|office\b|사무소|연구소|institute|aisi|"
                r"centre of excellence|center of excellence|위원회|committee|"
                r"board\b|agency\b|authority\b|거버넌스\s*기구|governance\s*body",
                re.I,
            ),
        ),
        (
            "법",
            re.compile(
                r"연방법률|법률|법령|\blaw\b|규정\b|regulation\b|\bact\b|기본법|이행법|"
                r"directive\b|decree\b|ordonnance|statute",
                re.I,
            ),
        ),
        (
            "행정규칙",
            re.compile(
                r"행정명령|executive\s*order|\beo\b|memorandum|\bmemo\b|메모|"
                r"지침\b|guidance|circular|고시|공고|결정\b|commission\s*decision|"
                r"시행\s*안내|omb\b",
                re.I,
            ),
        ),
        (
            "조약·협약",
            re.compile(r"조약|협약|convention|treaty|협정(?!.*보도)|framework\s*convention", re.I),
        ),
        (
            "가이드라인·원칙",
            re.compile(
                r"가이드라인|guideline|원칙|principle|행동규범|code\s*of\s*(conduct|practice)|"
                r"실천규범|권고|recommendation|framework(?!.*convention)|모범사례|"
                r"playbook|핸드북|handbook|advisory|"
                r"안내서|가이드(?!\s*라인)|매뉴얼|manual|toolkit|primer|essentials?|"
                r"기초\s*가이드|핵심\s*안내",
                re.I,
            ),
        ),
        (
            "전략·정책",
            re.compile(
                r"전략|strategy|action\s*plan|행동계획|기본계획|정책\s*프레임|"
                r"roadmap|로드맵|white\s*paper|백서(?!.*분석)|청사진|"
                r"national\s*ai\s*plan|policy\s*initiative|"
                r"실시의견|실시방안|이니셔티브|initiative|우선과제|priorit",
                re.I,
            ),
        ),
        (
            "선언·성명",
            re.compile(
                r"선언|declaration|성명|communiqu|공동성명|합의문|정상\s*성명|pledges?|"
                r"촉구문|call\s*to\s*action|leaders['’]?\s*call",
                re.I,
            ),
        ),
        (
            "정책보고서",
            re.compile(
                r"보고서|report|working\s*paper|워킹페이퍼|페이퍼|papers?\b|"
                r"정책브리프|brief|연구보고서|검토\s*보고서|\bnote\b|"
                r"인사이트|fact\s*sheet|팩트시트|평가|assessment|survey",
                re.I,
            ),
        ),
        (
            "표준",
            re.compile(r"표준|standard|iso/?iec|기술적\s*규격|specification", re.I),
        ),
        (
            "뉴스·보도",
            re.compile(r"뉴스|보도|press\s*release|기사|발표자료|미디어\s*성명", re.I),
        ),
    ]
    for kind, rx in rules:
        if rx.search(blob):
            return kind
    return "기타"


def split_document_names(raw: str) -> tuple[str, str]:
    raw = _fold(raw)
    if not raw:
        return "", ""
    main = re.split(r"※", raw, maxsplit=1)[0].strip()
    ko = ""
    m = re.search(r"「([^」]+)」", main)
    if m:
        ko = m.group(1).strip()
    left = re.split(r"\s*/\s*", main, maxsplit=1)[0].strip()
    left = re.sub(r"「[^」]+」", "", left).strip(" /")
    full = left or main
    return full, ko


def short_name_from_title(title: str) -> str:
    title = _fold(title)
    m = re.match(r"^[［\[]([^］\]]+)[］\]]\s*(.+)$", title)
    if m:
        return m.group(2).strip()
    return title


def _infer_org(item: dict[str, Any]) -> str:
    org = item.get("org") or item.get("institution") or ""
    if org:
        return str(org).strip()
    # OECD sometimes empty org — fall back to category country signals already elsewhere
    return ""


def _infer_summary(item: dict[str, Any], fields: dict[str, str]) -> str:
    if fields.get("핵심내용"):
        return fields["핵심내용"].strip()
    body = (item.get("body") or "").strip()
    if body and "●" not in body:
        return body[:1200]
    # AGORA/OECD English body often is the summary
    if body and "●핵심내용" not in body:
        # strip leading bullet block if partial
        if body.startswith("●"):
            return ""
        return body[:1200]
    return ""


def extract_meta(item: dict[str, Any]) -> dict[str, str]:
    """Build normalized metadata dict for one raw collection item."""
    body = item.get("body") or ""
    fields = parse_bullet_fields(body)
    category = item.get("category") or ""

    org = fields.get("기관") or _infer_org(item)
    raw_kind = fields.get("문서종류") or item.get("document_type") or category or ""
    raw_name = fields.get("문서명") or item.get("document_name") or ""
    summary = _infer_summary(item, fields)

    date_raw = pick_date_field(fields)
    published = normalize_date_ko(date_raw) or (item.get("date") or "")[:10]

    full_name, ko_alt = split_document_names(raw_name)
    short = short_name_from_title(item.get("title") or "")
    if ko_alt and (len(short) > 40 or not re.search(r"[가-힣]", short)):
        short = ko_alt
    if not full_name:
        # Prefer official English/original title when distinct from short UI title
        title = (item.get("title") or "").strip()
        original = (item.get("original_name") or item.get("document_name") or "").strip()
        if original and original != title and original != short:
            full_name = original
        else:
            full_name = raw_name or title

    status = (item.get("status") or "").strip()
    preset = (item.get("doc_kind") or category or "").strip()
    if preset in LEGACY_KIND_ALIASES:
        kind = LEGACY_KIND_ALIASES[preset]
    elif preset in DOC_KINDS:
        kind = preset
    else:
        kind = classify_doc_kind(
            raw_kind,
            item.get("title") or "",
            full_name,
            short,
            category=category,
            status=status,
        )
    # Lifecycle status wins even when category is Miscellaneous / Editors' Picks.
    st_l = status.lower()
    if kind == "법" and st_l in ("proposed", "defunct"):
        kind = "법안"

    country = fields.get("국가") or ""
    raw_kind_out = raw_kind.strip()
    if status and status.lower() not in raw_kind_out.lower():
        raw_kind_out = f"{raw_kind_out}|{status}" if raw_kind_out else status

    return {
        "org": org.strip(),
        "doc_kind": kind,
        "doc_kind_raw": raw_kind_out[:200],
        "status": status,
        "short_name": short.strip(),
        "full_name": full_name.strip(),
        "full_name_raw": raw_name.strip(),
        "published": published,
        "published_raw": date_raw.strip(),
        "summary": summary.strip()[:2000],
        "country_hint": country.strip(),
    }
