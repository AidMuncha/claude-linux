/* ---------- more keyboard shortcuts (the first set lives in palette.js) ---------- */
function zoom(d) { setSetting('fontSize', clamp((+S.settings.fontSize || 15) + d, 11, 24)); }
function switchTab(t) { tab = t; const n = visible().find(c => c.items.length); n ? select(n.id) : newChat(); }
document.addEventListener('keydown', e => {
  if (e.key === 'F11') { e.preventDefault(); post({type:'fullscreen'}); return; }
  if (!e.ctrlKey || e.altKey || e.metaKey) return;
  const k = e.key, go = f => { e.preventDefault(); e.stopPropagation(); f(); };
  if (k === '\\') go(toggleSplit);
  else if (k === '=' || k === '+') go(() => zoom(1));
  else if (k === '-' || k === '_') go(() => zoom(-1));
  else if (k === '0') go(() => setSetting('fontSize', 15));
  else if (k === 'w') go(() => post({type:'close'}));
  else if (k === 'q') go(() => post({type:'quit'}));
  else if (k === '1') go(() => switchTab('chat'));
  else if (k === '2') go(() => switchTab('code'));
  else if ((k === 'T' || k === 't') && e.shiftKey) go(nextTheme);
}, true);
