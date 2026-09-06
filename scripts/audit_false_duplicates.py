#!/usr/bin/env python3
"""Audit clusters for false duplicates (same title, different country/year/URL)."""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from library_common import ROOT, country_from_item  # noqa: E402

COLS = ["agora", "oecd-navigator", "mofa-governance", "mofa-country-policy", "iaae-ethics"]


def initiative_id(url: str) -> str:
    m = re.search(r"policy-initiatives/([^/?#]+)", url or "")
    return m.group(1) if m else ""


def main() -> None:
    cl = json.loads((ROOT / "clusters" / "clusters.json").read_text(encoding="utf-8"))
    items: dict[str, dict] = {}
    for col in COLS:
        path = ROOT / "collections" / col / "items.json"
        if not path.exists():
            continue
        for it in json.loads(path.read_text(encoding="utf-8")).get("items") or []:
            items[it["id"]] = it

    suspects = []
    for c in cl.get("clusters") or []:
        members = []
        for m in c.get("members") or []:
            it = items.get(m["id"], m)
            url = m.get("page_url") or it.get("page_url") or ""
            members.append(
                {
                    "country": country_from_item(it) or "",
                    "year": (m.get("date") or it.get("date") or "")[:4],
                    "init": initiative_id(url),
                    "url": re.sub(r"[?#].*", "", url),
                    "collection": m.get("collection") or it.get("collection"),
                }
            )
        years = {x["year"] for x in members if x["year"]}
        countries = {
            x["country"]
            for x in members
            if x["country"] and x["country"] != "International"
        }
        inits = {x["init"] for x in members if x["init"]}
        urls = {x["url"] for x in members if x["url"]}
        cols = {x["collection"] for x in members}
        reasons = []
        # Shared source URL across countries can be a real multilateral filing
        shared_url = len(urls) == 1 and len(countries) >= 2
        if len(countries) >= 2 and not shared_url:
            reasons.append(f"countries={len(countries)}")
        if len(inits) >= 2:
            reasons.append(f"oecd_inits={len(inits)}")
        if len(cols) == 1 and len(countries) >= 2 and not shared_url:
            reasons.append("same-col-multi-country")
        if (
            len(years) >= 2
            and (max(int(y) for y in years) - min(int(y) for y in years)) >= 1
            and (len(inits) >= 2 or len(urls) >= 2)
        ):
            reasons.append(f"years={'|'.join(sorted(years))}")
        if not reasons:
            continue
        suspects.append(
            {
                "id": c.get("id"),
                "kind": c.get("kind"),
                "size": c.get("size"),
                "title": (c.get("title") or "")[:120],
                "reasons": ";".join(reasons),
                "years": "|".join(sorted(years)),
                "countries": "|".join(sorted(countries)[:12]),
                "n_url": len(urls),
                "n_init": len(inits),
            }
        )

    out_dir = ROOT / "reports" / f"audit-{date.today().isoformat()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "false_duplicate_clusters.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "kind",
                "size",
                "title",
                "reasons",
                "years",
                "countries",
                "n_url",
                "n_init",
            ],
        )
        w.writeheader()
        for row in sorted(suspects, key=lambda r: -int(r["size"] or 0)):
            w.writerow(row)

    tags = Counter()
    for s in suspects:
        for part in s["reasons"].split(";"):
            tags[part.split("=")[0]] += 1
    print(json.dumps({"clusters": len(cl.get("clusters") or []), "suspects": len(suspects), "tags": dict(tags), "report": str(out)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
