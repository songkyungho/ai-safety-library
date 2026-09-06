#!/usr/bin/env python3
"""Group the same policy/legal document across library collections.

Deterministic pass (URL, slug, title, identifiers) always runs.
Optional --llm pass matches leftover Korean items (MOFA, IAAE) to English
records via OpenRouter. Loads ~/.ai_safety_daily_env if OPENROUTER_API_KEY
is not already set.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/Users/kyunghosong/Library/Mobile Documents/com~apple~CloudDocs/5_Code/AI Safety Library")
OUT = ROOT / "clusters"
COLLECTIONS = [
    "mofa-governance",
    "mofa-country-policy",
    "iaae-ethics",
    "agora",
    "oecd-navigator",
    "lab-policies",
]
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_LLM_MODEL = os.environ.get("CLUSTER_LLM_MODEL", "google/gemini-2.5-flash")

TRACKING_QS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
    "fbclid",
    "gclid",
    "ln",
    "v",
}
GENERIC_SLUGS = {
    "index",
    "index_en",
    "index.html",
    "home",
    "about",
    "en",
    "fr",
    "ko",
    "zh",
    "news",
    "documents",
    "document",
    "publications",
    "publication",
    "policies",
    "policy",
    "press-releases",
    "statements-releases",
    "bilateral-documents",
    "text",
    "pdf",
    "html",
    "default",
    "main",
}
CURATOR_HOSTS = {"agora.eto.tech", "iaae.ai"}
STOP = {
    "ai",
    "the",
    "and",
    "of",
    "for",
    "in",
    "on",
    "a",
    "an",
    "to",
    "with",
    "by",
    "or",
    "at",
    "from",
    "into",
    "over",
    "under",
    "via",
}


class UnionFind:
    def __init__(self, ids: list[str]) -> None:
        self.p = {i: i for i in ids}
        self.rank = {i: 0 for i in ids}

    def find(self, x: str) -> str:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            self.p[ra] = rb
        elif self.rank[ra] > self.rank[rb]:
            self.p[rb] = ra
        else:
            self.p[rb] = ra
            self.rank[ra] += 1


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = val


def ensure_openrouter_key() -> str:
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if key:
        return key
    for p in (
        Path.home() / ".ai_safety_daily_env",
        Path.home() / "ai_safety_daily_env",
        ROOT.parent / "AI Safety" / "ai_safety_daily_env",
        ROOT.parent / "AI Safety" / ".env.local",
    ):
        load_env_file(p)
        key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
        if key:
            return key
    return ""


def load_items() -> list[dict]:
    items = []
    for key in COLLECTIONS:
        data = json.loads((ROOT / "collections" / key / "items.json").read_text(encoding="utf-8"))
        for it in data.get("items") or []:
            items.append(it)
    return items


def norm_url(u: str) -> str:
    if not u:
        return ""
    u = u.strip()
    try:
        p = urllib.parse.urlparse(u)
    except Exception:
        return u.lower().rstrip("/")
    scheme = (p.scheme or "https").lower()
    if scheme == "http":
        scheme = "https"
    netloc = urllib.parse.unquote((p.netloc or "").lower())
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = urllib.parse.unquote(p.path or "")
    path = re.sub(r"/+", "/", path)
    path = path.rstrip("/")
    for suf in ("/text", "/pdf", "/html", "/index.html", "/index_en"):
        if path.endswith(suf):
            path = path[: -len(suf)]
    if path.endswith(".html") and "/publications/" in path:
        path = re.sub(r"_[a-f0-9]{6,}-en$", "", path[: -len(".html")]) + ".html"
    q = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
        if k.lower() not in TRACKING_QS
    ]
    q.sort()
    query = urllib.parse.urlencode(q)
    return urllib.parse.urlunparse((scheme, netloc, path, "", query, ""))


def path_parts(u: str) -> list[str]:
    return [x for x in urllib.parse.urlparse(u).path.split("/") if x]


def slug_of(u: str) -> str:
    parts = path_parts(u)
    if not parts:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
        for key in ("bill_id", "Hsid", "docid"):
            if q.get(key):
                return q[key][0].lower()
        return ""
    slug = parts[-1].lower()
    slug = re.sub(r"\.(pdf|docx?|html?|aspx?|xhtml)$", "", slug)
    slug = urllib.parse.unquote(slug)
    return slug


def url_spec(u: str) -> int:
    """0 = homepage, 1 = shallow, 2 = document-like, 3 = explicit document."""
    p = urllib.parse.urlparse(u)
    host = p.netloc
    parts = path_parts(u)
    slug = slug_of(u)
    q = p.query.lower()
    path = p.path.lower()
    if host in CURATOR_HOSTS:
        return 0
    if "mofa.go.kr" in host:
        return 0
    if "oecd.ai" in host and "policy-initiatives" in path:
        return 0
    if not parts:
        return 0
    if (
        path.endswith(".pdf")
        or "bill_id=" in q
        or "/bill/" in path
        or "congress.gov" in host
        or "federalregister.gov" in host
        or "presidential-actions" in path
        or "eur-lex.europa.eu" in host
        or "unesdoc.unesco.org" in host
        or "digitallibrary.un.org" in host
        or "/publications/" in path
        or host.endswith("legislature.ca.gov")
        or "whitehouse.gov" in host
        and ("presidential-actions" in path or "briefing-room" in path)
    ):
        return 3
    if slug and slug not in GENERIC_SLUGS and len(slug) >= 24 and len(parts) >= 2:
        return 2
    if len(parts) >= 3 and slug not in GENERIC_SLUGS and len(slug) >= 12:
        return 2
    if slug in GENERIC_SLUGS:
        return 0
    return 1


def item_urls(it: dict, *, identity: bool = True) -> list[str]:
    """URLs used to identify *this* document.

    OECD relevantUrls are related pages, not identity — use website only.
    MOFA page_url is the curator card — use source_urls.
    """
    col = it.get("collection") or ""
    raw: list = []
    if identity and col == "oecd-navigator":
        src = it.get("source_urls") or []
        if src:
            raw.append(src[0])
    elif identity and col.startswith("mofa"):
        raw.extend(it.get("source_urls") or [])
    else:
        raw.append(it.get("page_url"))
        raw.extend(it.get("source_urls") or [])
    out = []
    seen = set()
    for u in raw:
        if not isinstance(u, str) or not u.startswith("http"):
            continue
        n = norm_url(u)
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


PREFIX_RE = re.compile(r"^(\[[^\]]+\]\s*)+")


def norm_title(t: str) -> str:
    t = PREFIX_RE.sub("", t or "")
    t = unicodedata.normalize("NFKC", t).lower()
    t = t.replace("artificial intelligence", "ai")
    t = t.replace("artificial-intelligence", "ai")
    t = re.sub(r"[^a-z0-9가-힣]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def tokens(s: str) -> set[str]:
    return {w for w in norm_title(s).split() if len(w) >= 3 and w not in STOP}


def latin_tokens(s: str) -> set[str]:
    return {w for w in tokens(s) if re.fullmatch(r"[a-z0-9]+", w)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / len(a | b)


def slug_tokens(u: str) -> set[str]:
    slug = slug_of(u)
    slug = re.sub(r"_[a-f0-9]{6,}.*$", "", slug)
    slug = slug.replace("-", " ").replace("_", " ")
    return latin_tokens(slug)


ALIAS_RULES = [
    (
        "eu-ai-act",
        [
            r"\bregulation \(eu\) 2024/1689\b",
            r"artificial intelligence act \(ai act\)",
            r"\[유럽연합\].*ai act",
            r"ai에 관한 조화된 규칙",
            r"ai 기본법",
        ],
        ("검토", "개정안", "implementation of regulation", "code of practice", "실천규범", "가이드라인", "guideline", "의무 범위"),
    ),
    (
        "oecd-ai-principles",
        [r"oecd (ai )?principles", r"recommendation of the council on (artificial intelligence|ai)\b", r"oecd 인공지능 원칙"],
        (),
    ),
    (
        "unesco-ai-ethics",
        [r"unesco.*recommendation.*ethics", r"인공지능 윤리에 관한 권고", r"recommendation on the ethics of artificial intelligence"],
        (),
    ),
    (
        "nist-ai-rmf",
        [r"nist.*ai.*risk management framework", r"\bai rmf\b", r"artificial intelligence risk management framework"],
        (),
    ),
]


def alias_keys(it: dict) -> set[str]:
    blob = f"{it.get('title') or ''} {it.get('document_name') or ''}".lower()
    out = set()
    for key, pats, exclude in ALIAS_RULES:
        if any(x in blob for x in exclude):
            continue
        if any(re.search(p, blob, re.I) for p in pats):
            out.add(key)
    return out


EO_RE = re.compile(r"\b(?:eo|executive order)\s*[:#]?\s*(\d{4,5})\b", re.I)
EO_KO_RE = re.compile(r"행정명령\s*(?:제\s*)?(\d{4,5})\s*호")
EU_REG_RE = re.compile(r"\b(?:regulation\s*\(eu\)|eu)\s*(\d{4}/\d{3,5})\b", re.I)
AI_ACT_RE = re.compile(r"\b(?:eu\s+)?ai act\b|인공지능법|ai 법", re.I)


def identifiers(it: dict) -> set[str]:
    blob = " ".join(
        [
            it.get("title") or "",
            it.get("document_name") or "",
            " ".join(it.get("source_urls") or []),
            it.get("page_url") or "",
        ]
    )
    out = set()
    for m in EO_RE.finditer(blob):
        out.add(f"eo:{m.group(1)}")
    for m in EO_KO_RE.finditer(blob):
        out.add(f"eo:{m.group(1)}")
    for m in EU_REG_RE.finditer(blob):
        out.add(f"eu-reg:{m.group(1)}")
    # Congress bill from URL
    for u in item_urls(it):
        m = re.search(r"congress\.gov/bill/(\d+)(?:th|st|nd|rd)-congress/(senate-bill|house-bill)/(\d+)", u)
        if m:
            out.add(f"us-bill:{m.group(1)}:{m.group(2)}:{m.group(3)}")
        q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
        if q.get("bill_id"):
            out.add(f"bill_id:{q['bill_id'][0].lower()}")
    title = it.get("title") or ""
    m = re.search(r"\b(AB|SB|HR|S)\s*-?\s*(\d{2,5})\b", title, re.I)
    if m and it.get("collection") in {"agora", "mofa-country-policy"}:
        org = (it.get("org") or "").lower()
        if "california" in org or "calif" in title.lower() or m.group(1).upper() in {"AB", "SB"}:
            if "california" in org or re.search(r"california|캘리포니아", title, re.I):
                out.add(f"ca:{m.group(1).upper()}:{m.group(2)}")
    return out


def title_similar(a: dict, b: dict) -> bool:
    ka = act_section_key_local(a.get("title") or "")
    kb = act_section_key_local(b.get("title") or "")
    # Different sections/titles of an omnibus act are not the same document
    if ka and kb and ka != kb:
        return False
    ta, tb = latin_tokens(a.get("title") or ""), latin_tokens(b.get("title") or "")
    na, nb = norm_title(a.get("title") or ""), norm_title(b.get("title") or "")
    if na and na == nb and len(na) >= 16:
        return True
    if ta and tb and len(ta & tb) >= 4 and jaccard(ta, tb) >= 0.5:
        return True
    if ta and tb and len(ta & tb) >= 3 and jaccard(ta, tb) >= 0.72:
        return True
    return False


def is_parent_act_url(u: str) -> bool:
    p = urllib.parse.urlparse(u)
    path = p.path.lower()
    host = p.netloc
    if "congress.gov" in host and ("/bill/" in path or "/plaws/" in path):
        return True
    if "legislature.ca.gov" in host and "bill_id=" in p.query.lower():
        return True
    if "legislation.nysenate.gov" in host and "/bills/" in path:
        return True
    if "akleg.gov" in host and "bill" in path:
        return True
    if "legiscan.com" in host and "/bill/" in path:
        return True
    if "openstates.org" in host and "/bills/" in path:
        return True
    return False


def act_section_key_local(title: str) -> str:
    """Mirror library_common.act_section_key (kept local to avoid import path issues)."""
    t = title or ""
    m = re.search(r"\bSec(?:tion)?\.?\s*(\d+[A-Za-z\-]*)", t, re.I)
    if m:
        return f"sec:{m.group(1).lower()}"
    parts = []
    m = re.search(r"\bDivision\s+([A-Z\d]+)", t, re.I)
    if m:
        parts.append(f"div:{m.group(1).upper()}")
    m = re.search(r"\bTitle\s+([IVXLCDM\d]+)", t, re.I)
    if m:
        parts.append(f"title:{m.group(1).upper()}")
    m = re.search(r"\bSubtitle\s+([A-Z])", t, re.I)
    if m:
        parts.append(f"sub:{m.group(1).upper()}")
    if parts:
        return "-".join(parts)
    return ""


def link_url_group(group: list[str], u: str, spec: int, by_id: dict, link) -> None:
    group = list(dict.fromkeys(group))
    if len(group) < 2:
        return
    if is_parent_act_url(u):
        # Omnibus/bill pages list many sections — only merge true same-section
        # duplicates, never the whole act catalog.
        by_sec: dict[str, list[str]] = defaultdict(list)
        for iid in group:
            sk = act_section_key_local(by_id[iid].get("title") or "") or f"id:{iid}"
            by_sec[sk].append(iid)
        for sk, ids in by_sec.items():
            ids = list(dict.fromkeys(ids))
            if len(ids) < 2:
                continue
            for x in ids[1:]:
                link(ids[0], x, f"act-sec-dup:{u}|{sk}")
        return
    for i in range(len(group)):
        for j in range(i + 1, len(group)):
            a, b = by_id[group[i]], by_id[group[j]]
            if title_similar(a, b):
                link(group[i], group[j], f"url-title:{u}")
            elif spec >= 2 and a["collection"] != b["collection"]:
                la, lb = latin_tokens(a.get("title") or ""), latin_tokens(b.get("title") or "")
                if not la or not lb or len(la & lb) >= 2:
                    link(group[i], group[j], f"url-cross:{u}")


def cluster_kind(members: list[dict]) -> str:
    cols = {m["collection"] for m in members}
    if len(cols) >= 2:
        return "same-document"
    if cols == {"agora"}:
        titles = [m.get("title") or "" for m in members]
        sec_keys = {act_section_key_local(t) for t in titles}
        sec_keys.discard("")
        # Distinct sections of one act are NOT a display cluster anymore
        if len(sec_keys) >= 2:
            return "same-act"  # should be rare after link_url_group fix
        if sum(1 for t in titles if re.search(r"\bSec(?:tion)?\.?\s*\d", t, re.I)) >= 2:
            return "duplicate-record"
        return "duplicate-record" if len(members) >= 2 else "duplicate-record"
    return "duplicate-record"


def canonical_title(members: list[dict]) -> str:
    pref = {"agora": 0, "oecd-navigator": 1, "mofa-country-policy": 2, "mofa-governance": 3, "iaae-ethics": 4}
    members = sorted(members, key=lambda m: (pref.get(m["collection"], 9), -(len(m.get("title") or ""))))
    return members[0].get("title") or members[0]["id"]


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def deterministic(items: list[dict]) -> tuple[UnionFind, dict[str, list[dict]]]:
    ids = [it["id"] for it in items]
    uf = UnionFind(ids)
    by_id = {it["id"]: it for it in items}
    evidence: dict[tuple[str, str], str] = {}

    def link(a: str, b: str, why: str) -> None:
        if a == b:
            return
        uf.union(a, b)
        evidence[tuple(sorted((a, b)))] = why

    # 1) document URLs
    by_url: dict[str, list[str]] = defaultdict(list)
    url_score: dict[str, int] = {}
    for it in items:
        for u in item_urls(it):
            spec = url_spec(u)
            if spec < 1:
                continue
            by_url[u].append(it["id"])
            url_score[u] = max(url_score.get(u, 0), spec)

    for u, group in by_url.items():
        link_url_group(group, u, url_score[u], by_id, link)

    # 2) host+slug
    by_slug: dict[tuple[str, str], list[str]] = defaultdict(list)
    for it in items:
        for u in item_urls(it):
            if url_spec(u) < 2:
                continue
            slug = slug_of(u)
            if not slug or slug in GENERIC_SLUGS or len(slug) < 16:
                continue
            host = urllib.parse.urlparse(u).netloc
            by_slug[(host, slug)].append(it["id"])
    for key, group in by_slug.items():
        host, slug = key
        fake = f"https://{host}/{slug}"
        spec = 2
        link_url_group(group, fake, spec, by_id, link)

    # 3) exact normalized title — cross-collection only, same jurisdiction
    by_title: dict[str, list[str]] = defaultdict(list)
    for it in items:
        nt = norm_title(it.get("title") or "")
        if len(nt) >= 20:
            by_title[nt].append(it["id"])

    def _jur(it: dict) -> str:
        """Jurisdiction key for title matching; empty = unknown."""
        try:
            from library_common import country_from_item

            c = country_from_item(it) or ""
        except Exception:
            c = str(it.get("country") or it.get("gaiin_country") or "")
        if not c or c == "International":
            return ""
        return c

    for nt, group in by_title.items():
        group = list(dict.fromkeys(group))
        if len(group) < 2:
            continue
        cols = {by_id[g]["collection"] for g in group}
        # Generic English titles repeat across OECD countries — never merge
        # within a single collection by title alone.
        if len(cols) < 2:
            continue
        if len(nt) < 20:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = by_id[group[i]], by_id[group[j]]
                if a["collection"] == b["collection"]:
                    continue
                ca, cb = _jur(a), _jur(b)
                if ca and cb and ca != cb:
                    continue
                link(group[i], group[j], f"title:{nt[:80]}")

    # 4) identifiers
    by_ident: dict[str, list[str]] = defaultdict(list)
    for it in items:
        for ident in identifiers(it):
            by_ident[ident].append(it["id"])
    for ident, group in by_ident.items():
        group = list(dict.fromkeys(group))
        if len(group) < 2:
            continue
        if ident.startswith("us-bill:") or ident.startswith("bill_id:"):
            # Same bill number hosts many section cards — only merge same section
            by_sec: dict[str, list[str]] = defaultdict(list)
            for iid in group:
                sk = act_section_key_local(by_id[iid].get("title") or "") or f"id:{iid}"
                by_sec[sk].append(iid)
            for sk, ids in by_sec.items():
                ids = list(dict.fromkeys(ids))
                if len(ids) < 2:
                    continue
                for x in ids[1:]:
                    link(ids[0], x, f"id:{ident}|{sk}")
            continue
        num = ident.split(":")[-1] if ident.startswith("eo:") else ""
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = by_id[group[i]], by_id[group[j]]
                if ident.startswith("eo:") and num:
                    ta = (a.get("title") or "") + " " + (a.get("document_name") or "")
                    tb = (b.get("title") or "") + " " + (b.get("document_name") or "")
                    if num in ta and num in tb:
                        link(group[i], group[j], f"id:{ident}")
                        continue
                if title_similar(a, b):
                    link(group[i], group[j], f"id:{ident}")

    # 4b) well-known instrument aliases
    by_alias: dict[str, list[str]] = defaultdict(list)
    for it in items:
        for key in alias_keys(it):
            by_alias[key].append(it["id"])
    for key, group in by_alias.items():
        group = list(dict.fromkeys(group))
        if len(group) < 2:
            continue
        for x in group[1:]:
            link(group[0], x, f"alias:{key}")

    # 5) MOFA/IAAE slug tokens vs English titles
    english = [it for it in items if it["collection"] in {"agora", "oecd-navigator"}]
    korean = [it for it in items if it["collection"] in {"mofa-governance", "mofa-country-policy", "iaae-ethics"}]
    for k in korean:
        st: set[str] = set()
        for u in item_urls(k):
            st |= slug_tokens(u)
        lt = latin_tokens(k.get("title") or "")
        query = st | lt
        if len(query) < 3:
            continue
        best = None
        for e in english:
            et = latin_tokens(e.get("title") or "")
            if len(query & et) < 3:
                continue
            score = jaccard(query, et)
            if score >= 0.55 and (not best or score > best[0]):
                best = (score, e)
        if best:
            link(k["id"], best[1]["id"], f"slug-title:{best[0]:.2f}")

    groups: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        groups[uf.find(it["id"])].append(it)
    return uf, groups


def llm_chat(model: str, messages: list[dict], timeout: int = 90) -> str:
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    body = json.dumps(
        {
            "model": model,
            "temperature": 0,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
    ).encode()
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/songkyungho/ai-safety-library",
            "X-Title": "AI Safety Library cluster",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    return data["choices"][0]["message"]["content"]


def candidate_pool(query: dict, pool: list[dict], limit: int = 8) -> list[dict]:
    qt = latin_tokens(query.get("title") or "")
    st: set[str] = set()
    for u in item_urls(query):
        st |= slug_tokens(u)
    q = qt | st
    prefix = ""
    m = re.match(r"\[([^\]]+)\]", query.get("title") or "")
    if m:
        prefix = m.group(1).lower()
    scored = []
    qyear = (query.get("date") or "")[:4]
    qcol = query.get("collection")
    for it in pool:
        if it["id"] == query["id"] or it.get("collection") == qcol:
            continue
        et = latin_tokens(it.get("title") or "")
        inter = len(q & et) if q else 0
        score = jaccard(q, et) if q else 0.0
        # org hint
        org = (it.get("org") or it.get("category") or "").lower()
        if prefix:
            if prefix in org or prefix in (it.get("title") or "").lower():
                score += 0.08
            if prefix in {"oecd", "g7", "g20", "un", "unesco", "eu", "gpai"} and prefix.replace(" ", "") in (
                it.get("title") or ""
            ).lower() + org:
                score += 0.05
        if qyear and (it.get("date") or "")[:4] == qyear:
            score += 0.03
        if inter >= 2 or score >= 0.28:
            scored.append((score + inter * 0.02, it))
    scored.sort(key=lambda x: -x[0])
    return [it for _, it in scored[:limit]]


def llm_match(korean: list[dict], pool: list[dict], uf: UnionFind, model: str, limit: int | None) -> int:
    linked = 0
    work = korean if not limit else korean[:limit]
    for i, q in enumerate(work, 1):
        cands = candidate_pool(q, pool)
        if not cands:
            continue
        payload = {
            "query": {
                "id": q["id"],
                "title": q.get("title"),
                "org": q.get("org"),
                "date": q.get("date"),
                "urls": item_urls(q)[:5],
                "body": (q.get("body") or "")[:500],
            },
            "candidates": [
                {
                    "id": c["id"],
                    "title": c.get("title"),
                    "org": c.get("org"),
                    "date": c.get("date"),
                    "collection": c.get("collection"),
                    "urls": item_urls(c)[:3],
                }
                for c in cands
            ],
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "You match the SAME official document/instrument across archives. "
                    "Same means the same law, declaration, executive order, strategy, or "
                    "named report — not merely the same topic or a related implementing act. "
                    "Do not match a progress report, government response, update, profile, "
                    "sandbox, or guideline to the parent law/strategy unless both titles name "
                    "the same document. A Korean summary of an English original is a match. "
                    "Return JSON {\"matches\":[{\"id\":\"...\",\"confidence\":\"high|medium\"}]} "
                    "with at most one candidate. Empty matches if none are the same document."
                ),
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        try:
            raw = llm_chat(model, messages)
            data = json.loads(raw)
        except Exception as e:
            print(f"llm {i}/{len(work)} error {q['id']}: {type(e).__name__}")
            time.sleep(1.2)
            continue
        matches = data.get("matches") or []
        ids_ok = {c["id"] for c in cands}
        picked = None
        for m in matches:
            mid = m.get("id") if isinstance(m, dict) else m
            conf = (m.get("confidence") if isinstance(m, dict) else "medium") or "medium"
            if mid in ids_ok and conf == "high":
                picked = mid
                break
        if not picked:
            for m in matches:
                mid = m.get("id") if isinstance(m, dict) else m
                conf = (m.get("confidence") if isinstance(m, dict) else "medium") or "medium"
                if mid in ids_ok and conf == "medium":
                    picked = mid
                    break
        if picked:
            uf.union(q["id"], picked)
            linked += 1
            print(f"llm {i}/{len(work)} {q['id']} → {picked}", flush=True)
        else:
            print(f"llm {i}/{len(work)} {q['id']} → none", flush=True)
        time.sleep(0.15)
    return linked


def build_clusters(items: list[dict], uf: UnionFind) -> list[dict]:
    by_root: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_root[uf.find(it["id"])].append(it)
    clusters = []
    n = 0
    for members in by_root.values():
        if len(members) < 2:
            continue
        # Safety net: never keep multi-section omnibus act catalogs as one cluster
        sec_keys = {act_section_key_local(m.get("title") or "") for m in members}
        sec_keys.discard("")
        if len(sec_keys) >= 2:
            continue
        n += 1
        members_sorted = sorted(members, key=lambda m: (m.get("collection") or "", m.get("date") or ""), reverse=True)
        cols = sorted({m["collection"] for m in members_sorted})
        clusters.append(
            {
                "id": f"cluster-{n:04d}",
                "kind": cluster_kind(members_sorted),
                "title": canonical_title(members_sorted),
                "size": len(members_sorted),
                "collections": cols,
                "date_min": min((m.get("date") or "") for m in members_sorted if m.get("date")) or "",
                "date_max": max((m.get("date") or "") for m in members_sorted if m.get("date")) or "",
                "members": [
                    {
                        "id": m["id"],
                        "collection": m["collection"],
                        "title": m.get("title"),
                        "org": m.get("org"),
                        "date": m.get("date"),
                        "page_url": m.get("page_url"),
                    }
                    for m in members_sorted
                ],
            }
        )
    clusters.sort(key=lambda c: (0 if c["kind"] == "same-document" else 1, -c["size"], c["title"]))
    for i, c in enumerate(clusters, 1):
        c["id"] = f"cluster-{i:04d}"
    return clusters


def write_outputs(items: list[dict], clusters: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    clustered_ids = {m["id"] for c in clusters for m in c["members"]}
    pair = Counter()
    for c in clusters:
        cols = c["collections"]
        if len(cols) >= 2:
            pair[tuple(cols)] += 1
    stats = {
        "updated": "2026-09-04",
        "items": len(items),
        "clusters": len(clusters),
        "clustered_items": len(clustered_ids),
        "singletons": len(items) - len(clustered_ids),
        "by_kind": dict(Counter(c["kind"] for c in clusters)),
        "cross_collection": sum(1 for c in clusters if len(c["collections"]) >= 2),
        "cross_collection_items": sum(c["size"] for c in clusters if len(c["collections"]) >= 2),
        "collection_pair_counts": {"+".join(k): v for k, v in pair.most_common()},
        "by_collection_clustered": dict(
            Counter(m["collection"] for c in clusters for m in c["members"])
        ),
    }
    write_json(OUT / "clusters.json", {"stats": stats, "clusters": clusters})
    write_json(OUT / "stats.json", stats)

    with (OUT / "membership.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["cluster_id", "kind", "cluster_title", "item_id", "collection", "date", "title", "page_url"],
        )
        w.writeheader()
        for c in clusters:
            for m in c["members"]:
                w.writerow(
                    {
                        "cluster_id": c["id"],
                        "kind": c["kind"],
                        "cluster_title": c["title"],
                        "item_id": m["id"],
                        "collection": m["collection"],
                        "date": m.get("date") or "",
                        "title": m.get("title") or "",
                        "page_url": m.get("page_url") or "",
                    }
                )

    lines = [
        "# 동일 문서 클러스터",
        "",
        "컬렉션을 가로질러 같은 법·선언·전략·보고서를 묶었다. URL·슬러그·제목·식별자(행정명령 번호, 법안 번호)로 먼저 묶고, 남은 한국어 항목은 LLM으로 확인한다.",
        "",
        f"- 항목 {stats['items']}건 중 **{stats['clustered_items']}건**이 {stats['clusters']}개 클러스터에 들어간다.",
        f"- 교차 컬렉션: **{stats['cross_collection']}개** ({stats['cross_collection_items']}건).",
        f"- 종류: {', '.join(f'{k} {v}' for k, v in stats['by_kind'].items())}",
        "",
        "## 교차 컬렉션",
        "",
    ]
    cross = [c for c in clusters if c["kind"] == "same-document"]
    for c in cross:
        lines.append(f"### {c['id']} · {c['title']}")
        lines.append("")
        lines.append(f"- 컬렉션: {', '.join(c['collections'])} · {c['size']}건 · {c['date_min']} ~ {c['date_max']}")
        for m in c["members"]:
            url = m.get("page_url") or ""
            title = (m.get("title") or "").replace("[", "［").replace("]", "］")
            link = f"[{title}]({url})" if url else title
            lines.append(f"- `{m['collection']}` {link}")
        lines.append("")
    (OUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="match leftover Korean items via OpenRouter")
    ap.add_argument("--llm-limit", type=int, default=0, help="cap Korean items sent to LLM (0 = all)")
    ap.add_argument("--model", default=DEFAULT_LLM_MODEL)
    args = ap.parse_args()

    items = load_items()
    print(f"loaded {len(items)}", flush=True)
    uf, groups = deterministic(items)
    det_multi = sum(1 for g in groups.values() if len(g) >= 2)
    print(f"deterministic multi-groups {det_multi}", flush=True)

    if args.llm:
        key = ensure_openrouter_key()
        if not key:
            raise SystemExit("OPENROUTER_API_KEY 없음. ~/.ai_safety_daily_env 또는 환경변수를 넣어 주세요.")
        clustered = {it["id"] for g in groups.values() if len(g) >= 2 for it in g}
        korean = [
            it
            for it in items
            if it["collection"] in {"mofa-governance", "mofa-country-policy", "iaae-ethics"}
            and it["id"] not in clustered
        ]
        pool = [it for it in items if it["collection"] in {"agora", "oecd-navigator", "mofa-governance", "mofa-country-policy"}]
        print(f"llm candidates {len(korean)} korean vs {len(pool)} pool, model {args.model}", flush=True)
        n = llm_match(korean, pool, uf, args.model, args.llm_limit or None)
        print(f"llm links {n}")

    clusters = build_clusters(items, uf)
    write_outputs(items, clusters)
    stats = json.loads((OUT / "stats.json").read_text(encoding="utf-8"))
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
