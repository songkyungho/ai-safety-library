#!/usr/bin/env python3
"""Build the library static site using the international-cooperation page chrome."""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui_common import page_chrome, safe_json

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
TODAY = date.today().isoformat()

COLLECTIONS = [
    ("mofa-governance", "외교부 거버넌스", "igo", "UN·G7·OECD 등 국제 문서"),
    ("mofa-country-policy", "외교부 국가정책", "government", "미국·중국·EU·일본·영국 정책"),
    ("iaae-ethics", "IAAE", "assoc", "윤리 원칙·가이드라인"),
    ("agora", "AGORA", "law", "법·규정·표준 원문"),
    ("oecd-navigator", "OECD Navigator", "igo", "국가·기구 AI 정책 이니셔티브"),
]
COL_LABEL = {k: lab for k, lab, *_ in COLLECTIONS}
COL_SECTOR = {k: sec for k, _, sec, _ in COLLECTIONS}
KIND_LABEL = {
    "same-document": "교차 문서",
    "same-act": "같은 법률",
    "duplicate-record": "중복 레코드",
}
FOOTER_HTML = (
    '<footer class="site-footer">'
    "AI 안전 라이브러리 · 만든 사람: 인공지능안전연구소(Korea AISI) 송경호 · "
    '<a href="mailto:songkyungho@etri.re.kr">songkyungho@etri.re.kr</a><br>'
    "디자인: 국제협력 트래커와 같은 톤 · AGORA 데이터셋 CC BY-NC 4.0 · "
    '<a href="about.html">소개</a>'
    "</footer>"
)
EXTRA_CSS = """
.timeline { position: relative; padding-left: 20px; }
.timeline::before { content: ""; position: absolute; left: 4px; top: 6px; bottom: 6px; width: 2px; background: var(--baseline); }
.month-group { margin-bottom: 6px; }
.month-header { cursor: pointer; font-weight: 600; font-size: 17px; letter-spacing: -0.37px; padding: 8px 0; color: var(--ink); user-select: none; }
.month-header .muted { font-weight: 400; margin-left: 4px; }
.event-card, .month-header, .dir-row { font: inherit; color: inherit; }
button.event-card, button.month-header, button.dir-row { cursor: pointer; background: var(--surface-1); }
button.month-header { background: transparent; border: 0; width: 100%; text-align: left; }
button.back-link { font: inherit; background: none; border: 0; padding: 0; }
.event-card { position: relative; padding: 16px 18px; margin-bottom: 12px; }
.event-card::before { content: ""; position: absolute; left: -20px; top: 18px; width: 10px; height: 10px; border-radius: 50%; background: var(--c-l); border: 2px solid var(--plane); }
@media (prefers-color-scheme: dark) { :root:where(:not([data-theme="light"])) .event-card::before { background: var(--c-d); } }
:root[data-theme="dark"] .event-card::before { background: var(--c-d); }
.event-head { display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; margin-bottom: 4px; }
.event-date { font-variant-numeric: tabular-nums; color: var(--text-muted); font-size: 12px; }
.event-summary { margin: 6px 0; font-size: 17px; line-height: 1.47; letter-spacing: -0.37px; }
.event-section { font-size: 14px; margin-top: 6px; }
.chiplist { display: inline-flex; flex-wrap: wrap; gap: 6px; }
.tag { background: var(--plane); border: 1px solid var(--hairline); border-radius: 999px; padding: 1px 8px; font-size: 12px; color: var(--text-secondary); }
.linklist a { font-size: 14px; margin-right: 10px; }
a.stat-tile, a.dir-row { text-decoration: none; color: inherit; }
.dir-row .org { min-width: 0; flex: 1 1 240px; }
.thread-item { border-left: 2px solid var(--gridline); padding: 4px 0 14px 14px; margin-bottom: 4px; position: relative; }
.thread-item::before { content: ""; position: absolute; left: -5px; top: 6px; width: 8px; height: 8px; border-radius: 50%; background: var(--text-muted); }
.thread-date { font-size: 12px; color: var(--text-muted); font-variant-numeric: tabular-nums; }
.thread-summary { margin: 4px 0; font-size: 14px; }
.detail .sub { color: var(--text-secondary); font-size: 14px; margin-bottom: 18px; }
.col-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
"""
SHARED_JS = r"""
function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function colRibbon(col) {
  const m = COLS[col];
  if (!m) return '';
  return `<span class="org-decor"><span class="org-ribbon sector-${escapeHtml(m.sector)}">${escapeHtml(m.short)}</span></span>`;
}
"""


