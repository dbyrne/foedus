"""Self-contained HTML/CSS/JS for the two spectator views. No external CDNs,
no build step -- vanilla JS polling the JSON API routes in server.py.

Colorblind-safe throughout (Okabe-Ito, foedus/spectate/palette.py): stance/
role meaning is never carried by color alone -- every color is paired with a
text label or distinct shape (see the stance matrix cell text and the ★/🎭
badges).
"""

from __future__ import annotations

from foedus.spectate.palette import OKABE_ITO

_BASE_CSS = f"""
:root {{
  --blue: {OKABE_ITO['blue']}; --orange: {OKABE_ITO['orange']};
  --skyblue: {OKABE_ITO['skyblue']}; --vermillion: {OKABE_ITO['vermillion']};
  --bg: #ffffff; --fg: #111111; --card: #f4f4f6; --border: #d8d8dc;
}}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg: #14151a; --fg: #eaeaea; --card: #1e1f26; --border: #33343c; }}
}}
* {{ box-sizing: border-box; }}
body {{
  background: var(--bg); color: var(--fg); font-family: system-ui, sans-serif;
  margin: 0; padding: 12px 16px 40px;
}}
h1 {{ font-size: 1.3rem; margin: 0 0 4px; }}
h2 {{ font-size: 1.05rem; margin: 20px 0 8px; }}
h3, h4 {{ margin: 8px 0 4px; }}
.card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px;
  padding: 10px 14px; margin-bottom: 14px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; }}
th, td {{ border: 1px solid var(--border); padding: 4px 8px; text-align: left; }}
th {{ background: rgba(128,128,128,0.15); }}
.strip {{ display: flex; flex-wrap: wrap; gap: 16px; font-size: 0.85rem; }}
.strip div {{ white-space: nowrap; }}
.strip b {{ display: block; font-size: 0.7rem; opacity: 0.7; text-transform: uppercase; }}
blockquote {{ margin: 2px 0 10px; padding: 4px 10px; border-left: 3px solid var(--skyblue); font-style: italic; }}
.game-tag {{ font-size: 0.75rem; opacity: 0.65; margin-left: 6px; }}
.handle {{ font-weight: 600; }}
#notes-list, #entrant-declarations {{ list-style: none; padding: 0; }}
.spark-label {{ font-size: 0.72rem; opacity: 0.7; text-align: center; }}
.charts {{ display: flex; flex-wrap: wrap; gap: 18px; }}
.charts > div {{ flex: 1 1 220px; min-width: 200px; }}
button {{ font-size: 0.95rem; padding: 4px 12px; margin-right: 6px; cursor: pointer; }}
select {{ font-size: 0.95rem; padding: 3px 6px; }}
.stance-matrix td {{ text-align: center; font-size: 0.75rem; }}
.stance-matrix .diag {{ background: rgba(128,128,128,0.15); }}
.stance-ally {{ color: var(--blue); font-weight: 700; }}
.stance-hostile {{ color: var(--vermillion); font-weight: 700; }}
.stance-neutral {{ color: inherit; opacity: 0.7; }}
.entrant-col {{ display: inline-block; vertical-align: top; width: 220px;
  border: 1px solid var(--border); border-radius: 6px; padding: 8px; margin: 0 8px 8px 0; }}
.entrant-col ul {{ margin: 2px 0 6px; padding-left: 18px; font-size: 0.82rem; }}
.label {{ font-size: 0.7rem; text-transform: uppercase; opacity: 0.65; }}
.tag {{ font-size: 0.68rem; padding: 0 4px; border-radius: 4px; margin-left: 4px; }}
.tag.pub {{ background: rgba(0,114,178,0.18); }}
.tag.priv {{ background: rgba(230,159,0,0.25); }}
.tag.support-freerider {{ background: rgba(230,159,0,0.3); font-weight: 600; }}
.tag.support-llm {{ background: rgba(0,114,178,0.22); font-weight: 600; }}
.empty {{ opacity: 0.6; font-size: 0.8rem; }}
a {{ color: var(--blue); }}
nav a {{ margin-right: 14px; }}
"""

