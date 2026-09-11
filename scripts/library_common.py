"""Shared helpers: canonical original URLs, country/flags, collection IO."""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

ROOT = Path(__file__).resolve().parent.parent

COLLECTIONS = [
    ("mofa-governance", "외교부 글로벌 AI거버넌스 논의"),
    ("mofa-country-policy", "외교부 주요국 AI 정책"),
    ("iaae-ethics", "IAAE 연구자료실"),
    ("agora", "ETO AGORA"),
    ("oecd-navigator", "OECD.AI Policy Navigator"),
    ("dpa-ai", "DPA Regulating AI"),
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
    "digitalpolicyalert.org",
    "www.digitalpolicyalert.org",
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
    "바티칸": "Vatican City",
    "교황청": "Vatican City",
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
    "WHO": "🇺🇳",
    "ILO": "🇺🇳",
    "WIPO": "🇺🇳",
    "APEC": "🌏",
    "World Economic Forum": "",
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
    "who": "WHO",
    "world health organization": "WHO",
    "세계보건기구": "WHO",
    "ilo": "ILO",
    "international labour organization": "ILO",
    "international labor organization": "ILO",
    "국제노동기구": "ILO",
    "wipo": "WIPO",
    "world intellectual property organization": "WIPO",
    "세계지적재산권기구": "WIPO",
    "apec": "APEC",
    "아시아태평양경제협력체": "APEC",
    "wef": "World Economic Forum",
    "world economic forum": "World Economic Forum",
    "세계경제포럼": "World Economic Forum",
    "유럽의회": "European Union",
    "유럽이사회": "European Union",
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

# Same instrument, different curator URLs → one card + one jurisdiction.
# (pattern, canonical country/org, group key)
_KNOWN_INSTRUMENTS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(
            r"framework convention on artificial intelligence"
            r"|유럽평의회.{0,40}(?:인공지능|\bAI\b).{0,24}기본협약",
            re.I,
        ),
        "Council of Europe",
        "coe-ai-framework-convention",
    ),
    (
        re.compile(
            r"digital economy partnership agreement"
            r"|(?<![A-Za-z])DEPA(?![A-Za-z])"
            r"|디지털경제파트너십",
            re.I,
        ),
        "International",
        "depa",
    ),
    (
        re.compile(r"\bhuderia\b", re.I),
        "Council of Europe",
        "coe-huderia",
    ),
    (
        re.compile(
            r"asean guide on ai governance(?: and ethics)?"
            r"|ASEAN AI 거버넌스[··]?윤리 가이드",
            re.I,
        ),
        "ASEAN",
        "asean-ai-governance-ethics",
    ),
    (
        re.compile(
            r"guidelines for ai procurement"
            r"|영국\s*AI\s*조달",
            re.I,
        ),
        "United Kingdom",
        "uk-ai-procurement",
    ),
    (
        re.compile(
            r"人工知能基本計画"
            r"|ai basic plan"
            r"|일본\s*AI\s*기본계획",
            re.I,
        ),
        "Japan",
        "jp-ai-basic-plan",
    ),
    (
        re.compile(
            r"act on promotion of research.{0,48}utili[sz]ation of "
            r"(?:artificial intelligence|ai)[ -]?related technolog"
            r"|AI 관련 기술 연구.?개발.?활용 촉진법",
            re.I,
        ),
        "Japan",
        "jp-ai-rd-promotion-act",
    ),
    (
        re.compile(
            r"introduction to ai assurance"
            r"|영국\s*AI\s*보증 소개"
            r"|영국\s*AI\s*Assurance 입문",
            re.I,
        ),
        "United Kingdom",
        "uk-ai-assurance-intro",
    ),
    (
        re.compile(
            r"declaration on ai in the nordic[ -]?baltic region"
            r"|북유럽.?발트.{0,20}AI 선언"
            r"|노르딕.?발틱 AI 선언",
            re.I,
        ),
        "International",
        "nordic-baltic-ai-declaration",
    ),
    (
        re.compile(
            r"gu[ií]a para la auditor[ií]a del uso de herramientas de inteligencia artificial"
            r"|SCE.{0,28}(?:인공지능|AI) 도구 사용 감사",
            re.I,
        ),
        "Ecuador",
        "ec-sce-ai-audit-guide",
    ),
    (
        re.compile(
            r"guidance for ai adoption:\s*implementation guidance"
            r"|호주 AI 도입 (?:지침: 이행 지침|실행 가이드)",
            re.I,
        ),
        "Australia",
        "au-ai-adoption-implementation",
    ),
    (
        re.compile(
            r"KAIEA.{0,40}윤리 헌장.{0,24}191219"
            r"|KAIEA.{0,40}헌장_191219",
            re.I,
        ),
        "South Korea",
        "kaiea-charter-201912",
    ),
    (
        re.compile(r"KAIEA.{0,40}(인공지능 )?윤리 헌장", re.I),
        "South Korea",
        "kaiea-charter-201910",
    ),
    (
        re.compile(r"IAAE.{0,20}인공지능 윤리 헌장", re.I),
        "South Korea",
        "iaae-ethics-charter",
    ),
    (
        re.compile(
            r"the bletchley declaration"
            r"|bletchley.{0,12}선언"
            r"|블레츨리 선언",
            re.I,
        ),
        "International",
        "bletchley-declaration",
    ),
    (
        re.compile(r"seoul declaration|서울 선언", re.I),
        "International",
        "seoul-declaration",
    ),
    (
        re.compile(
            r"g7 leaders.?\s*statement on the hiroshima ai process"
            r"|히로시마 AI 프로세스 정상 성명",
            re.I,
        ),
        "G7",
        "g7-hiroshima-leaders-statement",
    ),
    (
        re.compile(
            r"hiroshima artificial intelligence process code of conduct reporting framework"
            r"|히로시마 AI 프로세스 행동규범 보고 프레임워크",
            re.I,
        ),
        "G7",
        "g7-hiroshima-reporting-framework",
    ),
    (
        re.compile(
            r"hiroshima process international code of conduct"
            r"|code of conduct for organizations developing advanced ai"
            r"|고도 AI 시스템 개발.{0,16}국제 행동규범",
            re.I,
        ),
        "G7",
        "g7-hiroshima-code-of-conduct",
    ),
    (
        re.compile(
            r"hiroshima process international guiding principles"
            r"|히로시마 프로세스 고도 AI 국제 지침 원칙",
            re.I,
        ),
        "G7",
        "g7-hiroshima-guiding-principles",
    ),
    (
        re.compile(
            r"\]\s*인공지능 안전성 확보 가이드라인",
            re.I,
        ),
        "South Korea",
        "kr-ai-safety-guideline",
    ),
    (
        re.compile(
            r"collaboration on global standards for the ai-enabled citiverse"
            r"|시티버스를 위한 글로벌 표준 협력",
            re.I,
        ),
        "ITU",
        "itu-ai-citiverse-standards",
    ),
    (
        re.compile(
            r"ghana national artificial intelligence strategy"
            r"|가나 국가 인공지능 전략",
            re.I,
        ),
        "Ghana",
        "gh-ai-strategy-2023",
    ),
    (
        re.compile(
            r"ethics guidelines (?:on |for )?trustworthy (?:artificial intelligence|\bai\b)"
            r"|ethics guidelines on artificial intelligence"
            r"|신뢰할 수 있는 AI 윤리 가이드라인",
            re.I,
        ),
        "European Union",
        "eu-hleg-ethics-guidelines",
    ),
    (
        re.compile(
            r"opinions? on strengthening (?:the )?(?:governance of )?science and technology ethics"
            r"|opinion on strengthening science and technology ethics"
            r"|중국 과학기술 윤리 거버넌스 강화 의견",
            re.I,
        ),
        "China",
        "cn-sti-ethics-opinions-2022",
    ),
    (
        re.compile(
            r"생성형 AI 서비스 (?:안전 기본 요구사항|기본 안전 요구사항)"
            r"|safety requirements for generative (?:artificial intelligence|ai) services"
            r"|生成式人工智能服务安全基本要求",
            re.I,
        ),
        "China",
        "cn-tc260-genai-safety-2024",
    ),
    (
        re.compile(r"openai charter|openai 헌장", re.I),
        "",
        "openai-charter",
    ),
    (
        re.compile(
            r"general[- ]purpose ai(?: \(gpai\))? code of practice"
            r"|gpai code of practice"
            r"|범용 AI 실천규범",
            re.I,
        ),
        "European Union",
        "eu-gpai-code-of-practice",
    ),
    (
        re.compile(
            r"g7 toolkit for artificial intelligence in the public sector"
            r"|공공부문 AI 활용 툴킷",
            re.I,
        ),
        "G7",
        "g7-public-sector-ai-toolkit",
    ),
]

