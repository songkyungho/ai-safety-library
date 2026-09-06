"""Shared helpers: canonical original URLs, country/flags, collection IO."""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

ROOT = Path(__file__).resolve().parent.parent

COLLECTIONS = [
    ("mofa-governance", "외교부 글로벌 AI거버넌스 논의"),
    ("mofa-country-policy", "외교부 주요국 AI 정책"),
    ("iaae-ethics", "IAAE 연구자료실"),
    ("agora", "ETO AGORA"),
    ("oecd-navigator", "OECD.AI Policy Navigator"),
    ("lab-policies", "개발사 프론티어 안전 정책"),
    ("derived-splits", "묶음 분리"),
]

CURATOR_HOSTS = {
    "www.mofa.go.kr",
    "mofa.go.kr",
    "iaae.ai",
    "www.iaae.ai",
    "oecd.ai",
    "www.oecd.ai",
}

# Hosts that are never a useful original landing page.
BAD_ORIGINAL_HOSTS = {
    "www.google.com",
    "google.com",
    "docs.google.com",
    "drive.google.com",
    "www.bing.com",
    "bing.com",
    "search.yahoo.com",
    "duckduckgo.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "www.facebook.com",
    "linkedin.com",
    "www.linkedin.com",
    "youtube.com",
    "www.youtube.com",
}

TITLE_COUNTRY = {
    "미국": "United States",
    "중국": "China",
    "일본": "Japan",
    "영국": "United Kingdom",
    "한국": "South Korea",
    "대한민국": "South Korea",
    "호주": "Australia",
    "캐나다": "Canada",
    "싱가포르": "Singapore",
    "독일": "Germany",
    "프랑스": "France",
    "UAE": "United Arab Emirates",
    "아랍에미리트": "United Arab Emirates",
    "인도": "India",
    "브라질": "Brazil",
    "이탈리아": "Italy",
    "스페인": "Spain",
    "네덜란드": "Netherlands",
    "벨기에": "Belgium",
    "스위스": "Switzerland",
    "스웨덴": "Sweden",
    "노르웨이": "Norway",
    "덴마크": "Denmark",
    "핀란드": "Finland",
    "폴란드": "Poland",
    "아일랜드": "Ireland",
    "오스트리아": "Austria",
    "뉴질랜드": "New Zealand",
    "멕시코": "Mexico",
    "이스라엘": "Israel",
    "사우디": "Saudi Arabia",
    "사우디아라비아": "Saudi Arabia",
    "말레이시아": "Malaysia",
    "인도네시아": "Indonesia",
    "태국": "Thailand",
    "베트남": "Vietnam",
    "필리핀": "Philippines",
    "대만": "Taiwan",
    "홍콩": "Hong Kong",
    "남아공": "South Africa",
    "남아프리카": "South Africa",
    "케냐": "Kenya",
    "나이지리아": "Nigeria",
    "이집트": "Egypt",
    "튀르키예": "Turkey",
    "터키": "Turkey",
    "러시아": "Russia",
    "우크라이나": "Ukraine",
    "칠레": "Chile",
    "아르헨티나": "Argentina",
    "콜롬비아": "Colombia",
    "페루": "Peru",
    "카타르": "Qatar",
    "바레인": "Bahrain",
    "오만": "Oman",
    "쿠웨이트": "Kuwait",
    "짐바브웨": "Zimbabwe",
    "Zimbabwe": "Zimbabwe",
}

# Orgs with Unicode flag emoji (not ISO country codes).
# Empty string = show the org name without an emoji (no official flag).
ORG_FLAGS = {
    "European Union": "🇪🇺",
    "United Nations": "🇺🇳",
    "UNESCO": "🇺🇳",
    "African Union": "🌍",  # no dedicated AU emoji; globe as stand-in
    "ASEAN": "🌏",
    "Council of Europe": "🇪🇺",  # European regional; CoE has no separate emoji
    "OECD": "",
    "IMF": "",
    "NATO": "",
    "WTO": "",
    "ISO": "",
    "IEEE": "",
    "ITU": "",
    "GPAI": "",
    "G7": "",
    "G20": "",
    "World Bank": "",
}

