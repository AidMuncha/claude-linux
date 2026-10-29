
/* ---------- slash commands ---------- */
const LOCAL = {
  help: ['Show all commands', () => sys('Commands:\n' + cmdList().map(([n, d]) => `  /${n.padEnd(18)} ${d}`).join('\n'))],
  clear: ['Start a fresh conversation', () => newChat()], new: ['Start a new session', () => newChat()],
  resume: ['Pick a previous conversation', () => listMenu($('#title'), visible().filter(c => c.items.length).slice(0, 12).map(c => ({label:c.title, run: () => select(c.id)})), false, 360)],
  rename: ['Rename: /rename <title>', a => { if (a && chats[cur]) { chats[cur].title = a; persist(); renderList(); } else sys('Usage: /rename <new title>'); }],
  model: ['Choose the model', a => { if (a) { setSetting('model', a); sys('Model set to ' + a); } else modelMenu(); }],
  effort: ['Reasoning effort: /effort [low|medium|high|xhigh|max|auto]', a => { if (a) { setSetting('effort', a === 'auto' ? '' : a); sys('Effort set to ' + a); } else modelMenu(); }],
  rewind: ['Restore files to an earlier message', () => { const c = chats[cur], us = c ? c.items.filter(x => x.k === 'user' && x.uid).slice(-12).reverse() : []; if (!isCode(c) || !us.length) return sys('Nothing to rewind yet. Rewind restores files Claude changed after one of your messages.'); listMenu($('#title'), us.map(u => ({label:(u.text || '[image]').slice(0, 60), run: () => post({type:'rewind', chat:cur, uid:u.uid, dry:true})})), false, 380); }],
  hooks: ['Manage hooks', () => openPanel('hooks')],
  config: ['Open settings', () => openPanel('config')], settings: ['Open settings', () => openPanel('general')],
  permissions: ['Edit permission rules', () => openPanel('perms')], memory: ['Edit CLAUDE.md', () => openPanel('memory')],
  usage: ['Show plan usage limits', () => { closePops(); const p = $('#upop'); fillUsage(p); p.style.display = 'block'; post({type:'refresh_usage'}); }],
  status: ['Show plan usage limits', () => LOCAL.usage[1]()],
  cost: ['Token usage for this chat', () => { const t = (chats[cur] || {}).tokens || {i:0, o:0, cr:0, cc:0, cost:0}; sys(`Input ${t.i} · output ${t.o} · cache read ${t.cr} · cache written ${t.cc} tokens · $${t.cost.toFixed(4)} at API list price`); }],
  cd: ['Change folder: /cd <path>', a => a ? setCwd(a.replace(/^~/, home)) : post({type:'pickdir', start:(chats[cur] || {}).cwd})],
  'add-dir': ['Allow another folder: /add-dir <path>', a => { if (!a) return sys('Usage: /add-dir <path>'); setSetting('addDirs', [...(S.settings.addDirs || []), a.replace(/^~/, home)]); sys('Added ' + a); }],
  'remote-control': ['Toggle Remote Control for this chat', () => { const c = chats[cur]; if (!isCode(c)) return sys('Remote Control is only available in Code chats.'); S.drawer = true; toggleRC(!(c.rc && c.rc.on)); }], rc: ['Toggle Remote Control for this chat', () => LOCAL['remote-control'][1]()],
  mcp: ['Manage MCP servers', () => openPanel('mcp')],
  export: ['Save this chat: /export [md|html|pdf]', a => exportChat(a)],
  theme: ['Change theme: /theme [name]', a => { const t = allThemes().find(x => x[0] === a.toLowerCase() || x[1].toLowerCase() === a.toLowerCase()); if (t) applyTheme(t[0]); else listMenu($('#title'), allThemes().map(x => ({label:x[1], on:S.settings.theme === x[0], run: () => applyTheme(x[0])})), false, 260); }],
  appearance: ['Colors, fonts, background and animations', () => openPanel('appearance')],
  accent: ['Accent color for this chat: /accent #rrggbb or /accent reset', a => { const c = chats[cur]; if (!c) return; if (a === 'reset' || a === '') { delete c.color; } else if (safeColor(a)) { c.color = safeColor(a); } else return sys('Usage: /accent #rrggbb   (or /accent reset)'); persist(); renderList(); applyAppearance(); }],
  split: ['Show a second chat beside this one', () => toggleSplit()],
  login: ['How to sign in', () => sys('Run `claude auth login` in a terminal, then restart Claude Linux.')], logout: ['How to sign out', () => sys('Run `claude auth logout` in a terminal.')],
  version: ['Show version', () => sys('Claude Code v' + S.version)], exit: ['Quit Claude Linux', () => post({type:'quit'})], quit: ['Quit Claude Linux', () => post({type:'quit'})],
};
const PASS = {
  compact: 'Compact the conversation', context: 'Show context usage', init: 'Create a CLAUDE.md', review: 'Review a pull request', 'security-review': 'Security review of pending changes', agents: 'Manage agents', doctor: 'Diagnose your installation', 'code-review': 'Review code for bugs',
  'deep-research': 'Multi-source research report', design: 'Visual designs and prototypes', 'design-sync': 'Sync a design system', dataviz: 'Charts and data visualization', 'update-config': 'Edit settings.json, hooks, permissions', verify: 'Verify a change really works', debug: 'Debug a problem', simplify: 'Simplify the changed code', batch: 'Run one change across many files',
  'fewer-permission-prompts': 'Allowlist common read-only commands', loop: 'Run a prompt on an interval', schedule: 'Scheduled cloud agents (routines)', 'claude-api': 'Claude API and SDK reference', 'workflow-authoring': 'Write a multi-agent workflow', run: "Launch this project's app", 'run-skill-generator': 'Generate a run skill', 'plugin-authoring': 'Build a mod or plugin',
  advisor: 'Ask the advisor model', 'auto-mode-setup': 'Set up auto mode', autocompact: 'Toggle auto-compaction', color: 'Set the session color', 'output-style': 'Change output style', fast: 'Toggle fast mode', focus: 'Focus mode', heapdump: 'Write a heap dump', import: 'Import from another tool', 'reload-plugins': 'Reload plugins', 'reload-skills': 'Reload skills',
  ultrareview: 'Deep cloud code review', 'usage-credits': 'Usage credits', 'extra-usage': 'Extra usage', insights: 'Insights about your usage', recap: 'Recap the session', 'skill-doctor': 'Diagnose skills', goal: 'Set a goal for the session', 'list-agents': 'List agents', 'team-onboarding': 'Team onboarding', 'design-consent': 'Design consent', 'design-revoke': 'Revoke design consent',
  'anthropic-skills:built-in-browser': 'Use the built-in browser', 'anthropic-skills:chrome-browser': 'Drive Chrome', 'anthropic-skills:computer-use': 'Control the desktop', 'anthropic-skills:deep-research': 'Multi-source research report', 'anthropic-skills:docs': 'Create and edit docs', 'anthropic-skills:docx': 'Word documents', 'anthropic-skills:google-workspace': 'Google Docs, Sheets, Slides',
  'anthropic-skills:import-memory': 'Import memory from another assistant', 'anthropic-skills:morning': 'Morning brief', 'anthropic-skills:pdf': 'Work with PDFs', 'anthropic-skills:pptx': 'PowerPoint decks', 'anthropic-skills:skill-creator': 'Create and test skills', 'anthropic-skills:xlsx': 'Spreadsheets' };
