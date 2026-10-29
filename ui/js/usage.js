/* ---------- usage (the CLI's own /usage numbers) ---------- */
function fmtClock(d) { return d.toLocaleTimeString([], {hour:'numeric', minute:'2-digit'}).replace(':00', '').replace(/ /g, ' '); }
function resetText(epoch, session) {
  if (!epoch) return '';
  const d = new Date(epoch * 1000), ms = d - Date.now();
  if (ms <= 0) return 'Resets now';
  if (session || ms < 3600e3 * 5) { const h = Math.floor(ms / 3600e3), m = Math.ceil(ms % 3600e3 / 60e3); return 'Resets in ' + (h ? h + ' hr ' : '') + m + ' min'; }
  const day = d.toDateString() === new Date().toDateString() ? 'today' : d.toDateString() === new Date(Date.now() + 864e5).toDateString() ? 'tomorrow' : d.toLocaleDateString([], {weekday:'long'});
  return `Resets ${day} at ${fmtClock(d)}`;
}
const isSess = r => /^session/i.test(r.label);
const rowName = r => isSess(r) ? 'Current session' : r.label.replace(/^week\s*\(?/i, '').replace(/\)$/, '').replace(/^all models$/i, 'All models').replace(/^./, x => x.toUpperCase());
function renderUsage() {
  const u = S.usage, rows = (u && u.rows) || [];
  const s = rows.find(isSess), w = rows.find(r => /all models/i.test(r.label));
  const mini = r => r ? `<span class="mini ${r.pct >= 85 ? 'hi' : ''}"><i style="width:${r.pct}%"></i></span> ${r.pct}%` : '—';
  $('#usage').innerHTML = !u ? 'Usage…' : !rows.length ? 'Usage' : `<span>Session ${mini(s)}</span><span>Week ${mini(w)}</span>`;
  if ($('#upop').style.display === 'block') fillUsage($('#upop'));
}
function usageBlock() {
  const u = S.usage; if (!u) return '<div class="ur"><div class="r">Loading…</div></div>';
  if (u.error) return `<div class="errtxt">${esc(u.error)}</div>`;
  if (!u.rows.length) return `<pre class="raw">${esc(u.text || 'No plan usage limits to show for this login.')}</pre>`;
  const row = r => `<div class="ur"><div class="l"><span>${esc(rowName(r))}</span><span>${r.pct}% used</span></div><div class="bar ${r.pct >= 85 ? 'hi' : ''}"><i style="width:${r.pct}%"></i></div><div class="r">${esc(r.resetsAt ? resetText(r.resetsAt, isSess(r)) : 'Resets ' + r.raw)}</div></div>`;
  const sess = u.rows.filter(isSess), wk = u.rows.filter(r => !isSess(r));
  return sess.map(row).join('') + (wk.length ? '<div class="uh2">Weekly limits</div>' + wk.map(row).join('') : '');
}
function ago(ts) { const m = Math.round((Date.now() / 1000 - ts) / 60); return m < 1 ? 'just now' : m + ' min ago'; }
function fillUsage(p) {
  const u = S.usage;
  p.innerHTML = `<div class="uh">Plan usage limits</div>${usageBlock()}<div class="uf"><span>${u && u.ts ? 'Last updated: ' + ago(u.ts) : ''}</span><button class="ib" id="urefresh" title="Refresh">${ico('refresh')}</button></div>`;
  $('#urefresh').onclick = e => { e.stopPropagation(); post({type:'refresh_usage'}); };
}
$('#usage').onclick = e => { e.stopPropagation(); const p = $('#upop'); if (p.style.display === 'block') { p.style.display = 'none'; return; } closePops(); fillUsage(p); p.style.display = 'block'; post({type:'refresh_usage'}); };
$('#upop').onclick = e => e.stopPropagation();
