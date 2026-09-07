#!/usr/bin/env bash
# 일일 라이브러리 갱신: OECD 수집 → 외교부 → IAAE 보강 → 큐레이션 → 사이트 빌드 → 텔레그램 요약
# 스케줄: launchd com.user.ai-safety-library-daily (매일 09:00)
#
# 실행: ./run_daily_pipeline.sh
# 환경: Digest와 같은 ai_safety_daily_env (OPENROUTER_API_KEY, TELEGRAM_* 등)
# LIBRARY_PUSH=0 이면 git push 생략 (기본 1)
# LIBRARY_CURATE_LIMIT 기본 120
# PIPELINE_TELEGRAM=0 이면 종료 텔레그램 알림만 생략
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
REPORT_FILE="$(mktemp -t ai-safety-library-pipeline.XXXXXX)"
BEFORE_FILE="$(mktemp -t ai-safety-library-before.XXXXXX)"
trap 'rm -f "$REPORT_FILE" "$BEFORE_FILE"' EXIT

_record() {
  # id  label  status  duration  detail
  printf '%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "${5:-}" >>"$REPORT_FILE"
}

_run_step() {
  local id="$1" label="$2"
  shift 2
  local t0 t1 dur rc=0
  echo ""
  echo "▶ ${id} ${label}"
  t0=$(date +%s)
  set +e
  "$@"
  rc=$?
  set -e
  t1=$(date +%s)
  dur=$((t1 - t0))s
  if [[ $rc -eq 0 ]]; then
    _record "$id" "$label" ok "$dur" ""
  else
    _record "$id" "$label" fail "$dur" "exit $rc"
    echo "  ⚠ ${label} 실패 (exit $rc) — 파이프라인은 계속합니다." >&2
  fi
  return 0
}

# 시작 시 컬렉션 건수 스냅샷 (텔레그램 변동 표시용)
python3 - <<'PY' >"$BEFORE_FILE"
import json, sys
from pathlib import Path
sys.path.insert(0, "scripts")
from library_common import COLLECTIONS, load_collection
out = {}
for key, _ in COLLECTIONS:
    try:
        out[key] = int(load_collection(key).get("count") or 0)
    except Exception:
        out[key] = 0
print(json.dumps(out, ensure_ascii=False))
PY

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
if [[ -n "${MOFA_COOKIE:-}" ]]; then
  echo " MOFA: 쿠키 설정됨"
else
  echo " MOFA: 쿠키 없음 — 외교부 수집은 건너뜀"
fi
if [[ -n "${TELEGRAM_BOT_TOKEN:-}" && -n "${TELEGRAM_CHAT_ID:-}" ]]; then
  echo " TELEGRAM: 설정됨"
else
  echo " TELEGRAM: 없음"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

_run_step "1" "OECD Policy Navigator 수집" \
  python3 scripts/ingest_agora_oecd.py --oecd-only

if [[ -f /tmp/agora_dl/agora/documents.csv ]]; then
  _run_step "1b" "AGORA 재수집" \
    python3 scripts/ingest_agora_oecd.py --agora-only
else
  echo "  (AGORA CSV 없음 — 건너뜀. 수동: Zenodo → /tmp/agora_dl/agora/documents.csv)"
  _record "1b" "AGORA 재수집" warn "0s" "CSV 없음"
fi

_run_step "1c" "외교부 게시판 수집" \
  python3 scripts/ingest_mofa_board.py

_run_step "2" "IAAE 목록 수집" \
  python3 scripts/ingest_iaae_board.py

_run_step "3" "IAAE 원문 보강" \
  python3 scripts/enrich_iaae.py

_run_step "4" "LLM 큐레이션" \
  python3 scripts/curate_llm.py --limit "$CURATE_LIMIT" --workers 6

_run_step "5" "사이트 빌드" \
  python3 scripts/build_site.py

if [[ "$PUSH" == "1" ]] && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo ""
  echo "▶ 6 변경분 커밋·푸시"
  t0=$(date +%s)
  git add -A collections/ cache/ docs/ dist/ documents.json 2>/dev/null || true
  if git diff --cached --quiet; then
    echo "  커밋할 변경 없음"
    _record "6" "커밋·푸시" ok "$(( $(date +%s) - t0 ))s" "변경 없음"
  else
    set +e
    git commit -m "$(cat <<'EOF'
일일 라이브러리 갱신 (자동)

OECD 수집·큐레이션·사이트 빌드.
EOF
)"
    commit_rc=$?
    if [[ $commit_rc -eq 0 ]]; then
      git push origin HEAD
      push_rc=$?
    else
      push_rc=1
    fi
    set -e
    dur=$(( $(date +%s) - t0 ))s
    if [[ $commit_rc -ne 0 ]]; then
      _record "6" "커밋·푸시" warn "$dur" "커밋 없음/실패"
    elif [[ $push_rc -ne 0 ]]; then
      _record "6" "커밋·푸시" fail "$dur" "push 실패"
      echo "  ⚠ push 실패 — 로컬 커밋만 유지" >&2
    else
      _record "6" "커밋·푸시" ok "$dur" ""
    fi
  fi
else
  _record "6" "커밋·푸시" warn "0s" "PUSH=0 또는 git 아님"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ "${PIPELINE_TELEGRAM:-1}" =~ ^(0|false|no|off)$ ]]; then
  echo " TELEGRAM: PIPELINE_TELEGRAM=0 — 요약 알림 생략"
elif ! python3 scripts/notify_pipeline_telegram.py --report "$REPORT_FILE" --before "$BEFORE_FILE"; then
  echo " ⚠ 텔레그램 파이프라인 요약 전송 실패 — 수집 결과는 그대로입니다." >&2
fi

echo "완료: $(date '+%Y-%m-%d %H:%M:%S %z')"
echo "로그: /tmp/ai-safety-library-daily.out.log"
echo "사이트: https://songkyungho.github.io/ai-safety-library/"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
