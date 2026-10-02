#!/usr/bin/env bash
# 수집·큐레이션·빌드 결과만 커밋하고 push한다 (run_daily_pipeline.sh 6단계, 매일 09:00).
#
# - 아래 DATA_PATHS의 바뀐 파일만 커밋한다. 작업 중인 코드나 다른 세션이 stage해 둔
#   파일은 섞이지 않는다.
# - 원격이 앞서 있으면(다른 세션이 코드를 올린 경우) 작업 폴더가 깨끗할 때만 rebase해서
#   올린다. 작업 중인 변경이 있거나 충돌하면 커밋은 로컬에 두고 경고만 남긴다
#   (force push 하지 않음, 다음 실행이 다시 시도).
#
# 종료 코드: 0 = 커밋·push 완료 또는 변경 없음, 3 = 경고(push 못 함), 그 외 = 실패.
# 다이제스트 저장소의 commit_digest_data.sh와 같은 방식.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

DATA_PATHS=(
  collections
  cache
  docs
  dist
  documents.json
  documents.csv
  catalog.csv
  catalog.json
)

existing=()
for p in "${DATA_PATHS[@]}"; do
  [[ -e "$p" ]] && existing+=("$p")
done

# 새 날짜 파일(untracked)까지 포함해 데이터 경로만 stage
git add -A -- "${existing[@]}"
if git diff --cached --quiet -- "${existing[@]}"; then
  echo "데이터 변경 없음 — 커밋 생략"
  exit 0
fi

# 폴더 이름 대신 바뀐 파일 목록으로 커밋한다 (추적 파일이 없는 폴더는 pathspec 오류).
changed="$(mktemp)"
trap 'rm -f "$changed"' EXIT
git diff --cached --name-only -z -- "${existing[@]}" >"$changed"
files=$(tr -cd '\0' <"$changed" | wc -c | tr -d ' ')
git commit -q -m "일일 라이브러리 갱신 (자동)" -m "OECD 수집·큐레이션·사이트 빌드." \
  --pathspec-from-file="$changed" --pathspec-file-nul
short=$(git rev-parse --short HEAD)

branch=$(git branch --show-current)
if ! git rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then
  echo "데이터 커밋 $short (${files}개 파일) — $branch 에 원격 추적 브랜치가 없어 push 생략"
  exit 3
fi

if ! git fetch -q origin; then
  echo "데이터 커밋 $short (${files}개 파일) — fetch 실패, push 생략"
  exit 3
fi
behind=$(git rev-list --count 'HEAD..@{u}')
if (( behind > 0 )); then
  # 다른 세션이 같은 브랜치에 코드를 올린 경우. 작업 폴더가 깨끗할 때만 rebase로
  # 데이터 커밋을 그 위에 올린다. 작업 중인 변경이 있거나 충돌하면 손대지 않는다.
  if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    echo "데이터 커밋 $short (${files}개 파일) — 원격이 ${behind}커밋 앞서고 작업 중인 변경이 있어 push 생략"
    exit 3
  fi
  if ! git rebase -q '@{u}' >/dev/null 2>&1; then
    git rebase --abort >/dev/null 2>&1 || true
    echo "데이터 커밋 $short (${files}개 파일) — 원격 ${behind}커밋과 rebase 충돌, push 생략"
    exit 3
  fi
  short=$(git rev-parse --short HEAD)
fi

if ! git push -q origin "HEAD:$branch"; then
  echo "데이터 커밋 $short (${files}개 파일) — push 실패"
  exit 3
fi
echo "데이터 커밋·push $short (${files}개 파일 → $branch)"
