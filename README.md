# AI 안전 라이브러리

AI 관련 법·윤리·선언·가이드라인을 **원본 랜딩 URL** 기준으로 모아 보여 주는 자료 저장소입니다. 외교부·IAAE·AGORA·OECD 등 여러 큐레이터에 같은 문서가 있어도 원본으로 묶고, 상세 페이지는 **발표 히스토리**입니다. 일일 뉴스 요약(AI Safety Digest)과는 별개입니다.

- **공개 사이트:** https://songkyungho.github.io/ai-safety-library/
- **소개:** https://songkyungho.github.io/ai-safety-library/about.html

**문서 필드**: 약칭 · 문서명(풀네임) · 기관 · 문서종류(법/법안/가이드라인·원칙/정책보고서 등) · 발표시점 · 핵심내용.
외교부 본문의 `●기관`/`●문서종류`/`●문서명`/`●핵심내용`을 파싱해 채웁니다.

## 빠른 사용

```bash
# 외교부 게시판 신규 (브라우저 Cookie → ~/.ai_safety_daily_env 의 MOFA_COOKIE)
python3 scripts/ingest_mofa_board.py

# IAAE 목록 신규 + 상세에서 [자료출처] URL 채우기
python3 scripts/ingest_iaae_board.py
python3 scripts/enrich_iaae.py

# OECD 재수집 (국가·sourceFiles 포함)
python3 scripts/ingest_agora_oecd.py --oecd-only

# 중복·원본 없음·약한 항목·죽은 링크 리포트 (+ 죽은 원본 URL 제거)
python3 scripts/audit_library.py --check-links --apply-dead

# 원본 기준 문서 인덱스 + 정적 사이트
python3 scripts/build_site.py
```

화면: [`docs/index.html`](docs/index.html) · 공개 https://songkyungho.github.io/ai-safety-library/

## 일일 자동 갱신

동향 Digest와 같이 **이 맥의 launchd**로 돌립니다. (GitHub Actions 아님)

- **시각:** 매일 09:00
- **에이전트:** `launchd/com.user.ai-safety-library-daily.plist`
- **하는 일:** OECD 수집 → 외교부 게시판(쿠키 있을 때) → IAAE 목록·보강 → 신규 LLM 큐레이션 → `build_site`(docs/) → MCP 검색 인덱스 → (기본) git push → GitHub Pages
- **수동 실행:** `./run_daily_pipeline.sh`

## 로컬 MCP

Cursor/Claude에서 라이브러리를 검색할 때 쓰는 stdio MCP 서버가 있습니다.

- 도구: `search_library` · `get_document` · `corpus_stats`
- 설정·색인: [`mcp_server/README.md`](mcp_server/README.md)
- 최초 1회: venv 설치 후 `python3 mcp_server/build_index.py`
- **로그:** `/tmp/ai-safety-library-daily.out.log` · `.err.log`
- **환경변수:** Digest의 `ai_safety_daily_env` (OpenRouter·텔레그램·`MOFA_COOKIE`) 재사용. 외교부 WAF 쿠키는 만료되면 브라우저에서 Cookie 헤더를 다시 넣는다. git에 커밋하지 말 것.
- **완료 알림:** 파이프라인 끝나면 텔레그램 한 통 (`PIPELINE_TELEGRAM=0`이면 생략)

IAAE는 이 라이브러리에서만 수집·보관한다. Digest로 신규분을 알리지 않는다.

push를 끄려면 `LIBRARY_PUSH=0 ./run_daily_pipeline.sh`.
텔레그램 알림을 끄려면 `PIPELINE_TELEGRAM=0 ./run_daily_pipeline.sh` (Digest와 같은 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`).

## 데이터

| 컬렉션 | 역할 |
|---|---|
| 외교부 글로벌 AI거버넌스 / 주요국 정책 | 한국어 요약 + 원문 URL |
| IAAE 연구자료실 | 큐레이터 카드 → 상세에서 원본 URL 추출 |
| ETO AGORA | 법·규정·표준 원문 메타 (CC BY-NC 4.0) |
| OECD.AI Policy Navigator | 정책 이니셔티브 + `gaiinCountry`·첨부 PDF |

공통 필드: `page_url`(큐레이터 또는 공식), `source_urls`(원본 후보), OECD는 `source_files`·`country` 추가.

**문서 단위** (`documents.json`): `canonical_url`, `title`(한글 우선), `country`/`flag`, `published`, `history[]`(발표·게시일만).

## 감사 리포트

`python3 scripts/audit_library.py` → `reports/audit-YYYYMMDD/`:

- `missing_original.csv` — 원본 랜딩 없음
- `duplicates.csv` — 동일 canonical / 기존 클러스터
- `weak.csv` — 본문 공란, OECD 2015년 이전 등
- `dead_links.csv` — HTTP 실패 (`--check-links`)

## 출처·인용

- AGORA: Emerging Technology Observatory, https://doi.org/10.5281/zenodo.20714047 (CC BY-NC 4.0)
- Policy Navigator: OECD.AI, https://oecd.ai/dashboards
