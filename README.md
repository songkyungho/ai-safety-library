# AI 안전 라이브러리

외교부·IAAE가 모아 둔 AI 거버넌스·국가 정책·윤리 원칙 문서를 한곳에 정리한 자료 저장소입니다. 일일 뉴스 요약(AI Safety Digest)과는 별개입니다.

2026-09-04 스냅샷 기준 **408건**.

| 컬렉션 | 건수 | 기간 | 목록 |
|---|---:|---|---|
| [외교부 글로벌 AI거버넌스 논의](collections/mofa-governance/catalog.md) | 168 | 2021-01-01 ~ 2026-07-21 | [catalog](collections/mofa-governance/catalog.md) · [본문](collections/mofa-governance/posts.md) |
| [외교부 주요국 AI 정책](collections/mofa-country-policy/catalog.md) | 96 | 2024-01-16 ~ 2026-08-02 | [catalog](collections/mofa-country-policy/catalog.md) · [본문](collections/mofa-country-policy/posts.md) |
| [IAAE 연구자료실](collections/iaae-ethics/catalog.md) | 144 | 2019-06-21 ~ 2026-08-28 | [catalog](collections/iaae-ethics/catalog.md) |

전체 색인: `catalog.csv` · `catalog.json`

## 컬렉션

- **외교부 글로벌 AI거버넌스 논의** — UN·OECD·G7·G20·GPAI·AI Summit 등 국제 문서. 한국어 핵심내용과 원문 URL이 있다.
- **외교부 주요국 AI 정책** — 미국·중국·EU·일본·영국 등 국가·지역 정책. 같은 형식.
- **IAAE 연구자료실** — 국제인공지능윤리협회가 큐레이션한 국내외 윤리 원칙·가이드라인. Digest에 쌓인 제목 카드(기관·날짜·IAAE 페이지 URL)를 모았다. 본문·PDF는 IAAE 원문을 본다.

## 데이터 필드

공통 필드(`catalog.csv`, 각 `collections/*/items.json`):

| 필드 | 설명 |
|---|---|
| `id` | `{컬렉션}-{원게시판 id}` |
| `collection` | `mofa-governance` · `mofa-country-policy` · `iaae-ethics` |
| `title` | 제목 |
| `org` / `category` | 기관 또는 게시판 분류 |
| `date` | 작성일 (YYYY-MM-DD) |
| `page_url` | 큐레이터 페이지 (외교부 또는 IAAE) |
| `source_urls` | 원 문서 URL (외교부 게시판의 「관련 링크」) |
| `body` | 한국어 핵심내용 (외교부만) |

## Digest와의 관계

신규 IAAE 항목은 계속 [AI Safety Digest](https://songkyunghosong.github.io/ai-safety-digest/) 파이프라인이 받는다. 이 저장소는 그 문서들을 라이브러리로 모아 둔 사본이다.
