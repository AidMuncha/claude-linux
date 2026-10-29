/* ---------- settings window ---------- */
const HOOK_EVENTS = ['PreToolUse', 'PostToolUse', 'UserPromptSubmit', 'Stop', 'SubagentStop', 'SessionStart', 'SessionEnd', 'Notification', 'PreCompact'];
const PAGES = [['general', 'General', 'cog'], ['model', 'Model', 'cpu'], ['config', 'Claude Code', 'code'], ['perms', 'Permissions', 'shield'], ['remote', 'Remote Control', 'remote'], ['usage', 'Usage', 'gauge'], ['memory', 'Memory', 'doc'], ['mcp', 'MCP servers', 'code'], ['hooks', 'Hooks', 'refresh'], ['advanced', 'Advanced', 'tool'], ['about', 'About', 'info']];
function openPanel(p) { closePops(); $('#modal').style.display = 'flex'; go(p); }
function closePanel() { $('#modal').style.display = 'none'; }
$('#modal').onclick = e => { if (e.target.id === 'modal') closePanel(); };
function go(p) { panel = p; if (p === 'mcp') { S.mcp = null; post({type:'mcp_list'}); } post({type:'getfile', which:'settings'}); if (p === 'memory') post({type:'getfile', which:'memory'}); if (p === 'usage') post({type:'refresh_usage'}); showPage(); }
const swH = (id, on) => `<label class="sw"><input type="checkbox" data-id="${id}" ${on ? 'checked' : ''}><i></i></label>`;
const selH = (id, opts, val) => `<select class="sel" data-id="${id}">${opts.map(([v, l]) => `<option value="${esc(v)}" ${String(val ?? '') === v ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
const setRow = (t, d, c) => `<div class="set"><div class="tx"><b>${t}</b>${d ? `<small>${d}</small>` : ''}</div>${c}</div>`;
const CONFIG = [
  ['permissions.defaultMode', 'Default permission mode', 'How Claude handles actions that need approval', 'enum', [['', 'Default'], ['acceptEdits', 'Accept edits'], ['plan', 'Plan mode'], ['bypassPermissions', 'Bypass permissions']], ''],
  ['alwaysThinkingEnabled', 'Always-on thinking', 'Let Claude think before every response', 'bool', null, false],
  ['includeCoAuthoredBy', 'Co-authored-by trailer', 'Add “Co-Authored-By: Claude” to commits Claude makes', 'bool', null, true],
  ['outputStyle', 'Output style', 'Adjust how Claude responds', 'enum', [['', 'Default'], ['Explanatory', 'Explanatory'], ['Learning', 'Learning']], ''],
  ['autoUpdatesChannel', 'Auto-update channel', 'Which release stream Claude Code updates from', 'enum', [['latest', 'Latest'], ['stable', 'Stable']], 'latest'],
  ['cleanupPeriodDays', 'Keep transcripts for (days)', 'Older conversations are deleted automatically', 'num', null, 30],
  ['enableAllProjectMcpServers', 'Approve all project MCP servers', 'Trust MCP servers defined in project .mcp.json files', 'bool', null, false],
];
function showPage(keep) {
  const b = $('#pbody'), sc = b.scrollTop, s = S.settings, c = cfg();
  $('#pnav').innerHTML = '<h3>Settings</h3>' + PAGES.map(([k, l, i]) => `<button data-k="${k}" class="${k === panel ? 'on' : ''}">${ico(i)}${l}</button>`).join('');
  $('#pnav').querySelectorAll('button').forEach(x => x.onclick = () => go(x.dataset.k));
  b.innerHTML = `<button class="ib" id="pclose">${ico('x')}</button>` + PAGE[panel](s, c);
  $('#pclose').onclick = closePanel; bindPage(b, s, c); if (PAGE_BIND[panel]) PAGE_BIND[panel](b); if (keep) b.scrollTop = sc;
}
const PAGE_BIND = {};   // per-page event wiring, registered by pages.js
const PAGE = {
  general: s => `<div class="ph">General</div><p class="pd">How Claude Linux looks and where it works.</p>
    <div class="card">${setRow('Theme and appearance', 'Colors, fonts, background and animations', '<button class="btn g" data-go="appearance">Open</button>')}</div>
    <div class="sec">Workspace</div><div class="card">
        ${setRow('Default folder', 'Where new Code sessions start', `<input class="txt" data-id="cwd" value="${esc(s.cwd || '')}" placeholder="${esc(home)}">`)}
    ${setRow('Default permission mode', 'Used by new Code sessions', selH('mode', MODES.map(m => [m[0], m[1]]), s.mode))}
    ${setRow('Desktop notifications', 'When Claude needs you or finishes a long task while this window is in the background', swH('notify', s.notify !== false))}</div>
    <div class="sec">Additional folders</div><textarea class="ta" data-id="addDirs" rows="3" placeholder="One folder per line. Claude may access these in every Code session.">${esc((s.addDirs || []).join('\n'))}</textarea>
    <div class="sec">Extra instructions</div><textarea class="ta" data-id="appendPrompt" rows="4" placeholder="Appended to Claude's system prompt in Code sessions.">${esc(s.appendPrompt || '')}</textarea>`,
  model: s => `<div class="ph">Model</div><p class="pd">Pick the model and how hard it thinks. Applies from your next message.</p><div class="card">
    ${MODELS.map(([id, n, d]) => `<div class="opt ${(s.model || '') === id ? 'on' : ''}" data-model="${id}"><span class="rd"></span><div class="tx"><b>${esc(n)}</b><small>${esc(id ? d : (S.model ? 'Currently ' + modelName(S.model) : d))}</small></div></div>`).join('')}</div>
    <div class="sec">Context and effort</div><div class="card">
    ${setRow('Extended context', '1M-token context window (where the model supports it)', swH('long', s.long))}
    ${setRow('Reasoning effort', 'How much Claude thinks before answering', selH('effort', EFFORTS, s.effort))}
    ${setRow('Fallback model', 'Used automatically if the main model is overloaded', selH('fallback', [['', 'None'], ...MODELS.slice(1, 5).map(m => [m[0], m[1]])], s.fallback))}
    ${setRow('Maximum turns', '0 means no limit per request', `<input class="num" type="number" min="0" data-id="maxTurns" value="${s.maxTurns || 0}">`)}</div>`,
  config: (s, c) => `<div class="ph">Claude Code</div><p class="pd">Saved to <code>~/.claude/settings.json</code> and used by Claude Code everywhere.</p>
    <input class="search" id="cfgq" placeholder="Search settings">
    <div class="card" id="cfglist">${CONFIG.map(([k, t, d, ty, opts, def]) => { const v = pick(c, k), val = v === undefined ? def : v;
      return `<div class="set" data-q="${esc((t + ' ' + d).toLowerCase())}"><div class="tx"><b>${t}</b><small>${d}</small></div>${ty === 'bool' ? swH('c:' + k, val) : ty === 'num' ? `<input class="num" type="number" data-id="c:${k}" value="${val}">` : selH('c:' + k, opts, val)}</div>`; }).join('')}</div>
    <p class="pd" style="margin-top:14px">Anything else (hooks, environment variables, status line, MCP servers) is in <a href="#" data-go="advanced" style="color:var(--accent)">Advanced</a>.</p>`,
  perms: (s, c) => { const pm = c.permissions || {}; return `<div class="ph">Permissions</div><p class="pd">Rules Claude Code follows in every session. Examples: <code>Bash(git status)</code>, <code>Read(~/projects/**)</code>, <code>Edit</code>.</p>
    ${['allow', 'ask', 'deny'].map(k => `<div class="sec">${k === 'allow' ? 'Always allow' : k === 'ask' ? 'Always ask' : 'Always deny'}</div><textarea class="ta" rows="4" data-p="${k}" placeholder="One rule per line">${esc((pm[k] || []).join('\n'))}</textarea>`).join('')}
    <div style="margin-top:16px"><button class="btn" id="psave">Save permissions</button></div>`; },
  mcp: () => { const m = S.mcp;
    const rows = !m ? '<p class="pd">Checking servers…</p>' : m.error ? `<p class="pd">${esc(m.error)}</p>` : m.rows.map(r => { const ok = /connected/i.test(r.status), auth = /auth/i.test(r.status);
      return `<div class="hk"><span class="ev" style="color:var(--fg)">${esc(r.name)}</span><code title="${esc(r.target)}">${esc(r.target)}</code><span class="mst ${ok ? 'ok' : auth ? 'warn' : 'bad'}">${esc(r.status.replace(/^[^\w]+/, ''))}</span><button data-mrm="${esc(r.name)}" title="Remove">✕</button></div>`; }).join('') || '<p class="pd">No MCP servers configured.</p>';
    return `<div class="ph">MCP servers</div><p class="pd">Tools and data sources Claude can use. Servers that need sign-in must be authenticated once in a terminal: run <code>claude</code>, then <code>/mcp</code>.</p>${rows}
    <div class="sec">Add a server</div><div class="hform">
      <input class="ta" id="mname" placeholder="Name, e.g. github" spellcheck="false">
      <select class="sel" id="mtr"><option value="stdio">Local command (stdio)</option><option value="http">Remote (http)</option><option value="sse">Remote (sse)</option></select>
      <input class="ta" id="mtarget" placeholder="Command (npx -y @scope/server) or URL" spellcheck="false">
      <select class="sel" id="mscope"><option value="user">All my projects</option><option value="local">This folder only (local)</option><option value="project">Shared with the project</option></select>
      <div><button class="btn" id="madd">Add server</button></div></div>`; },
  hooks: (s, c) => { const h = c.hooks || {}, rows = [];
    Object.entries(h).forEach(([ev, arr]) => (arr || []).forEach((g, gi) => (g.hooks || []).forEach((x, hi) => rows.push(`<div class="hk"><span class="ev">${esc(ev)}</span>${g.matcher ? `<span>${esc(g.matcher)}</span>` : ''}<code title="${esc(x.command || x.prompt || x.url || '')}">${esc(x.command || x.prompt || x.url || x.type)}</code><button data-hdel="${esc(ev)}|${gi}|${hi}" title="Remove">✕</button></div>`))));
    return `<div class="ph">Hooks</div><p class="pd">Shell commands Claude Code runs automatically at points in its lifecycle (for example after every file edit). They apply to every session, here and in the terminal.</p>
    ${rows.join('') || '<p class="pd">No hooks yet.</p>'}
    <div class="sec">Add a hook</div><div class="hform">
      <select class="sel" id="hev">${HOOK_EVENTS.map(e => `<option>${e}</option>`).join('')}</select>
      <input class="ta" id="hmatch" placeholder="Matcher (optional), e.g. Edit|Write or Bash" spellcheck="false">
      <input class="ta" id="hcmd" placeholder="Command, e.g. prettier --write &quot;$CLAUDE_PROJECT_DIR&quot;" spellcheck="false">
      <div><button class="btn" id="hadd">Add hook</button></div></div>`; },
  remote: () => { const on = Object.values(chats).filter(c => c.rc && c.rc.on);
    return `<div class="ph">Remote Control</div><p class="pd">Remote Control is per chat, like <code>/remote-control</code> in Claude Code. Turn it on in a Code chat from the Session panel (or type <code>/remote-control</code>) to continue that chat from claude.ai/code or the Claude app, or to let someone on your account join it.</p>
    <div class="card">${on.length ? on.map(c => `<div class="set"><div class="tx"><b>${esc(c.title)}</b><small>${c.rc.state === 'connected' ? 'Connected' : 'Connecting…'} · ${esc(c.cwd || '')}</small></div><button class="btn g" data-open="${esc(c.rc.url || '')}" ${c.rc.url ? '' : 'disabled'}>Open</button><button class="btn red" data-rcoff="${c.id}">Turn off</button></div>`).join('') : setRow('No chats are remote-controlled', 'Open a Code chat and use the toggle in its Session panel.', '')}</div>
    <p class="pd" style="margin-top:14px">Requires a Claude subscription login (not an API key). Everything runs on this computer with your account; the other device only sends and reads messages.</p><button class="btn g" data-open="https://claude.ai/code">Open claude.ai/code</button>`; },
  usage: () => `<div class="ph">Usage</div><p class="pd">Plan usage limits for your account, read from Claude Code (the same numbers as <code>/usage</code>).</p><div class="card" style="padding:6px 18px 14px">${usageBlock()}<div class="uf"><span>${S.usage && S.usage.ts ? 'Last updated: ' + ago(S.usage.ts) : ''}</span><button class="btn g" id="urefresh2">Refresh</button></div></div>
    ${S.usage && S.usage.text ? `<div class="sec">Details from Claude Code</div><pre class="raw">${esc(S.usage.text)}</pre>` : ''}`,
  memory: () => { const f = S.files.memory; return `<div class="ph">Memory</div><p class="pd">${f ? esc(f.path) : 'Loading…'} — instructions Claude reads in every session.</p><textarea class="ta big" id="raw" spellcheck="false">${f ? esc(f.text) : ''}</textarea><div style="margin-top:12px"><button class="btn" id="rsave" data-w="memory">Save</button></div>`; },
  advanced: () => { const f = S.files.settings; return `<div class="ph">Advanced</div><p class="pd">${f ? esc(f.path) : 'Loading…'} — every Claude Code setting (hooks, env, MCP servers, status line…) as JSON.</p><textarea class="ta big" id="raw" spellcheck="false">${f ? esc(f.text) : ''}</textarea><div style="margin-top:12px"><button class="btn" id="rsave" data-w="settings">Save</button></div>`; },
  about: () => `<div class="ph">About</div><p class="pd">Claude Linux is a desktop window around Claude Code v${esc(S.version)}.</p><div class="card">${setRow('Claude Linux version', esc(S.appVersion || ''), '<button class="btn g" data-upd="check">Check for updates</button>')}${setRow('Chat', 'No tools; Claude cannot touch this computer', '')}${setRow('Code', 'Full Claude Code tools in the folder you choose', '')}${setRow('Account', S.account && S.account.loggedIn ? esc((S.account.plan || '') + ' plan · signed in with ' + (S.account.method === 'claude.ai' ? 'your Claude subscription' : S.account.method)) : 'Checking…', '')}${setRow('Chats are stored in', '<code>~/.local/share/claude-linux/chats/</code>', '')}</div>`,
};
function bindPage(b, s, c) {
  b.querySelectorAll('[data-go]').forEach(a => a.onclick = e => { e.preventDefault(); go(a.dataset.go); });
  b.querySelectorAll('[data-open]').forEach(a => a.onclick = () => a.dataset.open && post({type:'open_url', url:a.dataset.open}));
  b.querySelectorAll('[data-theme-pick]').forEach(a => a.onclick = () => { applyTheme(a.dataset.themePick); showPage(true); });
  b.querySelectorAll('[data-rcoff]').forEach(a => a.onclick = () => { const id = a.dataset.rcoff, c = chats[id]; c.rc = {on:false}; post({type:'rc_chat', chat:id, on:false}); renderRC(); showPage(true); });
  b.querySelectorAll('[data-model]').forEach(o => o.onclick = () => { setSetting('model', o.dataset.model); showPage(true); });
  b.querySelectorAll('[data-id]').forEach(el => el.onchange = () => {
    const id = el.dataset.id, ty = el.type; let v = ty === 'checkbox' ? el.checked : ty === 'number' ? (parseInt(el.value) || 0) : el.value;
    if (id === 'rcmode') return;
    if (id.startsWith('c:')) { const k = id.slice(2); cset(k, v); if (k === 'permissions.defaultMode' && v) setSetting('mode', v); return; }
    if (id === 'addDirs') v = v.split('\n').map(x => x.trim()).filter(Boolean);
    setSetting(id, v);
    if (id === 'mode') cset('permissions.defaultMode', v);
  });
  const q = b.querySelector('#cfgq'); if (q) q.oninput = () => b.querySelectorAll('#cfglist .set').forEach(r => r.classList.toggle('hide', !r.dataset.q.includes(q.value.toLowerCase())));
  const ps = b.querySelector('#psave'); if (ps) ps.onclick = () => { const j = cfg(); j.permissions = j.permissions || {}; b.querySelectorAll('[data-p]').forEach(el => { const v = el.value.split('\n').map(x => x.trim()).filter(Boolean); if (v.length) j.permissions[el.dataset.p] = v; else delete j.permissions[el.dataset.p]; }); post({type:'putfile', which:'settings', text: JSON.stringify(j, null, 2) + '\n'}); };
  const rs = b.querySelector('#rsave'); if (rs) rs.onclick = () => post({type:'putfile', which:rs.dataset.w, text:$('#raw').value});
  b.querySelectorAll('[data-mrm]').forEach(x => x.onclick = () => { S.mcp = null; showPage(true); post({type:'mcp_remove', name:x.dataset.mrm}); });
  const ma = b.querySelector('#madd'); if (ma) ma.onclick = () => { const name = $('#mname').value.trim(), target = $('#mtarget').value.trim(); if (!name || !target) return toast('Enter a name and a command or URL', true); S.mcp = null; post({type:'mcp_add', name, target, transport:$('#mtr').value, scope:$('#mscope').value}); showPage(true); };
  b.querySelectorAll('[data-hdel]').forEach(x => x.onclick = () => {
    const [ev, gi, hi] = x.dataset.hdel.split('|'), j = cfg(), g = j.hooks && j.hooks[ev] && j.hooks[ev][+gi]; if (!g) return;
    g.hooks.splice(+hi, 1); if (!g.hooks.length) j.hooks[ev].splice(+gi, 1); if (!j.hooks[ev].length) delete j.hooks[ev]; if (!Object.keys(j.hooks).length) delete j.hooks;
    post({type:'putfile', which:'settings', text:JSON.stringify(j, null, 2) + '\n'});
  });
  const ha = b.querySelector('#hadd'); if (ha) ha.onclick = () => {
    const ev = $('#hev').value, m = $('#hmatch').value.trim(), cmd = $('#hcmd').value.trim(); if (!cmd) return toast('Enter a command', true);
    const j = cfg(); j.hooks = j.hooks || {}; (j.hooks[ev] = j.hooks[ev] || []).push({...(m ? {matcher:m} : {}), hooks:[{type:'command', command:cmd}]});
    post({type:'putfile', which:'settings', text:JSON.stringify(j, null, 2) + '\n'});
  };
  const u2 = b.querySelector('#urefresh2'); if (u2) u2.onclick = () => post({type:'refresh_usage'});
}