_SHORT_ORG_TOKENS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?<![A-Za-z])EU(?![A-Za-z])", re.I), "European Union"),
    (re.compile(r"(?<![A-Za-z])UN(?![A-Za-z])", re.I), "United Nations"),
    (re.compile(r"(?<![A-Za-z0-9])G7(?![A-Za-z0-9])", re.I), "G7"),
    (re.compile(r"(?<![A-Za-z0-9])G20(?![A-Za-z0-9])", re.I), "G20"),
]
_TREATY_LIKE = re.compile(
    r"\bagreement\b|\bconvention\b|\btreaty\b|\baccord\b|"
    r"partnership agreement|협정|협약|조약|공동성명|파트너십협정",
    re.I,
)

_SKIP_JURISDICTION_ORG = re.compile(
    r"private-sector companies|"
    r"\b(openai|anthropic|google(?:\s*deepmind)?|deepmind|microsoft|"
    r"meta(?:\s+platforms)?|\bibm\b|\bxai\b|naver|kakao)\b",
    re.I,
)

_SUBNAT_GOV_COUNTRY = {
    "flanders": "Belgium",
    "the scottish government": "United Kingdom",
    "scottish government": "United Kingdom",
    "welsh government": "United Kingdom",
    "new south wales": "Australia",
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
        "united states of america": "United States",
        "chinese taipei": "Taiwan",
        "taiwan, china": "Taiwan",
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


def clean_scraped_url(url: str) -> str:
    """스크랩 문장부호는 벗기되, (INI)·JSON 해시처럼 짝이 맞는 괄호는 남긴다."""
    u = re.sub(r"[\x00-\x1f\x7f]", "", (url or "").strip())
    while u and u[-1] in ".,; ":
        u = u[:-1]
    while u.endswith(("'", '"')):
        u = u[:-1]
    while u.endswith(")") and u.count("(") < u.count(")"):
        u = u[:-1]
    while u.endswith("]") and u.count("[") < u.count("]"):
        u = u[:-1]
    while u.endswith("}") and u.count("{") < u.count("}"):
        u = u[:-1]
    if u.count("{") == u.count("}") + 1:
        u += "}"
    return u


def as_url_list(val) -> list[str]:
    if not val:
        return []
    chunks = [val] if isinstance(val, str) else [u for u in val if isinstance(u, str)]
    out: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        found = re.findall(r"https?://[^\s<>\"']+", chunk)
        parts = found or [p.strip() for u in chunk.split(" | ") if (p := u.strip())]
        for raw in parts:
            u = clean_scraped_url(raw)
            if u and u not in seen:
                seen.add(u)
                out.append(u)
    return out


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
    if re.search(r"\[자료|자료제목|자료출처", url):
        return True
    if re.search(r"[\x00-\x1f\x7f<>]", url):
        return True
    path = (urlparse(url).path or "").rstrip("/") or "/"
    if host in {"futureoflife.org", "www.futureoflife.org"} and path == "/":
        return True
    if host in {"oas.org", "www.oas.org"} and path in {"/", "/en", "/es", "/fr", "/pt"}:
        return True
    if host.endswith(".google.com") and "scholar" not in host:
        path = urlparse(url).path or ""
        if path in ("", "/", "/search", "/url"):
            return True
    return False


def jurisdiction_from_host(host: str) -> str:
    """원문 호스트로 관할을 추정. 큐레이터 호스트는 쓰지 않는다."""
    h = (host or "").lower()
    if h.startswith("www."):
        h = h[4:]
    if not h:
        return ""
    if h.endswith(".europa.eu") or h == "europa.eu" or h.endswith(".eu"):
        return "European Union"
    if h.endswith(".oecd.org") or h == "oecd.org":
        return "OECD"
    if h.endswith(".oas.org") or h == "oas.org":
        return "International"
    if h.endswith(".senate.gov") or h.endswith(".house.gov") or h in {
        "congress.gov",
        "govinfo.gov",
    }:
        return "United States"
    if h.endswith(".futureoflife.org") or h == "futureoflife.org":
        return "United States"
    if h.endswith(".ainowinstitute.org") or h == "ainowinstitute.org":
        return "United States"
    if h.endswith(".itic.org") or h == "itic.org":
        return "United States"
    if h.endswith(".go.kr") or h.endswith(".or.kr") or h.endswith(".kr"):
        return "South Korea"
    if h in {"globalpolicy.ai"}:
        return "International"
    if h.endswith("aihubfordevelopment.org"):
        return "International"
    return ""


def jurisdiction_from_item_urls(item: dict) -> str:
    urls: list[str] = []
    urls.extend(candidate_originals(item))
    urls.extend(as_url_list(item.get("source_urls")))
    for key in ("page_url", "canonical_url"):
        u = item.get(key) or ""
        if u:
            urls.append(u)
    for h in item.get("history") or []:
        if isinstance(h, dict) and h.get("url"):
            urls.append(str(h["url"]))
    seen: set[str] = set()
    for u in urls:
        if not is_http_url(u) or is_curator_url(u):
            continue
        key = normalize_url(u) or u
        if key in seen:
            continue
        seen.add(key)
        hit = jurisdiction_from_host(host_of(u))
        if hit:
            return hit
    return ""


def identifying_fragment(fragment: str) -> str:
    """Keep fragments that distinguish documents (ISO OBP 등). 본문 위치 조각은 버린다."""
    frag = (fragment or "").strip()
    if not frag or frag.startswith(":~:text"):
        return ""
    if frag.lower().startswith("iso:std"):
        return frag
    if "coeidentifier" in frag.lower():
        return frag
    return ""


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
    q = [
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=True)
        if k.lower() not in {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}
    ]
    query = urlencode(q, doseq=True)
    fragment = identifying_fragment(p.fragment or "")
    return urlunparse((scheme, netloc, path, "", query, fragment))


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


