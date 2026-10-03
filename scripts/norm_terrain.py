"""메인 상단 '분야별 규범 지형' — 분야(주제) × 규범 수준, 분야 × 지역.

세는 단위는 관할(국가·국제기구) 수. 계산은 브라우저에서 메인 페이지의 DOCS로 한다
(목록 필터와 같은 판정 함수를 쓰도록). 칸을 누르면 아래 문서 목록이 그 조건으로 걸러진다.
"""
from __future__ import annotations

from issuer_levels import ISSUER_COLORS
from topics import TOPIC_COLORS, TOPIC_LABELS, TOPIC_ORDER
from ui_common import safe_json

# 규범 수준 (구속력 높은 순). 국제규범은 발행 주체가 국제기구·다자인 모든 문서.
LEVELS = [
    ("intl", "국제규범"),
    ("law", "법률"),
    ("rule", "행정규칙"),
    ("bill", "법안"),
    ("soft", "지침·표준"),
    ("plan", "전략·보고서"),
]
# 기구·제도·기타는 규범 수준 축에 넣지 않는다.
KIND_LEVEL = {
    "법": "law", "행정규칙": "rule", "법안": "bill", "가이드라인·원칙": "soft", "표준": "soft",
    "전략·정책": "plan", "정책보고서": "plan", "선언·성명": "plan", "조약·협약": "intl",
}
# 수준 색 = 문서 종류 리본 색 (build_site.KIND_COLORS와 같은 값)
LEVEL_KIND = {
    "intl": "조약·협약", "law": "법", "rule": "행정규칙", "bill": "법안",
    "soft": "가이드라인·원칙", "plan": "전략·정책",
}

REGIONS = [
    ("anglo", "영미권", ["United States", "United Kingdom", "Canada", "Australia", "New Zealand", "Ireland"]),
    ("europe", "EU·유럽", [
        "European Union", "Germany", "France", "Austria", "Spain", "Slovenia", "Belgium", "Denmark", "Greece",
        "Netherlands", "Latvia", "Finland", "Italy", "Poland", "Portugal", "Sweden", "Czechia", "Malta", "Hungary",
        "Estonia", "Bulgaria", "Lithuania", "Slovakia", "Norway", "Croatia", "Romania", "Serbia", "Luxembourg",
        "Switzerland", "Iceland", "Cyprus", "Vatican City", "Ukraine", "Russia"]),
    ("eastasia", "동아시아", ["South Korea", "China", "Japan", "Taiwan"]),
    ("sasia", "동남·남아시아", ["Singapore", "India", "Thailand", "Malaysia", "Indonesia", "Vietnam", "Cambodia",
                            "Philippines", "Brunei", "Pakistan", "Bangladesh", "Sri Lanka"]),
    ("mideast", "중동·중앙아", ["Saudi Arabia", "Israel", "Turkey", "United Arab Emirates", "Egypt", "Kazakhstan",
                            "Uzbekistan", "Qatar", "Jordan", "Oman", "Bahrain", "Kuwait", "Iran"]),
    ("latam", "중남미", ["Brazil", "Colombia", "Argentina", "Mexico", "Peru", "Chile", "Costa Rica", "Ecuador",
                      "Uruguay", "Dominican Republic", "Cuba", "Panama", "Paraguay", "Bolivia", "Venezuela"]),
    ("africa", "아프리카", ["Kenya", "Rwanda", "Nigeria", "South Africa", "Tunisia", "Zimbabwe", "Zambia", "Mauritania",
                        "Libya", "Ethiopia", "Senegal", "Ivory Coast", "Lesotho", "Mauritius", "Benin", "Ghana",
                        "Morocco", "Uganda", "Tanzania", "Egypt"]),
]