_NAV = (
    '<nav><a href="/">Dashboard</a><a href="/replay">Replay theater</a></nav>'
)

DASHBOARD_HTML = f"""<title>Arena Spectator — Campaign Dashboard</title>
<style>{_BASE_CSS}</style>
{_NAV}
<h1 id="match-id">Loading campaign…</h1>
<div class="card strip">
  <div><b>Entrants</b><span id="entrants">—</span></div>
  <div><b>Format</b><span id="format">—</span></div>
  <div><b>Seed commitment</b><span id="commit">—</span></div>
  <div><b>Games complete</b><span id="games-complete">—</span></div>
  <div><b>Elapsed</b><span id="elapsed">—</span></div>
  <div><b>In-flight claude calls</b><span id="inflight">—</span></div>
  <div><b>Last activity</b><span id="last-activity">—</span></div>
</div>

<h2>Standings</h2>
<div class="card">
  <table><thead><tr><th>Entrant</th><th>Cumulative score</th><th>Wins</th></tr></thead>
  <tbody id="standings-body"></tbody></table>
</div>

<h2>Games</h2>
<div class="card" style="overflow-x:auto">
  <table><thead><tr><th>#</th><tr id="games-head-entrants-row"><th></th><th id="games-head-entrants"></th><th>margin</th><th>subsidy</th><th>LLM↔LLM</th></tr></thead>
  <tbody id="games-body"></tbody></table>
</div>

<h2>Trajectories</h2>
<div class="card charts">
  <div id="spark-margin"></div>
  <div id="spark-subsidy"></div>
  <div id="spark-llmllm"></div>
</div>

<h2>Self-notes feed</h2>
<div class="card"><ul id="notes-list"></ul></div>

<script>
const OKABE = {{ blue: "{OKABE_ITO['blue']}", orange: "{OKABE_ITO['orange']}",
  vermillion: "{OKABE_ITO['vermillion']}", skyblue: "{OKABE_ITO['skyblue']}" }};
const POLL_MS = 15000;
let lastData = null;

function esc(s) {{ const d = document.createElement('div'); d.textContent = s ?? ''; return d.innerHTML; }}

function fmtElapsed(startedAtIso) {{
  if (!startedAtIso) return '—';
  const start = new Date(startedAtIso).getTime();
  const secs = Math.max(0, Math.floor((Date.now() - start) / 1000));
  const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60), s = secs % 60;
  return `${{h}}h ${{m}}m ${{s}}s`;
}}

function drawSparkline(id, values, color, label) {{
  const el = document.getElementById(id);
  if (!values.length) {{ el.innerHTML = `<div class="empty">${{label}}: no data yet</div>`; return; }}
  const w = 240, h = 56, pad = 6;
  const max = Math.max(...values, 0), min = Math.min(...values, 0);
  const range = (max - min) || 1;
  const xAt = i => pad + (i / Math.max(1, values.length - 1)) * (w - 2 * pad);
  const yAt = v => h - pad - ((v - min) / range) * (h - 2 * pad);
  const pts = values.map((v, i) => `${{xAt(i).toFixed(1)}},${{yAt(v).toFixed(1)}}`).join(' ');
  const zeroY = yAt(0);
  const dots = values.map((v, i) =>
    `<circle cx="${{xAt(i).toFixed(1)}}" cy="${{yAt(v).toFixed(1)}}" r="2.5" fill="${{color}}"/>`
  ).join('');
  el.innerHTML = `<svg viewBox="0 0 ${{w}} ${{h}}" width="100%" height="${{h}}">
    <line x1="${{pad}}" y1="${{zeroY.toFixed(1)}}" x2="${{w-pad}}" y2="${{zeroY.toFixed(1)}}" stroke="#888" stroke-dasharray="2,2"/>
    <polyline points="${{pts}}" fill="none" stroke="${{color}}" stroke-width="2"/>
    ${{dots}}
  </svg><div class="spark-label">${{label}}</div>`;
}}

function render(d) {{
  lastData = d;
  document.getElementById('match-id').textContent = d.match_id || '(no campaign_plan.json in run dir)';
  document.getElementById('entrants').textContent = (d.entrants || []).join(', ') || '—';
  const b = d.board || {{}};
  document.getElementById('format').textContent =
    `${{d.num_games}} games / ${{b.max_turns ?? '?'}} turns / radius ${{b.map_radius ?? '?'}} / détente@${{b.detente_threshold ?? '?'}}`;
  document.getElementById('commit').textContent = d.seed_commitment ? d.seed_commitment.slice(0, 16) + '…' : '—';
  document.getElementById('games-complete').textContent = `${{d.games_complete}} / ${{d.num_games}}`;
  document.getElementById('elapsed').textContent = fmtElapsed(d.started_at);
  document.getElementById('inflight').textContent = d.inflight_claude_calls ?? '0';
  document.getElementById('last-activity').textContent = d.last_activity_ago_s != null
    ? `${{Math.round(d.last_activity_ago_s)}}s ago` : '—';

  const freeriders = new Set(d.freerider_handles || []);
  const standingsRows = Object.entries(d.standings || {{}})
    .sort((a, b) => b[1].cumulative_score - a[1].cumulative_score)
    .map(([handle, s]) => `<tr><td>${{esc(handle)}}${{freeriders.has(handle) ? ' 🎭' : ''}}</td><td>${{s.cumulative_score.toFixed(1)}}</td><td>${{s.wins}}</td></tr>`)
    .join('');
  document.getElementById('standings-body').innerHTML = standingsRows || '<tr><td colspan="3">no games yet</td></tr>';

  document.getElementById('games-head-entrants').innerHTML =
    (d.entrants || []).map(h => `<th>${{esc(h)}}</th>`).join('');
  const gameRows = (d.games || []).map(g => {{
    const scoreCells = (d.entrants || []).map(h => {{
      const isWinner = g.winners_handles.includes(h);
      const score = g.by_handle_scores[h];
      return `<td>${{score !== undefined ? score.toFixed(1) : '—'}}${{isWinner ? ' ★' : ''}}</td>`;
    }}).join('');
    return `<tr><td><a href="/replay?game=${{g.game_id}}">${{g.game_index}}</a></td>${{scoreCells}}<td>${{g.margin != null ? g.margin.toFixed(1) : '—'}}</td><td>${{g.subsidy}}</td><td>${{g.llm_llm_supports}}</td></tr>`;
  }}).join('');
  document.getElementById('games-body').innerHTML = gameRows || `<tr><td colspan="99">no finished games yet</td></tr>`;

  drawSparkline('spark-margin', (d.games || []).map(g => g.margin ?? 0), OKABE.vermillion, 'freerider margin (score - LLM mean)');
  drawSparkline('spark-subsidy', (d.games || []).map(g => g.subsidy), OKABE.orange, 'subsidy (LLM supports of freerider)');
  drawSparkline('spark-llmllm', (d.games || []).map(g => g.llm_llm_supports), OKABE.blue, 'LLM ↔ LLM supports');

  const notesHtml = (d.self_notes || []).map(n =>
    `<li><span class="handle">${{esc(n.entrant_identity)}}</span><span class="game-tag">game ${{n.game_index}}</span><blockquote>${{esc(n.self_note)}}</blockquote></li>`
  ).join('');
  document.getElementById('notes-list').innerHTML = notesHtml || '<li class="empty">(no self-notes yet)</li>';
}}

async function refresh() {{
  try {{
    const res = await fetch('/api/dashboard');
    render(await res.json());
  }} catch (e) {{
    document.getElementById('match-id').textContent = 'fetch failed — retrying…';
  }}
}}

setInterval(() => {{ if (lastData) document.getElementById('elapsed').textContent = fmtElapsed(lastData.started_at); }}, 1000);
refresh();
setInterval(refresh, POLL_MS);
</script>
"""