def pick_canonical(item: dict, skip_normalized: set[str] | None = None) -> str:
    skip = skip_normalized or set()
    cands = candidate_originals(item)
    for u in cands:
        nu = normalize_url(u)
        if nu and nu not in skip:
            return u
    page = (item.get("page_url") or "").strip()
    if page and is_http_url(page) and not is_bad_original(page):
        return page
    return cands[0] if cands else ""


def pick_group_canonical(
    members: list[dict], skip_normalized: set[str] | None = None
) -> str:
    """Prefer a real original over a curator page, and a host that matches the title."""
    skip = skip_normalized or set()
    blob = " ".join(
        str(m.get(k) or "")
        for m in members
        for k in ("title", "org", "original_name", "document_name")
    ).lower()
    blob_compact = re.sub(r"[^a-z0-9가-힣]+", "", blob)
    scored: dict[str, tuple[int, str]] = {}
    curator_fallback = ""
    for m in members:
        urls = list(candidate_originals(m))
        page = (m.get("page_url") or "").strip()
        if page and is_http_url(page) and not is_bad_original(page):
            urls.append(page)
        for u in urls:
            nu = normalize_url(u)
            if not nu or nu in skip:
                continue
            if is_curator_url(u):
                if not curator_fallback:
                    curator_fallback = u
                continue
            host = host_of(u)
            if host.startswith("www."):
                host = host[4:]
            head = (host.split(".")[0] if host else "").lower()
            score = 5 if head and len(head) >= 4 and head in blob_compact else 0
            if re.search(r"\.pdf(?:$|[?#])", u, re.I):
                score -= 1
            if "utm_source=" in u.lower():
                score -= 1
            prev = scored.get(nu)
            if prev is None or score > prev[0]:
                scored[nu] = (score, u)
    if scored:
        ranked = sorted(scored.values(), key=lambda x: -x[0])
        return ranked[0][1]
    return curator_fallback