# Aliases → ORG_FLAGS key (or generic International).
ORG_ALIASES = {
    "eu": "European Union",
    "european union": "European Union",
    "유럽연합": "European Union",
    "유럽": "European Union",
    "europäische union": "European Union",
    "un": "United Nations",
    "united nations": "United Nations",
    "유엔": "United Nations",
    "国連": "United Nations",
    "unesco": "UNESCO",
    "유네스코": "UNESCO",
    "african union": "African Union",
    "아프리카연합": "African Union",
    "au": "African Union",
    "asean": "ASEAN",
    "아세안": "ASEAN",
    "council of europe": "Council of Europe",
    "유럽평의회": "Council of Europe",
    "coe": "Council of Europe",
    "oecd": "OECD",
    "organisation for economic co-operation and development": "OECD",
    "organization for economic cooperation and development": "OECD",
    "경제협력개발기구": "OECD",
    "imf": "IMF",
    "international monetary fund": "IMF",
    "국제통화기금": "IMF",
    "nato": "NATO",
    "북대서양조약기구": "NATO",
    "wto": "WTO",
    "world trade organization": "WTO",
    "iso": "ISO",
    "ieee": "IEEE",
    "itu": "ITU",
    "gpai": "GPAI",
    "g7": "G7",
    "g20": "G20",
    "world bank": "World Bank",
    "세계은행": "World Bank",
    "ibrd": "World Bank",
}

# Multilateral labels without a dedicated jurisdiction identity.
INTERNATIONAL_LABELS = {
    "igo",
    "국제",
    "다자",
    "글로벌",
    "multinational",
    "international",
    "ai summit",
    "ai 안전 정상회의",
}

_ISO = {
    "South Korea": "KR",
    "United States": "US",
    "United Kingdom": "GB",
    "United Arab Emirates": "AE",
    "Belgium": "BE",
    "Singapore": "SG",
    "France": "FR",
    "Malaysia": "MY",
    "Canada": "CA",
    "Japan": "JP",
    "Germany": "DE",
    "Italy": "IT",
    "Poland": "PL",
    "Spain": "ES",
    "Switzerland": "CH",
    "India": "IN",
    "Netherlands": "NL",
    "Australia": "AU",
    "Indonesia": "ID",
    "Taiwan": "TW",
    "Thailand": "TH",
    "China": "CN",
    "Kenya": "KE",
    "Hong Kong": "HK",
    "Brazil": "BR",
    "Sweden": "SE",
    "Norway": "NO",
    "Denmark": "DK",
    "Finland": "FI",
    "Ireland": "IE",
    "Austria": "AT",
    "New Zealand": "NZ",
    "Mexico": "MX",
    "Israel": "IL",
    "Saudi Arabia": "SA",
    "Vietnam": "VN",
    "Philippines": "PH",
    "South Africa": "ZA",
    "Nigeria": "NG",
    "Egypt": "EG",
    "Turkey": "TR",
    "Russia": "RU",
    "Ukraine": "UA",
    "Chile": "CL",
    "Argentina": "AR",
    "Colombia": "CO",
    "Peru": "PE",
    "Qatar": "QA",
    "Bahrain": "BH",
    "Oman": "OM",
    "Kuwait": "KW",
    "Zimbabwe": "ZW",
    "Portugal": "PT",
    "Greece": "GR",
    "Czech Republic": "CZ",
    "Czechia": "CZ",
    "Hungary": "HU",
    "Romania": "RO",
    "Slovakia": "SK",
    "Slovenia": "SI",
    "Croatia": "HR",
    "Estonia": "EE",
    "Latvia": "LV",
    "Lithuania": "LT",
    "Luxembourg": "LU",
    "Iceland": "IS",
    "Malta": "MT",
    "Cyprus": "CY",
    "Bulgaria": "BG",
    "Serbia": "RS",
    "Kazakhstan": "KZ",
    "Armenia": "AM",
    "Pakistan": "PK",
    "Bangladesh": "BD",
    "Sri Lanka": "LK",
    "Nepal": "NP",
    "Cambodia": "KH",
    "Laos": "LA",
    "Myanmar": "MM",
    "Mongolia": "MN",
    "Ghana": "GH",
    "Rwanda": "RW",
    "Ethiopia": "ET",
    "Morocco": "MA",
    "Tunisia": "TN",
    "Jordan": "JO",
    "Lebanon": "LB",
    "Iraq": "IQ",
    "Iran": "IR",
    "Uruguay": "UY",
    "Paraguay": "PY",
    "Ecuador": "EC",
    "Costa Rica": "CR",
    "Panama": "PA",
    "Dominican Republic": "DO",
    "Jamaica": "JM",
    "Trinidad and Tobago": "TT",
}

