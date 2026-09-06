#!/usr/bin/env bash
# 호환용: 일일 파이프라인으로 위임 (스케줄은 매일 09:00).
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_daily_pipeline.sh" "$@"