def legislation_family_key(url: str) -> str:
    """Same statute, different HTML/PDF/뷰어면 한 키로 묶는다."""
    if not is_http_url(url):
        return ""
    try:
        p = urlparse(url.strip())
    except Exception:
        return ""
    host = (p.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = p.path or ""
    if host == "legislation.gov.uk":
        m = re.match(
            r"^/(uksi|ukpga|ukla|asc|anaw|nia|ssi|wsi)/(\d+)/([^/]+)",
            path,
            re.I,
        )
        if m:
            return f"ukleg:{m.group(1).lower()}:{m.group(2)}:{m.group(3).lower()}"
    if host.endswith("legislature.ca.gov"):
        q = dict(parse_qsl(p.query))
        bid = (q.get("bill_id") or "").strip()
        if bid:
            return f"calib:{bid.lower()}"
    if host in {"congress.gov", "www.congress.gov"}:
        m = re.search(
            r"/bill/(\d+)(?:st|nd|rd|th)-congress/(house-bill|senate-bill)/(\d+)",
            path,
            re.I,
        )
        if m:
            return f"uscong:{m.group(1)}:{m.group(2).lower()}:{m.group(3)}"
    return ""


def congress_bill_label(url: str) -> str:
    """congress.gov 주소에서 HR 1692 / S 5109 같은 짧은 표시."""
    if not url:
        return ""
    m = re.search(
        r"/bill/(\d+)(?:st|nd|rd|th)-congress/(house-bill|senate-bill)/(\d+)",
        url,
        re.I,
    )
    if not m:
        return ""
    chamber = "HR" if "house" in m.group(2).lower() else "S"
    return f"{chamber} {m.group(3)}"


def item_legislation_family(item: dict) -> str:
    urls = list(candidate_originals(item))
    page = (item.get("page_url") or "").strip()
    if page:
        urls.append(page)
    for u in urls:
        k = legislation_family_key(u)
        if k:
            return k
    return ""


_REV_MARK = re.compile(r"_(\d{6})개정")


def apply_revision_labels(docs: list[dict]) -> int:
    """한·영을 합친 뒤에도 YYYY-MM 개정 표시는 제목에 남긴다."""
    n = 0
    for d in docs:
        blob = " ".join(
            [str(d.get("original_name") or "")]
            + [
                str(h.get("title") or "")
                for h in (d.get("history") or [])
                if isinstance(h, dict)
            ]
        )
        m = _REV_MARK.search(blob)
        if not m:
            continue
        sn = (d.get("short_name") or d.get("title") or "").strip()
        yy, mo = m.group(1)[:2], m.group(1)[2:4]
        label = f"20{yy}-{mo} 개정"
        if label in sn:
            continue
        base = re.sub(r"\s*[\(（](?:한글본|영문본)[\)）]\s*$", "", sn).strip()
        new = f"{base} ({label})"
        d["short_name"] = new
        d["title"] = new
        n += 1
    return n


def polish_short_names(docs: list[dict]) -> int:
    """한·영이 섞인 약칭에서 남은 영어 연결어를 정리한다."""
    n = 0
    for d in docs:
        sn = (d.get("short_name") or "").strip()
        if not sn or not re.search(r"[가-힣]", sn):
            continue
        new = _polish_mixed_title(sn)
        if new == sn:
            continue
        d["short_name"] = new
        if (d.get("title") or "").strip() == sn:
            d["title"] = new
        n += 1
    return n


def disambiguate_duplicate_short_names(docs: list[dict]) -> int:
    """같은 약칭이 다른 법안·주체이면 번호나 기관을 붙여 구분한다."""
    by: dict[str, list[dict]] = defaultdict(list)
    for d in docs:
        if not d.get("in_scope"):
            continue
        sn = (d.get("short_name") or "").strip()
        if sn:
            by[sn].append(d)
    n = 0
    for sn, group in by.items():
        if len(group) < 2:
            continue
        labels: list[str] = []
        for d in group:
            urls = [d.get("canonical_url") or ""]
            for h in d.get("history") or []:
                if isinstance(h, dict):
                    urls.append(h.get("url") or "")
            lab = ""
            for u in urls:
                lab = congress_bill_label(u)
                if lab:
                    break
            labels.append(lab)
        if all(labels) and len(set(labels)) == len(group):
            for d, lab in zip(group, labels):
                if re.search(rf"\b{re.escape(lab)}\b", d.get("short_name") or ""):
                    continue
                new = f"{sn} ({lab})"
                d["short_name"] = new
                d["title"] = new
                n += 1
            continue
        if sn != "AI 윤리 원칙":
            continue
        orgs = [(d.get("org") or "").strip() for d in group]
        if all(orgs) and len(set(orgs)) == len(group):
            for d, org in zip(group, orgs):
                new = f"{org} AI 윤리 원칙"
                d["short_name"] = new
                d["title"] = new
                n += 1
    return n


# 한·영 혼용 약칭에서 번역 잔여 영어. 고유명(Privacy Act, BridgeAI 등)은 건드리지 않는다.
_POLISH_SUBS: list[tuple[str, str]] = [
    (r"\(Relative\s+", "("),
    (r"(?i)(?<=\d)Relative(?:\s+to(?:\s+the)?)?\s*", " "),
    (r"(?i)\bRelative(?:\s+to(?:\s+the)?)?\s+", " "),
    (r"(?i)(\b(?:ACR|SCR)\s+\d+)\s+\d+\s+(Asilomar)", r"\1 \2"),
    (r"(?i)Inter-American\s+", "미주 "),
    (r"\bData\s+거버넌스", "데이터 거버넌스"),
    (r"\bReporting\b", "보고"),
    (r"\bHealth\s+시스템", "보건 시스템"),
    (r"\bCivil\s+Rights\b", "시민권"),
    (r"(?i)Information\s+기술", "정보기술"),
    (r"(?i)Management\s+시스템", "경영시스템"),
    (r"(?i)Data\s+\(\s*Use\s*·\s*Access\s*\)", "데이터 (이용·접근)"),
    (
        r"(?i)Digital\s+Markets,\s*Competition\s*·\s*Consumers",
        "디지털 시장·경쟁·소비자",
    ),
    (
        r"(?i)법\s+Promotion\s+Research,\s*Development,\s*·\s*Utilization\s+"
        r"인공\s+Intelligence-Related\s+기술",
        "AI 관련 기술 연구·개발·활용 촉진법",
    ),
    (r"(?i)Criminal\s+Code", "형법"),
    (r"(?i)Voluntary\s+(행동규범|행동 규범)", r"자율 \1"),
    (r"책임 있는 Use", "책임 있는 활용"),
    (r"(?i)New\s+Generation", "신세대"),
    (r"(?i)Defense\s+Authorization\s+법", "국방수권법"),
    (r"(?i)Fiscal\s+Year", "회계연도"),
    (r"(?i)Wisdom\s+Innovative\s+Small\s+Enterprises", "혁신 소기업"),
    (r"(?i)Resources\s+Evaluating\s*·\s*Documenting", "평가·문서화 자원"),
    (r"(?i)AI\s+의료\s+Efficiency", "AI 의료 효율"),
    (r"(?i)\bEfficiency\b", "효율"),
    (r"(?i)\bReadiness\b", "대비"),
    (r"(?i)Personal\s+개인", "개인"),
    (r"(?i)Protection\s+Personal\s+Data\s+Use", "개인정보 보호·활용"),
    (r"(?i)\bPromotion\s+사무소", "촉진 사무소"),
    (r"(?i)Open\s+Data\s+Regulations", "공개데이터 규정"),
    (r"(?i)Data\s+Classification\s+Regulations", "데이터 분류 규정"),
    (r"(?i)Freedom\s+(?:of\s+)?Information\s+Regulations", "정보공개 규정"),
    (
        r"(?i)전략 Digital Development Innovation Activity Ukraine until 2030",
        "우크라이나 혁신활동 디지털 발전 전략(2030)",
    ),
    (
        r"(?i)Institute(?: of)? Public Administration \(IPA\) Initiatives",
        "공공행정연구소(IPA) 이니셔티브",
    ),
    (
        r"(?i)프로그램 Support Applied Research Ministry Agriculture period 2024\s*[–-]\s*2032",
        "농림부 응용연구 지원 프로그램(2024–2032)",
    ),
    (
        r"(?i)Assignment Swedish Agency Digital Government · Swedish Authority Privacy Protection develop 가이드라인 use generative 인공지능 public administration",
        "생성형 AI 공공행정 활용 가이드라인 마련 과제(스웨덴 디지털정부청·개인정보보호청)",
    ),
    (r"(?i)world-class AI Research · Educational Institute", "세계적 AI 연구·교육 기관"),
    (r"(?i)Research Institute Development Digital 기술", "디지털 기술 개발 연구소"),
    (
        r"(?i)Public Call Applications Support AI Implementation Projects Government",
        "정부 AI 도입 사업 지원 공모",
    ),
    (
        r"(?i)법 No\.\s*9943 Creation 국가 Digital Government Agency",
        "법 제9943호 국가 디지털정부 기구 설치",
    ),
    (
        r"(?i)행정명령 Promoting Use 신뢰할 수 있는 AI 연방 Government",
        "신뢰할 수 있는 AI 연방정부 활용 촉진 행정명령",
    ),
    (
        r"(?i)Creation High-Level Commission Digital Government Bicentennial",
        "디지털정부 고위급 위원회(200주년) 설치",
    ),
    (
        r"(?i)이사회 Information · Communication 기술 Public Administration",
        "공공행정 정보통신기술 이사회",
    ),
    (r"(?i)Leveraging 인공지능 Streamline Code 연방 Regulations 법", "연방법규 간소화 AI 활용법"),
    (
        r"(?i)인공지능 Research, Innovation, · 책무성 법",
        "인공지능 연구·혁신·책무성 법",
    ),
    (
        r"(?i)전략 Public Health Preparedness · Response 인공지능 Threats",
        "인공지능 위협 공중보건 대비·대응 전략",
    ),
    (r"(?i)Closing Loopholes Overseas Use · Development 인공지능 법", "해외 AI 활용·개발 허점 차단법"),
    (r"(?i)AI 전략 Digital Government", "디지털정부 AI 전략"),
    (r"(?i)Digital Government", "디지털정부"),
    (r"(?i)Public Administration", "공공행정"),
    (r"(?i)Precision Agriculture", "정밀농업"),
    (r"(?i)Supporting Innovation Agriculture 법", "농업 혁신 지원법"),
    (r"(?i)Promoting\s+(정밀농업|책임)", r"촉진 \1"),
    (r"(?i)Promoting\s+Use", "활용 촉진"),
    (r"(?i)Public Health", "공중보건"),
    (r"(?i)Federal Government", "연방정부"),
    (r"(?i)Federal Regulations", "연방법규"),
    (r"(?i)Financial Services", "금융서비스"),
    (r"(?i)Small Business", "소기업"),
    (r"(?i)\bElections\b", "선거"),
    (
        r"(?i)European Digital Innovation Hubs",
        "유럽 디지털 혁신 허브",
    ),
    (r"(?i)Unleashing AI Innovation 금융서비스 법", "금융서비스 AI 혁신 촉진법"),
    (
        r"(?i)Fraudulent 인공지능 Regulations \(FAIR\) 선거 법",
        "허위 AI 규제(FAIR) 선거법",
    ),
    (
        r"(?i)촉진 책임 있는 Evaluation · 조달 Advance 대비 Enterprise-wide Deployment 인공지능 법",
        "책임 있는 평가·조달·전사 도입 대비 인공지능법",
    ),
    (
        r"(?i)인공지능 Allied Collaboration Crucial Operations, Research, · Development 법",
        "동맹 핵심 작전·연구·개발 AI 협력법",
    ),
    (r"(?i)Promoting Digital Privacy 기술 법", "디지털 프라이버시 기술 촉진법"),
    (
        r"(?i)Ensuring Safe · 윤리 AI Development Through SAFE AI Research Grants",
        "SAFE AI 연구지원을 통한 안전·윤리 개발 보장",
    ),
    (
        r"(?i)Tornado Observations Research · 통지 평가 Development Operations 법",
        "토네이도 관측 연구·통지·평가·개발 운용법",
    ),
    (r"\s*\(Subnational:[^)]*\)", ""),
    (
        r"(?i)Joint AI plan safe · effective use AI Norwegian health · care services 2024[–-]2025",
        "보건·돌봄 AI 안전·효과적 활용 공동계획(2024–2025)",
    ),
    (
        r"(?i)가이드라인 User Age-verification · 책임 있는 Dialogue 법",
        "이용자 연령확인·책임 있는 대화 가이드라인 법",
    ),
    (
        r"(?i)의료 Professions: Deceptive Terms or Letters: 인공지능",
        "의료 직역: 기만적 명칭·약어: 인공지능",
    ),
    (
        r"(?i)Tampere Pulse – AI-Driven Visitor Flow Forecasting Smarter Urban Decision-Making",
        "Tampere Pulse – 스마트 도시 의사결정을 위한 방문객 흐름 예측",
    ),
    (r"(?i)Digital Transformation Bulgaria 전략", "불가리아 디지털 전환 전략"),
    (r"(?i)Cloud 전략 Flemish Administration", "플란데런 행정 클라우드 전략"),
    (
        r"(?i)신뢰할 수 있는 Facial Recognition Applications · Protections Plan",
        "신뢰할 수 있는 얼굴인식 적용·보호 계획",
    ),
    (
        r"(?i)Towards AI 전략 Mexico: Harnessing AI Revolution",
        "멕시코 AI 전략을 향하여: AI 혁명 활용",
    ),
    (
        r'(?i)Strategic Approach 인공지능 [“"]?\s*more robust foundation 책임 있는 development · use AI Denmark"?',
        "덴마크 책임 있는 AI 개발·활용을 위한 전략적 접근",
    ),
    (
        r"(?i)Special Secretariat Foresight Presidency Government",
        "총리실 미래전망 특별사무국",
    ),
    (
        r"(?i)Regulating Public Mas Media 관련 AI Generated Content",
        "AI 생성 콘텐츠 관련 공영미디어 규제",
    ),
    (
        r"(?i)Protecting U\.S\. Advantage AI · Related Critical 기술",
        "AI·관련 핵심기술 미국 우위 보호",
    ),
    (
        r"(?i)Plan 연방 Engagement Developing Technical 표준 · Related Tools",
        "기술표준·관련 도구 개발을 위한 연방 참여 계획",
    ),
    (
        r"(?i)국가 Bioethics · Techno-ethics 위원회 \(Substitue 국가 Bioethics 위원회\)",
        "국가 생명윤리·기술윤리 위원회",
    ),
    (
        r"(?i)양해각서 Heads Agencies Regulatory · Non-Regulatory Approaches AI",
        "규제·비규제 AI 접근에 관한 기관장 양해각서",
    ),
    (
        r"(?i)Legal Opinion: Uses Copyrighted Materials 머신러닝",
        "머신러닝에서 저작권 자료 이용에 관한 법률의견",
    ),
    (
        r"(?i)법 31814, 법 that promotes use 인공지능 favor economic · social development country",
        "법 제31814호 경제·사회 발전을 위한 인공지능 활용 촉진법",
    ),
    (
        r"(?i)거버넌스 Innovation: Redesigning 법 · Architecture Society 5\.0",
        "거버넌스 혁신: Society 5.0을 위한 법·아키텍처 재설계",
    ),
    (r"(?i)Contract 가이드라인 Utilizing AI · Data", "AI·데이터 활용 계약 가이드라인"),
    (r"(?i)Government by 알고리즘: AI 연방 Administrative Agencies", "알고리즘에 의한 정부: 연방 행정기관의 AI"),
    (r"(?i)Next Generation Pipelines 연구개발 법", "차세대 파이프라인 연구개발법"),
    (
        r"(?i)Critical infrastructure: 인공지능 시스템: human oversight",
        "핵심기반시설: 인공지능 시스템: 인간 감독",
    ),
    (
        r"(?i)Strengthening 인공지능 Normalization · Diffusion By Oversight · eXperimentation 법",
        "인공지능 정상화·확산 강화(감독·실험) 법",
    ),
    (r"(?i)국가 Cloud Infrastructure", "국가 클라우드 인프라"),
    (r"(?i)국가 Big Data Observatory", "국가 빅데이터 관측소"),
    (r"(?i)Medical Research Future Fund", "의료연구미래기금"),
    (r"(?i)Expert Group 보고서", "전문가그룹 보고서"),
    (r"(?i)국가 AI Portal", "국가 AI 포털"),
    (r"(?i)Hellenic 국가 Bioethics Commission", "그리스 국가 생명윤리위원회"),
    (r"(?i)Facial Recognition", "얼굴인식"),
    (r"(?i)Digital Transformation", "디지털 전환"),
    (r"(?i)High Performance Computing", "고성능컴퓨팅"),
    (r"(?i)human oversight", "인간 감독"),
    (r"(?i)AI Generated Content", "AI 생성 콘텐츠"),
    (
        r"(?i)VELES - Smart Excellence Hub Southeastern Europe - Regional Smart Data Space",
        "VELES – 동남유럽 스마트 우수거점·지역 스마트 데이터 공간",
    ),
    (
        r"(?i)Technological sandbox use exponential 기술 selection procedures contracting goods, services, · execution works, scala",
        "지수함수적 기술을 활용한 재화·용역·공사 계약 선정절차 기술 샌드박스",
    ),
    (r"(?i)NSF Funding Opportunities with Special Emphasis AI", "NSF AI 중점 연구지원 공모"),
    (
        r"(?i)Establishing Local AI & HPC Compute Infrastrcuture",
        "지역 AI·HPC 컴퓨팅 인프라 구축",
    ),
    (r"(?i)Emerging Digital 기술 Kenya - Exploration · Analysis", "케냐 신흥 디지털 기술 탐색·분석"),
    (
        r"(?i)Calls 고성능컴퓨팅 R&D projects: 인공지능 cloud collaboration with Google",
        "고성능컴퓨팅 R&D 과제 공모: 구글 협력 클라우드 인공지능",
    ),
    (r"(?i)American Workforce 정책 Advisory Board", "미국 인력정책 자문위원회"),
    (r"(?i)AI subject curricula: 인공지능 - From Theory Practice", "AI 교과과정: 이론에서 실습으로"),
    (r"(?i)Promoting Resilient Supply Chains 법", "회복력 있는 공급망 촉진법"),
    (r"(?i)Modernizing Data Practices Improve Government 법", "정부 개선을 위한 데이터 관행 현대화법"),
    (r"(?i)Preparing Election Administrators AI 법", "선거관리자 AI 대비법"),
    (r"(?i)Emerging Innovative Border 기술 법", "신흥 혁신 국경 기술법"),
    (r"(?i)Safe · 보안 Innovation Frontier 인공지능 모델 법", "프론티어 AI 모델 안전·보안 혁신법"),
    (r"(?i)Protecting Consumers from Deceptive AI 법", "기만적 AI로부터 소비자 보호법"),
    (r"(?i)Protect(?:ing)? 선거 from Deceptive AI 법", "기만적 AI로부터 선거 보호법"),
    (r"(?i)Securing 선거 From AI Deception 법", "AI 기만으로부터 선거 보호법"),
    (r"(?i)Leading 윤리 AI Development \(LEAD\) Kids 법", "아동 윤리 AI 개발(LEAD) 법"),
    (r"(?i)Health Tech Investment 법", "헬스테크 투자법"),
    (r"(?i)Next Generation Military 교육 법", "차세대 군사교육법"),
    (r"(?i)TAME Extreme Weather · Wildfires 법", "극한기상·산불 TAME 법"),
    (r"(?i)Protect Victims Digital Exploitation · Manipulation 법", "디지털 착취·조작 피해자 보호법"),
    (r"(?i)Duplicative Grant Consolidation 법", "중복 보조금 통합법"),
    (r"(?i)Decoupling America's 인공지능 Capabilities from 중국 법", "대중국 미국 AI 역량 디커플링법"),
    (r"(?i)Improving Diagnosis Medicine 법", "의학 진단 개선법"),
    (r"(?i)Digital Content Provenance 표준", "디지털 콘텐츠 출처 표준"),
    (r"(?i)Public contracts: automated decision 시스템", "공공계약: 자동화된 의사결정 시스템"),
    (r"(?i)방지 알고리즘 Price Fixing 법: 금지 Certain Price-Setting 알고리즘 Uses", "알고리즘 가격담합 방지법: 특정 가격설정 알고리즘 사용 금지"),
    (r"(?i)Advancing Digital Freedom 법", "디지털 자유 진흥법"),
    (r"(?i)Protecting Our Children AI World 법", "AI 시대 아동 보호법"),
    (r"(?i)Comment Integrity · Management 법", "의견 무결성·관리법"),
    (r"(?i)Civilian Agency AI Watermark 법", "연방 민간기관 AI 워터마크법"),
    (r"(?i)Digital Social Platform 투명성 법", "디지털 소셜 플랫폼 투명성법"),
    (r"(?i)Living Wage Musicians 법", "음악인 생활임금법"),
    (r"(?i)Protect Working Musicians 법", "현업 음악인 보호법"),
    (r"(?i)Stop Spying Bosses 법", "직장 감시 금지법"),
    (r"(?i)Candidate Voice Fraud 금지 법", "후보자 음성 사기 금지법"),
    (r"(?i)Supercomputing Safer Chemicals 법", "더 안전한 화학물질을 위한 슈퍼컴퓨팅법"),
    (r"(?i)Digital Platform Commission 법", "디지털 플랫폼 위원회법"),
    (r"(?i)Stop Spying Bosses 법", "직장 감시 금지법"),
    (r"(?i)(\bH\s*\d+)(?=[가-힣A-Z])", r"\1 "),
    (r",?\s*·\s*other purposes\.?", ""),
    (r"샌드박스ble manner members\s*", "샌드박스 "),
    (r"(?i)\s+reliably members\s*", " "),
    (r"(?i)\s+is provided continuously Members\s*", " "),
    (r"(?i),\s*with emphasis public(?:\s*·\s*private)? sectors.*", ""),
    (r"(?i),\s*with emphasis public entities at three levels government.*", ""),
]


def _polish_mixed_title(sn: str) -> str:
    new = sn
    for pat, repl in _POLISH_SUBS:
        new = re.sub(pat, repl, new)
    new = re.sub(r"(?i)(\bHR\s*\d+)(?=[가-힣A-Z])", r"\1 ", new)
    new = re.sub(r"(?i)(\bS\s*\d+)(?=[가-힣A-Z])", r"\1 ", new)
    new = re.sub(r"\s*\(Subnational:[^)]*\)", "", new)
    new = re.sub(r"\s+", " ", new).strip()
    new = re.sub(r"\s+,", ",", new)
    return new


_TITLE_STOP = {
    "the", "and", "of", "for", "on", "in", "to", "a", "an", "ai",
    "인공지능", "artificial", "intelligence",
}


def title_tokens(text: str) -> set[str]:
    folded = re.sub(r"[^a-z0-9가-힣]+", " ", (text or "").lower())
    return {w for w in folded.split() if w not in _TITLE_STOP and len(w) > 1}


def titles_look_same_instrument(a: str, b: str) -> bool:
    ta, tb = title_tokens(a), title_tokens(b)
    if not ta or not tb:
        return False
    if ta <= tb or tb <= ta:
        return True
    return len(ta & tb) / len(ta | tb) >= 0.5


def url_owners_should_merge(items: list[dict]) -> bool:
    """같은 랜딩 URL을 쓰는 항목이 한 문서인지."""
    if len(items) <= 1:
        return True
    titles = [(it.get("title") or it.get("document_name") or "") for it in items]
    base = titles[0]
    return all(titles_look_same_instrument(base, t) for t in titles[1:])


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
    "WHO": "WHO",
    "ILO": "ILO",
    "WIPO": "WIPO",
    "APEC": "APEC",
    "World Economic Forum": "WEF",
    "International": "다자",
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
    if not country:
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
    r"국가기술표준원|국가사이버안보센터|국가인권위원회|국회입법조사처|"
    r"국민권익위원회|인터넷신문윤리위원회|경기도교육청|"
    r"세종대학교|중앙대학교|국민대학교|정보통신정책연구원|"
    r"NC문화재단|"
    r"\bNIA\b|\bKISA\b|\bKISDI\b|\bKAIEA\b|\bIAAE\b|\bETRI\b|\bKBS\b|\bKAIST\b|"
    r"소프트웨어야놀자|아름다운인터넷세상|\bAI4SCHOOL\b|"
    r"교육부|보건복지부",
    re.I,
)

