/* ---------- themes, colors, typography: everything that decides how the app looks ---------- */
Object.assign(IC, {
  palette:'<path d="M12 3a9 9 0 1 0 0 18c1.1 0 1.8-.9 1.5-1.9-.3-1 .4-2.1 1.5-2.1H17a4 4 0 0 0 4-4c0-5-4-10-9-10z"/><circle cx="7.5" cy="11" r="1"/><circle cx="10.5" cy="7" r="1"/><circle cx="15.5" cy="7.5" r="1"/>',
  sidebar:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>', split:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v16"/>',
  swap:'<path d="M7 7h13M16 3l4 4-4 4M17 17H4M8 13l-4 4 4 4"/>',
});

// [id, name, [background, card, accent]]
const THEMES = [
  ['dark', 'Dark', ['#262624', '#30302e', '#d97757']], ['light', 'Light', ['#faf9f5', '#ffffff', '#d97757']], ['sepia', 'Sepia', ['#f4ecd8', '#fbf6e9', '#b4552d']],
  ['midnight', 'Midnight', ['#0f1420', '#171d2c', '#6ea8fe']], ['nord', 'Nord', ['#2e3440', '#3b4252', '#88c0d0']], ['dracula', 'Dracula', ['#282a36', '#343746', '#bd93f9']],
  ['solarized', 'Solarized', ['#002b36', '#073642', '#cb4b16']], ['gruvbox', 'Gruvbox', ['#282828', '#3c3836', '#fe8019']], ['rosepine', 'Rosé Pine', ['#191724', '#26233a', '#eb6f92']],
  ['terminal', 'Terminal', ['#0c0c0c', '#161616', '#d97757']], ['contrast', 'High contrast', ['#000000', '#0d0d0d', '#ffb000']],
  ['catppuccin-mocha', 'Catppuccin Mocha', ['#1e1e2e', '#313244', '#cba6f7']], ['catppuccin-macchiato', 'Catppuccin Macchiato', ['#24273a', '#363a4f', '#c6a0f6']],
  ['catppuccin-latte', 'Catppuccin Latte', ['#eff1f5', '#ffffff', '#8839ef']], ['tokyonight', 'Tokyo Night', ['#1a1b26', '#24283b', '#7aa2f7']],
  ['onedark', 'One Dark', ['#282c34', '#2c313a', '#61afef']], ['everforest', 'Everforest', ['#2d353b', '#343f44', '#a7c080']], ['kanagawa', 'Kanagawa', ['#1f1f28', '#2a2a37', '#7e9cd8']],
  ['ayu', 'Ayu Mirage', ['#1f2430', '#272d3b', '#ffcc66']], ['monokai', 'Monokai', ['#272822', '#34352e', '#a6e22e']], ['cyberpunk', 'Cyberpunk', ['#0d0221', '#1a0b3a', '#ff2a6d']],
  ['synthwave', 'Synthwave', ['#262335', '#2f2b43', '#ff7edb']],
];
const ADAPTIVE = [['system', 'System (KDE colors)'], ['auto', 'Auto light / dark'], ['custom', 'Custom']];
const allThemes = () => [...ADAPTIVE.map(([i, n]) => [i, n, []]), ...THEMES];
const BASE_KEYS = ['bg', 'side', 'card', 'fg', 'dim', 'accent', 'green', 'red', 'yellow'];
const BASE_LABELS = { bg:'Background', side:'Sidebar', card:'Cards', fg:'Text', dim:'Muted text', accent:'Accent', green:'Success', red:'Error', yellow:'Warning' };
const CUSTOM_DEFAULT = { bg:'#262624', side:'#1f1e1d', card:'#30302e', fg:'#faf9f5', dim:'#a8a59c', accent:'#d97757', green:'#5fbf79', red:'#f0707f', yellow:'#e6c07b' };
const ACCENTS = ['#d97757', '#e5484d', '#f76b15', '#ffb224', '#46a758', '#12a594', '#3e63dd', '#8e4ec6', '#d6409f', '#7d8590'];
const APPEARANCE_KEYS = new Set(['theme', 'autoDark', 'autoLight', 'accent', 'kdeAccent', 'customTheme', 'projectColors', 'font', 'monoFont', 'fontSize', 'chatWidth',
  'bgMode', 'bgGradient', 'bgImage', 'bgDim', 'glass', 'glassOpacity', 'motion', 'animSpeed', 'syntax', 'codeNums', 'codeWrap']);