STAGES = ["입법 확산", "입법 시작", "법안·규칙", "지침·표준", "전략·정책", "국제 논의", "논의 시작"]
STAGE_HEAD = [
    "법률이 여러 관할로 퍼진 분야 (3곳 이상)",
    "법률이 마련되기 시작한 분야",
    "법안·행정규칙이 논의되는 분야",
    "지침·표준으로 다루는 분야",
    "전략·정책으로 방향을 잡은 분야",
    "국제 논의가 이끄는 분야",
    "논의가 이제 시작되는 분야",
]


def terrain_payload(kind_colors: dict[str, tuple[str, str]]) -> dict:
    topics = [["_general", "포괄 규범", "🌐", "#3a5270"]]
    topics += [[t, TOPIC_LABELS[t][0], TOPIC_LABELS[t][1], TOPIC_COLORS.get(t, "#534f4a")]
               for t in TOPIC_ORDER if t in TOPIC_LABELS]
    return {
        "levels": LEVELS,
        "levelColors": {lv: kind_colors[k][0] for lv, k in LEVEL_KIND.items()},
        "kindLevel": KIND_LEVEL,
        "regions": [[k, lab] for k, lab, _ in REGIONS],
        "regionOf": {c: k for k, _, cs in REGIONS for c in cs},
        "topics": topics,
        "stages": STAGES,
        "stageHead": STAGE_HEAD,
        "intlColor": ISSUER_COLORS["international"][0],
    }


def terrain_html() -> str:
    return """<section class="terrain" aria-label="분야별 규범 지형">
  <div class="nt-card">
    <div class="nt-head">
      <h2>분야별 규범 지형</h2>
      <div class="nt-views" role="tablist">
        <button class="on" data-view="level" role="tab" type="button">규범 수준</button>
        <button data-view="region" role="tab" type="button">지역 비교</button>
      </div>
    </div>
    <p class="nt-lead" id="ntLead"></p>
    <div class="nt-regions" id="ntRegions"></div>
    <div class="nt-scroller"><table class="nt-mx" id="ntMx"></table></div>
    <div class="nt-legend" id="ntLegend"></div>
  </div>
  <aside class="nt-panel"><div class="nt-panel-inner" id="ntPanel" aria-live="polite"></div></aside>
</section>"""


