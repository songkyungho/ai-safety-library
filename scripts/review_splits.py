#!/usr/bin/env python3
"""분할 플래그(possible_false_merge) 검수·확정.

이미 --analyze 가 OpenRouter로 남긴 notes / split_clusters / instrument_key 를
1차로 규칙 확정하고, 애매한 건만 OpenRouter로 재확인한다.

사용:
  python3 scripts/review_splits.py              # 검수·캐시 기록
  python3 scripts/review_splits.py --apply-build  # + build/사이트는 별도
  python3 scripts/build_site.py

캐시: cache/instrument_splits.json
  item_id → split bucket (build_documents 가 url/cluster 대신 이 키로 묶음)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_ko import DEFAULT_MODEL, ensure_openrouter_key, llm_json  # noqa: E402
from library_common import write_json  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ANALYZE_PATH = ROOT / "cache" / "instrument_analyze.json"
SPLITS_PATH = ROOT / "cache" / "instrument_splits.json"
REPORT_PATH = ROOT / "reports" / "split_review.json"
TODAY = date.today().isoformat()
CONF_OK = {"high", "medium"}

CONFIRM_SYSTEM = """당신은 AI 안전 라이브러리 편집자입니다.
규칙으로 한 카드에 묶였지만, 1차 분석에서 '다른 제도가 섞였다'고 한 그룹입니다.
정말 나눠야 하는지 재확인하고, 나눌 item_id 묶음만 JSON으로 제시하세요.
원문에 없는 사실을 만들지 마세요. JSON만 출력.
"""


def load_json(path: Path) -> dict:
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    return {}


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, data)


def member_keys(body: dict) -> set[str]:
    return {
        (m.get("instrument_key") or "").strip().lower()
        for m in (body.get("members") or [])
        if (m.get("instrument_key") or "").strip()
    }


def clusters_from_keys(body: dict) -> list[list[str]]:
    """instrument_key 별로 item_id 묶음."""
    by: dict[str, list[str]] = {}
    for m in body.get("members") or []:
        mid = (m.get("item_id") or "").strip()
        key = (m.get("instrument_key") or "").strip().lower() or "_unknown"
        if not mid:
            continue
        by.setdefault(key, []).append(mid)
    return [ids for ids in by.values() if ids]


def normalize_clusters(raw_clusters, members: list[dict]) -> list[list[str]]:
    known = {(m.get("item_id") or "").strip() for m in members if m.get("item_id")}
    out = []
    seen = set()
    for cl in raw_clusters or []:
        if not isinstance(cl, list):
            continue
        ids = []
        for x in cl:
            mid = str(x).strip()
            if mid in known and mid not in seen:
                seen.add(mid)
                ids.append(mid)
        if ids:
            out.append(ids)
    # 누락 멤버는 단독 클러스터
    for mid in sorted(known - seen):
        out.append([mid])
    return out


def rule_confirm(did: str, entry: dict, body: dict) -> dict | None:
    """명확하면 규칙으로 확정, 아니면 None → LLM."""
    conf = body.get("confidence") or "low"
    keys = member_keys(body)
    clusters = body.get("split_clusters") or []
    if conf not in CONF_OK:
        return None
    if len(keys) >= 2:
        use = normalize_clusters(clusters, body.get("members") or [])
        if len(use) < 2:
            use = clusters_from_keys(body)
        if len(use) >= 2:
            return {
                "doc_id": did,
                "confirm_split": True,
                "method": "rule_keys",
                "confidence": conf,
                "reason": body.get("notes") or f"distinct keys: {sorted(keys)}",
                "instrument_keys": sorted(keys),
                "clusters": [
                    {
                        "bucket": f"{did}__{i}",
                        "item_ids": cl,
                        "instrument_key": next(
                            (
                                (m.get("instrument_key") or "")
                                for m in (body.get("members") or [])
                                if m.get("item_id") in cl and m.get("instrument_key")
                            ),
                            "",
                        ),
                    }
                    for i, cl in enumerate(use)
                ],
            }
    # 키가 1개인데 split_clusters가 2개 이상이면 LLM
    return None


def llm_confirm(did: str, body: dict, *, model: str) -> dict:
    mem_lines = []
    for m in (body.get("members") or [])[:40]:
        mem_lines.append(
            f"- id={m.get('item_id')} key={m.get('instrument_key')} "
            f"year={m.get('year')} §={m.get('section')} | {(m.get('title') or '')[:120]}"
        )
    user = f"""1차 분석 notes: {body.get('notes') or ''}
1차 dominant_key: {body.get('dominant_key') or ''}
1차 split_clusters: {body.get('split_clusters') or []}

멤버:
{chr(10).join(mem_lines)}