_ORG_JURISDICTION_EXTRA: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"교황청|holy see|\bvatican\b", re.I), "Vatican City"),
    (re.compile(r"몬트리올대학교|université de montréal", re.I), "Canada"),
    (re.compile(r"스탠포드|stanford", re.I), "United States"),
    (re.compile(r"헬싱키대학교|university of helsinki", re.I), "Finland"),
    (re.compile(r"앨런튜링|turing institute", re.I), "United Kingdom"),
    (re.compile(r"베이징지원인공지능|\bbaai\b", re.I), "China"),
    (re.compile(r"berkman klein", re.I), "United States"),
    (re.compile(r"future of life|futureoflife", re.I), "United States"),
    (re.compile(r"ai now institute", re.I), "United States"),
    (re.compile(r"(?<![A-Za-z])ITI(?![A-Za-z])", re.I), "United States"),
]

_MULTILATERAL_TITLE = re.compile(
    r"santo domingo declaration|cartagena de indias|"
    r"declaration of santiago|declaraci[oó]n de santiago|"
    r"montevideo declaration|"
    r"산토도밍고|카르타헤나 데 인디아스|"
    r"산티아고 선언|몬테비데오 선언|"
    r"arab strategy regarding artificial|아랍 인공지능 전략|"
    r"latin america and the caribbean|"
    r"\bfair lac\b|\bfairlac\b|"
    r"\bmigdia\b|inter-american framework.{0,80}data governance|"
    r"미주 데이터 거버넌스",
    re.I,
)


def multilateral_jurisdiction(blob: str) -> str:
    if not blob:
        return ""
    if re.search(
        r"independent international scientific panel on ai|"
        r"독립 국제 AI 과학 패널",
        blob,
        re.I,
    ):
        return "United Nations"
    if re.search(r"beijing ai principles|베이징 AI 원칙", blob, re.I):
        return "China"
    if re.search(
        r"\bedpb\b|edpb_opinion|"
        r"opinion 28/2024.{0,80}(ai models|data protection)|"
        r"AI 모델 관련.{0,40}의견 28/2024",
        blob,
        re.I,
    ):
        return "European Union"
    if _MULTILATERAL_TITLE.search(blob):
        return "International"
    return ""


def known_instrument_match(*texts: str) -> tuple[str, str]:
    """Known same-instrument fingerprints → (jurisdiction, group_key)."""
    blob = " ".join(str(t or "") for t in texts)
    if not blob.strip():
        return "", ""
    for pat, jur, key in _KNOWN_INSTRUMENTS:
        if not pat.search(blob):
            continue
        if key == "kr-ai-safety-guideline" and blob.count("가이드라인") >= 2:
            continue
        if key == "cn-sti-ethics-opinions-2022" and re.search(
            r"draft for feedback|초안", blob, re.I
        ):
            continue
        if key == "cn-tc260-genai-safety-2024" and re.search(
            r"45654|draft for feedback|초안", blob, re.I
        ):
            continue
        if key == "g7-hiroshima-code-of-conduct" and re.search(
            r"보고 프레임워크|reporting framework|guiding principles", blob, re.I
        ):
            continue
        if key == "eu-gpai-code-of-practice" and re.search(
            r"생성 콘텐츠|ai-generated content|cyber security of ai|"
            r"automated driving|generative ai – code of practice|"
            r"canadian guardrails",
            blob,
            re.I,
        ):
            continue
        return jur, key
    return "", ""


