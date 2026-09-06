#!/usr/bin/env python3
"""Ingest AGORA (Zenodo documents.csv) and OECD.AI Policy Navigator into the library."""
from __future__ import annotations

import csv
import json
import re
import time
import urllib.request
from collections import Counter
from html import unescape
from pathlib import Path

ROOT = Path("/Users/kyunghosong/Library/Mobile Documents/com~apple~CloudDocs/5_Code/AI Safety Library")
AGORA_CSV = Path("/tmp/agora_dl/agora/documents.csv")
UA = "AI-Safety-Library/0.1 (research archive; local snapshot)"


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def strip_html(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</p>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = unescape(s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def md_title(title: str, url: str) -> str:
    safe = (title or "").replace("[", "［").replace("]", "］")
    return f"[{safe}]({url})" if url else safe


CSV_FIELDS = [
    "id",
    "collection",
    "collection_name",
    "date",
    "category",
    "org",
    "title",
    "page_url",
    "source_urls",
    "document_name",
    "body",
]


def fetch_oecd() -> list[dict]:
    items: list[dict] = []
    page = 1
    last = 1
    while page <= last:
        url = f"https://api.oecdai.org/policy-initiatives?page={page}&perPage=100"
        d = get_json(url)
        last = int(d.get("lastPage") or page)
        batch = d.get("data") or []
        items.extend(batch)
        print(f"oecd page {page}/{last} got {len(batch)} total {len(items)}")
        page += 1
        time.sleep(0.12)
    # de-dupe by id
    seen = {}
    for it in items:
        seen[it["id"]] = it
    return list(seen.values())


def oecd_storage_url(path: str) -> str:
    """Build absolute URL for OECD.AI uploaded files."""
    from urllib.parse import quote

    path = (path or "").lstrip("/")
    if not path:
        return ""
    return "https://api.oecdai.org/storage/" + quote(path, safe="/")


def oecd_country(it: dict) -> tuple[str, str]:
    """Return (country_name, iso3_or_empty) from gaiinCountry / org location."""
    gaiin = it.get("gaiinCountry")
    if isinstance(gaiin, dict) and (gaiin.get("name") or gaiin.get("slug")):
        return (gaiin.get("name") or gaiin.get("slug") or "", gaiin.get("code") or "")
    loc = it.get("responsibleOrganisationSILocation") or it.get("responsibleOrganisationSDLocation")
    if isinstance(loc, dict):
        return (loc.get("name") or loc.get("slug") or "", loc.get("code") or "")
    if isinstance(loc, str) and loc.strip():
        return (loc.strip(), "")
    return ("", "")


def oecd_records(raw: list[dict]) -> list[dict]:
    out = []
    for it in raw:
        slug = it.get("slug") or str(it.get("id"))
        page = f"https://oecd.ai/en/dashboards/policy-initiatives/{slug}"
        sources = []
        if it.get("website"):
            sources.append(it["website"])
        for u in it.get("relevantUrls") or []:
            if isinstance(u, str) and u and u not in sources:
                sources.append(u)
            elif isinstance(u, dict):
                href = u.get("url") or u.get("href") or ""
                if href and href not in sources:
                    sources.append(href)
        file_urls = []
        for f in it.get("sourceFiles") or []:
            if not isinstance(f, dict):
                continue
            href = oecd_storage_url(f.get("path") or "")
            if href and href not in file_urls:
                file_urls.append(href)
        # startYear = initiative 개시 연도(연 단위). 사이트 Added on / Updated on =
        # createdAt / updatedAt (일자). 라이브러리 date는 Added on을 우선한다.
        year = it.get("startYear")
        created = (it.get("createdAt") or "")[:10]
        updated = (it.get("updatedAt") or "")[:10]
        date = created or updated or (f"{year}-01-01" if year else "")
        body = strip_html(it.get("description") or "")
        overview = strip_html(it.get("overview") or "")
        if overview and overview not in body:
            body = (body + "\n\n" + overview).strip() if body else overview
        country_name, country_code = oecd_country(it)
        loc = it.get("responsibleOrganisationSILocation") or it.get("responsibleOrganisationSDLocation")
        loc_name = ""
        if isinstance(loc, dict):
            loc_name = loc.get("name") or loc.get("slug") or ""
        elif isinstance(loc, str):
            loc_name = loc
        org = it.get("responsibleOrganisation") or loc_name or country_name or ""
        if isinstance(org, dict):
            org = org.get("name") or org.get("englishName") or ""
        rec = {
            "id": f"oecd-navigator-{it['id']}",
            "collection": "oecd-navigator",
            "collection_name": "OECD.AI Policy Navigator",
            "oecd_id": it["id"],
            "title": it.get("englishName") or it.get("originalName") or slug,
            "original_name": it.get("originalName") or "",
            "org": org or "",
            "category": it.get("category") or "",
            "status": it.get("status") or "",
            "date": date,
            "start_year": year,
            "added_on": created,
            "updated_on": updated,
            "page_url": page,
            "source_urls": sources,
            "source_files": file_urls,
            "country": country_name,
            "country_code": country_code,
            "document_name": it.get("originalName") or "",
            "body": body,
            "extent": it.get("extentBinding") or "",
        }
        out.append(rec)
    out.sort(key=lambda r: (r["date"], r["title"]), reverse=True)
    return out


def agora_records() -> list[dict]:
    with AGORA_CSV.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for row in rows:
        aid = (row.get("AGORA ID") or "").strip()
        title = (row.get("Official name") or row.get("Casual name") or "").strip()
        official = (row.get("Link to document") or "").strip()
        short = (row.get("Short summary") or "").strip()
        long_s = (row.get("Long summary") or "").strip()
        body = short
        if long_s and long_s not in body:
            body = (body + "\n\n" + long_s).strip() if body else long_s
        date = (row.get("Most recent activity date") or row.get("Proposed date") or "")[:10]
        rec = {
            "id": f"agora-{aid}",
            "collection": "agora",
            "collection_name": "ETO AGORA",
            "agora_id": aid,
            "title": title,
            "org": (row.get("Authority") or "").strip(),
            "category": (row.get("Collections") or "").strip(),
            "status": (row.get("Most recent activity") or "").strip(),
            "date": date,
            "page_url": official or "https://agora.eto.tech/",
            "source_urls": [official] if official else [],
            "document_name": (row.get("Casual name") or "").strip(),
            "body": body,
            "tags": (row.get("Tags") or "").strip(),
            "machine_summary": (row.get("Summaries and tags may include unreviewed machine output") or "").strip(),
        }
        out.append(rec)
    out.sort(key=lambda r: (r["date"], r["title"]), reverse=True)
    return out


def pack(collection: str, name: str, source: dict, records: list[dict]) -> dict:
    return {
        "collection": collection,
        "name": name,
        "source": source,
        "count": len(records),
        "categories": dict(Counter((r.get("category") or "기타")[:80] for r in records)),
        "years": dict(Counter((r.get("date") or "")[:4] for r in records if r.get("date"))),
        "items": records,
    }


def catalog_md(title: str, intro: list[str], records: list[dict], cat_key="category") -> str:
    cats = Counter((r.get(cat_key) or "기타") for r in records)
    years = Counter((r.get("date") or "")[:4] for r in records)
    dates = [r["date"] for r in records if r.get("date")]
    lines = [f"# {title}", ""]
    lines.extend(intro)
    lines += ["", f"- 건수: **{len(records)}건**"]
    if dates:
        lines.append(f"- 기간: {min(dates)} ~ {max(dates)}")
    lines += ["", "## 분류", "", "| 분류 | 건수 |", "|---|---:|"]
    for c, n in cats.most_common(30):
        label = c.replace("\n", " ")[:80]
        lines.append(f"| {label} | {n} |")
    lines += ["", "## 연도", "", "| 연도 | 건수 |", "|---|---:|"]
    for y, n in sorted(years.items(), reverse=True):
        if y:
            lines.append(f"| {y} | {n} |")
    lines += ["", "## 목록", "", "| 날짜 | 분류 | 제목 | 원문 |", "|---|---|---|---|"]
    for r in records:
        src = r["source_urls"][0] if r.get("source_urls") else ""
        src_md = f"[원문]({src})" if src else ""
        cat = (r.get("category") or r.get("org") or "").replace("\n", " ")[:40]
        lines.append(f"| {r.get('date') or ''} | {cat} | {md_title(r['title'], r['page_url'])} | {src_md} |")
    return "\n".join(lines) + "\n"


def csv_row(r: dict) -> dict:
    return {
        **r,
        "source_urls": " | ".join(r.get("source_urls") or []),
        "body": (r.get("body") or "")[:8000],
    }


def rebuild_root_catalog() -> None:
    all_rows = []
    collections_meta = {}
    for key, name in [
        ("mofa-governance", "외교부 글로벌 AI거버넌스 논의"),
        ("mofa-country-policy", "외교부 주요국 AI 정책"),
        ("iaae-ethics", "IAAE 연구자료실"),
        ("agora", "ETO AGORA"),
        ("oecd-navigator", "OECD.AI Policy Navigator"),
    ]:
        p = ROOT / "collections" / key / "items.json"
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        collections_meta[key] = {
            "name": data.get("name") or name,
            "count": data.get("count"),
            "years": data.get("years"),
            "categories": {k: v for k, v in list((data.get("categories") or {}).items())[:20]},
        }
        for r in data.get("items") or []:
            all_rows.append(csv_row(r))
    all_rows.sort(key=lambda r: r.get("date") or "", reverse=True)
    write_csv(ROOT / "catalog.csv", all_rows, CSV_FIELDS)
    write_json(
        ROOT / "catalog.json",
        {
            "name": "AI 안전 라이브러리",
            "updated": time.strftime("%Y-%m-%d"),
            "collections": collections_meta,
            "total": sum(v.get("count") or 0 for v in collections_meta.values()),
        },
    )


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--oecd-only", action="store_true")
    ap.add_argument("--agora-only", action="store_true")
    ap.add_argument("--catalog-only", action="store_true")
    args = ap.parse_args()

    if args.catalog_only:
        rebuild_root_catalog()
        cat = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
        print("library total", cat["total"])
        return

    if not args.agora_only:
        print("fetching OECD…")
        oecd_raw = fetch_oecd()
        print("oecd unique", len(oecd_raw))
        oecd_source = {
            "count": len(oecd_raw),
            "board": "Policy Navigator",
            "list_url": "https://oecd.ai/en/dashboards/policy-initiatives",
            "api": "https://api.oecdai.org/policy-initiatives",
            "fetched": time.strftime("%Y-%m-%d"),
            "note": "국가·국제기구 AI 정책 이니셔티브. 인용: OECD.AI (2025), OECD.AI Policy Navigator, https://oecd.ai/dashboards. gaiinCountry·sourceFiles 포함.",
        }
        write_json(ROOT / "collections/oecd-navigator/source.json", oecd_source)
        oecd = oecd_records(oecd_raw)
        oecd_pack = pack(
            "oecd-navigator",
            "OECD.AI Policy Navigator",
            oecd_source,
            oecd,
        )
        write_json(ROOT / "collections/oecd-navigator/items.json", oecd_pack)
        write_csv(ROOT / "collections/oecd-navigator/items.csv", [csv_row(r) for r in oecd], CSV_FIELDS)
        (ROOT / "collections/oecd-navigator/catalog.md").write_text(
            catalog_md(
                "OECD.AI Policy Navigator",
                [
                    "- 큐레이터: OECD.AI / GPAI",
                    "- 출처: [Policy Navigator](https://oecd.ai/en/dashboards/policy-initiatives)",
                    "- API: `https://api.oecdai.org/policy-initiatives`",
                    "- 데이터: `items.json` · `items.csv`",
                ],
                oecd,
            ),
            encoding="utf-8",
        )

    if not args.oecd_only:
        print("parsing AGORA…")
        agora = agora_records()
        print("agora", len(agora))
        agora_source = {
            "count": len(agora),
            "board": "AI GOvernance and Regulatory Archive",
            "list_url": "https://agora.eto.tech/",
            "dataset": "https://doi.org/10.5281/zenodo.20714047",
            "version": "1.30.0 (2026-06-16)",
            "license": "CC BY-NC 4.0",
            "note": "CSET/ETO 문서 아카이브. 전문 파일은 넣지 않고 메타데이터·요약·공식 URL만 보관. 인용: Emerging Technology Observatory AGORA dataset, https://eto.tech/dataset-docs/agora-dataset/",
        }
        write_json(ROOT / "collections/agora/source.json", agora_source)
        agora_pack = pack(
            "agora",
            "ETO AGORA",
            agora_source,
            agora,
        )
        write_json(ROOT / "collections/agora/items.json", agora_pack)
        write_csv(ROOT / "collections/agora/items.csv", [csv_row(r) for r in agora], CSV_FIELDS)
        (ROOT / "collections/agora/catalog.md").write_text(
            catalog_md(
                "ETO AGORA",
                [
                    "- 큐레이터: Georgetown CSET / Emerging Technology Observatory",
                    "- 출처: [AGORA](https://agora.eto.tech/) · 데이터셋 [Zenodo 1.30.0](https://doi.org/10.5281/zenodo.20714047)",
                    "- 라이선스: CC BY-NC 4.0. 요약 일부는 미검수 기계생성일 수 있다.",
                    "- 데이터: `items.json` · `items.csv` (전문 텍스트는 용량 때문에 제외, 공식 URL 사용)",
                ],
                agora,
            ),
            encoding="utf-8",
        )

    rebuild_root_catalog()
    cat = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    print("library total", cat["total"])


if __name__ == "__main__":
    main()