_COUNTRY_ALIASES = {k.lower(): v for k, v in TITLE_COUNTRY.items()}
for name in _ISO:
    _COUNTRY_ALIASES[name.lower()] = name
_COUNTRY_ALIASES.update(
    {
        "usa": "United States",
        "us": "United States",
        "u.s.": "United States",
        "u.s.a.": "United States",
        "uk": "United Kingdom",
        "uae": "United Arab Emirates",
        "korea": "South Korea",
        "rok": "South Korea",
        "republic of korea": "South Korea",
        "korea, rep.": "South Korea",
        "korea, republic of": "South Korea",
        "czechia": "Czechia",
        "czech republic": "Czechia",
        "slovak republic": "Slovakia",
        "slovakia": "Slovakia",
        "saudi": "Saudi Arabia",
        "china (people’s republic of)": "China",
        "china (people's republic of)": "China",
        "people's republic of china": "China",
        "viet nam": "Vietnam",
        "vietnam": "Vietnam",
        "türkiye": "Turkey",
        "turkiye": "Turkey",
        "brunei darussalam": "Brunei",
        "côte d’ivoire": "Ivory Coast",
        "cote d'ivoire": "Ivory Coast",
        "holy see": "Vatican City",
    }
)

# Extra ISO codes for OECD country names
_ISO.update(
    {
        "Brunei": "BN",
        "Ivory Coast": "CI",
        "Vatican City": "VA",
        "Algeria": "DZ",
        "Benin": "BJ",
        "Cameroon": "CM",
        "Cuba": "CU",
        "Lesotho": "LS",
        "Libya": "LY",
        "Mauritania": "MR",
        "Mauritius": "MU",
        "Senegal": "SN",
        "Uganda": "UG",
        "Uzbekistan": "UZ",
        "Zambia": "ZM",
    }
)


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_collection(key: str) -> dict:
    path = ROOT / "collections" / key / "items.json"
    return json.loads(path.read_text(encoding="utf-8"))


def save_collection(key: str, data: dict) -> None:
    write_json(ROOT / "collections" / key / "items.json", data)


def iter_items() -> list[dict]:
    out = []
    for key, _name in COLLECTIONS:
        data = load_collection(key)
        for it in data.get("items") or []:
            out.append(it)
    return out


def as_url_list(val) -> list[str]:
    if not val:
        return []
    if isinstance(val, str):
        return [u.strip() for u in val.split(" | ") if u.strip()]
    return [u.strip() for u in val if isinstance(u, str) and u.strip()]