REPLAY_HTML = f"""<title>Arena Spectator — Replay Theater</title>
<style>{_BASE_CSS}</style>
{_NAV}
<h1>Replay theater</h1>
<div class="card strip">
  <div><b>Game</b><select id="game-select"></select></div>
  <div id="identities"></div>
</div>
<div id="status" class="empty"></div>

<div class="card">
  <div class="strip" style="margin-bottom:8px">
    <button id="prev-btn">⏮ Prev</button>
    <button id="play-btn">▶ Play</button>
    <button id="next-btn">Next ⏭</button>
    <span id="turn-label"></span>
  </div>
  <div id="final-banner" class="empty"></div>
</div>

<div class="card">
  <h3>Stance graph</h3>
  <div id="graph"></div>
  <div class="empty">Node fill: 🎭 orange = freerider seat, blue = LLM seat. Edge color/label: stance declared (ally/neutral/hostile) — never color alone.</div>
</div>

<div class="card" style="overflow-x:auto">
  <h3>Stance matrix (this turn)</h3>
  <div id="stance-matrix"></div>
</div>

<div class="card">
  <h3>Declared intents / submitted orders (this turn)</h3>
  <div id="turn-stats" class="empty"></div>
  <div id="entrant-declarations"></div>
</div>

<div class="card" id="game-end-card" style="display:none"></div>

<script>
const OKABE = {{ blue: "{OKABE_ITO['blue']}", orange: "{OKABE_ITO['orange']}",
  vermillion: "{OKABE_ITO['vermillion']}", skyblue: "{OKABE_ITO['skyblue']}" }};
let replayData = null, currentTurnIdx = 0, playing = false, playTimer = null;

function esc(s) {{ const d = document.createElement('div'); d.textContent = s ?? ''; return d.innerHTML; }}

function orderLabel(o) {{
  if (!o) return '?';
  if (o.type === 'Hold') return '■ Hold';
  if (o.type === 'Move') return `→ Move(n${{o.dest}})`;
  if (o.type === 'Support') return `▲ Support(u${{o.target}}${{o.require_dest != null ? ', →n'+o.require_dest : ''}})`;
  return JSON.stringify(o);
}}

async function loadGameList() {{
  const res = await fetch('/api/games');
  const games = await res.json();
  const sel = document.getElementById('game-select');
  sel.innerHTML = games.map(g =>
    `<option value="${{g.game_id}}">Game ${{g.game_index}}${{g.live ? ' 🔴 LIVE (in progress)' : ''}}</option>`
  ).join('');
  if (!games.length) {{
    document.getElementById('status').textContent = 'No finished games yet — the campaign is still running. Check back soon.';
    return;
  }}
  const params = new URLSearchParams(location.search);
  const wanted = params.has('game') ? parseInt(params.get('game'), 10) : games[0].game_id;
  sel.value = games.some(g => g.game_id === wanted) ? wanted : games[0].game_id;
  await loadGame(parseInt(sel.value, 10));
}}

async function loadGame(gameId) {{
  const res = await fetch(`/api/replay/${{gameId}}`);
  if (!res.ok) {{ document.getElementById('status').textContent = 'game not found'; return; }}
  document.getElementById('status').textContent = '';
  replayData = await res.json();
  currentTurnIdx = 0;
  renderHeader();
  renderTurn();
}}

function renderHeader() {{
  const d = replayData;
  document.getElementById('identities').textContent = d.identity_by_seat
    .map((h, i) => `${{i}}:${{h}}${{d.freerider_seats.includes(i) ? ' 🎭' : ''}}`).join('   ');
  const scores = Object.entries(d.final_scores)
    .map(([seat, score]) => `${{d.identity_by_seat[seat] ?? 'seat'+seat}}=${{score.toFixed(1)}}`).join(', ');
  document.getElementById('final-banner').textContent = d.live
    ? `🔴 LIVE — game in progress, turn ${{d.turns.length}} so far. Current scores: ${{scores}}`
    : `Final: ${{scores}} — winners: ${{d.winners.map(s => d.identity_by_seat[s] ?? s).join(', ')}}${{d.detente_reached ? ' (détente)' : ''}}`;
}}

function supportBadge(d, turn, seat, unitId) {{
  const cls = (turn.support_targets[seat] || {{}})[unitId];
  if (!cls) return '';
  const labels = {{
    freerider: '🎭 subsidizes freerider', llm: '🤝 LLM↔LLM', self: '(self)', unknown: '(unknown target)',
  }};
  return ` <span class="tag support-${{cls}}">${{labels[cls] || cls}}</span>`;
}}

function buildGraphSvg(d, turn) {{
  const seats = d.identity_by_seat.map((_, i) => i);
  const n = Math.max(1, seats.length);
  const cx = 160, cy = 160, r = 110;
  const pos = {{}};
  seats.forEach((s, i) => {{
    const angle = (2 * Math.PI * i / n) - Math.PI / 2;
    pos[s] = [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
  }});
  let svg = `<svg viewBox="0 0 320 320" width="100%" height="320" style="max-width:420px">`;
  svg += `<defs>
    <marker id="arrow-ally" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="${{OKABE.blue}}"/></marker>
    <marker id="arrow-hostile" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="${{OKABE.vermillion}}"/></marker>
    <marker id="arrow-neutral" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#888"/></marker>
  </defs>`;
  for (const from of seats) {{
    const decl = (turn.declarations[from] || {{}}).stance || {{}};
    for (const [toStr, st] of Object.entries(decl)) {{
      const to = parseInt(toStr, 10);
      if (!(to in pos)) continue;
      const [x1, y1] = pos[from], [x2, y2] = pos[to];
      const color = st === 'ally' ? OKABE.blue : st === 'hostile' ? OKABE.vermillion : '#888';
      const dash = st === 'hostile' ? '4,3' : st === 'neutral' ? '1,4' : 'none';
      const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy) || 1;
      const ux = dx / len, uy = dy / len;
      const sx = x1 + ux * 20, sy = y1 + uy * 20, ex = x2 - ux * 22, ey = y2 - uy * 22;
      svg += `<line x1="${{sx.toFixed(1)}}" y1="${{sy.toFixed(1)}}" x2="${{ex.toFixed(1)}}" y2="${{ey.toFixed(1)}}" stroke="${{color}}" stroke-width="2" stroke-dasharray="${{dash}}" marker-end="url(#arrow-${{st}})"/>`;
    }}
  }}
  for (const s of seats) {{
    const [x, y] = pos[s];
    const isFr = d.freerider_seats.includes(s);
    svg += `<circle cx="${{x.toFixed(1)}}" cy="${{y.toFixed(1)}}" r="18" fill="${{isFr ? OKABE.orange : OKABE.skyblue}}" stroke="#222" stroke-width="1.5"/>`;
    svg += `<text x="${{x.toFixed(1)}}" y="${{(y+4).toFixed(1)}}" text-anchor="middle" font-size="11" fill="#111">${{esc(d.identity_by_seat[s] || ('p'+s))}}</text>`;
  }}
  svg += `</svg>`;
  return svg;
}}

function renderTurn() {{
  const d = replayData, turn = d.turns[currentTurnIdx];
  document.getElementById('turn-label').textContent =
    `Turn ${{turn.turn}} / ${{d.turns.length}}${{d.stance_available ? '' : '  (orders only — no transcript recorded for this game)'}}`;

  const seats = d.identity_by_seat.map((_, i) => i);
  let matrix = '<table class="stance-matrix"><tr><th>from \\\\ to</th>' +
    seats.map(s => `<th>${{esc(d.identity_by_seat[s])}}</th>`).join('') + '</tr>';
  for (const from of seats) {{
    matrix += `<tr><th>${{esc(d.identity_by_seat[from])}}</th>`;
    const decl = (turn.declarations[from] || {{}}).stance || {{}};
    for (const to of seats) {{
      if (from === to) {{ matrix += '<td class="diag">—</td>'; continue; }}
      const st = decl[to];
      matrix += `<td class="${{st ? 'stance-' + st : ''}}">${{st ? st.toUpperCase() : '·'}}</td>`;
    }}
    matrix += '</tr>';
  }}
  matrix += '</table>';
  document.getElementById('stance-matrix').innerHTML = matrix;

  let decls = '';
  for (const seat of seats) {{
    const handle = d.identity_by_seat[seat];
    const isFr = d.freerider_seats.includes(seat);
    const declared = (turn.declarations[seat] || {{}}).intents || [];
    const orders = turn.orders[seat] || null;
    decls += `<div class="entrant-col"><h4>${{esc(handle)}}${{isFr ? ' 🎭' : ''}}</h4>`;
    if (declared.length) {{
      decls += '<div class="label">declared</div><ul>' + declared.map(it =>
        `<li>u${{it.unit_id}} ${{orderLabel(it.order)}} ${{it.visible_to === null ? '<span class="tag pub">public</span>' : `<span class="tag priv">→${{it.visible_to.join(',')}}</span>`}}</li>`
      ).join('') + '</ul>';
    }}
    if (orders) {{
      decls += '<div class="label">submitted orders</div><ul>' + Object.entries(orders).map(([uid, o]) =>
        `<li>u${{uid}} ${{orderLabel(o)}}${{supportBadge(d, turn, seat, uid)}}</li>`
      ).join('') + '</ul>';
    }}
    if (!declared.length && !orders) decls += '<div class="empty">(no data this turn)</div>';
    decls += '</div>';
  }}
  document.getElementById('entrant-declarations').innerHTML = decls;
  document.getElementById('graph').innerHTML = buildGraphSvg(d, turn);
  document.getElementById('turn-stats').textContent =
    `subsidy this turn (LLM→freerider supports): ${{turn.subsidy}}   |   LLM↔LLM supports: ${{turn.llm_llm_supports}}`;

  document.getElementById('prev-btn').disabled = currentTurnIdx === 0;
  document.getElementById('next-btn').disabled = currentTurnIdx === d.turns.length - 1;

  const endCard = document.getElementById('game-end-card');
  if (!d.live && currentTurnIdx === d.turns.length - 1) {{
    const scores = Object.entries(d.final_scores).map(([seat, score]) =>
      `<li>${{esc(d.identity_by_seat[seat] ?? 'seat' + seat)}}: ${{score.toFixed(1)}}</li>`).join('');
    const notes = d.self_notes.map(n => `<li><b>${{esc(n.entrant_identity)}}</b>: "${{esc(n.self_note)}}"</li>`).join('') || '<li class="empty">(none)</li>';
    endCard.style.display = 'block';
    endCard.innerHTML = `<h3>Game ${{d.game_index}} — final</h3><ul>${{scores}}</ul>
      <div>Winners: ${{d.winners.map(s => esc(d.identity_by_seat[s] ?? s)).join(', ')}}${{d.detente_reached ? ' (détente)' : ''}}</div>
      <h4>Self-notes</h4><ul>${{notes}}</ul>`;
  }} else {{
    endCard.style.display = 'none';
  }}
}}

function togglePlay() {{
  playing = !playing;
  document.getElementById('play-btn').textContent = playing ? '⏸ Pause' : '▶ Play';
  if (playing) {{
    playTimer = setInterval(() => {{
      if (!replayData) return;
      if (currentTurnIdx < replayData.turns.length - 1) {{ currentTurnIdx++; renderTurn(); }}
      else {{ togglePlay(); }}
    }}, 1500);
  }} else {{
    clearInterval(playTimer);
  }}
}}

document.getElementById('game-select').addEventListener('change', e => loadGame(parseInt(e.target.value, 10)));
document.getElementById('prev-btn').addEventListener('click', () => {{ if (currentTurnIdx > 0) {{ currentTurnIdx--; renderTurn(); }} }});
document.getElementById('next-btn').addEventListener('click', () => {{ if (replayData && currentTurnIdx < replayData.turns.length - 1) {{ currentTurnIdx++; renderTurn(); }} }});
document.getElementById('play-btn').addEventListener('click', togglePlay);

loadGameList();
</script>
"""