TERRAIN_CSS = """
.terrain { display: grid; grid-template-columns: minmax(0, 1.9fr) minmax(0, 1fr); gap: 14px; align-items: stretch;
  margin: 0 0 24px; }
.nt-card, .nt-panel { background: var(--surface-1); border: 1px solid var(--hairline); border-radius: 14px; }
.nt-card { padding: 16px; min-width: 0; }
.nt-head { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.nt-head h2 { font-size: 1rem; margin: 0; letter-spacing: -.2px; }
.nt-views { display: inline-flex; border: 1px solid var(--hairline); border-radius: 999px; overflow: hidden; }
.nt-views button { font: inherit; font-size: .74rem; border: 0; background: transparent; padding: 3px 11px; cursor: pointer; color: var(--ink-muted); }
.nt-views button.on { background: var(--navy); color: var(--on-navy); }
.nt-lead { font-size: .76rem; color: var(--text-muted); margin: 4px 0 10px; line-height: 1.5; }
.nt-regions { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 12px; }
.nt-regions button { font: inherit; font-size: .74rem; border: 1px solid var(--hairline); background: var(--surface-2);
  border-radius: 999px; padding: 2px 10px; cursor: pointer; color: var(--ink); line-height: 1.5; }
.nt-regions button.on { background: var(--ink); color: var(--on-dark); border-color: var(--ink); }
.nt-regions .lab { font-size: .72rem; color: var(--text-muted); align-self: center; margin-right: 2px; }
table.nt-mx { width: 100%; border-collapse: separate; border-spacing: 3px; table-layout: fixed; }
.nt-mx th { font-size: .68rem; font-weight: 600; color: var(--ink-muted); text-align: center; padding: 0 0 2px; line-height: 1.25; word-break: keep-all; }
.nt-mx thead .nt-dot { display: block; margin: 0 auto 2px; }
.nt-mx th.row { text-align: left; font-size: .78rem; color: var(--ink); font-weight: 500; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; width: 9.4rem; padding: 0 4px 0 6px; border-left: 3px solid var(--c, transparent); }
.nt-mx th.row .ic { margin-right: 4px; }
.nt-mx th.stage { width: 4.9rem; text-align: left; }
.nt-mx td { padding: 0; }
.nt-mx td.st { padding-left: 4px; }
.nt-mx tr.general th.row { font-weight: 700; }
.nt-mx tr.sep td { height: 6px; }
.nt-cell { width: 100%; height: 30px; border: 0; border-radius: 6px; cursor: pointer; font: inherit; font-size: .74rem;
  font-weight: 600; font-variant-numeric: tabular-nums; display: flex; align-items: center; justify-content: center;
  white-space: nowrap; background: var(--bg, #efe9dc); color: var(--fg, var(--text-muted)); padding: 0; }
.nt-cell.empty { background: repeating-linear-gradient(135deg, #efe9dc 0 5px, #f6f2e8 5px 10px); color: #b3a994; font-weight: 400; }
.nt-cell:hover { outline: 2px solid var(--navy); outline-offset: 1px; }
.nt-cell.sel { outline: 2.5px solid var(--accent); outline-offset: 1px; }
.nt-cell.ref { opacity: .55; }
.nt-mx.by-region .nt-cell { font-size: .68rem; letter-spacing: -.2px; }
.nt-stage { font-size: .7rem; padding: 0 7px; border-radius: 999px; white-space: nowrap; display: inline-block;
  border: 1.5px solid var(--c); color: var(--c); background: color-mix(in srgb, var(--c) 10%, #fffcf6); font-weight: 600; line-height: 1.55; }
.nt-stage.solid { background: var(--c); color: #fffcf6; }
.nt-stage.none { --c: #a99f8a; font-weight: 400; }
.nt-legend { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: .7rem; color: var(--text-muted); margin-top: 10px; align-items: center; }
.nt-legend i { width: 12px; height: 10px; border-radius: 2px; display: inline-block; margin-right: 4px; vertical-align: -1px; }
.nt-dot { display: inline-block; width: 9px; height: 9px; border-radius: 2px; background: var(--c); margin-right: 5px; }
.nt-panel { position: relative; font-size: .8rem; overflow: hidden; }
.nt-panel-inner { position: absolute; inset: 0; padding: 16px; overflow-y: auto; scrollbar-width: thin; }
.nt-panel h3 { font-size: 1rem; margin: 0 0 2px; line-height: 1.5; }
.nt-panel .sub { color: var(--text-muted); font-size: .74rem; margin-bottom: 10px; line-height: 1.5; }
.nt-panel h4 { font-size: .76rem; margin: 14px 0 6px; color: var(--ink-muted); }
.nt-panel ul { list-style: none; padding: 0; margin: 0; }
.nt-panel li { padding: 3px 0; border-top: 1px solid var(--gridline); display: flex; gap: 6px; align-items: baseline; line-height: 1.5; }
.nt-panel li:first-child { border-top: 0; }
.nt-panel li .d { color: var(--text-muted); font-variant-numeric: tabular-nums; flex: none; font-size: .72rem; }
.nt-panel li a { color: var(--ink); text-decoration: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.nt-panel li a:hover { color: var(--accent); text-decoration: underline; }
.nt-tp { display: inline-flex; align-items: center; gap: 4px; border-radius: 999px; padding: 0 8px 0 6px; line-height: 1.6;
  background: color-mix(in srgb, var(--c) 12%, #fffcf6); border: 1px solid color-mix(in srgb, var(--c) 45%, #fffcf6);
  color: color-mix(in srgb, var(--c) 80%, #243044); font-weight: 600; font-size: .76rem; margin: 0 3px 4px 0; font-family: inherit; cursor: pointer; }
button.nt-tp:hover { border-color: var(--c); }
span.nt-tp { cursor: default; }
.nt-jur { display: flex; flex-wrap: wrap; gap: 4px; }
.nt-jur button { font: inherit; font-size: .72rem; border: 1px solid var(--hairline); border-radius: 999px; padding: 1px 8px;
  color: var(--ink); background: var(--surface-2); cursor: pointer; line-height: 1.5; }
.nt-jur button:hover { border-color: var(--navy); }
.nt-jur b { font-weight: 600; margin-left: 2px; font-variant-numeric: tabular-nums; }
.nt-ladder { display: grid; grid-template-columns: auto 1fr auto; gap: 3px 8px; align-items: center; font-size: .74rem; }
.nt-ladder .bar { height: 7px; background: var(--gridline); border-radius: 3px; overflow: hidden; }
.nt-ladder .bar i { display: block; height: 100%; }
.nt-ladder .v { text-align: right; font-variant-numeric: tabular-nums; color: var(--ink-muted); }
.nt-actions { display: flex; gap: 12px; margin-top: 12px; flex-wrap: wrap; }
.nt-actions button { font: inherit; font-size: .8rem; font-weight: 600; color: var(--navy); background: none; border: 0; padding: 0; cursor: pointer; }
.nt-actions button:hover { color: var(--accent); }
.nt-note { color: var(--text-muted); font-size: .72rem; margin-top: 12px; line-height: 1.5; }
.nt-filter { display: none; align-items: center; gap: 8px; font-size: .78rem; margin: 0 0 10px; padding: 6px 10px;
  border-radius: 8px; background: color-mix(in srgb, var(--gold, #d4a45a) 16%, var(--surface-1)); }
.nt-filter.on { display: flex; }
.nt-filter button { font: inherit; font-size: .76rem; border: 0; background: none; color: var(--navy); cursor: pointer; font-weight: 600; margin-left: auto; }
#ntTip { position: fixed; pointer-events: none; background: var(--ink); color: var(--on-dark); font-size: .73rem;
  padding: 6px 9px; border-radius: 6px; z-index: 50; display: none; max-width: 280px; line-height: 1.45; }
@media (max-width: 820px) {
  .terrain { grid-template-columns: 1fr; }
  .nt-panel-inner { position: static; }
  .nt-scroller { overflow-x: auto; margin: 0 -16px; padding: 0 16px; }
  table.nt-mx { min-width: 560px; }
  .nt-mx th.row { position: sticky; left: 0; z-index: 1; background: var(--surface-1); }
}
"""