const SANS_STACK = '"Inter","Segoe UI","Cantarell","Noto Sans",system-ui,-apple-system,sans-serif';
const MONO_STACK = '"JetBrains Mono","Cascadia Code","Fira Code","DejaVu Sans Mono",monospace';
let KDE = { scheme:null, buttons:'' };      // Plasma's colors, pushed by Python and refreshed when the user changes scheme
EXTRA.kde = p => { KDE = p || { scheme:null }; applyAppearance(); if ($('#modal').style.display === 'flex' && ['appearance', 'desktop'].includes(panel)) showPage(true); };

/* ----- color helpers ----- */
const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));
function safeColor(v) {                       // '#abc' / '#aabbcc' -> '#aabbcc'; anything else -> ''
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(String(v || '').trim()); if (!m) return '';
  let h = m[1].toLowerCase(); if (h.length === 3) h = [...h].map(x => x + x).join(''); return '#' + h;
}
function parseColor(c) {
  c = String(c || '').trim(); let m;
  if ((m = c.match(/^#([0-9a-f]{3})$/i))) return [...m[1]].map(x => parseInt(x + x, 16));
  if ((m = c.match(/^#([0-9a-f]{6})/i))) return [0, 2, 4].map(i => parseInt(m[1].slice(i, i + 2), 16));
  if ((m = c.match(/^rgba?\(([^)]+)\)/i))) { const p = m[1].split(/[\s,\/]+/).filter(Boolean).slice(0, 3).map(parseFloat); return p.length === 3 && p.every(n => !isNaN(n)) ? p.map(Math.round) : null; }
  if ((m = c.match(/^color\(srgb\s+([^)]+)\)/i))) { const p = m[1].split(/[\s\/]+/).filter(Boolean).slice(0, 3).map(parseFloat); return p.length === 3 && p.every(n => !isNaN(n)) ? p.map(x => Math.round(x * 255)) : null; }
  return null;
}
const toHex = rgb => '#' + rgb.map(x => clamp(Math.round(x), 0, 255).toString(16).padStart(2, '0')).join('');
const relLum = ([r, g, b]) => { const f = x => { x /= 255; return x <= .03928 ? x / 12.92 : Math.pow((x + .055) / 1.055, 2.4); }; return .2126 * f(r) + .7152 * f(g) + .0722 * f(b); };
let _probe;   // a real (not display:none) element: WebKit does not refresh the cached style of hidden ones
function varRGB(name) {                       // the color a CSS variable currently resolves to, as [r, g, b]
  if (!_probe) { _probe = document.createElement('span'); _probe.style.cssText = 'position:fixed;left:-9999px;top:0;width:0;height:0;overflow:hidden;visibility:hidden;pointer-events:none;transition:none !important;animation:none !important'; document.body.appendChild(_probe); }
  _probe.style.color = ''; _probe.style.color = `var(${name})`;
  return parseColor(getComputedStyle(_probe).color);
}
const chatColor = c => c ? safeColor(c.color) || safeColor((S.settings.projectColors || {})[c.cwd]) : '';   // chat color, else its folder's, ignoring anything that is not a color

/* ----- which theme is really in use ----- */
function resolveTheme() {
  const s = S.settings || {}, id = s.theme || 'dark', k = KDE.scheme;
  const dark = k ? k.dark : matchMedia('(prefers-color-scheme: dark)').matches;
  if (id === 'auto') return { id: dark ? (s.autoDark || 'dark') : (s.autoLight || 'light') };
  if (id === 'system') {
    if (!k) return { id: dark ? 'dark' : 'light' };
    return { id:'system', base:{ bg:k.view, side:k.window, card:k.button, fg:k.fg, dim:k.dim, accent:s.kdeAccent ? k.accent : null, green:k.green, red:k.red, yellow:k.yellow } };
  }
  if (id === 'custom') return { id:'custom', base:{ ...CUSTOM_DEFAULT, ...(s.customTheme || {}) } };
  return { id: THEMES.some(t => t[0] === id) ? id : 'dark' };
}

let appKey = '', chromeKey = '';
function applyAppearance() {
  const root = document.documentElement, st = root.style, s = S.settings || {}, r = resolveTheme();
  const over = safeColor(chatColor(chats[cur])) || safeColor(s.accent);
  const key = r.id + '|' + JSON.stringify(r.base || 0) + '|' + over;
  const reduced = s.motion === 'reduced' || ((s.motion || 'system') === 'system' && matchMedia('(prefers-reduced-motion: reduce)').matches);
  if (appKey && key !== appKey && !reduced) {   // cross-fade: switch the transition on first, then change the colors
    root.classList.add('tfade'); void root.offsetWidth;
    clearTimeout(applyAppearance.t); applyAppearance.t = setTimeout(() => root.classList.remove('tfade'), 700);
  }
  appKey = key;
  for (const k of BASE_KEYS) st.removeProperty('--' + k);
  root.dataset.theme = r.id;
  if (r.base) for (const k of BASE_KEYS) { const v = safeColor(r.base[k]); if (v) st.setProperty('--' + k, v); }
  const bg = varRGB('--bg'); root.dataset.scheme = bg && relLum(bg) > .4 ? 'light' : 'dark';
  if (over) st.setProperty('--accent', over);
  st.setProperty('--accent2', 'color-mix(in srgb, var(--accent) 82%, #000)');
  const ac = varRGB('--accent') || [217, 119, 87];
  st.setProperty('--onacc', 1.05 / (relLum(ac) + .05) >= 2 ? '#fff' : '#1a1a1a');
  // typography and layout
  const fam = (n, base) => { n = String(n || '').replace(/["\\;{}<>]/g, '').trim(); return n ? `"${n}",${base}` : ''; };
  const put = (k, v) => v ? st.setProperty(k, v) : st.removeProperty(k);
  put('--sans', fam(s.font, SANS_STACK)); put('--mono', fam(s.monoFont, MONO_STACK));
  st.setProperty('--fs', clamp(+s.fontSize || 15, 11, 24) + 'px'); st.setProperty('--cw', clamp(+s.chatWidth || 800, 480, 1400) + 'px');
  // motion
  root.dataset.motion = reduced ? 'reduced' : 'full';
  st.setProperty('--sp', String(+(1 / clamp(+s.animSpeed || 1, .25, 3)).toFixed(3)));
  // code blocks
  root.classList.toggle('codenums', !!s.codeNums); root.classList.toggle('codewrap', !!s.codeWrap);
  if (s.syntax && s.syntax !== 'auto') root.dataset.syntax = s.syntax; else root.removeAttribute('data-syntax');
  // window
  root.classList.toggle('glass', !!s.glass); st.setProperty('--ga', String(clamp(+s.glassOpacity || .82, .3, 1)));
  applyBackground();
  const px = (n, d) => toHex(varRGB(n) || d);
  const msg = { type:'chrome', bg:px('--bg', [38, 38, 36]), side:px('--side', [31, 30, 29]), fg:px('--fg', [250, 249, 245]), line:px('--line', [52, 51, 47]), glass:!!s.glass, opacity:clamp(+s.glassOpacity || .82, .3, 1) };
  const mk = JSON.stringify(msg); if (mk !== chromeKey) { chromeKey = mk; post(msg); }
}

function setTheme(t) { S.settings.theme = t; applyAppearance(); }
function applyTheme(t) { setSetting('theme', t); if (t === 'dark' || t === 'light') cset('theme', t); }
function nextTheme() {
  const ids = THEMES.map(t => t[0]), i = ids.indexOf(S.settings.theme);
  const n = ids[(i + 1) % ids.length]; applyTheme(n); toast('Theme: ' + THEMES.find(t => t[0] === n)[1]);
}

/* ----- sidebar ----- */
function applySidebar(initial) {
  const root = document.documentElement, collapsed = S.settings.sidebar === false;
  if (initial) root.classList.add('notrans');
  $('#side').classList.toggle('collapsed', collapsed);
  if (initial) requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove('notrans')));
}
function toggleSidebar(force) {
  const open = force === undefined ? $('#side').classList.contains('collapsed') : !!force;
  $('#side').classList.toggle('collapsed', !open); setSetting('sidebar', open);
}

/* ----- custom themes: validate, import, export ----- */
function sanitizeTheme(o) {
  if (!o || typeof o !== 'object') return null;
  if (o.colors && typeof o.colors === 'object') o = o.colors;
  const out = {}; for (const k of BASE_KEYS) { const v = safeColor(o[k]); if (v) out[k] = v; }
  return out.bg && out.fg ? out : null;
}
function currentPalette() {                    // the colors on screen right now, ready to become a custom theme
  const out = {}; for (const k of BASE_KEYS) { const c = varRGB('--' + k); out[k] = c ? toHex(c) : CUSTOM_DEFAULT[k]; } return out;
}
function importThemeText(text) {
  let t = null; try { t = sanitizeTheme(JSON.parse(text)); } catch (e) { }
  if (!t) return toast('That does not look like a Claude Linux theme (it needs at least "bg" and "fg" colors)', true);
  setSetting('customTheme', { ...CUSTOM_DEFAULT, ...t }); setSetting('theme', 'custom'); toast('Theme imported');
  if ($('#modal').style.display === 'flex' && panel === 'appearance') showPage(true);
}
function exportTheme() {
  post({type:'savetext', name:'claude-linux-theme', ext:'.json', text:JSON.stringify({ name:'My theme', app:'claude-linux', version:1, colors:currentPalette() }, null, 2) + '\n'});
}
EXTRA.themefile = p => importThemeText(p.text);

/* ----- per-chat and per-folder accent colors (right-click a chat in the sidebar) ----- */
function colorMenu(e, c) {
  closePops(); const m = $('#menu'); m.style.width = '250px';
  const dirName = (c.cwd || '').split('/').filter(Boolean).pop() || '/', proj = (S.settings.projectColors || {})[c.cwd];
  const row = (scope, on) => `<div class="swatches" data-scope="${scope}">${ACCENTS.map(col => `<button class="swc ${on === col ? 'on' : ''}" style="background:${col}" data-c="${col}" title="${col}"></button>`).join('')}<button class="swc none ${!on ? 'on' : ''}" data-c="" title="No color"></button></div>`;
  m.innerHTML = `<div class="mhead">Color for this chat</div>${row('chat', safeColor(c.color))}` + (c.cwd ? `<div class="msep"></div><div class="mhead">Color for every chat in ${esc(dirName)}</div>${row('dir', safeColor(proj))}` : '');
  m.onclick = ev => {
    ev.stopPropagation(); const b = ev.target.closest('.swc'); if (!b) return;
    const val = safeColor(b.dataset.c);
    if (b.parentElement.dataset.scope === 'chat') { if (val) c.color = val; else delete c.color; persistChat(c.id); }
    else { const pc = { ...(S.settings.projectColors || {}) }; if (val) pc[c.cwd] = val; else delete pc[c.cwd]; setSetting('projectColors', pc); }
    m.style.display = 'none'; renderList(); applyAppearance();
  };
  place(m, { getBoundingClientRect: () => ({ left:e.clientX, top:e.clientY, bottom:e.clientY }) }, false);
}
