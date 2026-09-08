#!/usr/bin/env python3
"""관할·병합·주체 휴리스틱 회귀. python3 scripts/test_library_consistency.py"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from issuer_levels import infer_issuer_level, _issuer_looks_subnational
from library_common import (
    as_url_list,
    congress_bill_label,
    country_from_item,
    disambiguate_duplicate_short_names,
    identifying_fragment,
    is_bad_original,
    jurisdiction_from_host,
    known_instrument_group_key,
    legislation_family_key,
    normalize_url,
    pick_group_canonical,
    polish_short_names,
    titles_look_same_instrument,
    url_owners_should_merge,
)


def ok(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"FAIL {msg}")
    print("OK", msg)


def test_urls() -> None:
    a = "https://www.iso.org/obp/ui/en/#iso:std:iso-iec:42001:ed-1:v1:en"
    b = "https://www.iso.org/obp/ui/en/#iso:std:iso-iec:23894:ed-1:v1:en"
    ok(identifying_fragment("iso:std:iso-iec:42001:ed-1:v1:en").startswith("iso:std"), "iso fragment")
    ok(normalize_url(a) != normalize_url(b), "ISO standards stay distinct")
    utm = "https://www8.cao.go.jp/cstp/ai/ai_plan/ai_plan.html?utm_source=chatgpt.com"
    clean = "https://www8.cao.go.jp/cstp/ai/ai_plan/ai_plan.html"
    ok(normalize_url(utm) == normalize_url(clean), "strip utm")


def test_known() -> None:
    ok(
        known_instrument_group_key(
            "Council of Europe Framework Convention on Artificial Intelligence"
        )
        == "coe-ai-framework-convention",
        "CoE convention key",
    )
    ok(known_instrument_group_key("HUDERIA methodology") == "coe-huderia", "HUDERIA")
    ok(
        known_instrument_group_key("ASEAN Guide on AI Governance and Ethics")
        == "asean-ai-governance-ethics",
        "ASEAN",
    )
    ok(known_instrument_group_key("人工知能基本計画") == "jp-ai-basic-plan", "Japan plan")
    ok(
        known_instrument_group_key(
            "Act on Promotion of Research, Development, and Utilization of Artificial Intelligence-Related Technologies"
        )
        == "jp-ai-rd-promotion-act",
        "Japan AI R&D promotion act",
    )
    ok(
        known_instrument_group_key("일본 AI 관련 기술 연구개발·활용 촉진법")
        == known_instrument_group_key("일본 · AI 관련 기술 연구·개발·활용 촉진법")
        == "jp-ai-rd-promotion-act",
        "Japan promotion act twins share key",
    )
    ok(
        known_instrument_group_key("Introduction to AI Assurance")
        == "uk-ai-assurance-intro",
        "UK AI assurance intro",
    )
    ok(
        known_instrument_group_key("영국 AI 보증 혁신 기금") == "",
        "UK assurance fund stays separate",
    )
    ok(
        known_instrument_group_key("Declaration on AI in the Nordic-Baltic Region")
        == "nordic-baltic-ai-declaration",
        "Nordic-Baltic declaration",
    )
    ok(
        known_instrument_group_key("에콰도르 SCE AI 도구 사용 감사 가이드라인")
        == "ec-sce-ai-audit-guide",
        "Ecuador SCE audit",
    )
    ok(
        known_instrument_group_key("에콰도르 SCE 생성형 AI 사용 가이드") == "",
        "Ecuador SCE genAI guide stays separate",
    )
    ok(known_instrument_group_key("デジタル経済パートナー십협정(DEPA)") == "depa", "DEPA")
    ok(known_instrument_group_key("Guidelines for AI Procurement") == "uk-ai-procurement", "UK procurement")
    ok(
        known_instrument_group_key("KAIEA 인공지능 윤리 헌장_191219개정 (한글본)")
        == "kaiea-charter-201912",
        "KAIEA Dec",
    )
    ok(
        known_instrument_group_key("KAIEA 인공지능 윤리 헌장 (한글본)")
        == "kaiea-charter-201910",
        "KAIEA Oct",
    )
    ok(known_instrument_group_key("The Bletchley Declaration") == "bletchley-declaration", "Bletchley")
    ok(
        known_instrument_group_key("Chair’s Summary of the AI Safety Summit 2023, Bletchley Park")
        == "",
        "Bletchley chairs summary stays separate",
    )
    ok(known_instrument_group_key("Seoul Declaration for safe, innovative and inclusive AI") == "seoul-declaration", "Seoul")
    ok(known_instrument_group_key("OpenAI Charter") == "openai-charter", "OpenAI charter")
    ok(
        known_instrument_group_key("[과학기술정보통신부] 인공지능 안전성 확보 가이드라인")
        == "kr-ai-safety-guideline",
        "KR safety guideline",
    )
    ok(
        known_instrument_group_key(
            "[과기부/NIA/TTA/ETRI] 고영향 인공지능 판단 가이드라인, 고영향 인공지능 사업자 책무 가이드라인, 인공지능 투명성 확보 가이드라인, 인공지능 안전성 확보 가이드라인"
        )
        == "",
        "four-guideline pack stays separate",
    )
    ok(
        known_instrument_group_key("Ethics Guidelines for AI") == "",
        "Thai ethics guidelines stay separate",
    )
    ok(
        known_instrument_group_key("City Leader’s Field Guide: Preparing for the AI-enabled citiverse")
        == "",
        "citiverse field guide stays separate",
    )
    ok(
        known_instrument_group_key(
            "Collaboration on Global Standards for the AI-Enabled Citiverse"
        )
        == "itu-ai-citiverse-standards",
        "citiverse standards",
    )
    ok(
        known_instrument_group_key("Guidance for AI Adoption: Implementation Guidance")
        == "au-ai-adoption-implementation",
        "Australia AI adoption guidance",
    )
    ok(
        known_instrument_group_key("Egypt National Artificial Intelligence Strategy") == "",
        "Egypt 2025 strategy is not a known-instrument merge",
    )
    ok(
        known_instrument_group_key(
            "Guiding Opinions on Strengthening the Governance of Science and Technology Ethics (Draft for Feedback)"
        )
        == "",
        "China ethics draft stays separate",
    )
    ok(
        known_instrument_group_key(
            "Opinions on Strengthening the Governance of Science and Technology Ethics"
        )
        == "cn-sti-ethics-opinions-2022",
        "China ethics opinions 2022",
    )
    ok(is_bad_original("https://openai.com/charter[자료제목]"), "scraped OpenAI URL")
    openai_canon = pick_group_canonical(
        [
            {
                "title": "[OpenAI] OpenAI 헌장",
                "collection": "iaae-ethics",
                "page_url": "https://iaae.ai/research/?bmode=view&idx=5253877",
                "source_urls": ["https://openai.com/charter[자료제목]", "https://ainowinstitute.org/x.pdf"],
            },
            {
                "title": "OpenAI Charter",
                "collection": "agora",
                "page_url": "https://openai.com/charter",
                "source_urls": ["https://openai.com/charter"],
            },
        ]
    )
    ok(openai_canon.startswith("https://openai.com/charter"), "OpenAI group uses openai.com")
    ok(
        known_instrument_group_key(
            "Hiroshima Process International Code of Conduct for Organizations Developing Advanced AI Systems"
        )
        == "g7-hiroshima-code-of-conduct",
        "Hiroshima CoC",
    )
    ok(
        known_instrument_group_key("히로시마 AI 프로세스 행동규범 보고 프레임워크")
        == "g7-hiroshima-reporting-framework",
        "Hiroshima reporting framework",
    )
    ok(
        known_instrument_group_key("히로시마 AI 프로세스 행동규범 보고 프레임워크")
        != known_instrument_group_key(
            "Hiroshima Process International Code of Conduct for Organizations Developing Advanced AI Systems"
        ),
        "reporting framework ≠ CoC",
    )
    ok(
        known_instrument_group_key("EU General-Purpose AI (GPAI) Code of Practice")
        == "eu-gpai-code-of-practice",
        "GPAI CoP",
    )
    ok(
        known_instrument_group_key("[EU] AI 생성 콘텐츠 투명성 실천규범") == "",
        "AI-generated content CoP stays separate",
    )
    ok(
        known_instrument_group_key("G7 Toolkit for Artificial Intelligence in the Public Sector")
        == "g7-public-sector-ai-toolkit",
        "G7 public sector toolkit",
    )
    ok(is_bad_original("http://futureoflife.org"), "FLI homepage")
    ok(is_bad_original("https://futureoflife.org/"), "FLI homepage slash")
    ok(
        not is_bad_original("https://futureoflife.org/open-letter/ai-principles/"),
        "FLI principles page is ok",
    )
    gpai_canon = pick_group_canonical(
        [
            {
                "title": "[EU] 범용 AI 실천규범",
                "collection": "mofa-country-policy",
                "page_url": "https://www.mofa.go.kr/www/brd/m_29692/view.do?seq=40",
                "source_urls": [
                    "https://digital-strategy.ec.europa.eu/en/policies/contents-code-gpai?utm_source=chatgpt.com"
                ],
            },
            {
                "title": "General Purpose AI Code of Practice, Transparency Chapter",
                "collection": "agora",
                "page_url": "https://digital-strategy.ec.europa.eu/en/policies/contents-code-gpai",
                "source_urls": [
                    "https://digital-strategy.ec.europa.eu/en/policies/contents-code-gpai"
                ],
            },
        ]
    )
    ok(
        "contents-code-gpai" in gpai_canon and "utm_" not in gpai_canon,
        "GPAI uses EC original",
    )
    toolkit_canon = pick_group_canonical(
        [
            {
                "title": "[G7] 공공부문 AI 활용 툴킷",
                "collection": "mofa-governance",
                "page_url": "https://www.mofa.go.kr/www/brd/m_29691/view.do?seq=123",
                "source_urls": [
                    "https://www.oecd.org/en/publications/g7-toolkit-for-artificial-intelligence-in-the-public-sector_421c1244-en.html"
                ],
            },
            {
                "title": "G7 Toolkit for Artificial Intelligence in the Public Sector",
                "collection": "oecd-navigator",
                "page_url": "https://oecd.ai/en/dashboards/policy-initiatives/g7-toolkit-for-artificial-intelligence-in-the-public-sector-6153",
                "source_urls": [
                    "https://api.oecdai.org/storage/policy-initiatives/Jul2025/fu_bnns4ktbg6j5xg3.pdf"
                ],
            },
        ]
    )
    ok("oecd.org/en/publications/g7-toolkit" in toolkit_canon, "toolkit uses oecd.org")
    cong_a = "https://www.congress.gov/bill/118th-congress/house-bill/1234"
    cong_b = "https://www.congress.gov/bill/118th-congress/house-bill/1234/text"
    ok(
        legislation_family_key(cong_a)
        == legislation_family_key(cong_b)
        == "uscong:118:house-bill:1234",
        "congress bill family",
    )
    polished = [{"short_name": "캘리포니아 SCR 17 (Relative 인공지능 2023)", "title": "캘리포니아 SCR 17 (Relative 인공지능 2023)"}]
    ok(polish_short_names(polished) == 1, "Relative polish count")
    ok(polished[0]["short_name"] == "캘리포니아 SCR 17 (인공지능 2023)", "Relative polish text")
    acr = [{"short_name": "캘리포니아 ACR 96Relative 23 Asilomar AI 원칙 2023", "title": "캘리포니아 ACR 96Relative 23 Asilomar AI 원칙 2023"}]
    ok(polish_short_names(acr) == 1, "ACR Relative polish count")
    ok(
        acr[0]["short_name"] == "캘리포니아 ACR 96 Asilomar AI 원칙 2023",
        "ACR Relative polish text",
    )
    migdia = [{"short_name": "Inter-American 프레임워크 · 가이드라인 Data 거버넌스 · 인공지능 (MIGDIA)"}]
    ok(polish_short_names(migdia) == 1, "MIGDIA polish count")
    ok("미주 " in migdia[0]["short_name"] and "데이터 거버넌스" in migdia[0]["short_name"], "MIGDIA leftover EN")
    iso = [{"short_name": "Information 기술 — 인공지능 — Management 시스템 (ISO/IEC 42001)"}]
    ok(polish_short_names(iso) == 1, "ISO polish count")
    ok(iso[0]["short_name"].startswith("정보기술"), "ISO Information→정보기술")
    ok("경영시스템" in iso[0]["short_name"], "ISO Management→경영시스템")
    jp = [{"short_name": "일본 · 법 Promotion Research, Development, · Utilization 인공 Intelligence-Related 기술"}]
    ok(polish_short_names(jp) == 1, "Japan promotion polish")
    ok("연구·개발·활용 촉진법" in jp[0]["short_name"], "Japan promotion Korean")
    uk = [{"short_name": "영국 · Data (Use · Access) 법 2025"}]
    ok(polish_short_names(uk) == 1, "UK Data Act polish")
    ok("데이터 (이용·접근)" in uk[0]["short_name"], "UK Data Act Korean")
    sen = [{"short_name": "미국 상원법안 S 3202고도 인공지능 안보 Readiness 법 2025"}]
    ok(polish_short_names(sen) == 1, "Senate spacing polish")
    ok("S 3202 고도" in sen[0]["short_name"] and "대비" in sen[0]["short_name"], "Senate Readiness")
    ini = "https://oeil.secure.europarl.europa.eu/oeil/en/procedure-file?reference=2020/2013(INI)"
    ok(as_url_list(ini) == [ini], "keep europarl (INI)")
    ok(
        as_url_list("see (https://example.com/foo)") == ["https://example.com/foo"],
        "strip wrapping paren",
    )
    coe = "https://search.coe.int/cm#{%22CoEIdentifier%22:[%2209125948802ae993%22]"
    ok(as_url_list(coe)[0].endswith("%22]}"), "keep CoE JSON brackets")
    ukr = [{"short_name": "전략 Digital Development Innovation Activity Ukraine until 2030"}]
    ok(polish_short_names(ukr) == 1, "Ukraine strategy polish")
    ok("디지털 발전 전략" in ukr[0]["short_name"], "Ukraine strategy Korean")
    ag = [{"short_name": "Promoting Precision Agriculture 법 2025"}]
    ok(polish_short_names(ag) == 1, "precision ag polish")
    ok("촉진 정밀농업 법" in ag[0]["short_name"], "precision ag Korean")
    sub = [{"short_name": "핀란드 · Tampere Pulse (Subnational: City Tampere)"}]
    ok(polish_short_names(sub) == 1, "Subnational strip count")
    ok("Subnational" not in sub[0]["short_name"], "Subnational stripped")
    no = [{"short_name": "노르웨이 · Joint AI plan safe · effective use AI Norwegian health · care services 2024–2025"}]
    ok(polish_short_names(no) == 1, "Norway plan polish")
    ok("보건·돌봄" in no[0]["short_name"], "Norway plan Korean")
    chain = [{"short_name": "Promoting Resilient Supply Chains 법 2025"}]
    ok(polish_short_names(chain) == 1, "supply chain polish")
    ok("공급망 촉진법" in chain[0]["short_name"], "supply chain Korean")
    ok(is_bad_original("https://www.oas.org/en/"), "OAS homepage")
    ok(not is_bad_original("https://www.oas.org/en/sla/dia/MIGDIA.asp"), "OAS inner page ok")
    ok(jurisdiction_from_host("www.europarl.europa.eu") == "European Union", "europarl host")
    ok(jurisdiction_from_host("www.oecd.org") == "OECD", "oecd host")
    ok(jurisdiction_from_host("king.senate.gov") == "United States", "senate host")
    ok(
        known_instrument_group_key(
            "Hiroshima Process International Guiding Principles for Advanced AI Systems"
        )
        == "g7-hiroshima-guiding-principles",
        "Hiroshima guiding principles",
    )
    ok(
        known_instrument_group_key("생성형 AI 서비스 안전 기본 요구사항")
        == "cn-tc260-genai-safety-2024",
        "China genAI safety 2024",
    )
    ok(
        known_instrument_group_key("중국 생성형 AI 서비스 안전 기본 요구사항(GB/T 45654—2025)")
        == "",
        "China GB/T 45654 stays separate",
    )
    pdf = "https://www.legislation.gov.uk/uksi/2026/425/pdfs/uksi_20260425_en.pdf"
    html = "https://www.legislation.gov.uk/uksi/2026/425/contents/made"
    ok(legislation_family_key(pdf) == legislation_family_key(html) == "ukleg:uksi:2026:425", "UK SI family")
    a = "https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202320240SCR17"
    b = "https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202320240SCR17"
    ok(legislation_family_key(a) == legislation_family_key(b) == "calib:202320240scr17", "CA bill family")


def test_url_merge() -> None:
    same = [
        {"title": "Guidelines for AI Procurement"},
        {"title": "UK Government's Guidelines for AI Procurement"},
    ]
    ok(url_owners_should_merge(same), "UK procurement copies merge")
    diff = [
        {"title": "I Choose French Tech", "country": "France"},
        {"title": "AI Action Plan", "country": "Germany"},
    ]
    ok(not url_owners_should_merge(diff), "French Tech ≠ German plan")
    ok(
        titles_look_same_instrument(
            "Guidelines for AI Procurement",
            "UK Government's Guidelines for AI Procurement",
        ),
        "title similar",
    )


def test_country() -> None:
    uk = {
        "collection": "agora",
        "title": "Code of Practice for the Cyber Security of AI",
        "org": "Government of the United Kingdom",
        "category": "Miscellaneous documents",
    }
    ok(country_from_item(uk) == "United Kingdom", "UK from org")
    depa = {
        "collection": "oecd-navigator",
        "title": "Digital Economy Partnership Agreement",
        "org": "Ministry of Foreign Affairs Chile",
        "country": "Chile",
    }
    ok(country_from_item(depa) == "International", "DEPA not Chile-only")
    lab = {
        "collection": "lab-policies",
        "title": "Google DeepMind 2023 영국 AI 안전 정상회의 대응",
        "org": "Google DeepMind",
    }
    ok(country_from_item(lab) == "", "lab not UK")
    ok(
        country_from_item(
            {
                "collection": "oecd-navigator",
                "title": "산토도밍고 AI 윤리 선언",
                "original_name": "Santo Domingo Declaration",
            }
        )
        == "International",
        "Santo Domingo multilateral",
    )
    ok(
        country_from_item(
            {
                "collection": "oecd-navigator",
                "title": "독립 국제 AI 과학 패널",
                "original_name": "Independent International Scientific Panel on AI",
            }
        )
        == "United Nations",
        "scientific panel UN",
    )
    ok(
        country_from_item(
            {
                "collection": "iaae-ethics",
                "title": "[로마교황청] 로마 콜",
                "org": "로마교황청",
            }
        )
        == "Vatican City",
        "Holy See",
    )
    ok(
        country_from_item(
            {
                "collection": "iaae-ethics",
                "title": "[몬트리올대학교] 몬트리올 선언",
                "org": "몬트리올대학교",
            }
        )
        == "Canada",
        "Montreal university",
    )
    ok(
        country_from_item(
            {
                "collection": "iaae-ethics",
                "title": "[베이징지원인공지능연구원] Beijing AI Principles",
                "org": "베이징지원인공지능연구원",
            }
        )
        == "China",
        "BAAI China",
    )
    ok(
        country_from_item(
            {
                "collection": "oecd-navigator",
                "title": "fAIr LAC",
                "original_name": "fAIr LAC",
            }
        )
        == "International",
        "fAIr LAC multilateral",
    )
    ok(
        country_from_item(
            {
                "collection": "oecd-navigator",
                "title": "Inter-American Framework and Guidelines on Data Governance and Artificial Intelligence (MIGDIA)",
            }
        )
        == "International",
        "MIGDIA multilateral",
    )
    ok(
        country_from_item(
            {
                "collection": "oecd-navigator",
                "title": "Opinion 28/2024 on certain data protection aspects related to AI models",
            }
        )
        == "European Union",
        "EDPB opinion EU",
    )
    ok(
        country_from_item(
            {
                "collection": "iaae-ethics",
                "title": "[IAAE] IAAE 감정 교류 AI 윤리 가이드라인",
                "org": "IAAE",
            }
        )
        == "South Korea",
        "IAAE org Korea",
    )
    ok(
        country_from_item(
            {
                "collection": "iaae-ethics",
                "title": "[FUTURE OF LIFE] 아실로마 AI 원칙",
                "org": "FUTURE OF LIFE",
            }
        )
        == "United States",
        "FLI US",
    )
    ok(
        country_from_item(
            {
                "collection": "oecd-navigator",
                "title": "AI Watch",
                "source_urls": ["https://ec.europa.eu/knowledge4policy/ai-watch_en"],
            }
        )
        == "European Union",
        "AI Watch from EC url",
    )
    ok(
        country_from_item(
            {
                "collection": "agora",
                "title": "Framework to Mitigate AI-Enabled Extreme Risks",
                "org": "Federal government",
                "page_url": "https://www.king.senate.gov/imo/media/doc/bipartisan_ai_framework_letter.pdf",
                "source_urls": [
                    "https://www.king.senate.gov/imo/media/doc/bipartisan_ai_framework_letter.pdf"
                ],
            }
        )
        == "United States",
        "Senate letter US",
    )


def test_issuer() -> None:
    ab = {
        "org": "Canada",
        "original_name": "AI-Enabled Government Services Modernisation (Alberta) (Subnational: Alberta)",
        "issuer_level": "ministry",
        "country": "Canada",
    }
    ok(_issuer_looks_subnational(ab["org"], ab["original_name"]), "alberta subnat signal")
    ok(infer_issuer_level(ab) == "subnational", "alberta issuer")
    ibm = {"org": "IBM", "title": "IBM AI 원칙", "issuer_level": "national"}
    ok(infer_issuer_level(ibm) == "industry", "IBM industry")
    meta = {
        "org": "Private-sector companies",
        "title": "Meta 2023 영국 AI 안전 정상회의 대응",
        "issuer_level": "national",
    }
    ok(infer_issuer_level(meta) == "lab", "Meta summit → lab")
    uni = {"org": "세종대학교", "title": "생성형 AI 가이드라인", "issuer_level": "national"}
    ok(infer_issuer_level(uni) == "civil_society", "university")
    summit = {"org": "AI SAFETY SUMMIT", "title": "Bletchley 선언", "issuer_level": "national"}
    ok(infer_issuer_level(summit) == "international", "Bletchley")
    hud = {
        "org": "",
        "title": "HUDERIA AI 위험·영향 평가 방법론",
        "country": "Council of Europe",
        "issuer_level": "national",
    }
    ok(infer_issuer_level(hud) == "international", "HUDERIA intl")
    iti = {"org": "ITI", "title": "ITI AI 정책 원칙", "issuer_level": "national", "country": "United States"}
    ok(infer_issuer_level(iti) == "industry", "ITI industry")
    school = {
        "org": "AI4SCHOOL",
        "title": "Good AI 교육",
        "issuer_level": "national",
        "country": "South Korea",
    }
    ok(infer_issuer_level(school) == "civil_society", "AI4SCHOOL civil")
    citizen = {
        "org": "아름다운인터넷세상",
        "title": "코르셋에 갇힌 인공지능",
        "issuer_level": "national",
        "country": "South Korea",
    }
    ok(infer_issuer_level(citizen) == "civil_society", "digital citizen civil")


def test_leftover_titles() -> None:
    from enrich_ko import leftover_title_needs_rewrite

    bill = {
        "short_name": "HR 1142- amend 공중보건 Service 법 direct Secretary",
        "original_name": "H.R. 1142 - To amend the Public Health Service Act",
    }
    ok(leftover_title_needs_rewrite(bill), "US bill leftover rewrite")
    proper = {
        "short_name": "독일 Health Data Lab",
        "original_name": "Health Data Lab",
    }
    ok(not leftover_title_needs_rewrite(proper), "skip Health Data Lab")
    korean = {
        "short_name": "미국 HR 1142 공중보건서비스법 개정안",
        "original_name": "H.R. 1142",
    }
    ok(not leftover_title_needs_rewrite(korean), "clean Korean bill title")
    mixed_bill = {
        "short_name": "캘리포니아 AB 1331 (Workplace Surveillance 2025)",
        "original_name": "AB 1331 Workplace Surveillance",
        "canonical_url": "https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202520260AB1331",
    }
    ok(
        leftover_title_needs_rewrite(mixed_bill, min_words=2, bills_only=True),
        "CA bill leftover 2",
    )
    copilot = {
        "short_name": "호주 Microsoft 365 Copilot 시험",
        "original_name": "Microsoft 365 Copilot trial",
        "canonical_url": "https://example.org/copilot",
    }
    ok(
        not leftover_title_needs_rewrite(copilot, min_words=2, bills_only=True),
        "skip non-bill leftover 2",
    )
    ok(
        not leftover_title_needs_rewrite(copilot, min_words=2),
        "skip Copilot proper name",
    )
    from enrich_ko import english_summary_needs_rewrite

    en_sum = {
        "short_name": "영국 · 데이터 (이용·접근) 법 2025",
        "summary": "The Data (Use and Access) Act 2025, enacted on 19 June 2025 by the UK Parliament, establishes a broad legislative framework.",
    }
    ok(english_summary_needs_rewrite(en_sum), "KO title English summary")
    ko_sum = {
        "short_name": "영국 · 데이터 (이용·접근) 법 2025",
        "summary": "영국 의회가 2025년 6월 19일 제정한 데이터 이용·접근법으로, 폭넓은 입법 체계를 마련한다.",
    }
    ok(not english_summary_needs_rewrite(ko_sum), "already Korean summary")
    from enrich_ko import english_title_needs_rewrite

    ndaa = {
        "short_name": "NDAA FY2026",
        "original_name": "FY2026 NDAA",
        "canonical_url": "https://www.congress.gov/bill/119th-congress/senate-bill/1071/text",
    }
    ok(english_title_needs_rewrite(ndaa), "NDAA English title rewrite")
    leuven = {
        "short_name": "Leuven.AI",
        "original_name": "",
        "canonical_url": "https://ai.kuleuven.be/",
    }
    ok(not english_title_needs_rewrite(leuven), "skip Leuven.AI")


def test_disambiguate() -> None:
    ok(
        congress_bill_label("https://www.congress.gov/bill/119th-congress/house-bill/1692")
        == "HR 1692",
        "HR label",
    )
    ok(
        congress_bill_label("https://www.congress.gov/bill/118th-congress/senate-bill/5109")
        == "S 5109",
        "S label",
    )
    paths = [
        {
            "in_scope": True,
            "short_name": "PATHS 법",
            "title": "PATHS 법",
            "canonical_url": "https://www.congress.gov/bill/119th-congress/house-bill/1692",
        },
        {
            "in_scope": True,
            "short_name": "PATHS 법",
            "title": "PATHS 법",
            "canonical_url": "https://www.congress.gov/bill/118th-congress/house-bill/9459",
        },
    ]
    ok(disambiguate_duplicate_short_names(paths) == 2, "PATHS bill labels count")
    ok(paths[0]["short_name"] == "PATHS 법 (HR 1692)", "PATHS HR 1692")
    ok(paths[1]["short_name"] == "PATHS 법 (HR 9459)", "PATHS HR 9459")
    ethics = [
        {"in_scope": True, "short_name": "AI 윤리 원칙", "title": "AI 윤리 원칙", "org": "LG"},
        {
            "in_scope": True,
            "short_name": "AI 윤리 원칙",
            "title": "AI 윤리 원칙",
            "org": "CJ올리브네트웍스",
        },
    ]
    ok(disambiguate_duplicate_short_names(ethics) == 2, "ethics org labels count")
    ok(ethics[0]["short_name"] == "LG AI 윤리 원칙", "LG ethics title")
    ok(ethics[1]["short_name"] == "CJ올리브네트웍스 AI 윤리 원칙", "CJ ethics title")
    peru = [
        {
            "short_name": "페루 · 지수함수적 기술을 활용한 재화·용역·공사 계약 선정절차 기술 샌드박스ble manner members 국가 디지털 전환 시스템"
        }
    ]
    ok(polish_short_names(peru) == 1, "Peru sandbox polish count")
    ok("ble manner" not in peru[0]["short_name"], "Peru sandbox stripped")
    ok("샌드박스" in peru[0]["short_name"], "Peru sandbox kept")
    drone = [
        {
            "short_name": "페루 · Public-private regulatory sandbox regarding use 무인 vehicles reliably members 국가 디지털 전환 시스템, with emphasis public · private sectors"
        }
    ]
    ok(polish_short_names(drone) == 1, "Peru drone polish count")
    ok("reliably members" not in drone[0]["short_name"], "Peru drone members stripped")
    ok("with emphasis" not in drone[0]["short_name"], "Peru drone emphasis stripped")


def test_glued_summary() -> None:
    from parse_meta import extract_meta, parse_bullet_fields
    from curate_llm import apply_cache_to_docs

    body = (
        "●국가: EU ●기관: 유럽연합 집행위원회 ●문서종류: 자율준수 규범 "
        "●문서명: 범용 AI 실천규범 ●발표시점: 2025년 7월 10일 "
        "●핵심내용AI Act의 범용 AI 모델 의무 이행을 지원한다."
    )
    fields = parse_bullet_fields(body)
    ok(fields.get("핵심내용", "").startswith("AI Act"), "glued 핵심내용 field")
    item = {"collection": "mofa-country-policy", "body": body, "title": "GPAI"}
    ok("AI Act" in (extract_meta(item).get("summary") or ""), "extract glued summary")
    docs = [
        {
            "id": "doc-keep-sum",
            "summary": "외교부에서 가져온 실요약입니다. 내용이 충분히 있습니다.",
            "snippet": "외교부",
        }
    ]
    cache = {
        "doc-keep-sum": {
            "result": {"confidence": "medium", "in_scope": True, "summary": ""}
        }
    }
    apply_cache_to_docs(docs, cache)
    ok("실요약" in (docs[0].get("summary") or ""), "empty llm does not wipe summary")
    low = [
        {
            "id": "doc-low-sum",
            "summary": "외교부 저신뢰여도 원문 요약을 지우지 않습니다.",
            "snippet": "",
        }
    ]
    cache_low = {"doc-low-sum": {"result": {"confidence": "low", "summary": ""}}}
    apply_cache_to_docs(low, cache_low)
    ok("원문 요약" in (low[0].get("summary") or ""), "low-conf empty does not wipe")


def main() -> None:
    test_urls()
    test_known()
    test_url_merge()
    test_country()
    test_issuer()
    test_leftover_titles()
    test_disambiguate()
    test_glued_summary()
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
