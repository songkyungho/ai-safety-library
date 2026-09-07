#!/usr/bin/env python3
"""라이브러리 일일 파이프라인 종료 후 텔레그램 한 통 요약.

건마다 보내지 않는다. 단계 TSV + 수집·큐레이션 캐시 카운트만 모은다.
TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 없으면 건너뛴다.
PIPELINE_TELEGRAM=0 이면 호출부에서 이 스크립트를 안 탄다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from library_common import ROOT, load_collection  # noqa: E402
from telegram_notify import send_telegram_text, telegram_configured  # noqa: E402

PUBLIC_URL = "https://songkyungho.github.io/ai-safety-library/"
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def parse_report_tsv(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 4)
        while len(parts) < 5:
            parts.append("")
        sid, label, status, dur, detail = parts
        rows.append(
            {
                "id": sid.strip(),
                "label": label.strip(),
                "status": (status or "ok").strip(),
                "dur": dur.strip(),
                "detail": _ANSI_RE.sub("", detail).strip(),
            }
        )
    return rows


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _collection_count(key: str) -> int:
    try:
        return int(load_collection(key).get("count") or 0)
    except (OSError, json.JSONDecodeError, TypeError):
        return 0


def _iaae_new_count() -> int:
    path = ROOT / "cache" / "iaae_board_new_idxs.txt"
    if not path.is_file():
        return 0
    return sum(1 for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())


def _mofa_new_count() -> int:
    path = ROOT / "cache" / "mofa_board_new_seqs.txt"
    if not path.is_file():
        return 0
    return sum(1 for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())


def format_library_telegram(
    rows: list[dict[str, str]],
    *,
    now: datetime | None = None,
    before: dict | None = None,
    public_url: str = PUBLIC_URL,
) -> str:
    now = now or datetime.now()
    n = len(rows)
    n_ok = sum(1 for r in rows if r["status"] == "ok")
    n_warn = sum(1 for r in rows if r["status"] == "warn")
    n_fail = sum(1 for r in rows if r["status"] == "fail")
    lines = [
        "AI Safety Library 파이프라인",
        f"{now.strftime('%Y-%m-%d %H:%M')} · {n}단계  성공 {n_ok} · 경고 {n_warn} · 실패 {n_fail}",
    ]

    before = before or {}
    oecd_now = _collection_count("oecd-navigator")
    iaae_now = _collection_count("iaae-ethics")
    agora_now = _collection_count("agora")
    mofa_g = _collection_count("mofa-governance")
    mofa_c = _collection_count("mofa-country-policy")
    iaae_new = _iaae_new_count()
    mofa_new = _mofa_new_count()

    bits = []
    if oecd_now:
        bits.append(f"OECD {oecd_now}건")
    mofa_now = mofa_g + mofa_c
    if mofa_now:
        bit = f"외교부 {mofa_now}건"
        if mofa_new:
            bit += f"(+{mofa_new})"
        bits.append(bit)
    if iaae_now:
        bit = f"IAAE {iaae_now}건"
        if iaae_new:
            bit += f"(+{iaae_new})"
        bits.append(bit)
    if agora_now:
        bits.append(f"AGORA {agora_now}건")
    if bits:
        lines.append("수집  " + " · ".join(bits))

    # 시작 대비 델타(있으면)
    deltas = []
    for key, label, now_n in (
        ("oecd-navigator", "OECD", oecd_now),
        ("mofa-governance", "거버넌스", mofa_g),
        ("mofa-country-policy", "국가정책", mofa_c),
        ("iaae-ethics", "IAAE", iaae_now),
        ("agora", "AGORA", agora_now),
    ):
        prev = before.get(key)
        if isinstance(prev, int) and now_n != prev:
            deltas.append(f"{label} {prev}→{now_n}")
    if deltas:
        lines.append("변동  " + " · ".join(deltas))

    curate = _load_json(ROOT / "cache" / "curate_last_run.json")
    if curate:
        ok = curate.get("ok", 0)
        fail = curate.get("fail", 0)
        batch = curate.get("batch", 0)
        lines.append(f"큐레이션  시도 {batch} · 성공 {ok} · 실패 {fail}")

    docs = _load_json(ROOT / "documents.json")
    if docs:
        lines.append(
            f"문서  전체 {docs.get('count', '?')} · "
            f"범위내 {docs.get('in_scope_count', '?')} · "
            f"범위외 {docs.get('out_of_scope_count', '?')}"
        )

    lines.append(f"사이트  {public_url}")

    notable = [r for r in rows if r["status"] in ("fail", "warn")]
    if notable:
        lines.append("")
        for r in notable:
            mark = "실패" if r["status"] == "fail" else "경고"
            detail = r["detail"]
            if len(detail) > 90:
                detail = detail[:89] + "…"
            extra = f" — {detail}" if detail else ""
            lines.append(f"[{r['id']}] {r['label']}  {mark} ({r['dur']}){extra}")
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="라이브러리 파이프라인 텔레그램 요약")
    ap.add_argument("--report", required=True, help="단계 TSV 경로")
    ap.add_argument("--before", default="", help="시작 시 컬렉션 카운트 JSON")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    path = Path(args.report)
    rows = parse_report_tsv(path.read_text(encoding="utf-8") if path.is_file() else "")
    before = _load_json(Path(args.before)) if args.before else {}
    text = format_library_telegram(rows, before=before)

    if args.dry_run or not telegram_configured():
        if not args.dry_run:
            print(" TELEGRAM: 미설정 — 파이프라인 요약 알림 생략")
        print(text, end="")
        return 0
    if send_telegram_text(text):
        print(" TELEGRAM: 파이프라인 요약 전송")
        return 0
    print(" TELEGRAM: 전송 실패", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
