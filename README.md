# AI 안전 라이브러리

외교부·IAAE가 모아 둔 AI 거버넌스·국가 정책·윤리 원칙 문서와, 해외 문서 아카이브(AGORA, OECD Policy Navigator)를 한곳에 정리한 자료 저장소입니다. 일일 뉴스 요약(AI Safety Digest)과는 별개입니다.

2026-09-04 스냅샷 기준 **3,994건**.

| 컬렉션 | 건수 | 기간 | 목록 |
|---|---:|---|---|
| [외교부 글로벌 AI거버넌스 논의](collections/mofa-governance/catalog.md) | 168 | 2021-01-01 ~ 2026-07-21 | [catalog](collections/mofa-governance/catalog.md) · [본문](collections/mofa-governance/posts.md) |
| [외교부 주요국 AI 정책](collections/mofa-country-policy/catalog.md) | 96 | 2024-01-16 ~ 2026-08-02 | [catalog](collections/mofa-country-policy/catalog.md) · [본문](collections/mofa-country-policy/posts.md) |
| [IAAE 연구자료실](collections/iaae-ethics/catalog.md) | 144 | 2019-06-21 ~ 2026-08-28 | [catalog](collections/iaae-ethics/catalog.md) |
| [ETO AGORA](collections/agora/catalog.md) | 1,084 | 2016-12-12 ~ 2026-06-02 | [catalog](collections/agora/catalog.md) |
| [OECD.AI Policy Navigator](collections/oecd-navigator/catalog.md) | 2,502 | 1956 ~ 2026 (시작 연도) | [catalog](collections/oecd-navigator/catalog.md) |

전체 색인: `catalog.csv` · `catalog.json`

## 컬렉션

- **외교부 글로벌 AI거버넌스 논의** — UN·OECD·G7·G20·GPAI·AI Summit 등 국제 문서. 한국어 핵심내용과 원문 URL이 있다.
- **외교부 주요국 AI 정책** — 미국·중국·EU·일본·영국 등 국가·지역 정책. 같은 형식.
- **IAAE 연구자료실** — 국제인공지능윤리협회가 큐레이션한 국내외 윤리 원칙·가이드라인. Digest에 쌓인 제목 카드(기관·날짜·IAAE 페이지 URL)를 모았다. 본문·PDF는 IAAE 원문을 본다.
- **ETO AGORA** — Georgetown CSET / Emerging Technology Observatory의 법·규정·표준 아카이브. Zenodo v1.30.0 (2026-06-16). 메타데이터·요약·공식 URL만 보관하고, 전문 파일은 넣지 않는다. 라이선스 **CC BY-NC 4.0**. 미국 연방법·주법 비중이 크다.
- **OECD.AI Policy Navigator** — 국가·국제기구 AI 정책 이니셔티브. API `https://api.oecdai.org/policy-initiatives`에서 2,502건을 받았다. `date`는 시작 연도(`startYear-01-01`)라 일부 항목이 AI 이전 연도로 내려간다.

## 데이터 필드

공통 필드(`catalog.csv`, 각 `collections/*/items.json`):

| 필드 | 설명 |
|---|---|
| `id` | `{컬렉션}-{원 id}` |
| `collection` | `mofa-governance` · `mofa-country-policy` · `iaae-ethics` · `agora` · `oecd-navigator` |
| `title` | 제목 |
| `org` / `category` | 기관 또는 게시판 분류 |
| `date` | 작성일 (YYYY-MM-DD). OECD는 시작 연도 추정 |
| `page_url` | 큐레이터 페이지 또는 공식 문서 URL |
| `source_urls` | 원 문서 URL |
| `body` | 핵심내용·요약 (외교부는 한국어, AGORA·OECD는 영어) |

## 출처·인용

- AGORA: Emerging Technology Observatory AGORA dataset, https://eto.tech/dataset-docs/agora-dataset/ · https://doi.org/10.5281/zenodo.20714047 (CC BY-NC 4.0). 요약 일부는 미검수 기계생성일 수 있다.
- Policy Navigator: OECD.AI (2025), OECD.AI Policy Navigator, https://oecd.ai/dashboards

## Digest와의 관계

신규 IAAE 항목은 계속 [AI Safety Digest](https://songkyunghosong.github.io/ai-safety-digest/) 파이프라인이 받는다. 이 저장소는 그 문서들을 라이브러리로 모아 둔 사본이다. AGORA·OECD는 Digest가 받지 않는 문서 단위 아카이브라 여기만 둔다.

## 동일 문서 클러스터

2026-09-04 기준 3,994건 중 **484건**이 **135개** 클러스터로 묶인다. 교차 컬렉션(외교부·IAAE·AGORA·OECD에 같은 문서가 있는 경우)은 **50개**.

| 종류 | 의미 | 개수 |
|---|---|---:|
| `same-document` | 같은 법·선언·전략·보고서 | 50 |
| `same-act` | AGORA가 조항별로 나눈 같은 법률 (NDAA 등) | 31 |
| `duplicate-record` | 한 컬렉션 안의 중복 레코드 | 54 |

목록: [`clusters/README.md`](clusters/README.md) · 조인 테이블 `clusters/membership.csv` · 재실행 `scripts/cluster_documents.py` (`--llm`은 OpenRouter)

화면: `python3 scripts/build_site.py` 후 [`dist/index.html`](dist/index.html). 국제협력 트래커와 같은 네비·검색·카드 톤이다.

수집 스크립트: `scripts/ingest_agora_oecd.py`
