#!/usr/bin/env python3
"""동일 법령·정책: 큐레이션 → 분석 → 후보 → 통합 합성.

권장 순서
  1) python3 scripts/curate_llm.py --limit N
  2) python3 scripts/merge_instruments.py --analyze --limit N
  3) python3 scripts/merge_instruments.py --propose
  4) python3 scripts/merge_instruments.py --synthesize --limit N
  5) python3 scripts/build_site.py

규칙(build_documents URL/cluster)은 후보 그룹만 만든다.
합성은 멤버 분석에서 같은 제도로 합의된 경우에만 한다.

캐시
  cache/instrument_analyze.json
  cache/instrument_merge.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
import urllib.error
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_ko import DEFAULT_MODEL, ensure_openrouter_key, llm_json  # noqa: E402
from library_common import write_json  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ANALYZE_PATH = ROOT / "cache" / "instrument_analyze.json"
CACHE_PATH = ROOT / "cache" / "instrument_merge.json"
REPORT_PATH = ROOT / "reports" / "merge_candidates.json"
TODAY = date.today().isoformat()
CONF_OK = {"high", "medium"}

ANALYZE_SYSTEM = """당신은 AI 안전·거버넌스 라이브러리의 수석 분석가입니다.
한 규칙 그룹에 묶인 여러 게시물·조항을 개별 분석한 뒤, 같은 법령·정책인지 판정합니다.
지금은 통합 요약문을 쓰지 마세요. 식별·판정만 합니다.

절대 규칙
1) 원문 메타에 없는 사실·날짜·조항을 만들지 마세요.
2) 서로 다른 법령·연도·관할이면 group_same_instrument=false.
3) 같은 법의 조항·번역·미러·중복 카드면 group_same_instrument=true.
4) JSON만 출력하세요.

instrument_key 권장: "{관할}:{법약칭}:{연도}" (소문자, 공백은 -)
예: us:ndaa:2026 , eu:ai-act:2024
조항만 다르면 같은 key. 연도·법이 다르면 다른 key.
"""

SYNTH_SYSTEM = """당신은 AI 안전·거버넌스 라이브러리의 수석 편집터입니다.
멤버 분석에서 같은 제도로 합의된 그룹입니다. UI용 통합 한국어 약칭·핵심내용을 작성합니다.

절대 규칙
1) 원문 메타에 없는 사실·날짜·조항·기관을 만들지 마세요.
2) 조항 번호는 short_name에 넣지 말고 section_labels에 모으세요.
3) JSON만 출력하세요.
"""


def load_json(path: Path) -> dict:
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    return {}


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, data)


def load_cache() -> dict:
    return load_json(CACHE_PATH)


def save_cache(cache: dict) -> None:
    save_json(CACHE_PATH, cache)


def members_hash(doc: dict) -> str:
    """멤버 구성 지문. short_name/summary는 합성·큐레이션이 바꿔 자가무효화가 되므로 제외."""
    ids = sorted(str(x) for x in (doc.get("member_ids") or []) if x)
    titles = sorted(
        (h.get("title") or "")[:80]
        for h in (doc.get("history") or [])
        if h.get("title")
    )
    blob = "\n".join(
        [
            doc.get("id") or "",
            "|".join(ids),
            "|".join(titles[:20]),
            "1" if doc.get("llm_curated") else "0",
        ]
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def candidate_docs(docs: list[dict], *, min_members: int) -> list[dict]:
    out = [
        d
        for d in docs
        if int(d.get("member_count") or 1) >= min_members
        and (d.get("member_ids") or d.get("history"))
    ]
    out.sort(
        key=lambda d: (
            0 if d.get("llm_curated") else 1,
            -int(d.get("member_count") or 0),
            d.get("published") or "",
        )
    )
    return out


def curation_gate(doc: dict, *, require: bool) -> bool:
    return True if not require else bool(doc.get("llm_curated"))


def normalize_analyze(raw: dict, doc: dict) -> dict:
    conf = str(raw.get("confidence") or "low").lower()
    if conf not in ("high", "medium", "low"):
        conf = "low"
    members_out = []
    for m in raw.get("members") or []:
        if not isinstance(m, dict):
            continue
        members_out.append(
            {
                "item_id": str(m.get("item_id") or "")[:80],
                "title": str(m.get("title") or "")[:160],
                "instrument_key": str(m.get("instrument_key") or "").strip().lower()[:120],
                "act_name": str(m.get("act_name") or "").strip()[:200],
                "year": str(m.get("year") or "").strip()[:12],
                "section": str(m.get("section") or "").strip()[:80],
                "same_as_group": bool(m.get("same_as_group", True)),
            }
        )
    if not members_out:
        for h in (doc.get("history") or [])[:40]:
            members_out.append(
                {
                    "item_id": str(h.get("item_id") or "")[:80],
                    "title": str(h.get("title") or "")[:160],
                    "instrument_key": "",
                    "act_name": "",
                    "year": "",
                    "section": "",
                    "same_as_group": False,
                }
            )
    same = bool(raw.get("group_same_instrument"))
    keys = [m["instrument_key"] for m in members_out if m.get("instrument_key")]
    key_counts = Counter(keys)
    dominant = key_counts.most_common(1)[0][0] if key_counts else ""
    if same and dominant and any(k != dominant for k in keys):
        same = False
        if conf == "high":
            conf = "medium"
    split = []
    for cluster in raw.get("split_clusters") or []:
        if isinstance(cluster, list) and cluster:
            split.append([str(x)[:80] for x in cluster[:40]])
    return {
        "group_same_instrument": same,
        "confidence": conf,
        "dominant_key": dominant,
        "members": members_out,
        "split_clusters": split[:12],
        "notes": str(raw.get("notes") or "")[:240],
    }


def validate_analyze(entry: dict) -> list[str]:
    errs = []
    if entry.get("confidence") not in ("high", "medium", "low"):
        errs.append("bad confidence")
    if not entry.get("members"):
        errs.append("no members")
    return errs


def analyze_one(doc: dict, *, model: str) -> dict:
    history = doc.get("history") or []
    lines = []
    for i, h in enumerate(history[:40], 1):
        lines.append(
            f"{i}. item_id={h.get('item_id') or ''}\n"
            f"   date={h.get('date') or ''} label={h.get('label') or ''}\n"
            f"   title={(h.get('title') or '')[:180]}\n"
            f"   url={h.get('url') or ''}"
        )
    user = f"""멤버를 개별 분석한 뒤 그룹 판정만 하세요. 통합 요약은 쓰지 마세요.