function cmdList() {
  const m = new Map(Object.entries(LOCAL).map(([n, v]) => [n, v[0]]));
  [...Object.keys(PASS), ...S.cmds].forEach(n => { if (!m.has(n) && !n.startsWith('__')) m.set(n, PASS[n] || ((S.skills || []).includes(n) ? 'Skill' : 'Claude Code command')); });
  return [...m].sort((a, b) => a[0].localeCompare(b[0]));
}
let csel = 0, clist = [];
function showCmds() {
  const v = $('#in').value, p = $('#cmds'); fmode = false;
  if (!v.startsWith('/') || /\s/.test(v)) { p.style.display = 'none'; return; }
  const q = v.slice(1).toLowerCase();
  clist = cmdList().filter(([n]) => n.toLowerCase().includes(q)).sort((a, b) => b[0].startsWith(q) - a[0].startsWith(q) || a[0].localeCompare(b[0])).slice(0, 40);
  if (!clist.length) { p.style.display = 'none'; return; }
  csel = Math.min(csel, clist.length - 1);
  p.innerHTML = clist.map(([n, d], i) => `<div class="mi cmd ${i === csel ? 'sel' : ''}" data-n="${esc(n)}"><b>/${esc(n)}${(S.skills || []).includes(n) ? '<small class="tag">skill</small>' : ''}</b><small>${esc(d)}</small></div>`).join('');
  p.querySelectorAll('.mi').forEach(el => el.onmousedown = e => { e.preventDefault(); $('#in').value = '/' + el.dataset.n + ' '; p.style.display = 'none'; $('#in').focus(); });
  p.style.display = 'block'; const s = p.querySelector('.sel'); if (s) s.scrollIntoView({block:'nearest'});
}
