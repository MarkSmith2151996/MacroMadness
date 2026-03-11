"""InvestMCP Dashboard — served as an HTML page for Wave Terminal widget."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>InvestMCP Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
    background: #0a0a0f;
    color: #e2e8f0;
    padding: 16px;
    overflow-x: hidden;
  }
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 0;
    border-bottom: 1px solid #1e293b;
    margin-bottom: 16px;
  }
  .header h1 {
    font-size: 18px;
    font-weight: 700;
    color: #f1f5f9;
    letter-spacing: -0.5px;
  }
  .header .status {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: #94a3b8;
  }
  .header .dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #22c55e;
    animation: pulse 2s infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    grid-template-rows: auto auto auto;
    gap: 12px;
  }
  .card {
    background: #111827;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 14px;
    overflow: hidden;
  }
  .card.wide { grid-column: 1 / -1; }
  .card h2 {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #64748b;
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .card h2 .icon { font-size: 13px; }
  .total-value {
    font-size: 28px;
    font-weight: 700;
    color: #f1f5f9;
    margin-bottom: 4px;
  }
  .total-sub {
    font-size: 12px;
    color: #64748b;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }
  th {
    text-align: left;
    color: #64748b;
    font-weight: 500;
    padding: 4px 8px 6px 0;
    border-bottom: 1px solid #1e293b;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  td {
    padding: 5px 8px 5px 0;
    border-bottom: 1px solid #0f172a;
    white-space: nowrap;
  }
  .ticker {
    font-weight: 700;
    color: #f1f5f9;
  }
  .positive { color: #22c55e; }
  .negative { color: #ef4444; }
  .neutral { color: #94a3b8; }
  .badge {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 600;
  }
  .badge-high { background: #7f1d1d; color: #fca5a5; }
  .badge-medium { background: #78350f; color: #fcd34d; }
  .badge-low { background: #14532d; color: #86efac; }
  .badge-ok { background: #14532d; color: #86efac; }
  .badge-warn { background: #78350f; color: #fcd34d; }
  .badge-error { background: #7f1d1d; color: #fca5a5; }
  .event-row { display: flex; justify-content: space-between; align-items: center; padding: 5px 0; border-bottom: 1px solid #0f172a; font-size: 12px; }
  .event-date { color: #94a3b8; font-size: 11px; min-width: 80px; }
  .event-desc { flex: 1; margin: 0 10px; }
  .event-ticker { font-weight: 600; color: #38bdf8; }
  .health-row { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid #0f172a; font-size: 12px; }
  .cash-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 12px; }
  .cash-label { color: #94a3b8; }
  .cash-val { font-weight: 600; color: #f1f5f9; }
  .empty { color: #475569; font-style: italic; font-size: 12px; padding: 12px 0; }
  .refresh-bar {
    position: fixed;
    bottom: 0; left: 0; right: 0;
    background: #111827;
    border-top: 1px solid #1e293b;
    padding: 6px 16px;
    font-size: 10px;
    color: #475569;
    display: flex;
    justify-content: space-between;
  }
  .principle-item {
    padding: 5px 0;
    border-bottom: 1px solid #0f172a;
    font-size: 12px;
    color: #cbd5e1;
  }
  .principle-item .cat {
    font-size: 10px;
    color: #64748b;
    text-transform: uppercase;
  }
</style>
</head>
<body>

<div class="header">
  <h1>InvestMCP</h1>
  <div class="status"><div class="dot"></div> <span id="status-text">Connecting...</span></div>
</div>

<div class="grid">
  <!-- Portfolio Overview -->
  <div class="card wide">
    <h2><span class="icon">&#x1F4BC;</span> Portfolio</h2>
    <div id="total-value" class="total-value">--</div>
    <div id="total-sub" class="total-sub"></div>
    <table style="margin-top:10px">
      <thead>
        <tr><th>Ticker</th><th>Shares</th><th>Basis</th><th>Price</th><th>P&L</th><th>Stop</th><th>Sector</th></tr>
      </thead>
      <tbody id="portfolio-body"></tbody>
    </table>
    <div id="cash-section" style="margin-top:10px; border-top:1px solid #1e293b; padding-top:8px"></div>
  </div>

  <!-- Calendar -->
  <div class="card">
    <h2><span class="icon">&#x1F4C5;</span> Upcoming Catalysts</h2>
    <div id="calendar-body"></div>
  </div>

  <!-- System Health -->
  <div class="card">
    <h2><span class="icon">&#x2699;</span> System Health</h2>
    <div id="health-body"></div>
  </div>

  <!-- Alerts -->
  <div class="card">
    <h2><span class="icon">&#x1F514;</span> Alerts</h2>
    <div id="alerts-body"></div>
  </div>

  <!-- Scores -->
  <div class="card">
    <h2><span class="icon">&#x1F3AF;</span> Trade Scores</h2>
    <div id="scores-body"></div>
  </div>
</div>

<div class="refresh-bar">
  <span id="last-refresh">--</span>
  <span>Auto-refreshes every 60s</span>
</div>

<script>
const API = '';

function fmt(n) {
  if (n == null) return '--';
  return '$' + Number(n).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}
function pct(n) {
  if (n == null) return '--';
  const s = Number(n).toFixed(2);
  return (n >= 0 ? '+' : '') + s + '%';
}
function cls(n) {
  if (n == null) return 'neutral';
  return n >= 0 ? 'positive' : 'negative';
}
function impactBadge(level) {
  const l = (level || 'medium').toLowerCase();
  return `<span class="badge badge-${l}">${l}</span>`;
}
function healthBadge(status) {
  const s = (status || '').toLowerCase();
  if (s === 'ok' || s === 'valid') return `<span class="badge badge-ok">${status}</span>`;
  if (s.includes('expired') || s.includes('fail') || s.includes('limit')) return `<span class="badge badge-error">${status}</span>`;
  return `<span class="badge badge-warn">${status}</span>`;
}

async function fetchJSON(path) {
  const r = await fetch(API + path);
  return r.json();
}

async function loadPortfolio() {
  try {
    const data = await fetchJSON('/portfolio');
    const body = document.getElementById('portfolio-body');
    if (!data.length) { body.innerHTML = '<tr><td colspan="7" class="empty">No open positions</td></tr>'; return; }

    let totalValue = 0;
    let totalCost = 0;
    body.innerHTML = data.map(p => {
      const mv = p.shares * (p.current_price || p.cost_basis);
      const cost = p.shares * p.cost_basis;
      totalValue += mv;
      totalCost += cost;
      const pnl = p.unrealized_pnl || (mv - cost);
      const pnlPct = cost > 0 ? (pnl / cost * 100) : 0;
      return `<tr>
        <td class="ticker">${p.ticker}</td>
        <td>${p.shares}</td>
        <td>${fmt(p.cost_basis)}</td>
        <td>${p.current_price ? fmt(p.current_price) : '<span class="neutral">--</span>'}</td>
        <td class="${cls(pnl)}">${fmt(pnl)} (${pct(pnlPct)})</td>
        <td>${p.stop_loss ? fmt(p.stop_loss) : '--'}</td>
        <td style="color:#94a3b8">${p.sector || '--'}</td>
      </tr>`;
    }).join('');

    document.getElementById('total-value').textContent = fmt(totalValue);
    const totalPnl = totalValue - totalCost;
    document.getElementById('total-sub').innerHTML =
      `<span class="${cls(totalPnl)}">${fmt(totalPnl)} (${pct(totalCost > 0 ? totalPnl/totalCost*100 : 0)})</span> &middot; ${data.length} positions`;

    // Cash
    try {
      // Cash is only available via the MCP tool, not the widget endpoint
      // We'll show position count instead
    } catch(e) {}
  } catch(e) {
    document.getElementById('portfolio-body').innerHTML = '<tr><td colspan="7" class="empty">Failed to load</td></tr>';
  }
}

async function loadCalendar() {
  try {
    const data = await fetchJSON('/calendar?days_ahead=60');
    const body = document.getElementById('calendar-body');
    if (!data.length) { body.innerHTML = '<div class="empty">No upcoming events</div>'; return; }
    body.innerHTML = data.slice(0, 8).map(e => `
      <div class="event-row">
        <span class="event-date">${e.event_date}</span>
        <span class="event-desc">${e.ticker ? '<span class="event-ticker">' + e.ticker + '</span> ' : ''}${e.description}</span>
        ${impactBadge(e.impact_level)}
      </div>
    `).join('');
  } catch(e) {
    document.getElementById('calendar-body').innerHTML = '<div class="empty">Failed to load</div>';
  }
}

async function loadHealth() {
  try {
    const data = await fetchJSON('/system-health');
    const body = document.getElementById('health-body');
    if (!data.length) { body.innerHTML = '<div class="empty">No data</div>'; return; }
    body.innerHTML = data.map(c => `
      <div class="health-row">
        <span>${c.component}</span>
        ${healthBadge(c.status)}
      </div>
      <div style="font-size:10px;color:#475569;padding:0 0 4px">${c.detail}</div>
    `).join('');
  } catch(e) {
    document.getElementById('health-body').innerHTML = '<div class="empty">Failed to load</div>';
  }
}

async function loadAlerts() {
  try {
    const data = await fetchJSON('/alerts');
    const body = document.getElementById('alerts-body');
    if (!data.length) { body.innerHTML = '<div class="empty">No alerts</div>'; return; }
    body.innerHTML = data.slice(0, 6).map(a => `
      <div class="event-row">
        <span class="event-date">${new Date(a.sent_at).toLocaleDateString()}</span>
        <span class="event-desc">${a.ticker ? '<span class="event-ticker">' + a.ticker + '</span> ' : ''}${a.message}</span>
        <span class="badge badge-${a.priority >= 4 ? 'high' : a.priority >= 3 ? 'medium' : 'low'}">P${a.priority}</span>
      </div>
    `).join('');
  } catch(e) {
    document.getElementById('alerts-body').innerHTML = '<div class="empty">Failed to load</div>';
  }
}

async function loadScores() {
  try {
    const data = await fetchJSON('/scores');
    const body = document.getElementById('scores-body');
    if (!data.length) { body.innerHTML = '<div class="empty">No scored trades yet</div>'; return; }
    body.innerHTML = '<table><thead><tr><th>Ticker</th><th>Score</th><th>Outcome</th><th>Process</th></tr></thead><tbody>' +
      data.slice(0, 8).map(s => `
        <tr>
          <td class="ticker">${s.ticker}</td>
          <td>${s.composite_score || '--'}</td>
          <td class="${s.outcome === 'win' ? 'positive' : s.outcome === 'loss' ? 'negative' : 'neutral'}">${s.outcome || '--'}</td>
          <td style="font-size:10px">${(s.process_vs_outcome || '').replace(/_/g, ' ')}</td>
        </tr>
      `).join('') + '</tbody></table>';
  } catch(e) {
    document.getElementById('scores-body').innerHTML = '<div class="empty">Failed to load</div>';
  }
}

async function loadAll() {
  try {
    await Promise.all([loadPortfolio(), loadCalendar(), loadHealth(), loadAlerts(), loadScores()]);
    document.getElementById('status-text').textContent = 'Live';
    document.getElementById('last-refresh').textContent = 'Last refresh: ' + new Date().toLocaleTimeString();
  } catch(e) {
    document.getElementById('status-text').textContent = 'Error';
  }
}

loadAll();
setInterval(loadAll, 60000);
</script>
</body>
</html>"""


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML
