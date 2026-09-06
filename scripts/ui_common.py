#!/usr/bin/env python3
"""라이브러리 페이지 크롬 — 동향 Digest 헤더 구조를 따르되 라이트 전용·살짝 다른 팔레트."""
from __future__ import annotations

import html
import json

NAV_ITEMS = [
    ("index.html", "라이브러리"),
    ("about.html", "소개"),
]

# 동향(#474284 퍼플 네이비·#f6f1e4 크림·#f3b84f 골드)과 같은 시리즈이되
# 아카이브 톤으로 살짝 식힌 슬레이트 네이비·차가운 크림·브라스 골드.
NAV_CSS = """
:root {
  color-scheme: light;
  --ink: #243044;
  --ink-muted: #3a4658;
  --text-muted: #5c6670;
  --text-primary: #243044;
  --text-secondary: #3a4658;
  --plane: #f4f2eb;
  --surface-1: #fffcf6;
  --surface-2: #f7f4ec;
  --surface-pearl: #fffcf6;
  --hairline: #ddd6c8;
  --border: #ddd6c8;
  --gridline: #ebe6da;
  --baseline: #ddd6c8;
  --accent: #c45c48;
  --accent-focus: #3a5270;
  --navy: #3a5270;
  --navy-2: #4a6584;
  --gold: #d4a45a;
  --gold-strong: #e0b56e;
  --on-navy: #f4f2eb;
  --on-navy-muted: #c5ced8;
  --sage: #3f5340;
  --on-dark: #f4f2eb;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--plane);
  color: var(--ink);
  font-family: "IBM Plex Sans KR", "IBM Plex Sans", -apple-system, BlinkMacSystemFont,
    "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
  line-height: 1.7;
}
.viz-root { min-height: 100vh; background: var(--plane); color: var(--ink); }
.global-nav {
  position: sticky; top: 0; z-index: 40;
  background: var(--navy); color: var(--on-navy); height: 40px;
}
.global-nav-inner {
  max-width: 980px; margin: 0 auto; height: 40px; padding: 0 20px;
  display: flex; align-items: center; justify-content: space-between; gap: 24px;
  font-size: 0.78rem; font-weight: 500; letter-spacing: -0.02em;
}
.global-nav-left, .global-nav-right {
  display: flex; align-items: center; gap: 16px; flex-shrink: 0;
}
.global-nav a, .global-nav .nav-current {
  color: var(--on-navy); text-decoration: none; white-space: nowrap;
}
.global-nav a { opacity: 0.78; }
.global-nav a:hover { opacity: 1; color: var(--gold); }
.global-nav .nav-current { opacity: 1; font-weight: 650; }
.global-nav .nav-series {
  opacity: 0.55; font-size: 0.72rem; letter-spacing: 0.02em;
}
.global-nav .nav-series a { opacity: 0.85; }
header.page-head {
  background: linear-gradient(165deg, var(--navy) 0%, var(--navy-2) 100%);
  color: var(--on-navy);
}
.page-head-inner {
  max-width: 980px; margin: 0 auto; padding: 28px 20px 22px;
}
header.page-head h1 {
  font-size: 1.55rem; margin: 0 0 6px; font-weight: 700; letter-spacing: -0.02em;
}
header.page-head .tagline {
  margin: 0; font-size: 0.92rem; color: var(--on-navy-muted); line-height: 1.55;
  max-width: 42em;
}
.toolbar {
  position: sticky; top: 40px; z-index: 30;
  background: color-mix(in srgb, var(--plane) 88%, var(--gold) 12%);
  border-bottom: 1px solid var(--hairline);
  backdrop-filter: saturate(140%) blur(12px);
  -webkit-backdrop-filter: saturate(140%) blur(12px);
}
.toolbar-inner {
  max-width: 980px; margin: 0 auto; min-height: 56px; padding: 10px 20px;
  display: flex; align-items: center; gap: 14px;
}
.omni-wrap { position: relative; flex: 1 1 auto; min-width: 0; margin: 0; }
.omni-wrap input {
  width: 100%; height: 40px;
  border: 1px solid var(--hairline);
  background: var(--surface-1);
  color: var(--ink);
  border-radius: 10px;
  padding: 0 14px;
  font-size: 0.95rem;
  font-family: inherit;
  letter-spacing: -0.02em;
}
.omni-wrap input::placeholder { color: var(--text-muted); }
.omni-wrap input:focus {
  outline: 2px solid var(--navy);
  outline-offset: 1px;
  border-color: transparent;
}
.omni-results {
  position: absolute; z-index: 40; left: 0; right: 0; top: calc(100% + 6px);
  background: var(--surface-1); border: 1px solid var(--hairline); border-radius: 12px;
  max-height: 420px; overflow: auto;
  box-shadow: 0 8px 28px color-mix(in srgb, var(--ink) 10%, transparent);
}
.omni-results.hidden { display: none; }
.wrap { max-width: 980px; margin: 0 auto; padding: 22px 20px 80px; }
.site-footer {
  margin-top: 48px; padding-top: 20px; border-top: 1px solid var(--hairline);
  font-size: 0.82rem; color: var(--text-muted); line-height: 1.55;
}
.site-footer a { color: var(--sage); }
.org-flag { font-style: normal; font-size: 1.05em; line-height: 1; margin-right: 4px; }
"""

