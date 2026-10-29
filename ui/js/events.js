
/* ---------- events from the CLI ---------- */
const HIDDEN_TOOLS = { AskUserQuestion: 1, ExitPlanMode: 1 };
const findTool = (c, tid) => c.items.find(x => x.k === 'tool' && x.id === tid);
let taskRaf = 0;
function handleSys(id, c, ev) {
  const t = c.tasks = c.tasks || {};
  if (ev.subtype === 'compact_boundary') { pushItem(id, {k:'div', text:'Conversation compacted'}); scrollEnd(); persistChat(id); }
  else if (ev.subtype === 'task_started') t[ev.task_id] = {id:ev.task_id, desc:ev.description || ev.task_type || 'Task', type:ev.subagent_type || '', status:'running', tokens:0};
  else if (ev.subtype === 'task_progress' && t[ev.task_id]) { if (ev.description) t[ev.task_id].desc = ev.description; t[ev.task_id].tokens = (ev.usage || {}).total_tokens || t[ev.task_id].tokens; }
  else if ((ev.subtype === 'task_updated' && ev.patch && ev.patch.status || ev.subtype === 'task_notification') && t[ev.task_id]) t[ev.task_id].status = (ev.patch && ev.patch.status) || ev.status || 'completed';
  else if (ev.subtype === 'background_tasks_changed') { const live = new Set((ev.tasks || []).map(x => x.task_id)); for (const k in t) if (!live.has(k) && t[k].status === 'running') t[k].status = 'completed'; }
  else return;
  if (id === cur && !taskRaf) taskRaf = requestAnimationFrame(() => { taskRaf = 0; renderTasks(); });
}
function renderTasks() {
  const c = chats[cur], ts = Object.values((c && c.tasks) || {}), run = ts.filter(x => x.status === 'running'), chip = $('#taskchip');
  chip.classList.toggle('hide', !run.length); chip.innerHTML = `<span class="g y"></span>${run.length} agent${run.length > 1 ? 's' : ''} running`;
  if (S.drawer) renderDrawer();
}
$('#taskchip').onclick = () => { S.drawer = true; renderRC(); };
function handle(id, ev) {
  const c = chats[id]; if (!c) return;
  const par = ev.parent_tool_use_id;
  if (ev.type === 'system') { handleSys(id, c, ev); return; }
  if (ev.type === 'assistant' && !par && ev.uuid) c.lastAsst = ev.uuid;
  if (par && ev.type === 'stream_event') return;
  if (par && (ev.type === 'assistant' || ev.type === 'user')) {
    const p = findTool(c, par), ct = ev.message && ev.message.content; if (!p || !Array.isArray(ct)) return;
    p.kids = p.kids || [];
    for (const b of ct) {
      if (b.type === 'tool_use') p.kids.push({id:b.id, name:b.name, input:b.input, result:null});
      else if (b.type === 'tool_result') { const k = p.kids.find(x => x.id === b.tool_use_id); if (k) { k.result = trimLines(resultText(b.content), 20); k.err = !!b.is_error; } }
    }
    refreshTool(id, p); persistChat(id); return;
  }
  if (ev.type === 'stream_event') {
    const e = ev.event;
    if (e.type === 'message_start' && !c.busy) setBusy(id, true);
    if (e.type === 'message_start') endLive(id);
    if (e.type === 'content_block_delta' && e.delta.type === 'text_delta') {
      let s = st[id];
      if (!s) { const item = {k:'text', text:''}; s = st[id] = { item, raw:'', shown:0, streamed:true }; s.el = pushItem(id, item); if (s.el) s.el.classList.add('live'); }
      s.raw += e.delta.text; s.item.text = s.raw;
      if (id === cur && !pending) pending = requestAnimationFrame(typeTick);
    }
  }
  else if (ev.type === 'assistant') {
    for (const b of ev.message.content) {
      if (b.type === 'thinking' && b.thinking && b.thinking.trim()) pushItem(id, {k:'think', text:b.thinking});
      else if (b.type === 'tool_use' && HIDDEN_TOOLS[b.name]) endLive(id);
      else if (b.type === 'tool_use') { endLive(id); pushItem(id, {k:'tool', id:b.id, name:b.name, input:b.input, result:null}); }
      else if (b.type === 'text' && b.text.trim() && !(st[id] && st[id].streamed)) pushItem(id, {k:'text', text:b.text});
    }
    scrollEnd();
  }
  else if (ev.type === 'user' && ev.isReplay) {
    if (!mine.has(ev.uuid)) {
      const ct = ev.message.content, text = typeof ct === 'string' ? ct : (ct || []).filter(b => b.type === 'text').map(b => b.text).join('\n');
      if (text.trim()) { if (!c.items.length) c.title = text.slice(0, 44); pushItem(id, {k:'user', text, remote:true}); if (!c.busy) setBusy(id, true); scrollEnd(true); renderList(); }
    }
  }
  else if (ev.type === 'user' && Array.isArray(ev.message.content)) {
    for (const b of ev.message.content) if (b.type === 'tool_result') {
      const it = [...c.items].reverse().find(x => x.k === 'tool' && x.id === b.tool_use_id); if (!it) continue;
      it.result = trimLines(resultText(b.content), 80) || '(no output)'; it.err = !!b.is_error;
      const el = id === cur && toolEls[it.id];
      if (el) reTool(el, it);
    }
    scrollEnd();
  }
  else if (ev.type === 'result') {
    if (!ev.is_error) celebrate(id);
    const u = ev.usage || {}, t = c.tokens = c.tokens || {i:0, o:0, cr:0, cc:0, cost:0};
    t.i += u.input_tokens || 0; t.o += u.output_tokens || 0; t.cr += u.cache_read_input_tokens || 0; t.cc += u.cache_creation_input_tokens || 0; t.cost += ev.total_cost_usd || 0;
    for (const d of ev.permission_denials || []) {
      const it = c.items.find(x => x.k === 'tool' && x.id === d.tool_use_id);
      if (it) { it.result = null; settleTools(id, 'Permission denied: this action was not allowed in the current permission mode, so it did not run.', it.id); }
    }
    settleTools(id, 'No result: the command was interrupted or did not run.');
    if (ev.is_error && ev.result) pushItem(id, {k:'err', text:ev.result});
  }
  persistChat(id);
}