[큐레이션된 카드 — 참고]
doc_id: {doc.get("id")}
llm_curated: {bool(doc.get("llm_curated"))}
short_name: {doc.get("short_name") or doc.get("title") or ""}
full_name: {doc.get("full_name") or ""}
doc_kind: {doc.get("doc_kind") or ""}
country/org: {doc.get("country_ko") or doc.get("country") or ""} / {doc.get("org") or ""}
published: {doc.get("published") or ""}
member_count: {doc.get("member_count")}
summary:
{(doc.get("summary") or "")[:1800]}

[멤버 목록]
{chr(10).join(lines) or "(history 없음)"}

출력 JSON:
{{
  "group_same_instrument": true,
  "confidence": "high|medium|low",
  "members": [
    {{
      "item_id": "",
      "title": "",
      "instrument_key": "us:example:2024",
      "act_name": "짧은 법명",
      "year": "2024",
      "section": "§12 또는 빈칸",
      "same_as_group": true
    }}
  ],
  "split_clusters": [],
  "notes": ""
}}
다른 법이 섞였으면 group_same_instrument=false 이고,
split_clusters에 item_id 묶음을 나누어 넣으세요.
"""
    raw = llm_json(
        model,
        [
            {"role": "system", "content": ANALYZE_SYSTEM},
            {"role": "user", "content": user},
        ],
        timeout=120,
    )
    return normalize_analyze(raw if isinstance(raw, dict) else {}, doc)


def normalize_synth(raw: dict) -> dict:
    conf = str(raw.get("confidence") or "low").lower()
    if conf not in ("high", "medium", "low"):
        conf = "low"
    labels = []
    for x in raw.get("section_labels") or []:
        s = str(x).strip()
        if s and s not in labels:
            labels.append(s[:120])
    return {
        "same_instrument": True,
        "confidence": conf,
        "short_name": str(raw.get("short_name") or "").strip()[:200],
        "summary": str(raw.get("summary") or "").strip()[:5000],
        "section_labels": labels[:40],
        "split_reason": "",
        "notes": str(raw.get("notes") or "")[:240],
        "keep_members": True,
        "from_analyze": True,
    }


def validate_synth(entry: dict) -> list[str]:
    errs = []
    if entry.get("confidence") not in ("high", "medium", "low"):
        errs.append("bad confidence")
    if entry.get("confidence") in CONF_OK:
        if not entry.get("short_name"):
            errs.append("missing short_name")
        if not entry.get("summary"):
            errs.append("missing summary")
    return errs


def synthesize_one(doc: dict, analysis: dict, *, model: str) -> dict:
    mem_lines = []
    for m in (analysis.get("members") or [])[:40]:
        mem_lines.append(
            f"- [{m.get('instrument_key')}] {m.get('act_name') or ''} "
            f"{m.get('section') or ''} | {(m.get('title') or '')[:100]}"
        )
    user = f"""분석에서 같은 제도로 합의된 그룹입니다. 통합 표기만 작성하세요.

