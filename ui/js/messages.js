/* ---------- messages ---------- */
function hero() {
  const c = chats[cur] || {};
  return tab === 'chat' ? `<div class="hero">${LOGO}<h1>How can I help?</h1><p>Chat mode — Claude can't touch your computer.</p></div>`
    : `<div class="hero">${LOGO}<h1>What are we building?</h1><p>Code mode in <b>${esc(c.cwd || home)}</b></p></div>`;
}
function renderChat() {
  const col = $('#col'); col.innerHTML = ''; toolEls = {};
  const c = chats[cur]; if (!c) return;
  if (!c.items.length) col.innerHTML = hero();
  const ps = st[cur], LIM = 60, items = showAll[cur] || c.items.length <= LIM ? c.items : c.items.slice(-LIM);
  col.classList.add('norise'); requestAnimationFrame(() => requestAnimationFrame(() => col.classList.remove('norise')));
  if (items.length < c.items.length) { const b = document.createElement('button'); b.className = 'earlier'; b.textContent = `Show ${c.items.length - items.length} earlier items`; b.onclick = () => { showAll[cur] = true; renderChat(); $('#scroll').scrollTop = 0; }; col.appendChild(b); }
  items.forEach(it => { const el = addItem(it); if (ps && ps.item === it) { ps.el = el; ps.shown = ps.raw.length; el.classList.add('live'); } });
  $('#scroll').scrollTop = $('#scroll').scrollHeight;
}
const toolArg = i => i.command || i.file_path || i.pattern || i.path || i.url || i.query || i.description || JSON.stringify(i);
const EDIT_TOOLS = { Edit: 1, MultiEdit: 1, Write: 1 };
function toolDiff(it) {
  const i = it.input || {};
  const pairs = it.name === 'Write' ? [['', i.content || '']] : it.name === 'MultiEdit' ? (i.edits || []).map(e => [e.old_string || '', e.new_string || '']) : [[i.old_string || '', i.new_string || '']];
  const rows = []; let add = 0, del = 0;
  for (const [o, n] of pairs) {
    const a = o ? o.split('\n') : [], b = n ? n.split('\n') : [];
    let p = 0; while (p < a.length && p < b.length && a[p] === b[p]) p++;
    let s = 0; while (s < a.length - p && s < b.length - p && a[a.length - 1 - s] === b[b.length - 1 - s]) s++;
    const row = (cls, n, sign, t) => rows.push(`<div class="dr ${cls}" style="--n:${Math.min(rows.length, 14)}"><i>${n}</i><b>${sign}</b><span>${esc(t)}</span></div>`);
    if (rows.length) rows.push('<div class="dr sep"><i></i><b></b><span>⋯</span></div>');
    for (let k = Math.max(0, p - 2); k < p; k++) row('ctx', k + 1, ' ', a[k]);
    a.slice(p, a.length - s).forEach((t, k) => { row('del', p + k + 1, '−', t); del++; });
    b.slice(p, b.length - s).forEach((t, k) => { row('add', p + k + 1, '+', t); add++; });
    for (let k = 0; k < Math.min(2, s); k++) row('ctx', b.length - s + k + 1, ' ', b[b.length - s + k]);
  }
  const MAX = 300, more = rows.length - MAX;
  return { add, del, html: rows.slice(0, MAX).join('') + (more > 0 ? `<div class="dr sep"><i></i><b></b><span>… ${more} more lines</span></div>` : '') };
}
const OPEN_TOOL = it => EDIT_TOOLS[it.name] || it.bang || it.name === 'TodoWrite';
function toolHTML(it) {
  const state = it.result == null ? 'run' : it.err ? 'err' : 'ok';
  const d = EDIT_TOOLS[it.name] && toolDiff(it), inp = it.input || {};
  const cnt = d ? `<span class="dc"><em class="p">+${d.add}</em><em class="m">−${d.del}</em></span>` : '';
  const isAg = it.name === 'Agent' || it.name === 'Task';
  const todos = it.name === 'TodoWrite' && Array.isArray(inp.todos) ? inp.todos : null;
  const kids = (it.kids || []).map(k => `<div class="kid ${k.result == null ? 'run' : k.err ? 'err' : 'ok'}"><b>${esc(k.name)}</b>${esc(String(toolArg(k.input)).slice(0, 160))}</div>`).join('');
  let body = d ? `<div class="df">${d.html}</div>` + (it.err && it.result ? `<div class="dr er"><span>${esc(it.result)}</span></div>` : '') : it.result != null ? esc(it.result) : '(running…)';
  if (todos) body = '<div class="todo">' + todos.map(t => `<div class="${t.status === 'completed' ? 'done' : t.status === 'in_progress' ? 'cur' : ''}"><span>${t.status === 'completed' ? '☑' : t.status === 'in_progress' ? '◐' : '☐'}</span><span>${esc(t.status === 'in_progress' && t.activeForm ? t.activeForm : t.content)}</span></div>`).join('') + '</div>';
  else if (kids) body = `<div class="kids">${kids}</div>` + body;
  const name = isAg ? 'Agent' + (inp.subagent_type ? ' · ' + inp.subagent_type : '') : it.name;
  let arg = String(toolArg(inp)).slice(0, 200);
  if (todos) arg = `${todos.filter(t => t.status === 'completed').length}/${todos.length} done`;
  else if (isAg && it.kids && it.kids.length) arg = (inp.description || '') + ` · ${it.kids.length} tool call${it.kids.length > 1 ? 's' : ''}`;
  return [`tool ${state}`, `<div class="th"><span class="ts">${state === 'ok' ? ico('check') : state === 'err' ? ico('x') : ''}</span><span class="n">${esc(name)}</span><span class="a">${esc(arg)}</span>${cnt}${ico('chev', 'chev')}</div><div class="tb">${body}</div>`];
}
function reTool(el, it) {
  const open = el.classList.contains('open'), [cls, html] = toolHTML(it);
  el.className = 'msg ' + cls + (open ? ' open noanim' : ''); el.innerHTML = html;
  if (open) setTimeout(() => el.classList.remove('noanim'), 700);
}
function refreshTool(id, it) {
  const el = id === cur && toolEls[it.id];
  if (el) reTool(el, it);
}
function ctxBar(t) {
  if (!/^## Context Usage/m.test(t)) return '';
  const m = t.match(/\*\*Tokens:\*\*[^(]*\((\d+(?:\.\d+)?)%\)/); if (!m) return '';
  return `<div class="ctxbar"><i style="width:${Math.min(100, +m[1])}%"></i><span>${m[1]}% of context used</span></div>`;
}
function addItem(it) {
  let d = document.createElement('div');
  if (it.k === 'user') { d.className = 'msg user'; if (it.remote) { const w = document.createElement('span'); w.className = 'who'; w.textContent = 'Remote'; d.appendChild(w); } if (it.imgs) { const w = document.createElement('span'); w.className = 'imgs'; w.textContent = '🖼 ' + it.imgs + ' image' + (it.imgs > 1 ? 's' : ''); d.appendChild(w); } d.appendChild(document.createTextNode(it.text)); if (it.uid && isCode(chats[cur])) { const r = document.createElement('button'); r.className = 'rw'; r.textContent = '↶'; r.title = 'Restore files to before this message'; r.onclick = () => post({type:'rewind', chat:cur, uid:it.uid, dry:true}); d.appendChild(r); } }
  else if (it.k === 'perm') d = permEl(it);
  else if (it.k === 'text') { d.className = 'msg asst'; d.innerHTML = ctxBar(it.text) + md(it.text); }
  else if (it.k === 'think') { d.className = 'msg'; d.innerHTML = `<details class="think"><summary>Thinking</summary><div>${esc(it.text)}</div></details>`; }
  else if (it.k === 'div') { d.className = 'msg divider'; d.textContent = it.text; }
  else if (it.k === 'tool') { const [cls, html] = toolHTML(it); d.className = 'msg ' + cls + (OPEN_TOOL(it) ? ' open' : ''); d.innerHTML = html; toolEls[it.id] = d; }
  else if (it.k === 'err') { d.className = 'msg errtxt'; d.textContent = it.text; if (it.resume) { const b = document.createElement('button'); b.className = 'resume'; b.textContent = 'Resume'; b.onclick = () => { it.resume = false; b.remove(); const c = Object.values(chats).find(x => x.items.includes(it)); if (c) dispatch(c.id, 'continue', []); }; d.appendChild(b); } }
  else { d.className = 'msg sys'; d.textContent = it.text; }
  $('#col').appendChild(d); return d;
}
function pushItem(id, it) {
  const c = chats[id]; if (!c) return null;
  if (!c.items.length && id === cur) $('#col').innerHTML = '';
  c.items.push(it); c.t = Date.now();
  return id === cur ? addItem(it) : null;
}
function sys(text) { if (cur) { pushItem(cur, {k:'sys', text}); scrollEnd(true); persist(); } else toast(text); }
function scrollEnd(force) { const s = $('#scroll'); if (force || s.scrollHeight - s.scrollTop - s.clientHeight < 180) s.scrollTop = s.scrollHeight; }
const resultText = c => typeof c === 'string' ? c : Array.isArray(c) ? c.map(x => x.text || '').join('\n') : JSON.stringify(c);
const trimLines = (t, n) => { const l = t.split('\n'); return l.length > n ? l.slice(0, n).join('\n') + `\n… +${l.length - n} lines` : t; };
