"""Nav chrome matching intl-cooperation-tracker (same tokens, black bar, omnibox)."""
from __future__ import annotations

import html
import importlib.util
import json
from pathlib import Path

NAV_ITEMS = [
    ("index.html", "라이브러리"),
    ("about.html", "소개"),
]

_COOP_UI = (
    Path(__file__).resolve().parents[2]
    / "intl-cooperation-tracker"
    / "scripts"
    / "ui_common.py"
)


def _coop():
    spec = importlib.util.spec_from_file_location("coop_ui_common", _COOP_UI)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"국제협력 페이지 스타일을 찾을 수 없습니다: {_COOP_UI}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_COOP = _coop()
NAV_CSS = _COOP.NAV_CSS + """
.org-flag { font-style: normal; font-size: 1.05em; line-height: 1; margin-right: 4px; }
"""
THEME_JS = _COOP.THEME_JS


def nav_html(current: str = "") -> str:
    parts = []
    for href, label in NAV_ITEMS:
        if href == current:
            parts.append(f'<span class="nav-current">{html.escape(label)}</span>')
        else:
            parts.append(f'<a href="{href}">{html.escape(label)}</a>')
    return (
        '<nav class="global-nav" aria-label="사이트"><div class="global-nav-inner">'
        + "".join(parts)
        + "</div></nav>"
    )


def shell_html(current: str, title: str) -> str:
    return (
        nav_html(current)
        + '<div class="sub-nav"><div class="sub-nav-inner">'
        f"<h1>{html.escape(title)}</h1>"
        + omnibox_html()
        + '<button class="theme-toggle" id="themeToggle" type="button">라이트/다크</button>'
        + "</div></div>"
    )


def omnibox_html() -> str:
    return """<div class="omni-wrap">
    <input id="omniBox" type="search" placeholder="약칭 · 주제 · 기관 · 핵심내용  ( / )" autocomplete="off">
  <div id="omniResults" class="omni-results hidden"></div>
</div>"""


def safe_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def omnibox_boot_script(search_index_json: str) -> str:
    # 목록 필터는 페이지 스크립트가 #omniBox input으로 처리. 여기선 / 포커스만.
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
        "omni_js": omnibox_boot_script(safe_json(idx)) + THEME_JS,
        "nav_css": NAV_CSS,
    }