def terrain_js(kind_colors: dict[str, tuple[str, str]]) -> str:
    """메인 페이지 스크립트 안에 넣는다. DOCS·state·renderList·monthKey·escapeHtml을 쓴다."""
    return "const NT = " + safe_json(terrain_payload(kind_colors)) + ";\n" + _TERRAIN_JS


_TERRAIN_JS = r"""
(function normTerrain() {
  const mxEl = document.getElementById('ntMx');
  if (!mxEl) return;
  const LV = Object.fromEntries(NT.levels);
  const LV_KEYS = NT.levels.map(l => l[0]);
  const NAT_LV = LV_KEYS.filter(k => k !== 'intl');
  const RG = Object.fromEntries(NT.regions);
  const TP = Object.fromEntries(NT.topics.map(t => [t[0], t[1]]));
  const TI = Object.fromEntries(NT.topics.map(t => [t[0], t[2]]));
  const TC = Object.fromEntries(NT.topics.map(t => [t[0], t[3]]));
  const LC = NT.levelColors;
  const STAGE_LV = ['law', 'law', 'bill', 'soft', 'plan', 'intl', ''];
  const esc = escapeHtml;
  const brk = s => esc(s).replace(/·/g, '·<wbr>');
  const ui = { view: 'level', region: '' };

  // 문서마다 수준·지역·분야를 한 번만 정한다. 목록 필터도 이 값을 쓴다.
  DOCS.forEach(d => {
    const intl = d.issuer_level === 'international';
    d._lv = intl ? 'intl' : (NT.kindLevel[d.doc_kind] || '');
    d._rg = intl ? 'intl' : (NT.regionOf[d.country] || '');
    const ts = (d.topics || []).map(t => t.id).filter(t => TP[t]);
    d._tp = ts.length ? ts : ['_general'];
  });
  const ND = DOCS.filter(d => d._lv && d._rg);

  function where(topic, level, region) {
    return ND.filter(d => d._tp.includes(topic) && (!level || d._lv === level) && (!region || d._rg === region));
  }
  function juris(ds) {
    const m = new Map();
    ds.forEach(d => {
      const k = d.country || '(국제)';
      const e = m.get(k) || { key: d.country, ko: d.country_ko || k, flag: d.flag, n: 0 };
      e.n++; m.set(k, e);
    });
    return [...m.values()].sort((a, b) => b.n - a.n);
  }
  function stageOf(topic, region) {
    const j = lv => juris(where(topic, lv, region)).length;
    const law = j('law');
    if (law >= 3) return 0;
    if (law >= 1) return 1;
    if (j('rule') || j('bill')) return 2;
    if (j('soft')) return 3;
    if (j('plan')) return 4;
    if (juris(where(topic, 'intl', '')).length) return 5;
    return 6;
  }
  function topLevel(topic, region) {
    for (const lv of (region === 'intl' ? ['intl'] : NAT_LV)) {
      const ds = where(topic, lv, region);
      if (ds.length) return { lv, n: juris(ds).length };
    }
    return null;
  }
  function tint(color, n) {
    const pct = Math.round(Math.min(100, 30 + 70 * Math.log(n) / Math.log(40)));
    return { bg: `color-mix(in srgb, ${color} ${pct}%, #fffcf6)`, fg: pct >= 55 ? '#fffcf6' : `color-mix(in srgb, ${color} 85%, #1a2230)` };
  }
  const dot = lv => `<span class="nt-dot" style="--c:${LC[lv]}"></span>`;
  const lvName = lv => dot(lv) + esc(LV[lv]);
  const tpChip = (t, btn) => btn
    ? `<button type="button" class="nt-tp" data-topic="${esc(t)}" style="--c:${TC[t]}">${TI[t]} ${esc(TP[t])}</button>`
    : `<span class="nt-tp" style="--c:${TC[t]}">${TI[t]} ${esc(TP[t])}</span>`;
  function stageTag(st) {
    if (st === 6) return `<span class="nt-stage none">${NT.stages[st]}</span>`;
    return `<span class="nt-stage ${st === 0 ? 'solid' : ''}" style="--c:${LC[STAGE_LV[st]]}">${NT.stages[st]}</span>`;
  }
  const selKey = () => state.terrain ? [state.terrain.topic, state.terrain.level, state.terrain.region].join('|') : '';
  const cell = (bg, fg, text, key, cls = '') =>
    `<button type="button" class="nt-cell ${cls}${selKey() === key ? ' sel' : ''}" data-k="${esc(key)}" style="--bg:${bg};--fg:${fg}">${text}</button>`;
  const gapCell = key => cell('', '', '–', key, 'empty');
  const gapSwatch = '<i style="background:repeating-linear-gradient(135deg,#efe9dc 0 3px,#f6f2e8 3px 6px)"></i>';

  function rowOrder(region) {
    const rest = NT.topics.slice(1).map(t => t[0]);
    rest.sort((a, b) => stageOf(a, region) - stageOf(b, region) || where(b, '', region).length - where(a, '', region).length);
    return ['_general', ...rest];
  }
  function rowHead(t) {
    return `<th class="row" style="--c:${TC[t]}" title="${esc(TP[t])}"><span class="ic">${TI[t]}</span>${esc(TP[t])}</th>`;
  }
  function renderLevel() {
    const region = ui.region;
    const head = '<tr><th class="row"></th>' + NT.levels.map(([k, l]) =>
      `<th>${dot(k)}${brk(l)}${k === 'intl' && region ? '<br><span style="font-weight:400">(전 세계)</span>' : ''}</th>`).join('')
      + '<th class="stage">단계</th></tr>';
    const body = rowOrder(region).map((t, i) => {
      const cells = LV_KEYS.map(lv => {
        const r = lv === 'intl' ? '' : region;
        const key = `${t}|${lv}|${r}`;
        const n = juris(where(t, lv, r)).length;
        if (!n) return `<td>${gapCell(key)}</td>`;
        const { bg, fg } = tint(LC[lv], n);
        return `<td>${cell(bg, fg, n, key, lv === 'intl' && region ? 'ref' : '')}</td>`;
      }).join('');
      const sep = i === 0 ? '<tr class="sep"><td colspan="8"></td></tr>' : '';
      return `<tr class="${i === 0 ? 'general' : ''}">${rowHead(t)}${cells}<td class="st">${stageTag(stageOf(t, region))}</td></tr>${sep}`;
    }).join('');
    mxEl.innerHTML = `<thead>${head}</thead><tbody>${body}</tbody>`;
    document.getElementById('ntLead').textContent = region
      ? `${RG[region]}의 관할이 분야마다 어느 규범 수준까지 갖췄는지 보여 줍니다. 국제규범 열은 비교용으로 전 세계 기준입니다.`
      : '분야마다 각 규범 수준을 갖춘 관할(국가·국제기구) 수입니다. 칸을 누르면 아래 목록이 그 조건으로 걸러집니다.';
    document.getElementById('ntLegend').innerHTML = NT.levels.map(([k, l]) =>
      `<span><i style="background:${LC[k]}"></i>${esc(l)}</span>`).join('')
      + `<span>${gapSwatch}아직 없음</span><span>· 진할수록 관할이 많음</span>`;
  }
  function renderRegion() {
    const cols = [['intl', '국제']].concat(NT.regions);
    const head = '<tr><th class="row"></th>' + cols.map(([, l]) => `<th>${brk(l)}</th>`).join('') + '</tr>';
    const body = rowOrder('').map((t, i) => {
      const cells = cols.map(([rk]) => {
        const top = topLevel(t, rk);
        const key = `${t}||${rk}`;
        if (!top) return `<td>${gapCell(key)}</td>`;
        const { bg, fg } = tint(LC[top.lv], top.n);
        return `<td>${cell(bg, fg, `${top.lv === 'intl' ? '' : LV[top.lv].slice(0, 2) + ' '}${top.n}`, key)}</td>`;
      }).join('');
      const sep = i === 0 ? `<tr class="sep"><td colspan="${cols.length + 1}"></td></tr>` : '';
      return `<tr class="${i === 0 ? 'general' : ''}">${rowHead(t)}${cells}</tr>${sep}`;
    }).join('');
    mxEl.innerHTML = `<thead>${head}</thead><tbody>${body}</tbody>`;
    document.getElementById('ntLead').textContent = '지역마다 그 분야에서 도달한 가장 높은 규범 수준과, 그 수준을 갖춘 관할 수입니다.';
    document.getElementById('ntLegend').innerHTML = '칸 색 = 도달한 최고 수준 · ' + NT.levels.map(([k, l]) =>
      `<span><i style="background:${LC[k]}"></i>${esc(l)}</span>`).join('') + `<span>${gapSwatch}아직 없음</span>`;
  }
  function renderRegions() {
    const box = document.getElementById('ntRegions');
    if (ui.view !== 'level') { box.style.display = 'none'; return; }
    box.style.display = '';
    box.innerHTML = '<span class="lab">지역</span>' + [['', '전체']].concat(NT.regions).map(([k, l]) =>
      `<button type="button" data-region="${k}" class="${ui.region === k ? 'on' : ''}">${esc(l)}</button>`).join('');
  }

  function overview() {
    const region = ui.view === 'level' ? ui.region : '';
    const ts = NT.topics.slice(1).map(t => t[0]);
    const groups = NT.stageHead.map((h, st) => [st, ts.filter(t => stageOf(t, region) === st)]).filter(g => g[1].length);
    return `<h3>${region ? esc(RG[region]) : '전체'} 개요</h3>
      <div class="sub">분야를 지금 도달한 규범 수준별로 묶었습니다. 분야를 누르면 아래 목록이 그 분야로 걸러집니다.</div>
      ${groups.map(([st, list]) => `<h4>${STAGE_LV[st] ? dot(STAGE_LV[st]) : ''}${esc(NT.stageHead[st])}</h4><div>${list.map(t => tpChip(t, true)).join('')}</div>`).join('')}
      <p class="nt-note">분야 태그가 붙은 문서 기준입니다. 포괄 규범(EU AI법 등)은 모든 분야에 걸치므로 별도 줄로 봅니다. 기구·제도처럼 규범 수준으로 나누기 어려운 문서는 지형에서 뺐습니다.</p>`;
  }
  function detail() {
    const { topic, level, region } = state.terrain;
    const scope = region === 'intl' ? '국제기구·다자' : (region ? RG[region] : '전 세계');
    const ds = where(topic, level, region);
    const js = juris(ds);
    let ladder = '';
    if (!level) {
      const r = region === 'intl' ? '' : region;
      const rows = LV_KEYS.map(lv => [lv, juris(where(topic, lv, lv === 'intl' ? '' : r)).length]);
      const mx = Math.max(1, ...rows.map(x => x[1]));
      ladder = '<h4>규범 수준별 관할</h4><div class="nt-ladder">' + rows.map(([lv, n]) =>
        `<span>${lvName(lv)}</span><span class="bar"><i style="width:${n / mx * 100}%;background:${LC[lv]}"></i></span><span class="v">${n ? n + '곳' : '–'}</span>`).join('') + '</div>';
    }
    const latest = ds.slice().sort((a, b) => String(b.published || '').localeCompare(String(a.published || ''))).slice(0, 6);
    return `<h3>${tpChip(topic)}${level ? ' <span style="font-size:.85rem;font-weight:600">' + lvName(level) + '</span>' : ''}</h3>
      <div class="sub">${esc(scope)} · 관할 ${js.length}곳 · 문서 ${ds.length}건</div>
      ${ladder}
      ${js.length ? `<h4>${region === 'intl' ? '발행 주체' : '관할'}</h4><div class="nt-jur">${js.slice(0, 18).map(j =>
        `<button type="button" data-country="${esc(j.key || '')}">${j.flag ? j.flag + ' ' : ''}${esc(j.ko)}<b>${j.n}</b></button>`).join('')}${js.length > 18 ? ` <span style="color:var(--text-muted)">외 ${js.length - 18}곳</span>` : ''}</div>` : '<p>아직 해당 문서가 없습니다.</p>'}
      ${latest.length ? `<h4>최근 문서</h4><ul>${latest.map(d => `<li><span class="d">${esc(String(d.published || '').slice(0, 7))}</span><a href="#${encodeURIComponent(d.id)}" data-doc="${esc(d.id)}" title="${esc(d.short_name || d.title || '')}">${d.flag ? d.flag + ' ' : ''}${esc(d.short_name || d.title || '')}</a></li>`).join('')}</ul>` : ''}
      <div class="nt-actions"><button type="button" data-act="list">목록에서 보기 ↓</button><button type="button" data-act="clear">선택 해제</button></div>`;
  }
  function renderPanel() {
    document.getElementById('ntPanel').innerHTML = state.terrain ? detail() : overview();
  }

  // 목록 위 '지형 선택' 표시줄
  const bar = document.createElement('div');
  bar.className = 'nt-filter';
  bar.id = 'ntFilter';
  const controls = document.getElementById('listControls');
  controls.parentNode.insertBefore(bar, controls);
  function renderBar() {
    const t = state.terrain;
    bar.classList.toggle('on', !!t);
    if (!t) { bar.innerHTML = ''; return; }
    const scope = t.region === 'intl' ? '국제' : (t.region ? RG[t.region] : '전 세계');
    bar.innerHTML = `<span>규범 지형 선택: ${tpChip(t.topic)}${t.level ? ' ' + lvName(t.level) : ''} · ${esc(scope)}</span><button type="button">해제 ✕</button>`;
    bar.querySelector('button').onclick = () => select(null);
  }

  function render() {
    renderRegions();
    mxEl.classList.toggle('by-region', ui.view === 'region');
    ui.view === 'level' ? renderLevel() : renderRegion();
    renderPanel();
    renderBar();
  }
  function select(sel) {
    state.terrain = sel;
    render();
    renderList();
  }
  window.ntMatches = d => {
    const t = state.terrain;
    if (!t) return true;
    if (!d._lv || !d._rg || !d._tp.includes(t.topic)) return false;
    if (t.level && d._lv !== t.level) return false;
    if (t.region && d._rg !== t.region) return false;
    return true;
  };

  mxEl.addEventListener('click', ev => {
    const c = ev.target.closest('.nt-cell');
    if (!c) return;
    const [topic, level, region] = c.dataset.k.split('|');
    select(selKey() === c.dataset.k ? null : { topic, level, region });
  });
  document.getElementById('ntRegions').addEventListener('click', ev => {
    const b = ev.target.closest('button[data-region]');
    if (!b) return;
    ui.region = b.dataset.region;
    select(null);
  });
  document.querySelectorAll('.nt-views button').forEach(b => b.addEventListener('click', () => {
    ui.view = b.dataset.view;
    document.querySelectorAll('.nt-views button').forEach(x => x.classList.toggle('on', x === b));
    select(null);
  }));
  document.getElementById('ntPanel').addEventListener('click', ev => {
    const tp = ev.target.closest('button.nt-tp[data-topic]');
    if (tp) { select({ topic: tp.dataset.topic, level: '', region: ui.view === 'level' ? ui.region : '' }); return; }
    const cb = ev.target.closest('.nt-jur button[data-country]');
    if (cb) {
      const btn = document.querySelector(`#countryToggle button[data-country="${CSS.escape(cb.dataset.country)}"]`);
      if (btn) btn.click();
      document.getElementById('listControls').scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    const a = ev.target.closest('a[data-doc]');
    if (a) {
      ev.preventDefault();
      const d = DOCS.find(x => x.id === a.dataset.doc);
      if (!d) return;
      state.monthOpen[monthKey(d)] = true;
      renderList();
      const el = document.querySelector('.event-card[data-id="' + CSS.escape(d.id) + '"]');
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    const act = ev.target.closest('button[data-act]');
    if (act && act.dataset.act === 'clear') select(null);
    if (act && act.dataset.act === 'list') document.getElementById('listControls').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  const tip = document.createElement('div');
  tip.id = 'ntTip';
  document.body.appendChild(tip);
  mxEl.addEventListener('mousemove', ev => {
    const c = ev.target.closest('.nt-cell');
    if (!c) { tip.style.display = 'none'; return; }
    const [t, lv, r] = c.dataset.k.split('|');
    const level = lv || (ui.view === 'region' ? (topLevel(t, r) || {}).lv : '');
    const ds = where(t, level, r);
    const js = juris(ds);
    tip.innerHTML = `<b>${esc(TP[t])}</b>${level ? ' · ' + esc(LV[level]) : ''}${r ? ' · ' + esc(r === 'intl' ? '국제' : RG[r]) : ''}<br>`
      + (js.length ? `관할 ${js.length}곳 · 문서 ${ds.length}건<br>${js.slice(0, 5).map(j => (j.flag || '') + ' ' + esc(j.ko)).join(', ')}${js.length > 5 ? ' …' : ''}` : '아직 없음');
    tip.style.display = 'block';
    tip.style.left = Math.min(ev.clientX + 12, innerWidth - 290) + 'px';
    tip.style.top = (ev.clientY + 14) + 'px';
  });
  mxEl.addEventListener('mouseleave', () => { tip.style.display = 'none'; });

  render();
})();
"""