출력 JSON:
{{
  "confirm_split": true,
  "confidence": "high|medium|low",
  "reason": "한 문장",
  "clusters": [["item_id", ...], ["item_id", ...]]
}}
같은 제도면 confirm_split=false, clusters는 멤버 전부 한 묶음.
"""
    raw = llm_json(
        model,
        [
            {"role": "system", "content": CONFIRM_SYSTEM},
            {"role": "user", "content": user},
        ],
        timeout=90,
    )
    if not isinstance(raw, dict):
        raw = {}
    conf = str(raw.get("confidence") or "low").lower()
    if conf not in ("high", "medium", "low"):
        conf = "low"
    confirm = bool(raw.get("confirm_split"))
    clusters = normalize_clusters(raw.get("clusters"), body.get("members") or [])
    if confirm and len(clusters) < 2:
        confirm = False
    return {
        "doc_id": did,
        "confirm_split": confirm,
        "method": "llm",
        "confidence": conf,
        "reason": str(raw.get("reason") or body.get("notes") or "")[:240],
        "instrument_keys": sorted(member_keys(body)),
        "clusters": [
            {
                "bucket": f"{did}__{i}",
                "item_ids": cl,
                "instrument_key": "",
            }
            for i, cl in enumerate(clusters)
        ]
        if confirm
        else [],
    }


def build_item_map(confirmed: list[dict]) -> dict[str, str]:
    """item_id → split bucket."""
    out: dict[str, str] = {}
    for row in confirmed:
        if not row.get("confirm_split"):
            continue
        if row.get("confidence") not in CONF_OK:
            continue
        for cl in row.get("clusters") or []:
            bucket = cl.get("bucket") or ""
            for mid in cl.get("item_ids") or []:
                if mid and bucket:
                    out[mid] = bucket
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="분할 플래그 검수·확정")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--sleep", type=float, default=0.2)
    ap.add_argument("--limit-llm", type=int, default=40, help="LLM 재확인 최대 건수")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-llm", action="store_true", help="규칙 확정도 LLM 재확인")
    args = ap.parse_args()

    analyze = load_json(ANALYZE_PATH)
    if not analyze:
        raise SystemExit("cache/instrument_analyze.json 없음. 먼저 --analyze 실행.")

    candidates = []
    for did, entry in analyze.items():
        body = entry.get("result") or entry
        if not isinstance(body, dict):
            continue
        if body.get("group_same_instrument") is not False:
            continue
        candidates.append((did, entry, body))

    print(f"split candidates={len(candidates)}", flush=True)
    confirmed: list[dict] = []
    need_llm: list[tuple[str, dict, dict]] = []

    for did, entry, body in candidates:
        if args.force_llm:
            need_llm.append((did, entry, body))
            continue
        row = rule_confirm(did, entry, body)
        if row:
            confirmed.append(row)
        else:
            need_llm.append((did, entry, body))

    print(
        f"rule_confirmed={len(confirmed)} need_llm={len(need_llm)}",
        flush=True,
    )

    if need_llm and not args.dry_run:
        if not ensure_openrouter_key():
            raise SystemExit("OPENROUTER_API_KEY 없음.")
        for i, (did, entry, body) in enumerate(need_llm[: args.limit_llm], 1):
            title = (body.get("notes") or did)[:60]
            print(f"[llm {i}/{min(len(need_llm), args.limit_llm)}] {did} {title}", flush=True)
            try:
                row = llm_confirm(did, body, model=args.model)
                confirmed.append(row)
                print(
                    f"  → split={row.get('confirm_split')} conf={row.get('confidence')} "
                    f"clusters={len(row.get('clusters') or [])}",
                    flush=True,
                )
            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                json.JSONDecodeError,
                ValueError,
                KeyError,
                TypeError,
            ) as e:
                print(f"  FAIL {e}", flush=True)
                confirmed.append(
                    {
                        "doc_id": did,
                        "confirm_split": False,
                        "method": "llm_fail",
                        "confidence": "low",
                        "reason": str(e)[:200],
                        "clusters": [],
                    }
                )
            time.sleep(args.sleep)
        if len(need_llm) > args.limit_llm:
            print(f"skipped_llm={len(need_llm) - args.limit_llm} (raise --limit-llm)")
    elif need_llm and args.dry_run:
        for did, _, body in need_llm:
            confirmed.append(
                {
                    "doc_id": did,
                    "confirm_split": False,
                    "method": "dry_run_pending_llm",
                    "confidence": "low",
                    "reason": body.get("notes") or "",
                    "clusters": [],
                }
            )

    item_map = build_item_map(confirmed)
    split_yes = [r for r in confirmed if r.get("confirm_split") and r.get("confidence") in CONF_OK]
    keep = [r for r in confirmed if not r.get("confirm_split")]
    out = {
        "updated": TODAY,
        "model": args.model,
        "counts": {
            "candidates": len(candidates),
            "confirm_split": len(split_yes),
            "keep_merged": len(keep),
            "items_remapped": len(item_map),
            "by_method": dict(Counter(r.get("method") for r in confirmed)),
        },
        "item_to_bucket": item_map,
        "reviews": confirmed,
    }
    report = {
        "updated": TODAY,
        "counts": out["counts"],
        "split_docs": [
            {
                "doc_id": r["doc_id"],
                "method": r.get("method"),
                "confidence": r.get("confidence"),
                "reason": r.get("reason"),
                "n_clusters": len(r.get("clusters") or []),
                "keys": r.get("instrument_keys") or [],
            }
            for r in split_yes
        ],
        "keep_merged": [
            {"doc_id": r["doc_id"], "method": r.get("method"), "reason": r.get("reason")}
            for r in keep
        ],
    }

    if not args.dry_run:
        save_json(SPLITS_PATH, out)
        save_json(REPORT_PATH, report)
    print(f"counts={out['counts']}")
    print(f"→ {SPLITS_PATH}")
    print(f"→ {REPORT_PATH}")
    print("다음: python3 scripts/build_site.py  (build_documents가 item_to_bucket 반영)")


if __name__ == "__main__":
    main()
