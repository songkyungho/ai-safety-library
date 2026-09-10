# ai-safety-library MCP 서버

`documents.json`을 SQLite(`knowledge/library.db`)로 색인해, 주제를 던지면
관련 법·가이드라인·정책 문서를 키워드(FTS5 trigram) + 의미(임베딩) 검색으로
같이 찾아주는 로컬 MCP 서버. 임베딩은 OpenRouter(`OPENROUTER_API_KEY`, 모델
`openai/text-embedding-3-small`)를 우선 사용하고, 없으면 OpenAI 직접 호출로
폴백한다.

## 구조

- `build_index.py` — `documents.json` → `knowledge/library.db`. **시스템 python3**로 실행.
  `run_daily_pipeline.sh`의 사이트 빌드 직후 자동 실행.
- `server.py` — MCP 서버 본체. 검색 도구 3종 노출. **전용 venv**(python 3.10+)로 실행.
- `run_server.sh` — `$HOME/.venvs/ai-safety-library-mcp` 를 찾아 `server.py` 실행.
  프로젝트 `.mcp.json` / Cursor `~/.cursor/mcp.json`이 이 스크립트를 가리킴.

venv를 저장소 밖(`$HOME/.venvs/`)에 두는 이유: 이 저장소는 iCloud Drive 안이라
venv를 넣으면 바이너리·수천 파일이 불필요하게 동기화된다. **`knowledge/library.db`는
저장소 안에 남겨 iCloud로 동기화**되게 한다(git에는 올리지 않음).

## 도구

- `search_library(topic, limit=15, in_scope_only=true, country="", doc_kind="", …)`
  키워드+의미 하이브리드(RRF). summary 포함 — 최종 관련성 판단은 호출자.
- `get_document(doc_id)` — `doc-…` id로 1건 상세.
- `corpus_stats()` — 총 건수/범위/종류별/임베딩 커버리지.

## 이 Mac 최초 설정

```bash
brew install python@3.12   # 없으면
python3.12 -m venv "$HOME/.venvs/ai-safety-library-mcp"
"$HOME/.venvs/ai-safety-library-mcp/bin/pip" install -r mcp_server/requirements.txt
python3 mcp_server/build_index.py   # knowledge/library.db (임베딩 포함)
```

Cursor를 재시작하면 `ai-safety-library` 서버가 잡힌다.

## 다른 Mac에서 쓰기

저장소·`knowledge/library.db`가 iCloud로 동기화돼 있다는 전제. venv만 새로:

```bash
python3.12 -m venv "$HOME/.venvs/ai-safety-library-mcp"
"$HOME/.venvs/ai-safety-library-mcp/bin/pip" install -r "<저장소 경로>/mcp_server/requirements.txt"
```

## 색인 갱신

일일 파이프라인이 `build_site` 뒤 `build_index.py --skip-if-fresh`를 돌린다. 수동:

```bash
python3 scripts/build_site.py          # documents.json 갱신
python3 mcp_server/build_index.py
```

## 동작 확인

```bash
mcp_server/run_server.sh   # stdin 대기 — Ctrl+C로 종료
```