window.fromPyBatch = items => { for (const [n, p] of items) { try { window.fromPy(n, p); } catch (e) { post({type:'jserr', text:String(e && e.stack || e)}); } } };
window.fromPy = (name, p) => {
  if (EXTRA[name]) return EXTRA[name](p);
  if (name === 'init') {
    chats = p.chats || {}; home = p.home; S.version = p.version; S.appVersion = p.appVersion; Object.assign(S.settings, p.settings || {}); S.usage = p.usage; Object.values(chats).forEach(c => { delete c.rc; delete c.queue; delete c.tasks; expirePerms(c.id); });
    applyAppearance(); applySidebar(true); post({type:'getfile', which:'settings'});
    const first = Object.values(chats).sort((a, b) => b.t - a.t)[0];
    if (first) { tab = kindOf(first); select(first.id); } else newChat();
    return;
  }
  if (name === 'toast') return toast(p.text, p.err);
  if (name === 'mcp_state') { S.mcp = p; if ($('#modal').style.display === 'flex' && panel === 'mcp') showPage(true); return; }
  if (name === 'cmds') { S.cmds = p.commands || []; S.skills = p.skills || []; return; }
  if (name === 'sysmsg') return sys(p.text);
  if (name === 'usage') { S.usage = p; renderUsage(); if ($('#modal').style.display === 'flex' && panel === 'usage') showPage(true); return; }
  if (name === 'account') { S.account = p; if (S.drawer) renderRC(); if ($('#modal').style.display === 'flex' && panel === 'about') showPage(true); return; }
  if (name === 'file') { S.files[p.which] = p; if ($('#modal').style.display === 'flex' && ['config', 'perms', 'advanced', 'memory', 'hooks'].includes(panel)) showPage(true); return; }
  if (name === 'cwd') { if (chats[cur]) setCwd(p.path); return; }
  const id = p.chat; if (!chats[id]) return;
  if (name === 'done') { expirePerms(id); settleTools(id, 'No result: the command was interrupted or did not run.'); setBusy(id, false); persistChat(id); if (id === cur) $('#in').focus(); drainQueue(id); }
  else if (name === 'error') { expirePerms(id); settleTools(id, 'No result: the command crashed or was interrupted.'); pushItem(id, {k:'err', text:p.text, resume:!!chats[id].session}); setBusy(id, false); scrollEnd(); persistChat(id); }
  else if (name === 'meta_init') { chats[id].session = p.session; S.model = p.model; if (p.commands && p.commands.length) S.cmds = p.commands; renderComposer(); }
  else if (name === 'event') handle(id, p.ev);
  else if (name === 'perm') { const it = {k:'perm', chat:id, rid:p.rid, tool:p.tool, input:p.input, desc:p.desc, sugg:p.suggestions, blocked:p.blocked, status:'wait'}; pushItem(id, it); if (id === cur) scrollEnd(true); renderList(); persistChat(id); }
  else if (name === 'perm_cancel') { const it = chats[id].items.find(x => x.k === 'perm' && x.rid === p.rid && x.status === 'wait'); if (it) { it.status = 'gone'; redrawPerm(it); } }
  else if (name === 'rewind') rewindResult(id, p);
  else if (name === 'files') { const t = tokenAt(); if (id === cur && t && t.q === p.q && p.files.length) { fmode = true; flist = p.files; fsel = 0; showFiles(); } }
  else if (name === 'bang') { const it = findTool(chats[id], p.id); if (it) { it.result = trimLines((p.out + (p.err ? '\n' + p.err : '')).trim(), 200) || '(no output)'; it.err = p.code !== 0; refreshTool(id, it); const c2 = chats[id]; c2.ctx = (c2.ctx || '') + `<bash-input>${it.input.command}</bash-input>\n<bash-stdout>${p.out}</bash-stdout><bash-stderr>${p.err}</bash-stderr>\n`; scrollEnd(); persistChat(id); } }
  else if (name === 'rc_resp') { const c = chats[id]; if (p.ok) { if (c.rc && c.rc.on) c.rc.url = p.url || c.rc.url; } else if (c.rc && c.rc.on) { c.rc = {on:false, err:p.error}; toast(p.error || 'Remote Control failed', true); } renderRC(); if ($('#modal').style.display === 'flex' && panel === 'remote') showPage(true); }
  else if (name === 'rc_state') { const c = chats[id]; if (c.rc && c.rc.on) { c.rc.state = p.state; if (p.state === 'disconnected' || p.state === 'failed') c.rc.err = 'Disconnected'; } renderRC(); }
};
