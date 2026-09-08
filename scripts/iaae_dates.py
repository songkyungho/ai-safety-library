"""IAAE 연구자료실 게시일 ≠ 원문 발표일.

2020-08-04·2020-11-04는 자료실에 일괄 올린 날이다.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

IAAE_BOARD_DUMP_DATES = frozenset({"2020-08-04", "2020-11-04"})

# 일자가 문헌에 잡히는 것만 월·일까지. 나머지는 연도.
_KNOWN: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"asilomar|아실로마", re.I), "2017"),
    (re.compile(r"oecd.{0,40}(?:ai )?(?:principles|권고)|oecd ai 권고", re.I), "2019-05-22"),
    (re.compile(r"google.{0,20}(?:ai )?principles|구글 AI 원칙", re.I), "2018-06-07"),
    (re.compile(r"microsoft.{0,30}(?:responsible ai|ai principles)|ms ai 원칙", re.I), "2018"),
    (re.compile(r"montr[eé]al declaration|몬트리올 선언", re.I), "2018-12-04"),
    (re.compile(r"rome call|로마 콜", re.I), "2020-02-28"),
    (re.compile(r"ethics guidelines.{0,40}trustworthy|신뢰할 수 있는 AI 윤리 가이드라인", re.I), "2019-04-08"),
    (re.compile(r"preparing for the future of (?:artificial intelligence|\bai\b)|미래 준비 보고서", re.I), "2016-10"),
    (re.compile(r"beijing ai principles|베이징 인공지능 원칙", re.I), "2019-05-25"),
    (re.compile(r"openai charter|openai 헌장", re.I), "2018-04-09"),
    (re.compile(r"ibm.{0,40}trust and transparency|ibm ai 원칙", re.I), "2018-05"),
    (re.compile(r"partnership on ai|ai 파트너십", re.I), "2016"),
    (re.compile(r"ai now 2019", re.I), "2019"),
    (re.compile(r"discriminating systems", re.I), "2019"),
    (re.compile(r"ethically aligned design|윤리적 인공지능 시스템 개발을 위한 설계", re.I), "2019"),
    (re.compile(r"seven principles for ai|bmw.{0,20}7대 원칙", re.I), "2018-10"),
    (re.compile(r"iti.{0,20}ai policy principles|iti ai 정책 원칙", re.I), "2017"),
    (re.compile(r"카카오.{0,16}알고리즘 윤리", re.I), "2018"),
    (re.compile(r"이용자 중심의 지능정보사회", re.I), "2018"),
    (re.compile(r"principled artificial intelligence|원칙 기반 인공지능", re.I), "2020"),
    (re.compile(r"using artificial intelligence and algorithms", re.I), "2020-04"),
    (re.compile(r"understanding artificial intelligence ethics and safety|ai 윤리와 안전 이해", re.I), "2019-06"),
]


def _urls_of(item: dict) -> list[str]:
    out: list[str] = []
    raw = item.get("source_urls") or []
    if isinstance(raw, str):
        raw = [raw]
    for u in list(raw) + [item.get("page_url") or ""]:
        u = (u or "").strip()
        if u.startswith("http"):
            out.append(u.split("[")[0].strip())
    return out


def year_from_original_urls(urls: list[str]) -> str:
    """원문 경로의 /2019-06/ · /2020/04/ 만. iaae.ai 게시판은 무시."""
    for url in urls:
        host = (urlparse(url).hostname or "").lower()
        if "iaae.ai" in host:
            continue
        path = urlparse(url).path or ""
        m = re.search(r"/(20\d{2})-(\d{2})(?:/|$)", path)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
        m = re.search(r"/(20\d{2})/(\d{2})(?:/|$)", path)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
        m = re.search(r"/(20\d{2})(?:/|$)", path)
        if m:
            return m.group(1)
    return ""


def known_iaae_date(title: str) -> str:
    blob = title or ""
    for pat, d in _KNOWN:
        if pat.search(blob):
            return d
    return ""


def iaae_card_date(item: dict) -> str:
    """Dump-day 게시일이면 원문 연도·알려진 발표일, 아니면 항목 date."""
    raw = (item.get("date") or "")[:10]
    if raw not in IAAE_BOARD_DUMP_DATES:
        return raw
    title = " ".join(
        str(item.get(k) or "")
        for k in ("title", "document_name", "original_name", "short_name")
    )
    known = known_iaae_date(title)
    if known:
        return known
    extracted = year_from_original_urls(_urls_of(item))
    if extracted:
        return extracted
    m = re.search(r"\b(20\d{2})\b", item.get("title") or "")
    if m and m.group(1) not in {"2020"}:
        return m.group(1)
    return raw