def load_docs() -> list[dict]:
    cluster_of = {}
    clusters_path = ROOT / "clusters" / "clusters.json"
    if clusters_path.exists():
        blob = json.loads(clusters_path.read_text(encoding="utf-8"))
        for c in blob.get("clusters") or []:
            for m in c.get("members") or []:
                cluster_of[m["id"]] = c["id"]
    docs = []
    for key, label, sector, _blurb in COLLECTIONS:
        data = json.loads((ROOT / "collections" / key / "items.json").read_text(encoding="utf-8"))
        for it in data.get("items") or []:
            body = (it.get("body") or "").strip()
            src = it.get("source_urls") or []
            if isinstance(src, str):
                src = [u for u in src.split(" | ") if u]
            docs.append(
                {
                    "id": it["id"],
                    "title": it.get("title") or "",
                    "col": key,
                    "date": it.get("date") or "",
                    "org": it.get("org") or "",
                    "cat": it.get("category") or "",
                    "url": it.get("page_url") or "",
                    "src": [u for u in src if isinstance(u, str) and u.startswith("http")][:4],
                    "cluster": cluster_of.get(it["id"], ""),
                    "snippet": body[:400],
                }
            )
    docs.sort(key=lambda d: d["date"] or "", reverse=True)
    return docs


def load_clusters() -> list[dict]:
    path = ROOT / "clusters" / "clusters.json"
    if not path.exists():
        return []
    blob = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for c in blob.get("clusters") or []:
        out.append(
            {
                "id": c["id"],
                "kind": c.get("kind") or "",
                "kindLabel": KIND_LABEL.get(c.get("kind") or "", c.get("kind") or ""),
                "title": c.get("title") or "",
                "size": c.get("size") or len(c.get("members") or []),
                "collections": c.get("collections") or [],
                "date_min": c.get("date_min") or "",
                "date_max": c.get("date_max") or "",
                "members": [
                    {
                        "id": m["id"],
                        "col": m.get("collection"),
                        "title": m.get("title") or "",
                        "date": m.get("date") or "",
                        "url": m.get("page_url") or "",
                    }
                    for m in c.get("members") or []
                ],
            }
        )
    return out


def search_index(docs: list[dict], clusters: list[dict]) -> dict:
    return {
        "docs": [
            {"id": d["id"], "title": d["title"][:120], "org": d["org"], "col": d["col"], "date": d["date"]}
            for d in docs[:2500]
        ],
        "clusters": [
            {
                "id": c["id"],
                "title": c["title"][:120],
                "kind": c["kind"],
                "kindLabel": c["kindLabel"],
                "size": c["size"],
            }
            for c in clusters
        ],
    }


def cols_json() -> str:
    return safe_json(
        {
            k: {"label": lab, "short": lab.replace("외교부 ", ""), "sector": sec}
            for k, lab, sec, _ in COLLECTIONS
        }
    )


