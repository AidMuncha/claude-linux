/* ---------- chats ---------- */
const kindOf = c => c.kind || 'code';
function newChat() {
  const id = crypto.randomUUID();
  chats[id] = { id, title:'New session', kind:tab, session:null, items:[], t:Date.now(), cwd:S.settings.cwd || home, mode:S.settings.mode || 'acceptEdits' };
  select(id);
}
function select(id) { cur = id; renderAll(); $('#in').focus(); }
const visible = () => Object.values(chats).filter(c => kindOf(c) === tab && (c.items.length || c.id === cur)).sort((a, b) => b.t - a.t);
function renderAll() { att = []; renderAtt(); renderQueue(); renderTasks(); renderTabs(); renderList(); renderChat(); renderComposer(); renderBusy(); renderUsage(); renderRC(); applyAppearance(); renderSplit(); }
function renderTabs() {
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.t === tab));
  $('#in').placeholder = tab === 'chat' ? 'Message Claude…  (type / for commands)' : 'Describe what you want to build or fix…  (type / for commands)';
  $('#new').innerHTML = ico('plus') + 'New ' + (tab === 'chat' ? 'chat' : 'session');
  $('#setbtn').innerHTML = ico('gear') + 'Settings';
}
function dayGroup(t) { const d = new Date(t), n = new Date(); const diff = Math.round((new Date(n.getFullYear(), n.getMonth(), n.getDate()) - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 864e5); return diff <= 0 ? 'Today' : diff === 1 ? 'Yesterday' : diff < 8 ? 'Previous 7 days' : 'Older'; }
let sq = '';
$('#search').oninput = e => { sq = e.target.value.trim().toLowerCase(); renderList(); };
$('#search').onkeydown = e => { if (e.key === 'Escape') { e.target.value = ''; sq = ''; renderList(); e.target.blur(); } };
function renderList() {
  const l = $('#list'); l.innerHTML = ''; let last = '';
  visible().filter(c => !sq || c.title.toLowerCase().includes(sq) || c.items.some(i => i.text && String(i.text).toLowerCase().includes(sq))).forEach(c => {
    const g = dayGroup(c.t); if (g !== last) { l.insertAdjacentHTML('beforeend', `<div class="grp">${g}</div>`); last = g; }
    const snip = sq && !c.title.toLowerCase().includes(sq) ? snippet(c, sq) : '', col = safeColor(chatColor(c));
    const d = document.createElement('div'); d.className = 'chat' + (c.id === cur ? ' active' : '') + (snip ? ' hasSnip' : '');
    d.oncontextmenu = e => { e.preventDefault(); e.stopPropagation(); colorMenu(e, c); };
    d.innerHTML = (col ? `<span class="cdot" style="background:${col}"></span>` : '') + (snip ? `<span class="snip">${snip}</span>` : '') + `<span class="t">${esc(c.title)}</span>${c.items.some(x => x.k === 'perm' && x.status === 'wait') ? '<span class="bz ask" title="Waiting for you"></span>' : c.busy ? '<span class="bz"></span>' : ''}<button class="x" title="Delete">${ico('x')}</button>`;
    d.onclick = () => select(c.id);
    d.querySelector('.x').onclick = e => { e.stopPropagation(); delete chats[c.id]; post({type:'delete', id:c.id}); const n = visible().find(x => x.id !== c.id && x.items.length); if (n) select(n.id); else { cur = null; newChat(); } };
    l.appendChild(d);
  });
  const ttl = chats[cur] && chats[cur].items.length ? chats[cur].title : '';
  $('#title').textContent = ttl; if (ttl !== lastTitle) { lastTitle = ttl; post({type:'title', text:ttl}); }
  reportStatusSoon();
}
let lastTitle = null;
function snippet(c, q) {
  const it = c.items.find(i => i.text && String(i.text).toLowerCase().includes(q)); if (!it) return '';
  const t = String(it.text).replace(/\s+/g, ' '), at = t.toLowerCase().indexOf(q), a = Math.max(0, at - 24);
  return (a ? '…' : '') + esc(t.slice(a, at)) + '<mark>' + esc(t.slice(at, at + q.length)) + '</mark>' + esc(t.slice(at + q.length, at + q.length + 60));
}
function renderComposer() {
  const c = chats[cur] || {}, isChat = tab === 'chat', s = S.settings;
  $('#dirbtn').classList.toggle('hide', isChat); $('#modebtn').classList.toggle('hide', isChat);
  $('#dirbtn').innerHTML = ico('folder') + `<span>${esc(((c.cwd || home) || '/').split('/').filter(Boolean).pop() || '/')}</span>`; $('#dirbtn').title = c.cwd || home;
  $('#modebtn').innerHTML = ico('shield') + `<span>${esc(modeName(c.mode || s.mode))}</span>`;
  const nm = modelName(s.model) || (S.model ? modelName(S.model) : 'Default'), ef = s.effort ? ' · ' + effortName(s.effort) : '';
  $('#modelbtn').innerHTML = `<span>${esc(nm + (s.long && s.model ? ' (1M)' : '') + ef)}</span>` + ico('down');
  $('#modelbtn').classList.add('acc');
  $('#sendb').innerHTML = ico(c.busy ? 'stop' : 'send');
}
const isCode = c => c && kindOf(c) !== 'chat';
function renderRC() {
  const c = chats[cur], r = (c && c.rc) || {}, chip = $('#rcchip');
  $('#drbtn').classList.toggle('hide', tab !== 'code'); $('#drbtn').innerHTML = ico('panel');
  chip.classList.toggle('hide', !(r.on && tab === 'code'));
  if (r.on) chip.innerHTML = `<span class="g ${r.state === 'connected' ? '' : 'y'}"></span>Remote · ${r.state === 'connected' ? 'connected' : 'connecting…'}`;
  const d = $('#drawer'); d.classList.toggle('open', S.drawer && tab === 'code');
  if (S.drawer && tab === 'code') renderDrawer();
}
function renderDrawer() {
  const c = chats[cur]; if (!c) return; const r = c.rc || {}, t = c.tokens || {i:0, o:0, cr:0, cc:0, cost:0}, a = S.account;
  const state = !r.on ? ['', 'Off'] : r.state === 'connected' ? ['on', 'Connected'] : r.err ? ['', r.err] : ['y', 'Connecting…'];
  $('#drawer').innerHTML = `<div class="dh"><span>Session</span><button class="ib" id="dclose">${ico('x')}</button></div>
    <div class="dsec"><h4>Remote Control <label class="sw"><input type="checkbox" id="rctog" ${r.on ? 'checked' : ''}><i></i></label></h4>
      <p>Continue this chat from claude.ai/code or the Claude app, or let someone on your account join it. Messages sent from there show up here.</p>
      <div class="rstate"><span class="d ${state[0]}"></span>${esc(state[1])}</div>
      ${r.on && r.url ? `<div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap"><button class="btn" id="rcopen">Open session</button><button class="btn g" id="rccopy">Copy link</button></div>` : ''}</div>
    ${Object.keys(c.tasks || {}).length ? `<div class="dsec"><h4>Background agents</h4>${Object.values(c.tasks).reverse().slice(0, 12).map(x => `<div class="task"><span class="d ${x.status === 'running' ? 'run' : /fail|error|kill|stop/.test(x.status) ? 'bad' : 'ok'}"></span><span class="tx" title="${esc(x.desc)}">${x.type ? '<b>' + esc(x.type) + '</b> · ' : ''}${esc(x.desc)}</span>${x.status === 'running' ? `<button data-stop="${esc(x.id)}">Stop</button>` : ''}</div>`).join('')}</div>` : ''}
    <div class="dsec"><h4>This session</h4>
      <div class="kv"><span>Model</span><span>${esc(modelName(S.settings.model) || (S.model ? modelName(S.model) : 'Default'))}</span></div>
      <div class="kv"><span>Folder</span><span title="${esc(c.cwd || home)}">${esc(((c.cwd || home).split('/').filter(Boolean).pop()) || '/')}</span></div>
      <div class="kv"><span>Permissions</span><span>${esc(modeName(c.mode || S.settings.mode))}</span></div>
      <div class="kv"><span>Input / output</span><span>${fmt(t.i)} / ${fmt(t.o)}</span></div>
      <div class="kv"><span>Cache read / written</span><span>${fmt(t.cr)} / ${fmt(t.cc)}</span></div></div>
    <div class="dsec"><h4>Account</h4>
      ${a && a.loggedIn ? `<div class="kv"><span>Signed in with</span><span>${esc(a.method === 'claude.ai' ? 'Claude subscription' : a.method)}</span></div><div class="kv"><span>Plan</span><span>${esc((a.plan || '').replace(/^./, x => x.toUpperCase()))}</span></div><div class="kv"><span>Account</span><span>${esc(a.email || '')}</span></div>` : '<p>' + (a ? 'Not signed in. Run <code>claude auth login</code> in a terminal.' : 'Checking…') + '</p>'}</div>`;
  $('#dclose').onclick = () => { S.drawer = false; renderRC(); };
  $('#drawer').querySelectorAll('[data-stop]').forEach(b => b.onclick = () => post({type:'stoptask', chat:cur, task_id:b.dataset.stop}));
  $('#rctog').onchange = e => toggleRC(e.target.checked);
  const o = $('#rcopen'); if (o) o.onclick = () => post({type:'open_url', url:r.url});
  const cp = $('#rccopy'); if (cp) cp.onclick = () => navigator.clipboard.writeText(r.url).then(() => toast('Link copied')).catch(() => toast(r.url));
}
const fmt = n => n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? (n / 1e3).toFixed(1) + 'k' : String(n || 0);
function toggleRC(on) {
  const c = chats[cur]; if (!isCode(c)) return toast('Remote Control is only available in Code chats.', true);
  c.rc = on ? {on:true, state:'connecting'} : {on:false}; renderRC();
  post({type:'rc_chat', chat:cur, on, title:c.title, kind:kindOf(c), cwd:c.cwd || home, mode:c.mode || S.settings.mode, session:c.session});
}
$('#drbtn').onclick = () => { S.drawer = !S.drawer; renderRC(); };
$('#rcchip').onclick = () => { S.drawer = true; renderRC(); };
$('#setbtn').onclick = () => openPanel('general');

