# Digital Policy Alert (DPA) 소스 검토 메모

작성일: 2026-09-11  
목적: **AI 안전 라이브러리**에 DPA를 소스 후보로 넣을지 논의하기 위한 사실 정리  
대상 스레드: [Regulating Artificial Intelligence](https://digitalpolicyalert.org/threads/regulating-artificial-intelligence)

> 결론 방향: 일일 뉴스 다이제스트보다 **라이브러리(규제·정책 문서/조치 카탈로그)** 쪽 작업에 더 가깝다.  
> 원본 공식 문서 URL은 현재 API 응답에 없고, **DPA 이벤트/intervention 페이지로 연결**하는 방식이면 당장 사용 가능하다.

---

## 1. 왜 라이브러리인가

| | Digest | Library |
|---|---|---|
| 단위 | 하루·뉴스성 링크 | 원본 기준 문서/조치 카탈로그 |
| DPA 성격 | 월간 블로그 RSS는 얇음 | 규제 **intervention + event 타임라인**이 핵심 |
| 스레드 규모 | 일일 수집에 과함 | 증분·카탈로그화에 맞음 |

DPA *Regulating Artificial Intelligence* 스레드는 intervention 약 **2,700+** / jurisdiction **215** 규모다.  
법안 발의→가결→서명→시행, 소송, 국제 성명 등 **정책 생애주기**가 구조화되어 있어 라이브러리 문서/히스토리 모델과 결이 맞다.

---

## 2. 접근 채널 요약

### 2.1 RSS

- URL: `https://digitalpolicyalert.org/feed.xml`
- 제목: *Digital Policy Alert — Reports & Blog*
- 내용: 월간 Global Digital Policy Roundup, 주제 리포트, 블로그 (최근 약 20건)
- **Activity Tracker / 스레드 이벤트는 없음**
- AI 안전·거버넌스로 직접 쓸 만한 건 산발적 (예: Nigeria AI Governance 리포트 정도)

→ 라이브러리 본수집 소스로는 부적합. 참고용만.

### 2.2 API (확인 완료, 키 동작)

- 키: `DPA_API` (현재 `AI Safety/ai_safety_daily_env`에 저장됨 — 라이브러리 env로 이전 검토 필요)
- 인증 헤더: `Authorization: APIKey <key>`
- 호스트: `https://api.globaltradealert.org`
- 발급: [API Access](https://digitalpolicyalert.org/api-access) → 가입 후 demo key
- Demo 한도(계정 UI 기준): **일 1,000 / 주 4,000** entries  
  무제한은 연구·비상업 목적 신청(폼 검토)

공개 문서: [global-trade-alert/docs `.api/dpa-data.md`](https://github.com/global-trade-alert/docs/blob/main/.api/dpa-data.md)  
(README에는 “DPA not yet available”로 남아 있으나, 실제 엔드포인트는 동작함)

### 2.3 MCP

- `https://mcp.digitalpolicyalert.org/mcp` (Claude/ChatGPT 등)
- 라이브러리 배치 수집보다는 질의용. 이번 검토의 주경로는 REST API.

---

## 3. 타깃 스레드 식별

| 필드 | 값 |
|---|---|
| 이름 | Regulating Artificial Intelligence |
| slug | `regulating-artificial-intelligence` |
| issue id | **42** |
| interventions (메타) | ≈ 2,731 |
| jurisdictions | 215 |
| event-list count | ≈ 2,703 |
| last_updated (확인 시점) | 2026-09-10 |

레이아웃/메타:

```http
GET /dpa/issue/regulating-artificial-intelligence/layout
Authorization: APIKey …
```

---

## 4. 실제로 쓸 엔드포인트

### A. 스레드 단위 수집 (권장)

사이트가 쓰는 issue API이며, **같은 API 키로 동작**한다.

```http
GET /dpa/issue/42/event-list/?limit=100&offset=0
Authorization: APIKey …
```

- 페이지네이션: `limit` / `offset` (`count`로 전체 건수)
- 응답 단위: **intervention** (그 안에 `events[]` 타임라인)

관련:

- `GET /dpa/issue/{id}` / `…/layout` / `…/stats`
- `GET /dpa/event/{id}/` — 이벤트 상세(출처 메타 포함, URL은 아래 참고)

### B. 공식 문서 엔드포인트

```http
POST /api/v1/dpa/events/
Content-Type: application/json
Authorization: APIKey …
```

필터 예: `implementing_jurisdiction`, `economic_activity`, `policy_area`, `event_period` 등  
(`economic_activity` 9 = *ML and AI development*)

**주의:** `issue` / `thread` / `slug` 필터는 **없음** (넣으면 400).  
다만 응답 item에 `threads: [{ id: 42, slug: "regulating-artificial-intelligence", … }]` 가 붙는 경우가 있어,  
EA=9 등으로 받은 뒤 클라이언트에서 thread id=42로 걸러낼 수는 있다.  
스레드 정합성을 우선하면 **A(event-list)가 맞다.**

---

## 5. 데이터 구조 (라이브러리 매핑용)

### Intervention (정책 조치 / 상위 레코드)

`event-list` 한 줄 ≈ 하나의 intervention.

주요 필드:

- `id`, `title`, `slug`
- `country`
- `status` (`{ id, name }` — 예: adopted, under deliberation, in force)
- `date_current`
- `events[]`

라이브러리 링크 후보:

- `https://digitalpolicyalert.org/intervention/{slug}`  
  (또는 공식 API의 `intervention_url` 형태: `/change/{id}-…`)

### Event (생애주기 단계)

intervention 하위, 또는 `GET /dpa/event/{id}/`.

주요 필드:

- `id`, `slug`, `title`, `description`, `date`
- `action_type` / `status` (발의·가결·서명·시행·판결 등)
- `implementers` / `implementer`
- `sources[]` (아래)

라이브러리 링크 (사용 가능):

- `https://digitalpolicyalert.org/event/{slug}`

### 출처(sources) — 원본 아웃링크

| 채널 | 원본 공식 URL | 비고 |
|---|---|---|
| `event-list` | 없음 (`source: null`) | |
| `GET /dpa/event/{id}/` | **URL 필드 없음** | `name`, `institution_name`, `source_type`만 |
| 공식 `dpa/events` | 원본 없음 | DPA `url` / `intervention_url`만 |

예시 (`/dpa/event/{id}/`의 sources):

```json
{
  "name": "SB-813 Independent verification organizations",
  "institution_name": "California Legislative Information",
  "source_type": "Official"
}
```

**결정:** 원본 공식 문서 URL이 없어도 **DPA 이벤트/intervention URL을 랜딩으로 연결**해도 된다.  
(라이브러리가 “원본 랜딩”을 원칙으로 하되, DPA를 **큐레이터·2차 출처**로 두는 형태.)

---

## 6. 최근 intervention 샘플 (2026-09-11 API 스냅샷)

`event-list` 앞쪽 일부. 전체 ~2,703건 중 일부.

1. **US** — Artificial Intelligence: Auditors: Registration (AB 1405) — adopted  
2. **UK** — Personal Data (Digital Twins) Bill (No. 144) — under deliberation  
3. **US** — Independent Verification Organizations Act (SB 813) — adopted  
4.–5. **UK** — Artificial Superintelligence Bill (No. 142) 관련 조항들 — under deliberation  
6. **Korea** — 개인정보보호법 개정(AI 개발용 개인정보 이용 예외) — adopted / 2027-03-09 시행 예정  
7.–11. **Australia** — AI Kill Switch and Data Centre Control Bill 2026 (동일 법안이 조항별 intervention으로 분할)  
12. **US** — Minnesota AI-nudification 금지법 관련 xAI 소송 — under deliberation  
13. **Chinese Taipei** — frontier AI cybersecurity risks 정책 — adopted  
14. **G20** — Innovation Ministerial Statement on emerging technologies and AI — adopted  
15. **Brazil** — 선거 deepfake 민사소송 판결 — in force  

특징:

- 한 법안이 **여러 intervention**으로 쪼개지기도 함 (호주 Kill Switch 등)
- 국가법·주법·소송·국제 성명이 한 스레드에 혼재
- 한국 항목도 포함 (개인정보·AI 학습 예외 등)

---

## 7. 라이브러리 편입 시 논의 포인트

1. **단위**  
   - intervention 1건 = 라이브러리 document 1건?  
   - 아니면 event(단계) 단위?  
   - 법안 분할(조항별 intervention)을 어떻게 묶을지.

2. **랜딩 URL**  
   - 1차: DPA intervention 또는 event URL  
   - 추후: 웹/수동/다른 소스로 공식 문서 URL enrichment

3. **필드 매핑 초안**

   | 라이브러리 | DPA |
   |---|---|
   | 문서명 | `intervention.title` 또는 최신 `event.title` |
   | 기관/관할 | `country` / implementers |
   | 문서종류 | status + action_type / event type으로 추론 또는 “규제 이벤트” 고정 |
   | 발표시점 | `date_current` 또는 최초/최신 event.date |
   | 핵심내용 | event `description` (상세 API) |
   | 랜딩 URL | DPA intervention/event URL |
   | 외부 ID | `dpa:intervention:{id}` / `dpa:event:{id}` |

4. **수집 전략**  
   - 전체 백필: demo 한도 고려해 여러 날에 나눠 offset 페이지  
   - 이후: `last_updated` / `date_current` 기준 증분  
   - 키·env는 digest(`ai_safety_daily_env`)와 분리해 **라이브러리 쪽**으로 두는 편이 맞음

5. **범위 필터**  
   - 스레드 전체 vs 한국·주요국만 vs `in force`/`adopted`만  
   - “AI 안전”보다 넓은 **AI 규제 전반**이므로 큐레이션 기준 필요

6. **라이선스**  
   - 사이트: CC BY-NC 4.0 (비상업)  
   - API/재배포 조건은 이용 전 재확인

---

## 8. 하지 말 것 / 오해 방지

- RSS만으로 스레드 이벤트를 수집하려 하지 말 것  
- 공식 `dpa/events`만으로 스레드 필터가 된다고 가정하지 말 것 (`issue` 필터 없음)  
- `economic_activity=9` ≠ 스레드 42 (근사치일 뿐, 수출통제·파트너십 등 혼입)  
- demo 응답의 `sources`에 공식 URL이 있다고 가정하지 말 것  

---

## 9. 다음 액션 후보

- [ ] 라이브러리 env에 `DPA_API` 이전/공유 방식 결정  
- [ ] `ingest_dpa_ai_thread.py` 초안 (issue 42 event-list → documents.json 스키마)  
- [ ] intervention vs event 단위·중복 병합 규칙 확정  
- [ ] 파일럿: 최근 N건 또는 한국-only ingest → `audit_library` / 사이트 미리보기  
- [ ] (선택) unlimited API 신청 후 sources URL 재확인  

---

## 참고 링크

- 스레드: https://digitalpolicyalert.org/threads/regulating-artificial-intelligence  
- API Access: https://digitalpolicyalert.org/api-access  
- RSS: https://digitalpolicyalert.org/feed.xml  
- DPA API 문서(초안): https://github.com/global-trade-alert/docs/blob/main/.api/dpa-data.md  
- 라이브러리 공개: https://songkyungho.github.io/ai-safety-library/  
- Digest(별개): https://songkyungho.github.io/ai-safety-digest/  