def known_instrument_group_key(*texts: str) -> str:
    return known_instrument_match(*texts)[1]


def _scan_needles(text: str, needles: list[tuple[str, str]]) -> list[str]:
    """Non-overlapping hits; longer needles first. ASCII uses word boundaries."""
    if not text:
        return []
    occupied = [False] * len(text)
    lower = text.lower()
    found: list[str] = []
    for needle, canon in needles:
        if not needle:
            continue
        nlow = needle.lower()
        start = 0
        nlen = len(needle)
        while True:
            i = lower.find(nlow, start)
            if i < 0:
                break
            j = i + nlen
            if j > len(occupied) or any(occupied[i:j]):
                start = i + 1
                continue
            if needle.isascii() and re.fullmatch(r"[A-Za-z0-9 .'-]+", needle):
                if i > 0 and text[i - 1].isalpha():
                    start = i + 1
                    continue
                if j < len(text) and text[j].isalpha():
                    start = i + 1
                    continue
            found.append(canon)
            for k in range(i, min(j, len(occupied))):
                occupied[k] = True
            start = j
    out: list[str] = []
    for c in found:
        if c not in out:
            out.append(c)
    return out


def _jurisdiction_needles() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(needle: str, canon: str) -> None:
        key = needle.lower()
        if not needle or key in seen:
            return
        seen.add(key)
        pairs.append((needle, canon))

    for name in ORG_FLAGS:
        add(name, name)
    for alias, canon in ORG_ALIASES.items():
        # 한글 별칭은 2글자(유엔·유럽)도 쓴다. ASCII는 3글자 이상.
        if len(alias) >= 3 or not alias.isascii():
            add(alias, canon)
    for ko, en in TITLE_COUNTRY.items():
        add(ko, en)
    for name in _ISO:
        add(name, name)
    for alias, canon in _COUNTRY_ALIASES.items():
        if len(alias) >= 4:
            add(alias, canon)
    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    return pairs


_JURISDICTION_NEEDLES: list[tuple[str, str]] | None = None


def countries_in_text(text: str) -> list[str]:
    """Distinct countries/orgs mentioned in text, longest match first."""
    global _JURISDICTION_NEEDLES
    if _JURISDICTION_NEEDLES is None:
        _JURISDICTION_NEEDLES = _jurisdiction_needles()
    hits = _scan_needles(text, _JURISDICTION_NEEDLES)
    for pat, canon in _SHORT_ORG_TOKENS:
        if pat.search(text or "") and canon not in hits:
            hits.append(canon)
    return hits


def country_from_free_text(text: str) -> str:
    """Pick a country/org from free text (title body, org string)."""
    hits = countries_in_text(text)
    if not hits:
        return ""
    if len(hits) >= 2 and _TREATY_LIKE.search(text or ""):
        orgs = [c for c in hits if c in ORG_FLAGS]
        real = [c for c in hits if c not in ORG_FLAGS and c != "International"]
        if len(real) >= 2:
            return "International"
        if orgs and not real:
            return orgs[0]
    return hits[0]


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


