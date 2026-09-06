#!/usr/bin/env bash
# 일일 라이브러리 갱신: OECD 수집 → IAAE 보강 → 큐레이션 → 사이트 빌드
# 스케줄: launchd com.user.ai-safety-library-daily (매일 09:00)
#
# 실행: ./run_daily_pipeline.sh
# 환경: Digest와 같은 ai_safety_daily_env (OPENROUTER_API_KEY 등)
# LIBRARY_PUSH=0 이면 git push 생략 (기본 1)
# LIBRARY_CURATE_LIMIT 기본 120
#
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

_load_env_file() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  set -a
  # shellcheck disable=SC1090
  source "$f"
  set +a
}

if [[ -n "${AI_SAFETY_ENV_FILE:-}" ]]; then
  _load_env_file "$AI_SAFETY_ENV_FILE"
else
  _load_env_file "$HOME/.ai_safety_daily_env"
  _load_env_file "$DIR/../AI Safety/ai_safety_daily_env"
  _load_env_file "$DIR/ai_safety_library_env"
fi

export PYTHONWARNINGS="${PYTHONWARNINGS:-ignore::Warning:urllib3}"
export PYTHONUNBUFFERED=1

# launchd 백그라운드 스로틀·유휴 슬립 완화 (Digest와 동일 패턴)
if [[ -z "${PIPELINE_PERF_WRAP:-}" ]]; then
  export PIPELINE_PERF_WRAP=1
  if [[ -x /usr/sbin/taskpolicy ]]; then
    exec /usr/bin/caffeinate -i -m /usr/sbin/taskpolicy -a /bin/bash "$0" "$@"
  fi
  exec /usr/bin/caffeinate -i -m /bin/bash "$0" "$@"
fi

CURATE_LIMIT="${LIBRARY_CURATE_LIMIT:-120}"
PUSH="${LIBRARY_PUSH:-1}"
LOG_TS="$(date '+%Y-%m-%d %H:%M:%S %z')"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " AI Safety Library 일일 파이프라인"
echo " 시작: $LOG_TS"
echo " 작업 디렉터리: $DIR"
echo " CURATE_LIMIT=$CURATE_LIMIT  PUSH=$PUSH"
if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
  echo " LLM: OpenRouter 설정됨"
else
  echo " LLM: OPENROUTER_API_KEY 없음 — 큐레이션은 실패할 수 있음"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

step() { echo ""; echo "▶ $*"; }

step "1/5 OECD Policy Navigator 수집"
python3 scripts/ingest_agora_oecd.py --oecd-only

# AGORA는 Zenodo CSV가 있을 때만
if [[ -f /tmp/agora_dl/agora/documents.csv ]]; then
  step "1b AGORA CSV 감지 → 재수집"
  python3 scripts/ingest_agora_oecd.py --agora-only || echo "(AGORA 수집 실패 — 계속)"
else
  echo "  (AGORA CSV 없음 — 건너뜀. 수동: Zenodo → /tmp/agora_dl/agora/documents.csv)"
fi

step "2/5 IAAE 연구자료실 목록 수집 (신규만)"
python3 scripts/ingest_iaae_board.py || echo "(IAAE 목록 수집 실패 — 계속)"

step "3/5 IAAE 원문 URL 보강 (미충족 항목만)"
python3 scripts/enrich_iaae.py || echo "(IAAE enrich 일부 실패 — 계속)"

step "4/5 LLM 큐레이션 (신규·미충족 최대 ${CURATE_LIMIT}건)"
python3 scripts/curate_llm.py --limit "$CURATE_LIMIT" --workers 6

step "5/5 사이트 빌드"
python3 scripts/build_site.py

if [[ "$PUSH" == "1" ]] && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  step "변경분 커밋·푸시"
  git add -A collections/ cache/ docs/ dist/ documents.json 2>/dev/null || true
  if git diff --cached --quiet; then
    echo "  커밋할 변경 없음"
  else
    git commit -m "$(cat <<'EOF'
일일 라이브러리 갱신 (자동)

OECD 수집·큐레이션·사이트 빌드.
EOF
)" || true
    git push origin HEAD || echo "(push 실패 — 로컬 커밋만 유지)"
  fi
fi

echo ""
echo "완료: $(date '+%Y-%m-%d %H:%M:%S %z')"
echo "로그: /tmp/ai-safety-library-daily.out.log"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
