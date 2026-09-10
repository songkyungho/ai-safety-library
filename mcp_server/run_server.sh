#!/bin/bash
# iCloud로 동기화되는 이 저장소와 별개로, 파이썬 venv는 기기별로
# $HOME/.venvs/ai-safety-library-mcp 에 로컬로만 둔다 (README.md 설정 참고).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HOME/.venvs/ai-safety-library-mcp"

if [[ ! -x "$VENV/bin/python3" ]]; then
  echo "venv 없음: $VENV — mcp_server/README.md 의 설정 단계를 먼저 실행하세요." >&2
  exit 1
fi

exec "$VENV/bin/python3" "$DIR/server.py"