def jurisdiction_from_org(org: str) -> str:
    """Map an issuing-body string to a country or flagged org."""
    if not org:
        return ""
    raw = unicodedata.normalize("NFKC", str(org)).strip()
    if not raw or _SKIP_JURISDICTION_ORG.search(raw):
        return ""
    if _KR_ORG_RE.search(raw):
        return "South Korea"
    for pat, jur in _ORG_JURISDICTION_EXTRA:
        if pat.search(raw):
            return jur
    if re.search(r"library of congress|united states congress|\bu\.s\.\s+congress\b", raw, re.I):
        return "United States"
    head = re.split(r"[|/]", raw)[0].strip()
    folded = re.sub(r"\s+", " ", head.lower())
    if folded in _SUBNAT_GOV_COUNTRY:
        return _SUBNAT_GOV_COUNTRY[folded]
    hit = resolve_org_or_country(head)
    if hit:
        return hit
    try:
        from issuer_levels import _US_STATE_ORG

        if _US_STATE_ORG.match(head):
            return "United States"
    except Exception:
        pass
    m = re.match(r"^(?:the\s+)?government of (?:the\s+)?(.+)$", head, re.I)
    if m:
        rest = re.sub(r"\s+", " ", m.group(1).strip())
        rest_l = rest.lower()
        if rest_l in _SUBNAT_GOV_COUNTRY:
            return _SUBNAT_GOV_COUNTRY[rest_l]
        hit = resolve_org_or_country(rest)
        if hit:
            return hit
        rest2 = re.sub(r"^(?:the\s+)?republic of\s+", "", rest, flags=re.I).strip()
        hit = resolve_org_or_country(rest2)
        if hit:
            return hit
    return country_from_free_text(head)


def _explicit_item_country(item: dict) -> str:
    for key in ("country", "gaiin_country", "country_name"):
        val = item.get(key)
        if isinstance(val, dict):
            val = val.get("name") or val.get("slug") or ""
        if val:
            return canonicalize_country_name(str(val))
    return ""


def country_from_item(item: dict) -> str:
    col = item.get("collection") or ""
    title = item.get("title") or ""
    cat = item.get("category") or ""
    org = item.get("org") or ""
    original = item.get("original_name") or item.get("document_name") or ""
    blob = f"{title} {original} {org} {cat}"

    known, _ = known_instrument_match(title, original, org)
    if known:
        return known

    ml = multilateral_jurisdiction(blob)
    if ml:
        return ml

    if col == "lab-policies" or _SKIP_JURISDICTION_ORG.search(org):
        return ""

    mentioned = countries_in_text(f"{title} {original} {org}")
    real = [c for c in mentioned if c not in ORG_FLAGS and c != "International"]
    if len(real) >= 2 and _TREATY_LIKE.search(blob):
        return "International"

    explicit = _explicit_item_country(item)
    if explicit and explicit not in ("International",):
        return explicit

    c = jurisdiction_from_org(org)
    if c:
        return c

    c = jurisdiction_from_item_urls(item)
    if c:
        return c

    low = cat.lower()
    if "chinese" in low or (col == "agora" and "china" in low):
        return "China"
    if (
        "u.s." in low
        or "us federal" in low
        or "us state" in low
        or "united states" in low
    ):
        return "United States"

    c = country_from_title(title)
    if c:
        return c
    c = resolve_org_or_country(cat)
    if c:
        return c
    if _KR_ORG_RE.search(blob):
        return "South Korea"

    if "multinational" in low or org.strip().lower() in {
        "other multinational",
        "other authorities",
    }:
        c = country_from_free_text(blob)
        if c:
            return c
        return "International"

    if col == "mofa-governance":
        return "International"
    return ""


def choose_group_country(members: list[dict], extra_text: str = "") -> str:
    """Pick one jurisdiction for a merged document group."""
    blobs = [extra_text]
    for m in members:
        blobs.extend(
            [
                m.get("title") or "",
                m.get("org") or "",
                m.get("document_name") or "",
                m.get("original_name") or "",
            ]
        )
    blob = " ".join(blobs)
    known, _ = known_instrument_match(blob)
    if known:
        return known
    ml = multilateral_jurisdiction(blob)
    if ml:
        return ml

    hits: list[str] = []
    for m in members:
        c = country_from_item(m)
        if c and c not in hits:
            hits.append(c)
    real = [c for c in hits if c != "International" and c not in ORG_FLAGS]
    orgs = [c for c in hits if c in ORG_FLAGS]
    if len(real) >= 2:
        return "International"
    mentioned = [
        c
        for c in countries_in_text(blob)
        if c not in ORG_FLAGS and c != "International"
    ]
    if len(mentioned) >= 2 and _TREATY_LIKE.search(blob):
        return "International"
    if real:
        return real[0]
    if orgs:
        return orgs[0]
    for c in hits:
        if c:
            return c
    return country_from_free_text(blob)


def fill_missing_country(doc: dict) -> bool:
    """LLM 한국어 제목이 붙은 뒤에 빈 관할을 다시 채운다."""
    if (doc.get("country") or "").strip():
        return False
    org = doc.get("org") or ""
    if _SKIP_JURISDICTION_ORG.search(org):
        return False
    blob = " ".join(
        str(doc.get(k) or "")
        for k in ("title", "short_name", "full_name", "original_name", "org")
    )
    known, _ = known_instrument_match(blob)
    c = (
        known
        or multilateral_jurisdiction(blob)
        or jurisdiction_from_org(org)
        or jurisdiction_from_item_urls(doc)
        or country_from_title(doc.get("short_name") or doc.get("title") or "")
        or country_from_free_text(blob)
    )
    if not c:
        return False
    doc["country"] = c
    doc["country_ko"] = country_label_ko(c)
    doc["flag"] = flag_emoji(c)
    return True


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


def is_scrape_chrome(text: str) -> bool:
    """IAAE 상세 페이지 안내문·내비·깨진 HTML 조각. 문서 요약으로 쓰지 않는다."""
    s = (text or "").strip()
    if not s:
        return False
    if '"/>' in s or "자료출처" in s or "자료제목" in s:
        return True
    if re.search(r"자세한\s*내용은.{0,80}첨부", s):
        return True
    if s.startswith("연구 자료실") and "연합뉴스" in s:
        return True
    return False


def rebuild_collection_stats(data: dict) -> dict:
    items = data.get("items") or []
    data["count"] = len(items)
    data["categories"] = dict(Counter((r.get("category") or "기타")[:80] for r in items))
    data["years"] = dict(Counter((r.get("date") or "")[:4] for r in items if r.get("date")))
    return data