def page(current: str, title: str, extra_css: str, body: str, page_js: str, index: dict) -> str:
    chrome = page_chrome(current, index, title=title)
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ color-scheme: light dark; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; }}
{chrome["nav_css"]}
{EXTRA_CSS}
{extra_css}
</style>
</head>
<body>
<div class="viz-root">
{chrome["shell"]}
<div class="wrap">
{body}
{FOOTER_HTML}
</div>
</div>
{page_js}
{chrome["omni_js"]}
</body>
</html>
"""


def render_index(docs: list[dict], clusters: list[dict], index: dict) -> str:
    counts = Counter(d["col"] for d in docs)
    cross = [c for c in clusters if c["kind"] == "same-document"]
    tiles = "".join(
        f'<a class="stat-tile" href="documents.html?col={key}">'
        f'<div class="value">{counts.get(key, 0):,}</div>'
        f'<div class="label">{label}</div></a>'
        for key, label, *_ in COLLECTIONS
    )
    featured = cross[:12]
    feat_rows = "".join(
        f'<a class="dir-row" href="clusters.html#{c["id"]}">'
        f'<span class="org">{_esc(c["title"][:90])}</span>'
        f'<span class="muted">{c["size"]}건 · {" · ".join(COL_LABEL.get(x, x) for x in c["collections"])}</span>'
        "</a>"
        for c in featured
    )
    recent = docs[:12]
    rec_cards = "".join(_event_card_html(d) for d in recent)
    body = f"""
  <p class="meta">{TODAY} 스냅샷 · 문서 {len(docs):,}건 · 클러스터 {len(clusters)}개</p>
  <div class="stats">
    <a class="stat-tile" href="documents.html"><div class="value">{len(docs):,}</div><div class="label">문서</div></a>
    <a class="stat-tile" href="documents.html"><div class="value">5</div><div class="label">컬렉션</div></a>
    <a class="stat-tile" href="clusters.html?kind=same-document"><div class="value">{len(cross)}</div><div class="label">교차 문서</div></a>
    <a class="stat-tile" href="clusters.html"><div class="value">{len(clusters)}</div><div class="label">클러스터</div></a>
  </div>
  <h2 class="section-h">컬렉션</h2>
  <div class="stats">{tiles}</div>
  <h2 class="section-h">교차 컬렉션 문서</h2>
  <p class="lede">외교부·IAAE·AGORA·OECD에 같은 법·선언·전략이 올라온 묶음.</p>
  {feat_rows}
  <p class="lede"><a href="clusters.html?kind=same-document">교차 문서 전체 보기</a></p>
  <h2 class="section-h">최근 문서</h2>
  <div class="timeline">{rec_cards}</div>
"""
    return page("index.html", "라이브러리", "", body, f"<script>const COLS={cols_json()};</script>", index)


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _event_card_html(d: dict) -> str:
    ribbon = COL_LABEL.get(d["col"], d["col"])
    href = f"documents.html#{d['id']}"
    return (
        f'<a class="event-card" href="{href}" style="--c-l:#5b3d8f;--c-d:#c4a6e8;display:block;color:inherit;text-decoration:none">'
        f'<div class="event-head"><span class="event-date">{_esc(d["date"])}</span>'
        f'<span class="tag">{_esc(ribbon)}</span></div>'
        f'<div class="event-summary">{_esc(d["title"][:140])}</div>'
        f'<div class="muted">{_esc(d["org"][:80])}</div></a>'
    )


def render_documents(docs: list[dict], index: dict) -> str:
    buttons = ['<button class="active" data-col="" type="button">전체</button>']
    for key, label, *_ in COLLECTIONS:
        buttons.append(f'<button data-col="{key}" type="button">{label}</button>')
    body = f"""
  <p class="meta" id="countLine"></p>
  <button type="button" class="back-link" id="backLink">← 목록으로</button>
  <div class="controls" id="listControls">
    <input class="search" id="searchBox" type="search" placeholder="이 목록에서 찾기 (제목 · 기관)">
    <div class="sort-toggle" id="colToggle">{"".join(buttons)}</div>
  </div>
  <div id="listView"></div>
  <div id="detailView" class="detail hidden"></div>
"""
    js = f"""
<script id="docs-data" type="application/json">{safe_json(docs)}</script>
<script>
const DOCS = JSON.parse(document.getElementById('docs-data').textContent);
const COLS = {cols_json()};
const KIND = {safe_json(KIND_LABEL)};
{SHARED_JS}
const state = {{ q: '', col: '' }};
const byId = Object.fromEntries(DOCS.map(d => [d.id, d]));

