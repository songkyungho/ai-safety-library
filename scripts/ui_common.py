#!/usr/bin/env python3
"""라이브러리 페이지 크롬 — 동향 Digest 헤더 구조를 따르되 라이트 전용·살짝 다른 팔레트."""
from __future__ import annotations

import html
import json

NAV_RIGHT = [
    ("about.html", "소개"),
    ("about/log.html", "업데이트"),
]
DIGEST_URL = "https://songkyungho.github.io/ai-safety-digest/"
DIGEST_LABEL = "AI 안전 다이제스트"
GLOSSARY_URL = "https://songkyungho.github.io/ai-safety-glossary/"
GLOSSARY_LABEL = "AI 안전 용어집"
NAV_ITEMS = NAV_RIGHT

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
header.page-head {
  background: linear-gradient(165deg, var(--navy) 0%, var(--navy-2) 100%);
  color: var(--on-navy);
}
.page-head-inner {
  max-width: 980px; margin: 0 auto; padding: 28px 20px 22px;
}
header.page-head h1 {
  font-size: 1.55rem; margin: 0 0 6px; font-weight: 700; letter-spacing: -0.02em;
  line-height: 1.35;
}
header.page-head .tagline {
  margin: 0; font-size: 0.95rem; color: var(--on-navy-muted); line-height: 1.55;
  max-width: 48em;
}
header.page-head .tagline a {
  color: var(--on-navy-muted);
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 3px;
  font-weight: 500;
}
header.page-head .tagline a:hover { color: var(--gold); }
.list-search.omni-wrap {
  position: relative; margin: 14px 0 18px; max-width: 100%;
}
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
.wrap { max-width: 980px; margin: 0 auto; padding: 18px 20px 80px; }
.site-footer {
  margin-top: 48px; padding-top: 20px; border-top: 1px solid var(--hairline);
  font-size: 0.82rem; color: var(--text-muted); line-height: 1.55;
}
.site-footer a { color: var(--sage); }
.org-flag { font-style: normal; font-size: 1.05em; line-height: 1; margin-right: 4px; }
"""

TAGLINES = {
    "about.html": "수집·분류·표시 파이프라인과 데이터 출처",
    "about/log.html": "사이트 구조·분류·파이프라인이 바뀐 기록",
}


AUTHOR_NAME = "인공지능안전연구소 송경호"
AUTHOR_URL = "https://songkyungho.github.io"
CONTACT_EMAIL = "songkyungho@etri.re.kr"


def author_byline_html() -> str:
    """동향 Digest와 같은 byline — 송경호만 Home으로 링크."""
    linked = html.escape(AUTHOR_NAME).replace(
        "송경호",
        f'<a href="{html.escape(AUTHOR_URL)}" target="_blank" rel="noopener">송경호</a>',
    )
    return f" by {linked}"


def footer_inner_html() -> str:
    """다이제스트와 같은 푸터 문구."""
    author_linked = html.escape(AUTHOR_NAME).replace(
        "송경호",
        f'<a href="{html.escape(AUTHOR_URL)}" target="_blank" rel="noopener">송경호</a>',
    )
    return (
        f"만든 사람: {author_linked} · "
        f'문의/오류제보: <a href="mailto:{html.escape(CONTACT_EMAIL)}">{html.escape(CONTACT_EMAIL)}</a>'
    )


def footer_html() -> str:
    return f'<footer class="site-footer">{footer_inner_html()}</footer>'


def _nav_item(href: str, label: str, *, active: bool, rel_prefix: str) -> str:
    if active:
        return f'<span class="nav-current">{html.escape(label)}</span>'
    external = href.startswith("http://") or href.startswith("https://")
    resolved = href if external else f"{rel_prefix}{href}"
    attrs = f'href="{html.escape(resolved)}"'
    if external:
        attrs += ' target="_blank" rel="noopener noreferrer"'
    return f"<a {attrs}>{html.escape(label)}</a>"


def _nav_items(items: list[tuple[str, str]], current: str, *, rel_prefix: str) -> str:
    parts: list[str] = []
    for href, label in items:
        external = href.startswith("http://") or href.startswith("https://")
        resolved = href if external else f"{rel_prefix}{href}"
        if not external and href == current:
            parts.append(f'<span class="nav-current">{html.escape(label)}</span>')
            continue
        attrs = f'href="{html.escape(resolved)}"'
        if external:
            attrs += ' target="_blank" rel="noopener noreferrer"'
        parts.append(f"<a {attrs}>{html.escape(label)}</a>")
    return "".join(parts)


def nav_html(current: str = "", *, rel_prefix: str = "") -> str:
    left = (
        _nav_item(DIGEST_URL, DIGEST_LABEL, active=False, rel_prefix="")
        + _nav_item("index.html", "AI 안전 라이브러리", active=True, rel_prefix=rel_prefix)
        + _nav_item(GLOSSARY_URL, GLOSSARY_LABEL, active=False, rel_prefix="")
    )
    return (
        '<nav class="global-nav" aria-label="사이트">'
        '<div class="global-nav-inner">'
        f'<div class="global-nav-left">{left}</div>'
        f'<div class="global-nav-right">{_nav_items(list(NAV_RIGHT), current, rel_prefix=rel_prefix)}</div>'
        "</div></nav>"
    )


def shell_html(
    current: str,
    title: str,
    *,
    head_count: int | None = None,
    rel_prefix: str = "",
) -> str:
    parts = [
        nav_html(current, rel_prefix=rel_prefix),
        '<header class="page-head"><div class="page-head-inner">',
    ]
    if current == "index.html":
        n = head_count if head_count is not None else 0
        n_fmt = f"{n:,}"
        parts.append("<h1>AI 안전 라이브러리</h1>")
        parts.append(
            '<p class="tagline">AI 안전 법·가이드라인·정책 라이브러리 '
            f'(총 <span id="headCount">{html.escape(n_fmt)}</span>건)'
            f"{author_byline_html()}</p>"
        )
    else:
        parts.append(f"<h1>{html.escape(title)}</h1>")
        tagline = TAGLINES.get(current)
        if tagline:
            parts.append(f'<p class="tagline">{html.escape(tagline)}</p>')
    parts.append("</div></header>")
    return "".join(parts)


def omnibox_html() -> str:
    return """<div class="list-search omni-wrap">
    <input id="omniBox" type="search" placeholder="약칭 · 주제 · 기관 · 핵심내용  ( / )" autocomplete="off">
  <div id="omniResults" class="omni-results hidden"></div>
</div>"""


def safe_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def omnibox_boot_script(search_index_json: str) -> str:
    return f"""<script id="search-index" type="application/json">{search_index_json}</script>
<script>
(function() {{
  document.addEventListener('click', (ev) => {{
    const a = ev.target.closest && ev.target.closest('a[href]');
    if (!a) return;
    const href = a.getAttribute('href') || '';
    if (/^https?:\\/\\//i.test(href) || href.startsWith('//')) {{
      a.setAttribute('target', '_blank');
      a.setAttribute('rel', 'noopener noreferrer');
    }}
  }}, true);
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


def page_chrome(
    current: str,
    search_index=None,
    title: str = "",
    *,
    head_count: int | None = None,
    rel_prefix: str = "",
):
    idx = search_index or {"docs": []}
    titles = dict(NAV_ITEMS)
    return {
        "shell": shell_html(
            current,
            title or titles.get(current, ""),
            head_count=head_count,
            rel_prefix=rel_prefix,
        ),
        "omni_js": omnibox_boot_script(safe_json(idx)),
        "nav_css": NAV_CSS,
        "omnibox_html": omnibox_html(),
    }