def host_of(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def is_http_url(url: str) -> bool:
    return isinstance(url, str) and url.startswith(("http://", "https://"))


def is_curator_url(url: str) -> bool:
    host = host_of(url)
    if host in CURATOR_HOSTS:
        return True
    if host.endswith(".oecd.ai"):
        return True
    return False


def is_bad_original(url: str) -> bool:
    host = host_of(url)
    if host in BAD_ORIGINAL_HOSTS:
        return True
    if host.endswith(".google.com") and "scholar" not in host:
        path = urlparse(url).path or ""
        if path in ("", "/", "/search", "/url"):
            return True
    return False


def normalize_url(url: str) -> str:
    """Normalize for dedup keys; keep a usable href separately."""
    if not is_http_url(url):
        return ""
    try:
        p = urlparse(url.strip())
    except Exception:
        return ""
    scheme = (p.scheme or "https").lower()
    netloc = (p.netloc or "").lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = p.path or ""
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    # Drop tracking / fragment
    q = [
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=True)
        if k.lower() not in {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}
    ]
    query = urlencode(q, doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def candidate_originals(item: dict) -> list[str]:
    """Ordered original-landing candidates (not curator pages)."""
    seen = set()
    out: list[str] = []

    def add(url: str) -> None:
        if not is_http_url(url):
            return
        if is_curator_url(url) or is_bad_original(url):
            return
        key = normalize_url(url)
        if not key or key in seen:
            return
        seen.add(key)
        out.append(url.strip())

    for u in as_url_list(item.get("source_urls")):
        add(u)
    # AGORA page_url is usually the official document link
    if item.get("collection") == "agora":
        add(item.get("page_url") or "")
    if item.get("collection") == "derived-splits":
        add(item.get("page_url") or "")
    for u in as_url_list(item.get("source_files") or item.get("file_urls")):
        add(u)
    return out


def pick_canonical(item: dict) -> str:
    cands = candidate_originals(item)
    if cands:
        return cands[0]
    # Fall back to curator landing (OECD initiative page, etc.) when no
    # better original URL was extracted — still one document per URL.
    page = (item.get("page_url") or "").strip()
    if page and is_http_url(page) and not is_bad_original(page):
        return page
    return ""


def is_parent_act_url(u: str) -> bool:
    """Bill-level landing pages that host many section-level AGORA cards."""
    if not u:
        return False
    p = urlparse(u)
    path = p.path.lower()
    host = p.netloc.lower()
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


def act_section_key(title: str) -> str:
    """Stable key for a section/subtitle within a parent act URL group."""
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


def act_base_name(title: str) -> str:
    """Act-level compact name without section/title markers (e.g. NDAA FY2026)."""
    t = (title or "").strip()
    if not t:
        return ""
    has_sec = bool(re.search(r"\bSec(?:tion)?\.?\s*\d", t, re.I))
    has_div = bool(re.search(r"\b(?:Division|Title|Subtitle)\b", t, re.I))
    if not has_sec and not has_div:
        return ""

    base = re.split(
        r",\s*(?=Section\b|Sec\.\s*\d|Title\b|Division\b)|(?<=Act)\s+(?=Section\b|Sec\.\s*\d|Title\b|Division\b)",
        t,
        maxsplit=1,
        flags=re.I,
    )[0].strip(" ,")
    if not base:
        base = t

    base = re.sub(
        r"^Servicemember Quality of Life Improvement and National Defense Authorization Act"
        r"(?:\s+for Fiscal Year\s+(\d{4}))?",
        lambda m: f"NDAA FY{m.group(1)}" if m.group(1) else "NDAA",
        base,
        flags=re.I,
    )
    base = re.sub(
        r"^(?:James M\.\s+Inhofe\s+|William M\.\s+\(Mac\)\s+Thornberry\s+|John S\.\s+McCain\s+)?"
        r"National Defense Authorization Act for Fiscal Year\s+(\d{4})",
        r"NDAA FY\1",
        base,
        flags=re.I,
    )
    base = re.sub(
        r"^One Big Beautiful Bill Act(?:\s+(\d{4}))?",
        lambda m: f"OBBB Act {m.group(1)}" if m.group(1) else "OBBB Act",
        base,
        flags=re.I,
    )
    base = re.sub(
        r"^Infrastructure Investment and Jobs Act",
        "IIJA",
        base,
        flags=re.I,
    )
    base = re.sub(
        r"^Research and Development, Competition, and Innovation Act",
        "CHIPS/R&D Act",
        base,
        flags=re.I,
    )
    base = re.sub(
        r"^Consolidated Appropriations Act,\s*(\d{4})",
        r"CAA \1",
        base,
        flags=re.I,
    )
    base = re.sub(
        r"^Intelligence Authorization Act for Fiscal Year\s+(\d{4})",
        r"IAA FY\1",
        base,
        flags=re.I,
    )
    if len(base) > 72:
        base = base[:69] + "…"
    return base


def act_short_name(title: str) -> str:
    """Compact display name for a single section card (e.g. NDAA FY2025 §225)."""
    t = (title or "").strip()
    base = act_base_name(t)
    if not base:
        return ""

    m = re.search(
        r"\bSec(?:tion)?\.?\s*(\d+[A-Za-z\-]*(?:\([^)]*\))?)\s*(?:\(\"([^\"]+)\")?",
        t,
        re.I,
    )
    if m:
        sec, quote = m.group(1), (m.group(2) or "").strip()
        if quote:
            q = quote if len(quote) <= 64 else quote[:61] + "…"
            return f"{base} §{sec} — {q}"
        return f"{base} §{sec}"

    bits = [base]
    m = re.search(r"\bDivision\s+([A-Z\d]+)", t, re.I)
    if m:
        bits.append(f"Div {m.group(1).upper()}")
    m = re.search(r"\bTitle\s+([IVXLCDM\d]+)", t, re.I)
    if m:
        bits.append(f"Title {m.group(1).upper()}")
    m = re.search(r"\bSubtitle\s+([A-Z])", t, re.I)
    if m:
        bits.append(f"Subtitle {m.group(1).upper()}")
    quote = ""
    mq = re.search(r"\(\"([^\"]+)\"\)\s*$", t)
    if not mq:
        mq = re.search(r"\(\"([^\"]+)\"\)", t)
    if mq:
        quote = mq.group(1).strip()
    label = " ".join(bits)
    if quote and label != base:
        q = quote if len(quote) <= 64 else quote[:61] + "…"
        return f"{label} — {q}"
    if label != base:
        return label
    return ""


def format_act_section_labels(titles: list[str], limit: int = 12) -> str:
    """Human-readable section list for a merged parent-act document."""
    labels: list[str] = []
    seen: set[str] = set()
    for title in titles:
        t = title or ""
        m = re.search(r"\bSec(?:tion)?\.?\s*(\d+[A-Za-z\-]*(?:\([^)]*\))?)", t, re.I)
        if m:
            lab = f"§{m.group(1)}"
        else:
            bits = []
            md = re.search(r"\bDivision\s+([A-Z\d]+)", t, re.I)
            if md:
                bits.append(f"Div {md.group(1).upper()}")
            mt = re.search(r"\bTitle\s+([IVXLCDM\d]+)", t, re.I)
            if mt:
                bits.append(f"Title {mt.group(1).upper()}")
            ms = re.search(r"\bSubtitle\s+([A-Z])", t, re.I)
            if ms:
                bits.append(f"Subtitle {ms.group(1).upper()}")
            lab = " ".join(bits)
        if not lab or lab in seen:
            continue
        seen.add(lab)
        labels.append(lab)
    if not labels:
        return ""
    if len(labels) > limit:
        return ", ".join(labels[:limit]) + f" 외 {len(labels) - limit}건"
    return ", ".join(labels)


def flag_emoji(country: str) -> str:
    country = (country or "").strip()
    if not country or country == "International":
        return ""
    if country in ORG_FLAGS:
        return ORG_FLAGS[country]
    code = _ISO.get(country)
    if not code:
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in code)