TAGLINES = {
    "index.html": "원본 랜딩 URL 기준 · 발표 히스토리 · 법·가이드라인·정책 아카이브",
    "about.html": "수집·분류·표시 파이프라인과 데이터 출처",
}


def nav_html(current: str = "") -> str:
    left = []
    for href, label in NAV_ITEMS:
        if href == current:
            left.append(f'<span class="nav-current">{html.escape(label)}</span>')
        else:
            left.append(f'<a href="{href}">{html.escape(label)}</a>')
    # 시리즈 연결 — 동향 Digest로 가는 힌트
    right = (
        '<span class="nav-series">'
        '<a href="https://songkyungho.github.io/ai-safety-digest/" '
        'target="_blank" rel="noopener">AI 안전 동향</a>'
        "</span>"
    )
    return (
        '<nav class="global-nav" aria-label="사이트">'
        '<div class="global-nav-inner">'
        f'<div class="global-nav-left">{"".join(left)}</div>'
        f'<div class="global-nav-right">{right}</div>'
        "</div></nav>"
    )


def shell_html(current: str, title: str) -> str:
    tagline = TAGLINES.get(current, "AI 안전·거버넌스 문서 라이브러리")
    parts = [
        nav_html(current),
        '<header class="page-head"><div class="page-head-inner">',
        f"<h1>{html.escape(title)}</h1>",
        f'<p class="tagline">{html.escape(tagline)}</p>',
        "</div></header>",
    ]
    if current == "index.html":
        parts.append('<div class="toolbar"><div class="toolbar-inner">')
        parts.append(omnibox_html())
        parts.append("</div></div>")
    return "".join(parts)


def omnibox_html() -> str:
    return """<div class="omni-wrap">
    <input id="omniBox" type="search" placeholder="약칭 · 주제 · 기관 · 핵심내용  ( / )" autocomplete="off">
  <div id="omniResults" class="omni-results hidden"></div>
</div>"""


def safe_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def omnibox_boot_script(search_index_json: str) -> str:
    return f"""<script id="search-index" type="application/json">{search_index_json}</script>
<script>
(function() {{
  const box = document.getElementById('omniBox');
  const panel = document.getElementById('omniResults');
  if (!box) return;
  if (panel) panel.classList.add('hidden');
  document.addEventListener('keydown', (ev) => {{
    if (ev.key === '/' && ev.target.tagName !== 'INPUT' && ev.target.tagName !== 'TEXTAREA') {{
      ev.preventDefault();
      box.focus();
    }}
    if (ev.key === 'Escape') {{
      box.blur();
      if (panel) panel.classList.add('hidden');
    }}
  }});
}})();
</script>"""


def page_chrome(current: str, search_index=None, title: str = ""):
    idx = search_index or {"docs": []}
    titles = dict(NAV_ITEMS)
    return {
        "shell": shell_html(current, title or titles.get(current, "")),
        "omni_js": omnibox_boot_script(safe_json(idx)),
        "nav_css": NAV_CSS,
    }