[분석]
dominant_key: {analysis.get("dominant_key")}
confidence: {analysis.get("confidence")}
notes: {analysis.get("notes") or ""}

[카드]
doc_id: {doc.get("id")}
curated_short_name: {doc.get("short_name") or ""}
doc_kind: {doc.get("doc_kind") or ""}
country/org: {doc.get("country_ko") or doc.get("country") or ""} / {doc.get("org") or ""}
current_summary:
{(doc.get("summary") or "")[:2000]}

[멤버 분석]
{chr(10).join(mem_lines)}

출력 JSON:
{{
  "short_name": "한국어 통합 약칭",
  "summary": "한국어 통합 핵심내용",
  "section_labels": ["조항…"],
  "confidence": "high|medium|low",
  "notes": ""
}}
"""
    raw = llm_json(
        model,
        [
            {"role": "system", "content": SYNTH_SYSTEM},
            {"role": "user", "content": user},
        ],
        timeout=120,
    )
    return normalize_synth(raw if isinstance(raw, dict) else {})


def apply_cache_to_docs(docs: list[dict], cache: dict | None = None) -> dict:
    """고·중신뢰 합성 반영 + 분석 분할 플래그. build_documents에서 호출."""
    cache = cache if cache is not None else load_cache()
    analyze = load_json(ANALYZE_PATH)
    stats: Counter = Counter()
    for d in docs:
        did = d.get("id") or ""
        a = analyze.get(did) or {}
        a_body = a.get("result") or a
        if (
            isinstance(a_body, dict)
            and a_body.get("confidence") in CONF_OK
            and a_body.get("group_same_instrument") is False
        ):
            d["merge_flag"] = "possible_false_merge"
            d["merge_split_reason"] = a_body.get("notes") or "analyze: different instruments"
            stats["flagged_split"] += 1

        entry = cache.get(did)
        if not entry:
            continue
        body = entry.get("result") or entry
        if not isinstance(body, dict):
            continue
        if body.get("confidence") not in CONF_OK:
            stats["skip_low_conf"] += 1
            continue
        # 분석 없이 돌린 구버전 합성은 반영하지 않음
        if not (body.get("from_analyze") or entry.get("analyze_hash")):
            stats["skip_pre_analyze"] += 1
            continue
        if body.get("same_instrument") is False:
            stats["flagged_split"] += 1
            d["merge_flag"] = "possible_false_merge"
            d["merge_split_reason"] = body.get("split_reason") or ""
            continue
        if entry.get("members_hash") and entry["members_hash"] != members_hash(d):
            stats["stale_hash"] += 1
            continue

        stats["applied"] += 1
        d["instrument_merged"] = True
        if body.get("short_name"):
            if not (d.get("original_name") or "").strip():
                prev = d.get("short_name") or d.get("title") or ""
                if prev and prev != body["short_name"]:
                    d["original_name"] = prev
            d["short_name"] = body["short_name"]
            d["title"] = body["short_name"]
            stats["short_name"] += 1
        if body.get("summary"):
            summary = body["summary"]
            labels = body.get("section_labels") or []
            if labels and "관련 조항" not in summary and "색인된 조항" not in summary:
                summary = summary.rstrip() + "\n\n관련 조항: " + "; ".join(labels[:30])
            d["summary"] = summary
            d["snippet"] = summary[:500]
            stats["summary"] += 1
        if body.get("section_labels"):
            d["section_labels"] = list(body["section_labels"])
        if isinstance(a_body, dict) and a_body.get("dominant_key"):
            d["instrument_key"] = a_body["dominant_key"]
    return dict(stats)


def build_propose_report(docs: list[dict], analyze: dict) -> dict:
    by_key: dict[str, list[str]] = defaultdict(list)
    rows = []
    for d in docs:
        did = d.get("id") or ""
        if int(d.get("member_count") or 1) < 2 and did not in analyze:
            continue
        entry = analyze.get(did) or {}
        body = entry.get("result") or entry
        if not isinstance(body, dict) or not body:
            rows.append(
                {
                    "doc_id": did,
                    "status": "needs_analyze",
                    "members": d.get("member_count"),
                    "curated": bool(d.get("llm_curated")),
                    "title": (d.get("short_name") or "")[:80],
                }
            )
            continue
        same = body.get("group_same_instrument")
        conf = body.get("confidence")
        key = body.get("dominant_key") or ""
        if key:
            by_key[key].append(did)
        if same and conf in CONF_OK:
            status = "merge_ok"
        elif same is False:
            status = "split"
        else:
            status = "uncertain"
        rows.append(
            {
                "doc_id": did,
                "status": status,
                "confidence": conf,
                "dominant_key": key,
                "members": d.get("member_count"),
                "curated": bool(d.get("llm_curated")),
                "title": (d.get("short_name") or "")[:80],
                "split_clusters": body.get("split_clusters") or [],
            }
        )
    cross = {k: ids for k, ids in by_key.items() if len(set(ids)) >= 2}
    return {
        "updated": TODAY,
        "counts": dict(Counter(r["status"] for r in rows)),
        "cross_doc_same_key": cross,
        "rows": rows,
    }


def run_validate_analyze(analyze: dict) -> int:
    bad = 0
    for did, entry in analyze.items():
        body = entry.get("result") or entry
        errs = validate_analyze(body or {})
        if errs:
            bad += 1
            print(f"INVALID analyze {did}: {', '.join(errs)}")
    print(f"validate analyze={len(analyze)} invalid={bad}")
    return bad


def run_validate_synth(cache: dict) -> int:
    bad = 0
    for did, entry in cache.items():
        body = entry.get("result") or entry
        errs = validate_synth(body or {})
        if errs:
            bad += 1
            print(f"INVALID synth {did}: {', '.join(errs)}")
    print(f"validate synth={len(cache)} invalid={bad}")
    return bad


def main() -> None:
    ap = argparse.ArgumentParser(description="분석→후보→동일 법령 합성")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--min-members", type=int, default=2)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--sleep", type=float, default=0.05, help="워커당 제출 간격(초)")
    ap.add_argument(
        "--workers",
        type=int,
        default=8,
        help="병렬 워커 수 (4~12 권장)",
    )
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--validate-only", action="store_true")
    ap.add_argument(
        "--require-curation",
        action="store_true",
        help="llm_curated 문서만 처리 (전체 큐레이션 후 권장)",
    )
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--analyze", action="store_true", help="멤버 식별·그룹 합의")
    g.add_argument("--propose", action="store_true", help="후보 리포트 (LLM 없음)")
    g.add_argument("--synthesize", action="store_true", help="합의 그룹만 통합 합성")
    args = ap.parse_args()
    workers = max(1, int(args.workers))

    analyze = load_json(ANALYZE_PATH)
    cache = load_cache()

    if args.validate_only:
        raise SystemExit(run_validate_analyze(analyze) + run_validate_synth(cache))

    from build_documents import build_documents

    print("building documents…")
    docs = build_documents(skip_instrument_merge=True)
    cands = candidate_docs(docs, min_members=args.min_members)
    curated_n = sum(1 for d in cands if d.get("llm_curated"))
    print(
        f"multi≈{len(cands)} curated_among_multi={curated_n} "
        f"analyze_cache={len(analyze)} synth_cache={len(cache)}",
        flush=True,
    )

    if args.propose or (not args.analyze and not args.synthesize):
        report = build_propose_report(docs, analyze)
        save_json(REPORT_PATH, report)
        print(
            f"propose → {REPORT_PATH} counts={report['counts']} "
            f"cross_keys={len(report['cross_doc_same_key'])}"
        )
        if curated_n < max(1, len(cands) // 2):
            print(
                "안내: 멀티멤버 큐레이션이 적습니다. "
                "먼저 `python3 scripts/curate_llm.py` 전체 실행을 권장합니다."
            )
        if not args.propose:
            print(
                "단계: --analyze | --propose | --synthesize\n"
                "권장: 큐레이션 → --analyze → --propose → --synthesize → build_site"
            )
        return

    if not args.dry_run and not ensure_openrouter_key():
        raise SystemExit("OPENROUTER_API_KEY 없음.")

    if args.analyze:
        todo = []
        for d in cands:
            if not curation_gate(d, require=args.require_curation):
                continue
            did = d["id"]
            h = members_hash(d)
            prev = analyze.get(did) or {}
            body = prev.get("result") or prev
            if (
                not args.force
                and prev.get("members_hash") == h
                and body.get("confidence") in CONF_OK
            ):
                continue
            todo.append(d)
            if len(todo) >= args.limit:
                break
        print(
            f"ANALYZE queue={len(todo)} workers={workers} model={args.model}",
            flush=True,
        )
        if args.dry_run:
            for i, d in enumerate(todo, 1):
                title = (d.get("short_name") or d.get("title") or "")[:56]
                print(f"[{i}/{len(todo)}] {d['id']} m={d.get('member_count')} {title}")
            return

        lock = threading.Lock()
        ok = fail = 0
        done = 0
        total = len(todo)
        t0 = time.time()

        def _work(doc: dict):
            if args.sleep > 0:
                time.sleep(args.sleep)
            result = analyze_one(doc, model=args.model)
            errs = validate_analyze(result)
            if errs:
                raise ValueError("; ".join(errs))
            return doc, result

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_work, d) for d in todo]
            for fut in as_completed(futs):
                done += 1
                try:
                    d, result = fut.result()
                    with lock:
                        analyze[d["id"]] = {
                            "members_hash": members_hash(d),
                            "model": args.model,
                            "updated": TODAY,
                            "member_count": d.get("member_count"),
                            "curated": bool(d.get("llm_curated")),
                            "result": result,
                        }
                        ok += 1
                        if ok % 10 == 0:
                            save_json(ANALYZE_PATH, analyze)
                    elapsed = time.time() - t0
                    rate = done / elapsed if elapsed else 0
                    eta = (total - done) / rate / 60 if rate else 0
                    print(
                        f"[{done}/{total}] {d['id']} same={result.get('group_same_instrument')} "
                        f"conf={result.get('confidence')} key={result.get('dominant_key')} "
                        f"| {rate:.2f}/s ETA {eta:.0f}m",
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
                    fail += 1
                    print(f"[{done}/{total}] FAIL {e}", flush=True)

        save_json(ANALYZE_PATH, analyze)
        print(f"analyze done ok={ok} fail={fail} → {ANALYZE_PATH}")
        run_validate_analyze(analyze)
        return

    # --synthesize
    todo = []
    for d in cands:
        if not curation_gate(d, require=args.require_curation):
            continue
        did = d["id"]
        a = analyze.get(did) or {}
        a_body = a.get("result") or a
        if not isinstance(a_body, dict) or not a_body:
            continue
        if a_body.get("confidence") not in CONF_OK:
            continue
        if not a_body.get("group_same_instrument"):
            continue
        h = members_hash(d)
        prev = cache.get(did) or {}
        body = prev.get("result") or prev
        if (
            not args.force
            and prev.get("members_hash") == h
            and prev.get("analyze_hash") == a.get("members_hash")
            and body.get("confidence") in CONF_OK
        ):
            continue
        todo.append((d, a_body, a.get("members_hash") or ""))
        if len(todo) >= args.limit:
            break

    print(
        f"SYNTHESIZE queue={len(todo)} workers={workers} model={args.model}",
        flush=True,
    )
    if not todo and not analyze:
        print("분석 캐시가 비어 있습니다. 먼저 --analyze 를 실행하세요.")
        return
    if args.dry_run:
        for i, (d, a_body, _) in enumerate(todo, 1):
            title = (d.get("short_name") or d.get("title") or "")[:56]
            print(f"[{i}/{len(todo)}] {d['id']} key={a_body.get('dominant_key')} {title}")
        return

    lock = threading.Lock()
    ok = fail = 0
    done = 0
    total = len(todo)
    t0 = time.time()

    def _synth(item):
        d, a_body, a_hash = item
        if args.sleep > 0:
            time.sleep(args.sleep)
        result = synthesize_one(d, a_body, model=args.model)
        errs = validate_synth(result)
        if errs:
            raise ValueError("; ".join(errs))
        return d, a_hash, result

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_synth, item) for item in todo]
        for fut in as_completed(futs):
            done += 1
            try:
                d, a_hash, result = fut.result()
                with lock:
                    cache[d["id"]] = {
                        "members_hash": members_hash(d),
                        "analyze_hash": a_hash,
                        "model": args.model,
                        "updated": TODAY,
                        "member_count": d.get("member_count"),
                        "result": result,
                    }
                    ok += 1
                    if ok % 10 == 0:
                        save_cache(cache)
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed else 0
                eta = (total - done) / rate / 60 if rate else 0
                print(
                    f"[{done}/{total}] {d['id']} conf={result.get('confidence')} "
                    f"{(result.get('short_name') or '')[:50]} | {rate:.2f}/s ETA {eta:.0f}m",
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
                fail += 1
                print(f"[{done}/{total}] FAIL {e}", flush=True)

    save_cache(cache)
    print(f"synthesize done ok={ok} fail={fail} → {CACHE_PATH}")
    run_validate_synth(cache)
    print("다음: python3 scripts/build_site.py")


if __name__ == "__main__":
    main()