# English canonical → Korean short label for UI.
COUNTRY_KO = {
    "South Korea": "한국",
    "United States": "미국",
    "United Kingdom": "영국",
    "United Arab Emirates": "UAE",
    "European Union": "EU",
    "United Nations": "UN",
    "UNESCO": "유네스코",
    "ASEAN": "아세안",
    "Council of Europe": "유럽평의회",
    "African Union": "AU",
    "OECD": "OECD",
    "IMF": "IMF",
    "NATO": "NATO",
    "WTO": "WTO",
    "ISO": "ISO",
    "IEEE": "IEEE",
    "ITU": "ITU",
    "GPAI": "GPAI",
    "G7": "G7",
    "G20": "G20",
    "World Bank": "세계은행",
    "China": "중국",
    "Japan": "일본",
    "Germany": "독일",
    "France": "프랑스",
    "Canada": "캐나다",
    "Australia": "호주",
    "Singapore": "싱가포르",
    "India": "인도",
    "Italy": "이탈리아",
    "Spain": "스페인",
    "Netherlands": "네덜란드",
    "Belgium": "벨기에",
    "Switzerland": "스위스",
    "Sweden": "스웨덴",
    "Norway": "노르웨이",
    "Denmark": "덴마크",
    "Finland": "핀란드",
    "Poland": "폴란드",
    "Ireland": "아일랜드",
    "Austria": "오스트리아",
    "New Zealand": "뉴질랜드",
    "Mexico": "멕시코",
    "Israel": "이스라엘",
    "Saudi Arabia": "사우디",
    "Vietnam": "베트남",
    "Philippines": "필리핀",
    "Indonesia": "인도네시아",
    "Malaysia": "말레이시아",
    "Thailand": "태국",
    "Taiwan": "대만",
    "Hong Kong": "홍콩",
    "Brazil": "브라질",
    "Russia": "러시아",
    "Ukraine": "우크라이나",
    "Turkey": "튀르키예",
    "Czechia": "체코",
    "Czech Republic": "체코",
    "Slovakia": "슬로바키아",
    "Greece": "그리스",
    "Latvia": "라트비아",
    "Bulgaria": "불가리아",
    "Colombia": "콜롬비아",
    "Slovenia": "슬로베니아",
    "Malta": "몰타",
    "Peru": "페루",
    "Egypt": "이집트",
    "Argentina": "아르헨티나",
    "Cambodia": "캄보디아",
    "Chile": "칠레",
    "Portugal": "포르투갈",
    "Costa Rica": "코스타리카",
    "Lithuania": "리투아니아",
    "Luxembourg": "룩셈부르크",
    "Croatia": "크로아티아",
    "Ecuador": "에콰도르",
    "South Africa": "남아공",
    "Romania": "루마니아",
    "Uruguay": "우루과이",
    "Hungary": "헝가리",
    "Kenya": "케냐",
    "Rwanda": "르완다",
    "Estonia": "에스토니아",
    "Dominican Republic": "도미니카공화국",
    "Uzbekistan": "우즈베키스탄",
    "Iceland": "아이슬란드",
    "Zimbabwe": "짐바브웨",
    "Vatican City": "바티칸",
    "Zambia": "잠비아",
    "Libya": "리비아",
    "Nigeria": "나이지리아",
    "Ivory Coast": "코트디부아르",
    "Cameroon": "카메룬",
    "Lesotho": "레소토",
    "Cuba": "쿠바",
    "Senegal": "세네갈",
    "Mauritania": "모리타니",
    "Ethiopia": "에티오피아",
    "Brunei": "브루나이",
    "Ghana": "가나",
    "Benin": "베냉",
    "Mauritius": "모리셔스",
    "Morocco": "모로코",
    "Armenia": "아르메니아",
    "Cyprus": "키프로스",
    "Uganda": "우간다",
    "Serbia": "세르비아",
    "Qatar": "카타르",
    "Bahrain": "바레인",
    "Oman": "오만",
    "Kuwait": "쿠웨이트",
    "Pakistan": "파키스탄",
    "Bangladesh": "방글라데시",
    "Sri Lanka": "스리랑카",
    "Nepal": "네팔",
    "Laos": "라오스",
    "Myanmar": "미얀마",
    "Mongolia": "몽골",
    "Tunisia": "튀니지",
    "Jordan": "요르단",
    "Lebanon": "레바논",
    "Iraq": "이라크",
    "Iran": "이란",
    "Paraguay": "파라과이",
    "Panama": "파나마",
    "Jamaica": "자메이카",
    "Trinidad and Tobago": "트리니다드토바고",
    "Kazakhstan": "카자흐스탄",
    "Algeria": "알제리",
}


