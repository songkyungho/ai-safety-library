#!/usr/bin/env python3
"""Build canonical document index (original landing URL + publish history)."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_safety import apply_safety_scope  # noqa: E402
from library_common import (  # noqa: E402
    COLLECTIONS,
    ROOT,
    act_base_name,
    act_section_key,
    act_short_name,
    as_url_list,
    candidate_originals,
    country_label_ko,
    choose_group_country,
    flag_emoji,
    format_act_section_labels,
    is_curator_url,
    is_http_url,
    is_parent_act_url,
    is_scrape_chrome,
    known_instrument_group_key,
    korean_title_rank,
    load_collection,
    normalize_url,
    pick_canonical,
    pick_group_canonical,
    item_legislation_family,
    url_owners_should_merge,
    write_json,
)
from parse_meta import extract_meta, lifecycle_label  # noqa: E402
from title_ko import resolve_display_titles  # noqa: E402

COL_LABEL = {k: name for k, name in COLLECTIONS}


def short_name_fallback(title: str) -> str:
    title = (title or "").strip()
    m = re.match(r"^[［\[]([^］\]]+)[］\]]\s*(.+)$", title)
    if m:
        return m.group(2).strip()
    return title


def date_precision(date: str, *, collection: str = "", added_on: str = "") -> int:
    """Higher = more trustworthy calendar date. OECD Added-on is weaker than a peer day."""
    d = (date or "").strip()[:10]
    col = (collection or "").strip()
    added = (added_on or "").strip()[:10]
    if not d:
        return 0
    if col == "oecd-navigator" and added and d == added:
        return 1
    if col == "iaae-ethics" and d in ("2020-08-04", "2020-11-04"):
        return 1
    if col == "oecd-navigator" and re.fullmatch(r"20\d{2}-01-01", d):
        return 1
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", d):
        if d.endswith("-01-01"):
            return 1
        return 3
    if re.fullmatch(r"20\d{2}-\d{2}", d):
        return 2
    if re.fullmatch(r"20\d{2}", d):
        return 1
    return 0


def load_oecd_date_cache() -> dict:
    path = ROOT / "cache" / "oecd_dates.json"
    if not path.exists():
        return {}
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return blob if isinstance(blob, dict) else {}


def member_published_date(item: dict, meta: dict | None = None, *, oecd_cache: dict | None = None) -> str:
    """Card date: OECD uses verified publication, else Added-on."""
    col = item.get("collection") or ""
    if col == "oecd-navigator":
        from resolve_oecd_dates import oecd_card_date

        return oecd_card_date(item, oecd_cache if oecd_cache is not None else {})
    if col == "iaae-ethics":
        from iaae_dates import iaae_card_date

        d = iaae_card_date(item)
        if d.endswith("-01-01"):
            return d[:4]
        return d
    if col.startswith("mofa"):
        from mofa_dates import mofa_card_date

        return mofa_card_date(item)
    d = ((meta or {}).get("published") or item.get("date") or "").strip()
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", d[:10]):
        if d.endswith("-01-01"):
            return d[:4]
        return d[:10]
    if re.fullmatch(r"20\d{2}-\d{2}", d[:7]):
        return d[:7]
    if re.fullmatch(r"20\d{2}", d[:4]) and len(d) <= 7:
        return d[:4]
    return d[:10]


def pick_best_published(
    members: list[dict],
    metas: list[tuple[dict, dict]],
    *,
    oecd_cache: dict | None = None,
) -> str:
    """Prefer a verified peer calendar date over OECD Added-on."""
    scored: list[tuple[int, str]] = []
    for m, meta in metas:
        d = member_published_date(m, meta, oecd_cache=oecd_cache)
        if not d:
            continue
        scored.append(
            (
                date_precision(
                    d,
                    collection=m.get("collection") or "",
                    added_on=m.get("added_on") or "",
                ),
                d,
            )
        )
    for m in members:
        d = member_published_date(m, oecd_cache=oecd_cache)
        if not d:
            continue
        scored.append(
            (
                date_precision(
                    d,
                    collection=m.get("collection") or "",
                    added_on=m.get("added_on") or "",
                ),
                d,
            )
        )
    if not scored:
        return ""
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return scored[0][1]


def load_cluster_membership() -> dict[str, str]:
    """item_id → cluster_id for same-document clusters only."""
    path = ROOT / "clusters" / "clusters.json"
    if not path.exists():
        return {}
    blob = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for c in blob.get("clusters") or []:
        if c.get("kind") != "same-document":
            continue
        for m in c.get("members") or []:
            out[m["id"]] = c["id"]
    return out


def doc_id_for(seed: str) -> str:
    """Stable id from a seed string. Only normalize when seed is a bare URL."""
    seed = (seed or "").strip()
    if seed.startswith(("http://", "https://")):
        seed = normalize_url(seed) or seed
    h = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"doc-{h}"


def history_label(item: dict) -> str:
    col = item.get("collection") or ""
    if col.startswith("mofa"):
        return "외교부 게시"
    if col == "iaae-ethics":
        return "IAAE 게시"
    if col == "agora":
        return "원문 기록"
    if col == "oecd-navigator":
        return "OECD 등록"
    if col == "lab-policies":
        return "개발사 게시"
    if col == "derived-splits":
        return "원문 첨부"
    return COL_LABEL.get(col, col)


def load_split_parents() -> set[str]:
    path = ROOT / "collections" / "derived-splits" / "parents.json"
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")).get("parent_ids") or [])


def load_item_split_buckets() -> dict[str, str]:
    """item_id → split bucket (from review_splits.py)."""
    path = ROOT / "cache" / "instrument_splits.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    m = raw.get("item_to_bucket") or {}
    return {str(k): str(v) for k, v in m.items() if k and v}


def build_documents(*, skip_instrument_merge: bool = False) -> list[dict]:
    membership = load_cluster_membership()
    split_parents = load_split_parents()
    item_buckets = load_item_split_buckets()
    oecd_dates = load_oecd_date_cache()
    # Group key: prefer confirmed instrument split, else same-document cluster, else URL
    groups: dict[str, list[dict]] = defaultdict(list)
    pending: list[dict] = []

    for key, _name in COLLECTIONS:
        path = ROOT / "collections" / key / "items.json"
        if not path.exists():
            continue
        data = load_collection(key)
        for it in data.get("items") or []:
            if it.get("id") in split_parents:
                continue
            pending.append(it)

    url_owners: dict[str, list[dict]] = defaultdict(list)
    for it in pending:
        canon = pick_canonical(it)
        if not canon:
            continue
        url_owners[normalize_url(canon)].append(it)
    contested_urls = {
        nu for nu, its in url_owners.items() if nu and not url_owners_should_merge(its)
    }

    for it in pending:
        item_id = it.get("id") or ""
        fp = known_instrument_group_key(
            it.get("title") or "",
            it.get("document_name") or "",
            it.get("original_name") or "",
        )
        if fp:
            groups[f"instr:{fp}"].append(it)
            continue
        bucket = item_buckets.get(item_id)
        if bucket:
            groups[f"split:{bucket}"].append(it)
            continue
        fam = item_legislation_family(it)
        if fam:
            groups[f"leg:{fam}"].append(it)
            continue
        cluster = membership.get(item_id, "")
        if cluster:
            groups[f"cluster:{cluster}"].append(it)
            continue
        canon = pick_canonical(it, skip_normalized=contested_urls)
        if not canon:
            continue
        nu = normalize_url(canon)
        if nu in contested_urls:
            page = (it.get("page_url") or "").strip()
            if page and is_http_url(page):
                groups[f"url:{normalize_url(page)}"].append(it)
            else:
                groups[f"item:{item_id}"].append(it)
            continue
        groups[f"url:{nu}"].append(it)

    # Attach parent curator records to derived-split groups (history only)
    parent_items: dict[str, dict] = {}
    for key, _name in COLLECTIONS:
        if key == "derived-splits":
            continue
        path = ROOT / "collections" / key / "items.json"
        if not path.exists():
            continue
        for it in load_collection(key).get("items") or []:
            if it.get("id") in split_parents:
                parent_items[it["id"]] = it

    for gkey, members in list(groups.items()):
        if not gkey.startswith("split:"):
            continue
        for m in list(members):
            pid = m.get("parent_id")
            if pid and pid in parent_items:
                parent = parent_items[pid]
                if all(x.get("id") != parent.get("id") for x in members):
                    members.append(parent)

    docs = []
    for gkey, members in groups.items():
        # Resolve canonical: prefer a landing that isn't shared by unrelated items
        skip = None if gkey.startswith(("instr:", "leg:")) else contested_urls
        canon = pick_group_canonical(members, skip_normalized=skip)
        if not canon:
            continue

        # Prefer Korean title
        title_item = max(members, key=korean_title_rank)
        title = title_item.get("title") or ""

        # Structured meta: prefer diplomatically curated MOFA bodies.
        # For AGORA law cards, prefer Enacted over Proposed/Defunct when merging.
        metas = [(m, extract_meta(m)) for m in members]

        def _status_rank(pair: tuple[dict, dict]) -> int:
            st = (pair[1].get("status") or pair[0].get("status") or "").strip().lower()
            if st == "enacted":
                return 0
            if st == "proposed":
                return 1
            if st == "defunct":
                return 2
            return 3

        metas.sort(
            key=lambda pair: (
                0 if (pair[0].get("collection") or "").startswith("mofa") else 1,
                _status_rank(pair),
                0 if pair[1].get("summary") else 1,
                0 if pair[1].get("full_name") else 1,
            )
        )
        meta = metas[0][1] if metas else {}
        # If any member is an enacted statute, keep 법 even when other members are bills.
        member_kinds = {m.get("doc_kind") for _, m in metas if m.get("doc_kind")}
        if "법" in member_kinds and meta.get("doc_kind") == "법안":
            meta = dict(meta)
            meta["doc_kind"] = "법"

        short_name = meta.get("short_name") or short_name_fallback(title)
        short_name = re.sub(r"^[［\[][^］\]]+[］\]]\s*", "", short_name).strip()
        full_name = meta.get("full_name") or ""
        member_titles = [(m.get("title") or "").strip() for m in members if m.get("title")]
        section_titles = [
            t for t in member_titles if act_section_key(t) or act_base_name(t)
        ]
        # Omnibus / parent-act pages: one card per act, not per § / Title.
        merge_as_act = is_parent_act_url(canon) and (
            len(section_titles) >= 2
            or (len(members) >= 2 and any(act_base_name(t) for t in member_titles))
            or bool(act_base_name(title) and act_section_key(title))
        )
        if merge_as_act:
            base = ""
            for t in member_titles:
                base = act_base_name(t) or base
                if base:
                    break
            if base:
                short_name = base
            cleaned = short_name_fallback(title)
            if not full_name and cleaned and cleaned != short_name:
                # Prefer act-level title without trailing section clause
                full_name = act_base_name(cleaned) or re.split(
                    r",\s*(?=Section\b|Sec\.\s*\d|Title\b|Division\b)",
                    cleaned,
                    maxsplit=1,
                    flags=re.I,
                )[0].strip(" ,")
        else:
            act_name = act_short_name(title)
            if act_name:
                cleaned = short_name_fallback(title)
                short_name = act_name
                if not full_name and cleaned and cleaned != act_name:
                    full_name = cleaned

        original_names = []
        for m in members:
            for key in ("original_name", "document_name"):
                val = (m.get(key) or "").strip()
                if val:
                    original_names.append(val)
        short_name, full_name, original_name = resolve_display_titles(
            short_hint=short_name,
            full_hint=full_name,
            member_titles=member_titles if not merge_as_act else [short_name] + member_titles[:1],
            original_names=original_names,
        )
        if merge_as_act:
            # resolve_display_titles may reintroduce a section card title — keep act base.
            for t in member_titles:
                b = act_base_name(t)
                if b:
                    short_name = b
                    break
        country = choose_group_country(
            members,
            extra_text=" ".join(
                [
                    title,
                    short_name,
                    full_name,
                    original_name,
                    meta.get("country_hint") or "",
                ]
            ),
        )
        # OECD template titles omit the country — prefix for disambiguation
        country_ko = country_label_ko(country) if country else ""
        if (
            country_ko
            and country != "International"
            and any((m.get("collection") or "") == "oecd-navigator" for m in members)
            and country_ko not in short_name
            and (country or "").lower() not in (short_name + " " + original_name).lower()
        ):
            short_name = f"{country_ko} · {short_name}"
        summary = meta.get("summary") or ""
        if is_scrape_chrome(summary):
            summary = ""
        # 원문 스크랩을 카드 요약으로 쓰지 않는다. 외교부 ●핵심내용만 허용하고,
        # IAAE 안내문·깨진 HTML은 빈칸. 나머지는 LLM 큐레이션이 채운다.
        if not summary:
            for m in sorted(members, key=korean_title_rank, reverse=True):
                col = m.get("collection") or ""
                if col in ("iaae-ethics", "derived-splits"):
                    continue
                s = extract_meta(m).get("summary") or ""
                if is_scrape_chrome(s):
                    s = ""
                if s:
                    summary = s
                    break
        if merge_as_act and len(section_titles) >= 2:
            sec_list = format_act_section_labels(section_titles)
            if sec_list:
                note = f"이 법·법안에서 AI 관련으로 색인된 조항: {sec_list}."
                if summary and note not in summary:
                    summary = f"{note}\n\n{summary}"
                elif not summary:
                    summary = note

        org = meta.get("org") or ""
        if not org:
            for m in members:
                if m.get("org"):
                    org = m["org"]
                    break

        history = []
        seen_hist = set()
        for m in members:
            if (m.get("collection") or "") == "oecd-navigator":
                d = (m.get("added_on") or m.get("date") or "").strip()
            else:
                d = (m.get("date") or "").strip()
            label = history_label(m)
            url = ""
            page = m.get("page_url") or ""
            if page and is_curator_url(page):
                url = page
            elif page:
                url = page
            else:
                cands = candidate_originals(m)
                url = cands[0] if cands else ""
            hk = (d, label, normalize_url(url) if url else "")
            if hk in seen_hist:
                continue
            seen_hist.add(hk)
            history.append(
                {
                    "date": d,
                    "label": label,
                    "url": url,
                    "title": (m.get("title") or "")[:160],
                    "item_id": m.get("id") or "",
                }
            )
        history.sort(key=lambda h: h["date"] or "", reverse=True)

        published = pick_best_published(members, metas, oecd_cache=oecd_dates)
        if not published:
            dates = [h["date"] for h in history if h.get("date")]
            published = max(dates) if dates else ""

        display_country = country
        cache_urls: list[str] = []
        for m in members:
            cache_urls.extend(candidate_originals(m))
            if m.get("page_url"):
                cache_urls.append(m["page_url"])
        # Stable id: 그룹 키 전체를 해시해 split 버킷이 같은 원문 URL을 써도 겹치지 않게 한다.
        id_seed = gkey

        doc_kind = meta.get("doc_kind") or "기타"
        # Prefer Enacted status when merging; otherwise first member status.
        status = ""
        for _, m in metas:
            st = (m.get("status") or "").strip()
            if st.lower() == "enacted":
                status = st
                break
            if st and not status:
                status = st
        if not status:
            for m in members:
                st = (m.get("status") or "").strip()
                if st:
                    status = st
                    break
        status_ko = ""
        if doc_kind in ("법", "법안"):
            status_ko = lifecycle_label(
                status,
                short_name,
                full_name,
                original_name,
                title,
                *member_titles[:8],
                doc_kind=doc_kind,
            )

        docs.append(
            {
                "id": doc_id_for(id_seed),
                "title": short_name or title,
                "short_name": short_name,
                "full_name": full_name,
                "original_name": original_name,
                "doc_kind": doc_kind,
                "doc_kind_raw": meta.get("doc_kind_raw") or "",
                "status": status,
                "status_ko": status_ko,
                "canonical_url": canon,
                "country": display_country,
                "country_ko": country_label_ko(display_country),
                "flag": flag_emoji(country) if country else "",
                "org": org,
                "published": published,
                "published_raw": meta.get("published_raw") or "",
                "summary": summary,
                "snippet": summary[:500],
                "history": history,
                "member_ids": [m.get("id") for m in members],
                "member_count": len(members),
                "_cache_urls": cache_urls,
            }
        )

    docs.sort(key=lambda d: d.get("published") or "", reverse=True)
    apply_safety_scope(docs)
    try:
        from curate_llm import apply_cache_to_docs as apply_curation

        stats = apply_curation(docs)
        if stats.get("applied"):
            print(f"llm_curate applied: {stats}")
    except Exception as e:
        print("llm_curate skip:", e)
    # 법령 합성은 큐레이션 뒤에 적용해 short_name/summary가 덮이지 않게 한다.
    # analyze/synthesize 시에는 적용을 건너뛰어 members_hash가 합성 결과로 오염되지 않게 한다.
    if not skip_instrument_merge:
        try:
            from merge_instruments import apply_cache_to_docs as apply_instrument_merge

            merge_stats = apply_instrument_merge(docs)
            if merge_stats.get("applied") or merge_stats.get("flagged_split"):
                print(f"instrument_merge applied: {merge_stats}")
        except Exception as e:
            print("instrument_merge skip:", e)
    # 한글 약칭은 큐레이션·합성 뒤에 적용해 한·영 혼용 제목이 다시 덮이지 않게 한다.
    try:
        from enrich_ko import apply_cache_to_docs

        n = apply_cache_to_docs(docs)
        if n:
            print(f"ko_enrich applied to {n} fields/docs")
    except Exception as e:
        print("ko_enrich skip:", e)
    try:
        from library_common import fill_missing_country

        filled = sum(1 for d in docs if fill_missing_country(d))
        if filled:
            print(f"country filled from title/org: {filled}")
    except Exception as e:
        print("country fill skip:", e)
    try:
        from issuer_levels import apply_issuer_taxonomy

        iss = apply_issuer_taxonomy(docs)
        if iss.get("lab_kind_migrated") or iss.get("issuer_set"):
            print(f"issuer_level applied: {iss}")
    except Exception as e:
        print("issuer_level skip:", e)
    try:
        from library_common import (
            apply_revision_labels,
            disambiguate_duplicate_short_names,
            polish_short_names,
        )

        nrev = apply_revision_labels(docs)
        if nrev:
            print(f"revision labels applied: {nrev}")
        npol = polish_short_names(docs)
        if npol:
            print(f"short names polished: {npol}")
        ndup = disambiguate_duplicate_short_names(docs)
        if ndup:
            print(f"duplicate short names labeled: {ndup}")
    except Exception as e:
        print("revision label skip:", e)
    for d in docs:
        d.pop("_cache_urls", None)
    seen_ids: set[str] = set()
    collisions = 0
    for d in docs:
        did = d.get("id") or ""
        if did not in seen_ids:
            seen_ids.add(did)
            continue
        collisions += 1
        extra = "|" + "|".join(str(x) for x in (d.get("member_ids") or []) if x)
        d["id"] = doc_id_for(did + extra)
        seen_ids.add(d["id"])
    if collisions:
        print(f"doc id collisions remapped: {collisions}")
    return docs


def main() -> None:
    import csv
    from datetime import date

    docs = build_documents()
    in_scope = [d for d in docs if d.get("in_scope")]
    out_scope = [d for d in docs if not d.get("in_scope")]
    out = {
        "name": "AI 안전 라이브러리 문서",
        "updated": date.today().isoformat(),
        "count": len(docs),
        "in_scope_count": len(in_scope),
        "out_of_scope_count": len(out_scope),
        "documents": docs,
    }
    write_json(ROOT / "documents.json", out)

    fields = [
        "id",
        "title",
        "country",
        "flag",
        "published",
        "canonical_url",
        "org",
        "member_count",
        "in_scope",
        "safety_score",
    ]
    with (ROOT / "documents.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for d in docs:
            w.writerow(d)

    report_dir = ROOT / "reports" / f"audit-{date.today().isoformat()}"
    report_dir.mkdir(parents=True, exist_ok=True)
    with (report_dir / "out_of_scope.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["id", "title", "safety_score", "published", "canonical_url", "safety_reasons"],
            extrasaction="ignore",
        )
        w.writeheader()
        for d in out_scope:
            row = dict(d)
            row["safety_reasons"] = ";".join(d.get("safety_reasons") or [])
            w.writerow(row)
    with (report_dir / "in_scope.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["id", "title", "safety_score", "published", "canonical_url", "country"],
            extrasaction="ignore",
        )
        w.writeheader()
        for d in in_scope:
            w.writerow(d)

    print(
        f"documents {len(docs)} → in_scope={len(in_scope)} out={len(out_scope)} "
        f"(documents.json)"
    )


if __name__ == "__main__":
    main()
