#!/usr/bin/env python3
"""Classify documents into broad AI-safety scope (governance/ethics/risk/reg).

in_scope = True → show in the library UI.
Raw collections stay intact; classification is attached at document-index time.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# 광의의 AI 안전: 기술안전·보안·위험관리·윤리·거버넌스·규제·권리·평가
_POS = [
    (r"\bai\s*safety\b|인공지능\s*안전|AI\s*안전", 5),
    (r"\balignment\b|정렬", 4),
    (r"\bred\s*team|레드팀", 4),
    (r"catastroph|재앙|existential|존속", 4),
    (r"frontier\s*ai|프론티어|advanced\s*ai\s*system|고도\s*AI", 3),
    (r"\brisk\b|위험\s*관리|위험관리|고위험|high[-\s]?risk", 3),
    (r"\bsafety\b|안전성|안전\s*확보", 3),
    (r"\bsecurit|보안|사이버보안|cybersecurity", 3),
    (r"\bethic|윤리", 3),
    (r"responsible\s*ai|책임\s*있는\s*AI|책임있는\s*AI", 3),
    (r"trustworth(?:y)?\s*ai|신뢰\s*가능(?:한)?\s*AI|신뢰할\s*수\s*있는\s*AI", 3),
    (r"governan|거버넌스", 3),
    (r"regulat|규제", 3),
    (r"(?:artificial\s*intelligence\s*act|\bAI\s*Act\b|AI\s*기본법|인공지능\s*기본법)", 3),
    (r"guideline|가이드라인|지침|(?<![a-z])guidance(?![a-z])", 2),
    (r"principle|원칙|권고|recommendation", 2),
    (r"(?:AI|인공지능).{0,12}(?:framework|프레임워크)|(?:framework|프레임워크).{0,12}(?:AI|인공지능|ethic|윤리|risk|안전)", 2),
    (r"standard|표준|iso/?iec", 2),
    (r"code\s*of\s*conduct|행동규범|실천규범|code\s*of\s*practice", 3),
    (r"declarat|선언|convention|협약|조약", 2),
    (r"oversight|감독|감사|audit|evaluat|평가\s*체계|conformit|적합성", 2),
    (r"transpar|투명|explainab|설명\s*가능|accountability|책무", 2),
    (r"privacy|개인정보|data\s*protection", 2),
    (r"bias|편향|discriminat|차별|fairness|공정", 2),
    (r"harm|피해|misuse|악용|dual[-\s]?use|무기화|(?:\blethal\s*autonomous\b)|자율무기", 3),
    (r"prohibit|금지|banned\s*ai|금지\s*AI", 3),
    (r"guardrail|안전장치", 3),
    (r"human\s*rights|인권|문화적\s*권리", 2),
    (r"\bmilitary\b|군사\b", 2),
    (r"bletchley|hiroshima\s*process|히로시마|ai\s*safety\s*summit|AI\s*안전\s*정상", 3),
    (r"\baisi\b|안전연구소|safety\s*institute", 4),
    (r"risk\s*management|위험관리\s*프레임", 3),
    (r"licen[cs]|면허|등록\s*의무|provider\s*oblig", 2),
    (r"incident|사고\s*보고|reporting\s*oblig|보고\s*의무", 2),
    (r"model\s*eval|시스템\s*평가|benchmark.*(safe|risk|harm)", 2),
    (r"\bwaico\b|인공지능협력기구|ai\s*cooperation\s*(org|agency|body)", 3),
]

# 산업·혁신·인재·단순 도입 촉진 (안전/거버넌스 신호 없으면 제외)
_NEG = [
    (r"startup|스타트업|smes?\b|중소기업", 3),
    (r"innovation\s*package|혁신\s*패키지|혁신촉진(?!.*규제)", 3),
    (r"invest(ment)?\b|투자\s*유치|venture|펀드|기금(?!.*안전)", 2),
    (r"talent|인재\s*양성|skills\s*agenda|역량\s*강화(?!.*윤리)", 2),
    (r"competitiv|경쟁력|market\s*share|시장\s*동향", 2),
    (r"(?:ai\s+)?adoption\b|도입\s*가속|활용\s*촉진|deploy(?:ment)?\b(?!.*safe)", 2),
    (r"cluster|허브\s*조성|sandbox(?!.*(안전|risk|ethic|규제))", 2),
    (r"chip|반도체|compute\s*infr|데이터센터\s*투자", 2),
    (r"gdp|생산성|productivity|growth\s*strateg", 2),
    (r"curriculum|교육\s*과정(?!.*윤리)|literacy(?!.*(윤리|안전|risk))", 1),
    (r"agriculture|농업\s*AI|관광|tourism", 1),
]

_POS_RE = [(re.compile(p, re.I), w) for p, w in _POS]
_NEG_RE = [(re.compile(p, re.I), w) for p, w in _NEG]


@dataclass
class SafetyScore:
    score: int
    in_scope: bool
    reasons: list[str]


def _hay(doc: dict) -> str:
    parts = [
        doc.get("title") or "",
        doc.get("short_name") or "",
        doc.get("full_name") or "",
        doc.get("summary") or "",
        doc.get("snippet") or "",
        doc.get("org") or "",
        doc.get("country") or "",
        doc.get("doc_kind") or "",
        doc.get("doc_kind_raw") or "",
    ]
    for h in doc.get("history") or []:
        parts.append(h.get("title") or "")
        parts.append(h.get("label") or "")
    return "\n".join(parts)


def score_document(doc: dict) -> SafetyScore:
    text = _hay(doc)
    score = 0
    reasons: list[str] = []

    # Collection / history priors (broad governance sources lean in)
    labels = {h.get("label") for h in (doc.get("history") or [])}
    if "IAAE 게시" in labels:
        score += 3
        reasons.append("+iaae")
    if "외교부 게시" in labels:
        score += 1
        reasons.append("+mofa")
    if "DPA 기록" in labels:
        score += 1
        reasons.append("+dpa")
    if "원문 기록" in labels:
        score += 1
        reasons.append("+agora")
    # OECD alone is weak prior (many non-safety initiatives)
    if labels == {"OECD 등록"}:
        score -= 1
        reasons.append("-oecd-only")

    pos_hits = 0
    for rx, w in _POS_RE:
        if rx.search(text):
            score += w
            pos_hits += 1
            reasons.append(f"+{rx.pattern[:28]}")
            if pos_hits >= 8:
                break

    for rx, w in _NEG_RE:
        if rx.search(text):
            score -= w
            reasons.append(f"-{rx.pattern[:28]}")

    has_ai = bool(
        re.search(
            r"\bAI\b|A\.I\.|인공지능|artificial\s*intelligence|machine\s*learning|"
            r"생성형|generative\s*ai|foundation\s*model|기초모형",
            text,
            re.I,
        )
    )
    safety_core = bool(
        re.search(
            r"ai\s*safety|인공지능\s*안전|고위험|high[-\s]?risk|\bethic|윤리|"
            r"\balign|정렬|금지|prohibit|risk\s*management|위험\s*관리|"
            r"red\s*team|\baisi\b|행동규범|code\s*of\s*conduct|code\s*of\s*practice|"
            r"거버넌스|governance|trustworth(?:y)?\s*ai|책임\s*있는\s*AI|"
            r"bletchley|hiroshima|AI\s*안전\s*정상|안전연구소",
            text,
            re.I,
        )
    )
    industry_heavy = bool(
        re.search(
            r"startup|스타트업|smes?\b|중소기업|innovation\s*package|혁신\s*패키지|"
            r"chips?\s*(act|ju|competence)|반도체|인재\s*양성|talent\s*program",
            text,
            re.I,
        )
    )
    title = doc.get("title") or ""
    industry_title = bool(
        re.search(r"startup|스타트업|smes?\b|중소|혁신\s*패키지|innovation\s*package", title, re.I)
    )
    title_has_core = bool(
        re.search(
            r"안전|safety|ethic|윤리|govern|거버넌스|risk|위험|regul|규제|금지|align",
            title,
            re.I,
        )
    )
    if safety_core and score < 2:
        score = 2
        reasons.append("+safety-core-floor")

    # Must be about AI (broad), and clear safety/governance signal
    in_scope = score >= 3 and has_ai
    if safety_core and has_ai and score >= 2:
        in_scope = True
        reasons.append("+core+ai")
    if industry_heavy and not safety_core:
        in_scope = False
        reasons.append("-industry-heavy")
    if industry_title and not title_has_core:
        in_scope = False
        reasons.append("-industry-title")
    if not has_ai:
        reasons.append("-no-ai")
        in_scope = False
    # Soft exclude: news blurbs & bare institution listings aren't library documents
    if (doc.get("doc_kind") or "") == "뉴스·보도":
        reasons.append("-news")
        in_scope = False
    if (doc.get("doc_kind") or "") == "기구·제도" and not safety_core:
        # Keep AISI / ethics committees with safety signal; drop generic institutes
        if not re.search(r"aisi|ethics|안전|ethic|oversight|감독", text, re.I):
            reasons.append("-bare-institution")
            in_scope = False

    return SafetyScore(score=score, in_scope=in_scope, reasons=reasons[:12])


def apply_safety_scope(docs: list[dict]) -> list[dict]:
    for d in docs:
        s = score_document(d)
        d["safety_score"] = s.score
        d["in_scope"] = s.in_scope
        d["safety_reasons"] = s.reasons
    return docs