def country_label_ko(country: str) -> str:
    country = (country or "").strip()
    if not country or country == "International":
        return ""
    return COUNTRY_KO.get(country, country)


def resolve_org_or_country(raw: str) -> str:
    """Map free text to a country, org-with-flag, or International."""
    if not raw:
        return ""
    text = unicodedata.normalize("NFKC", str(raw)).strip()
    folded = re.sub(r"\s+", " ", text.lower())
    if folded in ORG_ALIASES:
        return ORG_ALIASES[folded]
    if folded in INTERNATIONAL_LABELS:
        return "International"
    if text in ORG_FLAGS:
        return text
    hit = _COUNTRY_ALIASES.get(folded)
    if hit:
        return hit
    for name in _ISO:
        if name.lower() == folded:
            return name
    return ""


def canonicalize_country_name(raw: str) -> str:
    return resolve_org_or_country(raw)


_KR_ORG_RE = re.compile(
    r"과기부|과학기술정보통신부|개인정보보호위원회|방송통신위원회|"
    r"한국저작권위원회|한국지능정보사회진흥원|한국연구재단|한국교육과정평가원|"
    r"한국대학교육협의회|서울디지털재단|서울시교육청|서울특별시|전북특별자치도|"
    r"시청자미디어재단|인공지능안전연구소|부처합동|"
    r"\bNIA\b|\bKISA\b|\bKISDI\b|\bKAIEA\b|\bETRI\b|"
    r"교육부|보건복지부",
    re.I,
)