function monthLabel(ym) {{
  if (!ym || ym.length < 7) return '날짜 없음';
  return ym.slice(0,4) + '년 ' + String(Number(ym.slice(5,7))) + '월';
}}
function visible() {{
  const q = state.q.trim().toLowerCase();
  return DOCS.filter(d => {{
    if (state.col && d.col !== state.col) return false;
    if (!q) return true;
    return (d.title + ' ' + d.org + ' ' + d.cat).toLowerCase().includes(q);
  }});
}}
function renderList() {{
  const rows = visible();
  document.getElementById('countLine').textContent = rows.length.toLocaleString('ko-KR') + '건';
  const groups = {{}};
  rows.forEach(d => {{
    const k = (d.date || '').slice(0,7) || 'undated';
    (groups[k] || (groups[k] = [])).push(d);
  }});
  const keys = Object.keys(groups).sort().reverse();
  let html = '<div class="timeline">';
  keys.forEach((k, i) => {{
    const open = i < 2 ? '' : ' hidden';
    html += `<div class="month-group"><button type="button" class="month-header" data-month="${{k}}">${{monthLabel(k)}} <span class="muted">${{groups[k].length}}</span></button><div class="month-body${{open}}">`;
    groups[k].forEach(d => {{
      html += `<button type="button" class="event-card" data-id="${{escapeHtml(d.id)}}" style="--c-l:#5b3d8f;--c-d:#c4a6e8;width:100%;text-align:left">
        <div class="event-head"><span class="event-date">${{escapeHtml(d.date)}}</span>${{colRibbon(d.col)}}<span class="muted">${{escapeHtml(d.org)}}</span></div>
        <div class="event-summary">${{escapeHtml(d.title)}}</div>
      </button>`;
    }});
    html += '</div></div>';
  }});
  html += '</div>';
  document.getElementById('listView').innerHTML = html || '<div class="empty">해당하는 문서가 없습니다.</div>';
}}
function showDetail(id) {{
  const d = byId[id];
  if (!d) return;
  const src = (d.src || []).map(u => `<a href="${{escapeHtml(u)}}" target="_blank" rel="noopener">원문</a>`).join(' ');
  const page = d.url ? `<a href="${{escapeHtml(d.url)}}" target="_blank" rel="noopener">페이지</a>` : '';
  const cl = d.cluster ? `<a href="clusters.html#${{encodeURIComponent(d.cluster)}}">같은 문서 클러스터</a>` : '';
  document.getElementById('listControls').classList.add('hidden');
  document.getElementById('listView').classList.add('hidden');
  document.getElementById('backLink').classList.add('show');
  document.getElementById('detailView').className = 'detail';
  document.getElementById('detailView').innerHTML = `<div class="detail-panel">
    <div class="event-head">${{colRibbon(d.col)}}<span class="event-date">${{escapeHtml(d.date)}}</span></div>
    <h2 class="section-title">${{escapeHtml(d.title)}}</h2>
    <p class="sub">${{escapeHtml(d.org)}} ${{d.cat ? '· ' + escapeHtml(d.cat) : ''}}</p>
    <p>${{escapeHtml(d.snippet)}}</p>
    <div class="linklist">${{page}} ${{src}} ${{cl}}</div>
  </div>`;
  history.replaceState(null, '', 'documents.html#' + encodeURIComponent(id));
}}
function showList() {{
  document.getElementById('listControls').classList.remove('hidden');
  document.getElementById('listView').classList.remove('hidden');
  document.getElementById('backLink').classList.remove('show');
  document.getElementById('detailView').className = 'detail hidden';
  history.replaceState(null, '', 'documents.html' + (state.col ? '?col=' + encodeURIComponent(state.col) : ''));
}}
document.getElementById('searchBox').addEventListener('input', ev => {{ state.q = ev.target.value; renderList(); }});
document.getElementById('colToggle').querySelectorAll('button').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.getElementById('colToggle').querySelectorAll('button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.col = btn.dataset.col || '';
    renderList();
  }});
}});
document.getElementById('listView').addEventListener('click', ev => {{
  const head = ev.target.closest('.month-header');
  if (head) {{
    head.nextElementSibling.classList.toggle('hidden');
    return;
  }}
  const card = ev.target.closest('.event-card');
  if (card && card.dataset.id) showDetail(card.dataset.id);
}});
document.getElementById('backLink').addEventListener('click', showList);
(function boot() {{
  const params = new URLSearchParams(location.search);
  if (params.get('col')) {{
    state.col = params.get('col');
    document.getElementById('colToggle').querySelectorAll('button').forEach(b => {{
      b.classList.toggle('active', (b.dataset.col || '') === state.col);
    }});
  }}
  renderList();
  const hash = decodeURIComponent((location.hash || '').slice(1));
  if (hash && byId[hash]) showDetail(hash);
}})();
</script>
"""
    return page("documents.html", "문서", "", body, js, index)


def render_clusters(clusters: list[dict], index: dict) -> str:
    buttons = ['<button class="active" data-kind="" type="button">전체</button>']
    for kind, lab in KIND_LABEL.items():
        n = sum(1 for c in clusters if c["kind"] == kind)
        buttons.append(f'<button data-kind="{kind}" type="button">{lab} {n}</button>')
    body = f"""
  <p class="meta" id="countLine"></p>
  <button type="button" class="back-link" id="backLink">← 목록으로</button>
  <div class="controls" id="listControls">
    <input class="search" id="searchBox" type="search" placeholder="이 목록에서 찾기">
    <div class="sort-toggle" id="kindToggle">{"".join(buttons)}</div>
  </div>
  <div id="listView"></div>
  <div id="detailView" class="detail hidden"></div>
