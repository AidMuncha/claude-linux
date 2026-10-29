/* ---------- command palette + shortcuts ---------- */
let pal = [], psel = 0;
function palItems() {
  const it = [{l:'New session', h:'Ctrl+N', run:newChat}, {l:'Settings', h:'Ctrl+,', run:() => openPanel('general')}, {l:'Toggle session panel', run:() => $('#drbtn').click()}, {l:'Keyboard shortcuts', run:() => sys(SHORTCUTS)}];
  PAGES.forEach(([k, n]) => it.push({l:'Settings: ' + n, run:() => openPanel(k)}));
  allThemes().forEach(t => it.push({l:'Theme: ' + t[1], run:() => applyTheme(t[0])}));
  it.push({l:'Next theme', h:'Ctrl+Shift+T', run:nextTheme}, {l:'Split view', h:'Ctrl+\\', run:toggleSplit}, {l:'Toggle sidebar', h:'Ctrl+B', run:() => toggleSidebar()},
    {l:'Export chat as Markdown', run:() => exportChat('md')}, {l:'Export chat as HTML', run:() => exportChat('html')}, {l:'Export chat as PDF', run:() => exportChat('pdf')},
    {l:'Appearance settings', run:() => openPanel('appearance')}, {l:'Desktop settings', run:() => openPanel('desktop')}, {l:'Full screen', h:'F11', run:() => post({type:'fullscreen'})});
  visible().concat(Object.values(chats).filter(c => kindOf(c) !== tab && c.items.length)).sort((a, b) => b.t - a.t).slice(0, 40).forEach(c => it.push({l:'Chat: ' + c.title, h:kindOf(c), run:() => { tab = kindOf(c); select(c.id); }}));
  cmdList().forEach(([n, d]) => it.push({l:'/' + n, h:d, run:() => { $('#in').value = '/' + n + ' '; $('#in').focus(); showCmds(); }}));
  return it;
}
function palRender() {
  const q = $('#palin').value.toLowerCase().split(/\s+/).filter(Boolean);
  pal = palItems().filter(x => q.every(w => (x.l + ' ' + (x.h || '')).toLowerCase().includes(w))).slice(0, 40); psel = Math.min(psel, Math.max(0, pal.length - 1));
  $('#pallist').innerHTML = pal.map((x, i) => `<div class="mi ${i === psel ? 'sel' : ''}" data-i="${i}"><span class="tx"><b>${esc(x.l)}</b></span>${x.h ? `<small>${esc(x.h)}</small>` : ''}</div>`).join('') || '<div class="mi"><span class="tx"><small>No matches</small></span></div>';
  $('#pallist').querySelectorAll('.mi[data-i]').forEach(el => el.onmousedown = e => { e.preventDefault(); palRun(+el.dataset.i); });
  const sel = $('#pallist').querySelector('.sel'); if (sel) sel.scrollIntoView({block:'nearest'});
}
function palOpen() { $('#pal').style.display = 'flex'; $('#palin').value = ''; psel = 0; palRender(); $('#palin').focus(); }
function palClose() { $('#pal').style.display = 'none'; if ($('#modal').style.display !== 'flex') $('#in').focus(); }
function palRun(i) { const x = pal[i]; palClose(); if (x) x.run(); }
$('#palin').oninput = () => { psel = 0; palRender(); };
$('#palin').onkeydown = e => {
  if (e.key === 'Escape') { e.preventDefault(); palClose(); }
  else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); psel = (psel + (e.key === 'ArrowDown' ? 1 : pal.length - 1)) % Math.max(1, pal.length); palRender(); }
  else if (e.key === 'Enter') { e.preventDefault(); palRun(psel); }
};
$('#pal').onmousedown = e => { if (e.target === $('#pal')) palClose(); };
const SHORTCUTS = 'Shortcuts:\n  Ctrl+K   command palette\n  Ctrl+N   new session\n  Ctrl+L   focus the message box\n  Ctrl+,   settings\n  Ctrl+B   toggle sidebar\n  Ctrl+W   close the window (to the tray if enabled)\n  Ctrl+Q   quit\n  Ctrl+F   search chats\n  Ctrl+\\   split view\n  Ctrl+1 / Ctrl+2   Chat / Code\n  Ctrl+= / Ctrl+-   bigger / smaller text (Ctrl+0 resets)\n  Ctrl+Shift+T   next theme\n  F11      full screen\n  Ctrl+/   this list\n  Shift+Tab  cycle permission mode\n  Esc      stop the current run\n  ↑ / ↓    earlier prompts\n  @file    mention a file   !cmd  run a shell command';
document.addEventListener('keydown', e => {
  if (!e.ctrlKey || e.altKey || e.metaKey) return;
  const k = e.key.toLowerCase(), go2 = f => { e.preventDefault(); e.stopPropagation(); f(); };
  if (k === 'k') go2(() => $('#pal').style.display === 'flex' ? palClose() : palOpen());
  else if (k === 'n') go2(newChat);
  else if (k === 'l') go2(() => $('#in').focus());
  else if (k === ',') go2(() => openPanel('general'));
  else if (k === '/') go2(() => sys(SHORTCUTS));
  else if (k === 'b') go2(() => toggleSidebar());
  else if (k === 'f') go2(() => { toggleSidebar(false); $('#search').focus(); });
}, true);

