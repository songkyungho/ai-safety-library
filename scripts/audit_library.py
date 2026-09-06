#!/usr/bin/env python3
"""Audit library: missing originals, duplicates, weak rows, dead links.

Optionally removes dead original URLs from collection items.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from library_common import (  # noqa: E402
    COLLECTIONS,
    ROOT,
    as_url_list,
    candidate_originals,
    is_bad_original,
    is_curator_url,
    is_http_url,
    load_collection,
    normalize_url,
    pick_canonical,
    rebuild_collection_stats,
    save_collection,
    write_json,
)

UA = "AI-Safety-Library/0.1 (link-check)"


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def check_url(url: str, timeout: float = 6.0) -> dict:
    result = {"url": url, "ok": False, "status": "", "error": ""}
    if not is_http_url(url):
        result["error"] = "not-http"
        return result
    headers = {
        "User-Agent": UA,
        "Accept": "*/*",
        "Range": "bytes=0-0",
    }
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                code = getattr(r, "status", 200) or 200
                # 206 Partial Content is fine
                result["status"] = str(code)
                result["ok"] = 200 <= int(code) < 400
                if result["ok"]:
                    return result
        except urllib.error.HTTPError as e:
            result["status"] = str(e.code)
            if e.code in (405, 403, 401, 400) and method == "HEAD":
                continue
            if 200 <= e.code < 400:
                result["ok"] = True
                return result
            # Soft-fail common anti-bot blocks as "alive but blocked"
            if e.code in (403, 429) and method == "GET":
                result["ok"] = True
                result["error"] = f"blocked-{e.code}"
                return result
            result["error"] = f"HTTPError {e.code}"
            if method == "HEAD":
                continue
            return result
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {e}"
            if method == "HEAD":
                continue
            return result
    return result


def load_clusters() -> list[dict]:
    path = ROOT / "clusters" / "clusters.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("clusters") or []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-links", action="store_true", help="HTTP-check original (+ optional curator) URLs")
    ap.add_argument("--check-curators", action="store_true", help="also check curator page_url")
    ap.add_argument("--apply-dead", action="store_true", help="strip dead original URLs from items")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--limit-links", type=int, default=0, help="max unique URLs to check (0=all)")
    args = ap.parse_args()

    today = date.today().isoformat()
    out_dir = ROOT / "reports" / f"audit-{today}"
    out_dir.mkdir(parents=True, exist_ok=True)

    items_by_col: dict[str, list[dict]] = {}
    all_items: list[dict] = []
    for key, _name in COLLECTIONS:
        data = load_collection(key)
        items_by_col[key] = data.get("items") or []
        all_items.extend(items_by_col[key])

    missing = []
    weak = []
    canon_map: dict[str, list[dict]] = defaultdict(list)

    for it in all_items:
        cands = candidate_originals(it)
        canon = pick_canonical(it)
        row_base = {
            "id": it.get("id"),
            "collection": it.get("collection"),
            "title": (it.get("title") or "")[:200],
            "date": it.get("date") or "",
            "page_url": it.get("page_url") or "",
            "source_urls": " | ".join(as_url_list(it.get("source_urls"))),
            "canonical_url": canon,
        }
        if not canon:
            missing.append({**row_base, "reason": "no-original-landing"})
        else:
            canon_map[normalize_url(canon)].append(it)

        reasons = []
        body = (it.get("body") or "").strip()
        if not body and it.get("collection") != "iaae-ethics":
            # iaae may still be enriching; still flag empty after enrich
            reasons.append("empty-body")
        if it.get("collection") == "iaae-ethics" and not body:
            reasons.append("empty-body")
        if it.get("collection") == "oecd-navigator":
            year = str(it.get("start_year") or (it.get("date") or "")[:4] or "")
            if year.isdigit() and int(year) < 2015:
                reasons.append("oecd-pre-2015")
        for u in as_url_list(it.get("source_urls")):
            if is_bad_original(u):
                reasons.append("bad-source-host")
                break
        if not cands and it.get("page_url") and is_curator_url(it.get("page_url") or ""):
            reasons.append("curator-only")
        if reasons:
            weak.append({**row_base, "reasons": ";".join(reasons)})

    # duplicates by canonical
    duplicates = []
    for key, group in sorted(canon_map.items(), key=lambda x: -len(x[1])):
        if len(group) < 2:
            continue
        duplicates.append(
            {
                "canonical_url": group[0] and pick_canonical(group[0]),
                "size": len(group),
                "ids": " | ".join(g.get("id") or "" for g in group),
                "collections": " | ".join(sorted({g.get("collection") or "" for g in group})),
                "titles": " || ".join((g.get("title") or "")[:80] for g in group[:6]),
                "kind": "same-canonical",
            }
        )

    for c in load_clusters():
        kind = c.get("kind") or ""
        if kind not in {"duplicate-record", "same-document", "same-act"}:
            continue
        members = c.get("members") or []
        duplicates.append(
            {
                "canonical_url": "",
                "size": c.get("size") or len(members),
                "ids": " | ".join(m.get("id") or "" for m in members),
                "collections": " | ".join(c.get("collections") or []),
                "titles": (c.get("title") or "")[:160],
                "kind": f"cluster:{kind}",
            }
        )

    write_csv(
        out_dir / "missing_original.csv",
        missing,
        ["id", "collection", "title", "date", "page_url", "source_urls", "canonical_url", "reason"],
    )
    write_csv(
        out_dir / "duplicates.csv",
        duplicates,
        ["kind", "size", "canonical_url", "collections", "ids", "titles"],
    )
    write_csv(
        out_dir / "weak.csv",
        weak,
        ["id", "collection", "title", "date", "page_url", "source_urls", "canonical_url", "reasons"],
    )

    dead_rows = []
    url_status: dict[str, dict] = {}

    if args.check_links:
        urls = set()
        for it in all_items:
            for u in candidate_originals(it):
                urls.add(u)
            if args.check_curators and is_http_url(it.get("page_url") or ""):
                urls.add(it["page_url"])
        url_list = sorted(urls)
        if args.limit_links:
            url_list = url_list[: args.limit_links]
        print(f"checking {len(url_list)} URLs with {args.workers} workers…", flush=True)
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(check_url, u): u for u in url_list}
            done = 0
            for fut in as_completed(futs):
                done += 1
                try:
                    res = fut.result(timeout=20)
                except Exception as e:
                    u = futs[fut]
                    res = {"url": u, "ok": False, "status": "", "error": f"future: {e}"}
                url_status[res["url"]] = res
                if not res["ok"]:
                    dead_rows.append(res)
                if done % 50 == 0 or done == len(url_list):
                    print(f"  {done}/{len(url_list)} dead={len(dead_rows)}", flush=True)
        write_csv(
            out_dir / "dead_links.csv",
            [
                {
                    "url": r["url"],
                    "status": r.get("status") or "",
                    "error": r.get("error") or "",
                    "host_kind": "curator" if is_curator_url(r["url"]) else "original",
                }
                for r in dead_rows
            ],
            ["url", "host_kind", "status", "error"],
        )

        if args.apply_dead:
            dead_set = {r["url"] for r in dead_rows if not is_curator_url(r["url"])}
            # also mark by normalized key
            dead_norm = {normalize_url(u) for u in dead_set}
            removed = 0
            for key, items in items_by_col.items():
                for it in items:
                    src = as_url_list(it.get("source_urls"))
                    if not src:
                        continue
                    kept = [
                        u
                        for u in src
                        if u not in dead_set and normalize_url(u) not in dead_norm
                    ]
                    if len(kept) != len(src):
                        removed += len(src) - len(kept)
                        it["source_urls"] = kept
                    # OECD hosted PDFs
                    files = as_url_list(it.get("source_files"))
                    if files:
                        kept_f = [
                            u
                            for u in files
                            if u not in dead_set and normalize_url(u) not in dead_norm
                        ]
                        if len(kept_f) != len(files):
                            removed += len(files) - len(kept_f)
                            it["source_files"] = kept_f
                    # agora page_url may be the original
                    if it.get("collection") == "agora":
                        pu = it.get("page_url") or ""
                        if pu in dead_set or normalize_url(pu) in dead_norm:
                            it["page_url"] = ""
                            it["source_urls"] = [
                                u
                                for u in as_url_list(it.get("source_urls"))
                                if u != pu and normalize_url(u) != normalize_url(pu)
                            ]
                data = load_collection(key)
                data["items"] = items
                rebuild_collection_stats(data)
                save_collection(key, data)
            print(f"removed {removed} dead original URL references")

    summary = {
        "updated": today,
        "items": len(all_items),
        "missing_original": len(missing),
        "weak": len(weak),
        "duplicate_groups": len(duplicates),
        "dead_links": len(dead_rows),
        "links_checked": len(url_status),
        "apply_dead": bool(args.apply_dead),
    }
    write_json(out_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("wrote", out_dir)


if __name__ == "__main__":
    main()