"""
    js = f"""
<script id="clusters-data" type="application/json">{safe_json(clusters)}</script>
<script>
const CLUSTERS = JSON.parse(document.getElementById('clusters-data').textContent);
const COLS = {cols_json()};
{SHARED_JS}
const state = {{ q: '', kind: '' }};
const byId = Object.fromEntries(CLUSTERS.map(c => [c.id, c]));

function visible() {{
  const q = state.q.trim().toLowerCase();
  return CLUSTERS.filter(c => {{
    if (state.kind && c.kind !== state.kind) return false;
    if (!q) return true;
    return (c.title + ' ' + c.members.map(m => m.title).join(' ')).toLowerCase().includes(q);
  }});
}}
function renderList() {{
  const rows = visible();
  document.getElementById('countLine').textContent = rows.length.toLocaleString('ko-KR') + '개 클러스터';
  document.getElementById('listView').innerHTML = rows.map(c => `
    <button type="button" class="dir-row" data-id="${{escapeHtml(c.id)}}" style="width:100%;text-align:left">
      <span class="org">${{escapeHtml(c.title)}}</span>
      <span class="badge">${{escapeHtml(c.kindLabel)}}</span>
      <span class="muted">${{c.size}}건 · ${{c.collections.map(x => (COLS[x]||{{}}).short || x).join(' · ')}}</span>
    </button>`).join('') || '<div class="empty">해당하는 클러스터가 없습니다.</div>';
}}
function showDetail(id) {{
  const c = byId[id];
  if (!c) return;
  const members = c.members.map(m => `
    <div class="thread-item">
      <div class="thread-date">${{escapeHtml(m.date)}} ${{colRibbon(m.col)}}</div>
      <div class="thread-summary"><a href="documents.html#${{encodeURIComponent(m.id)}}">${{escapeHtml(m.title)}}</a></div>
      ${{m.url ? `<div class="linklist"><a href="${{escapeHtml(m.url)}}" target="_blank" rel="noopener">페이지</a></div>` : ''}}
    </div>`).join('');
  document.getElementById('listControls').classList.add('hidden');
  document.getElementById('listView').classList.add('hidden');
  document.getElementById('backLink').classList.add('show');
  document.getElementById('detailView').className = 'detail';
  document.getElementById('detailView').innerHTML = `<div class="detail-panel">
    <span class="badge">${{escapeHtml(c.kindLabel)}}</span>
    <h2 class="section-title">${{escapeHtml(c.title)}}</h2>
    <p class="sub">${{c.size}}건 · ${{escapeHtml(c.date_min)}} ~ ${{escapeHtml(c.date_max)}}</p>
    <div class="section-title">구성 문서</div>
    ${{members}}
  </div>`;
  history.replaceState(null, '', 'clusters.html#' + encodeURIComponent(id));
}}
function showList() {{
  document.getElementById('listControls').classList.remove('hidden');
  document.getElementById('listView').classList.remove('hidden');
  document.getElementById('backLink').classList.remove('show');
  document.getElementById('detailView').className = 'detail hidden';
  const q = state.kind ? '?kind=' + encodeURIComponent(state.kind) : '';
  history.replaceState(null, '', 'clusters.html' + q);
}}
document.getElementById('searchBox').addEventListener('input', ev => {{ state.q = ev.target.value; renderList(); }});
document.getElementById('kindToggle').querySelectorAll('button').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.getElementById('kindToggle').querySelectorAll('button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.kind = btn.dataset.kind || '';
    renderList();
  }});
}});
document.getElementById('listView').addEventListener('click', ev => {{
  const row = ev.target.closest('.dir-row');
  if (row && row.dataset.id) showDetail(row.dataset.id);
}});
document.getElementById('backLink').addEventListener('click', showList);
(function boot() {{
  const params = new URLSearchParams(location.search);
  if (params.get('kind')) {{
    state.kind = params.get('kind');
    document.getElementById('kindToggle').querySelectorAll('button').forEach(b => {{
      b.classList.toggle('active', (b.dataset.kind || '') === state.kind);
    }});
  }}
  renderList();
  const hash = decodeURIComponent((location.hash || '').slice(1));
  if (hash && byId[hash]) showDetail(hash);
}})();
</script>
"""
    return page("clusters.html", "클러스터", "", body, js, index)


def render_about(docs: list[dict], clusters: list[dict], index: dict) -> str:
    counts = Counter(d["col"] for d in docs)
    rows = "".join(
        f"<tr><td>{label}</td><td>{counts.get(key, 0):,}</td><td>{blurb}</td></tr>"
        for key, label, _sec, blurb in COLLECTIONS
    )
    body = f"""
  <p class="meta">{TODAY}</p>
  <p class="lede">외교부·IAAE가 모아 둔 문서와 AGORA·OECD Policy Navigator를 한곳에 둔 자료 저장소입니다. 화면 톤은 국제협력 트래커와 같습니다.</p>
  <h2 class="section-h">컬렉션</h2>
  <table class="data-table">
    <thead><tr><th>컬렉션</th><th>건수</th><th>내용</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <h2 class="section-h">클러스터</h2>
  <p class="lede">같은 법·선언·전략을 URL·식별자·제목으로 묶고, 한국어 항목은 OpenRouter로 대조했습니다. {len(clusters)}개 클러스터, 그중 교차 컬렉션 {sum(1 for c in clusters if c["kind"]=="same-document")}개.</p>
  <h2 class="section-h">출처</h2>
  <p class="lede">AGORA: Emerging Technology Observatory, CC BY-NC 4.0, <a href="https://doi.org/10.5281/zenodo.20714047">Zenodo 1.30.0</a>. Policy Navigator: OECD.AI. 외교부 게시판 · IAAE 연구자료실.</p>
"""
    return page("about.html", "소개", "", body, "", index)


def main() -> None:
    print("loading…")
    docs = load_docs()
    clusters = load_clusters()
    index = search_index(docs, clusters)
    DIST.mkdir(parents=True, exist_ok=True)
    pages = {
        "index.html": render_index(docs, clusters, index),
        "documents.html": render_documents(docs, index),
        "clusters.html": render_clusters(clusters, index),
        "about.html": render_about(docs, clusters, index),
    }
    for name, html in pages.items():
        (DIST / name).write_text(html, encoding="utf-8")
        print(name, f"{(DIST / name).stat().st_size / 1024:.0f} KB")
    print("wrote", DIST)


if __name__ == "__main__":
    main()