def country_from_free_text(text: str) -> str:
    """Pick a country/org from free text (title body, org string)."""
    if not text:
        return ""
    for ko in sorted(TITLE_COUNTRY, key=len, reverse=True):
        if ko in text:
            return TITLE_COUNTRY[ko]
    for name in sorted(ORG_FLAGS, key=len, reverse=True):
        if name in text:
            return name
    folded = text.lower()
    for alias, canon in sorted(_COUNTRY_ALIASES.items(), key=lambda x: -len(x[0])):
        if len(alias) >= 4 and alias in folded:
            return canon
    return ""


def country_from_title(title: str) -> str:
    if not title:
        return ""
    m = re.match(r"^[［\[]([^］\]]+)[］\]]", title.strip())
    if m:
        tag = m.group(1).strip()
        # "미국 FCC" → 미국
        head = re.split(r"[\s,/]", tag)[0]
        # Orgs / countries from full tag or head
        for candidate in (tag, head):
            hit = resolve_org_or_country(candidate)
            if hit:
                return hit
        if tag in TITLE_COUNTRY:
            return TITLE_COUNTRY[tag]
        if head in TITLE_COUNTRY:
            return TITLE_COUNTRY[head]
        if _KR_ORG_RE.search(tag):
            return "South Korea"
    # Title body: 「대한민국 …」, 「한국 …」
    hit = country_from_free_text(title)
    if hit:
        return hit
    if _KR_ORG_RE.search(title):
        return "South Korea"
    return ""


def country_from_item(item: dict) -> str:
    # Explicit fields first
    for key in ("country", "gaiin_country", "country_name"):
        val = item.get(key)
        if isinstance(val, dict):
            val = val.get("name") or val.get("slug") or ""
        if val:
            return canonicalize_country_name(str(val))

    col = item.get("collection") or ""
    title = item.get("title") or ""
    cat = item.get("category") or ""
    org = item.get("org") or ""

    if col in ("mofa-country-policy", "mofa-governance", "iaae-ethics", "derived-splits"):
        c = country_from_title(title)
        if c:
            return c
        # Board category: UN / G7 / EU / OECD …
        c = resolve_org_or_country(cat)
        if c:
            return c
        blob = f"{title} {cat} {org}"
        if _KR_ORG_RE.search(blob):
            return "South Korea"
        c = country_from_free_text(blob)
        if c:
            return c
        if col == "mofa-governance":
            return "International"

    if col == "agora":
        low = cat.lower()
        if "chinese" in low or "china" in low:
            return "China"
        if "u.s." in low or "us federal" in low or "us state" in low or "united states" in low:
            return "United States"
        if "multinational" in low:
            return "International"
        c = country_from_title(title)
        if c:
            return c

    if col == "oecd-navigator":
        # org sometimes embeds country; title rarely has brackets
        pass

    return ""


def korean_title_rank(item: dict) -> int:
    """Higher = prefer as display title."""
    col = item.get("collection") or ""
    title = item.get("title") or ""
    has_hangul = bool(re.search(r"[가-힣]", title))
    # Split children must keep their own short titles
    if col == "derived-splits":
        return 40
    if col.startswith("mofa") and has_hangul:
        return 30
    if col == "iaae-ethics" and has_hangul:
        return 20
    if has_hangul:
        return 10
    if col == "agora":
        return 5
    return 0


def rebuild_collection_stats(data: dict) -> dict:
    items = data.get("items") or []
    data["count"] = len(items)
    data["categories"] = dict(Counter((r.get("category") or "기타")[:80] for r in items))
    data["years"] = dict(Counter((r.get("date") or "")[:4] for r in items if r.get("date")))
    return data
