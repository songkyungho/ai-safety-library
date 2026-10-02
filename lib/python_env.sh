# shellcheck shell=bash
# 라이브러리 파이프라인이 쓸 파이썬을 한 곳에서 고정한다 (run_*.sh 에서 source).
#
# launchd는 PATH가 /usr/bin:/bin 뿐이라 python3이 macOS 기본 3.9로 가고,
# 터미널은 Homebrew python3(패키지 없음)으로 가서 실행 경로마다 환경이 달랐다.
# 전용 venv(Homebrew 3.12)의 bin을 PATH 맨 앞에 두면 스크립트 안의
# python3 호출(heredoc 포함)이 모두 같은 venv로 간다.
#
# venv 만들기:
#   /opt/homebrew/opt/python@3.12/bin/python3.12 -m venv ~/.venvs/ai-safety-library
#   ~/.venvs/ai-safety-library/bin/pip install -r requirements.txt
#
# venv가 없으면 예전처럼 /usr/bin/python3(3.9)로 돌되 경고를 남긴다.
AI_SAFETY_LIBRARY_VENV="${AI_SAFETY_LIBRARY_VENV:-$HOME/.venvs/ai-safety-library}"
if [[ -x "$AI_SAFETY_LIBRARY_VENV/bin/python3" ]]; then
  case ":$PATH:" in
    *":$AI_SAFETY_LIBRARY_VENV/bin:"*) ;;
    *) export PATH="$AI_SAFETY_LIBRARY_VENV/bin:$PATH" ;;
  esac
  export VIRTUAL_ENV="$AI_SAFETY_LIBRARY_VENV"
  # TLS 검증을 macOS 신뢰 저장소로 (lib/py/sitecustomize.py)
  _ai_safety_lib_py="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/py"
  case ":${PYTHONPATH:-}:" in
    *":$_ai_safety_lib_py:"*) ;;
    *) export PYTHONPATH="$_ai_safety_lib_py${PYTHONPATH:+:$PYTHONPATH}" ;;
  esac
else
  echo "⚠ 라이브러리 venv 없음: $AI_SAFETY_LIBRARY_VENV — /usr/bin/python3로 실행합니다." >&2
  export PATH="/usr/bin:$PATH"
fi
