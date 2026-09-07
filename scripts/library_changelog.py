"""소개 하위 페이지용 업데이트 로그.

매일 도는 수집 커밋은 넣지 않는다. 사이트 구조·분류·파이프라인이
바뀐 지점만 날짜순(최신 먼저)으로 적는다.
"""
from __future__ import annotations

from typing import TypedDict


class ChangelogEntry(TypedDict):
    date: str
    title: str
    body: str
    tags: tuple[str, ...]


LIBRARY_CHANGELOG: list[ChangelogEntry] = [
    {
        "date": "2026-09-07",
        "title": "메뉴를 라이브러리·동향 / 소개·업데이트로 나눈다",
        "body": "왼쪽은 라이브러리와 AI 안전 동향, 오른쪽은 소개와 업데이트다. 동향은 시리즈 사이트로 새 탭에서 연다.",
        "tags": ("사이트",),
    },
    {
        "date": "2026-09-07",
        "title": "종류와 겹치는 주제 리본을 뺀다",
        "body": "윤리·규범, 법, 가이드라인, 표준은 문서 종류와 같은 축이라 주제 필터·카드에서 빼 둔다. 국가안보·피지컬AI·딥페이크 같은 내용 주제만 남긴다.",
        "tags": ("사이트",),
    },
    {
        "date": "2026-09-07",
        "title": "카드는 접지 않고 제목에서 원문을 연다",
        "body": "카드 클릭으로 요약을 접지 않는다. URL이 있는 제목은 파란 밑줄 링크로 두고, 원문과 다른 외부 링크는 새 탭에서 연다.",
        "tags": ("사이트",),
    },
    {
        "date": "2026-09-07",
        "title": "시·도·주 문서는 지방·주로 분류한다",
        "body": "교육청·광역시·특별시, 미국 주·시, 중국 지방정부처럼 발급 주체가 지방이면 국가·부처가 아니라 지방·주로 둔다. 교육부+교육청이나 노르웨이 지방정부부 같은 중앙부처는 그대로 둔다.",
        "tags": ("분류",),
    },
    {
        "date": "2026-09-07",
        "title": "필터에 종류·주체·주제·국가 라벨을 단다",
        "body": "리본 묶음마다 ‘전체’ 왼쪽에 이름을 쓰고, 묶음 사이는 실선으로 구분한다. 상세 요약은 종류·주체 키워드에 밑줄, 주제 키워드에 볼드를 쓴다.",
        "tags": ("사이트",),
    },
]


def changelog_months(
    entries: list[ChangelogEntry] | None = None,
) -> list[tuple[str, str, list[ChangelogEntry]]]:
    src = entries if entries is not None else LIBRARY_CHANGELOG
    buckets: dict[str, list[ChangelogEntry]] = {}
    order: list[str] = []
    for item in src:
        ym = item["date"][:7]
        if ym not in buckets:
            buckets[ym] = []
            order.append(ym)
        buckets[ym].append(item)
    out: list[tuple[str, str, list[ChangelogEntry]]] = []
    for ym in order:
        y, m = ym.split("-")
        out.append((ym, f"{int(y)}년 {int(m)}월", buckets[ym]))
    return out
