
/* ---------- sending ---------- */
const showAll = {};
let att = [], fmode = false, flist = [], fsel = 0, hi = -1;
const hist = (() => { try { return JSON.parse(localStorage.getItem('hist') || '[]'); } catch (e) { return []; } })();
const clearInput = () => { $('#in').value = ''; resize(); $('#box').classList.remove('bang'); };
const stopChat = () => { const c = chats[cur]; if (c) c.queue = []; renderQueue(); post({type:'stop', chat:cur}); };
function renderAtt() {
  $('#att').innerHTML = att.map((a, i) => `<div class="th2"><img src="${a.url}"><button data-i="${i}">✕</button></div>`).join('');
  $('#att').querySelectorAll('button').forEach(b => b.onclick = () => { att.splice(+b.dataset.i, 1); renderAtt(); });
}
function addFiles(files) {
  for (const f of files) if (f.type.startsWith('image/')) { const r = new FileReader(); r.onload = () => { att.push({type:f.type, data:String(r.result).split(',')[1], url:r.result}); renderAtt(); }; r.readAsDataURL(f); }
}
function renderQueue() {
  const c = chats[cur], q = $('#queue');
  q.innerHTML = ((c && c.queue) || []).map((m, i) => `<div><span>Queued: ${esc(m.text || '[image]')}</span><button data-i="${i}" title="Remove">✕</button></div>`).join('');
  q.querySelectorAll('button').forEach(b => b.onclick = () => { c.queue.splice(+b.dataset.i, 1); renderQueue(); });
}
function send() {
  const text = $('#in').value.trim(), c = chats[cur];
  if (!c) return;
  if (!text && !att.length) { if (c.busy) stopChat(); return; }
  $('#cmds').style.display = 'none';
  if (text) { if (hist[hist.length - 1] !== text) hist.push(text); hist.splice(0, hist.length - 100); try { localStorage.setItem('hist', JSON.stringify(hist)); } catch (e) {} } hi = -1;
  const m = text.match(/^\/(\S+)\s*([\s\S]*)$/);
  if (m && LOCAL[m[1]]) { clearInput(); LOCAL[m[1]][1](m[2].trim()); return; }
  if (text[0] === '!' && text.length > 1 && isCode(c)) { clearInput(); runBang(c, text.slice(1).trim()); return; }
  const images = att; att = []; renderAtt(); clearInput();
  if (c.busy) { (c.queue = c.queue || []).push({text, images}); renderQueue(); return; }
  dispatch(c.id, text, images);
}
function dispatch(id, text, images) {
  const c = chats[id]; if (!c) return;
  if (!c.items.length) c.title = (text || 'Image').slice(0, 44);
  const uid = crypto.randomUUID(); mine.add(uid);
  pushItem(id, {k:'user', text, uid, after:c.lastAsst || null, imgs: images.length || undefined}); if (id === cur) scrollEnd(true); setBusy(id, true); persistChat(id);
  const full = (c.ctx || '') + text; c.ctx = ''; c.items.forEach(i => { if (i.resume) i.resume = false; });
  const resumeAt = c.resumeAt; c.resumeAt = null;
  post({type:'send', chat:id, text:full, uuid:uid, kind:kindOf(c), cwd:c.cwd || home, mode:c.mode || S.settings.mode, session:c.session, resumeAt, images:images.map(a => ({type:a.type, data:a.data}))});
}
function runBang(c, cmd) {
  const id = 'bang-' + crypto.randomUUID();
  pushItem(c.id, {k:'tool', id, name:'Bash', input:{command:cmd}, result:null, bang:true}); scrollEnd(true); persistChat(c.id);
  post({type:'bang', chat:c.id, id, cmd, cwd:c.cwd || home});
}
function drainQueue(id) {
  const c = chats[id]; if (!c || !c.queue || !c.queue.length || c.busy) return;
  const n = c.queue.shift(); if (id === cur) renderQueue(); dispatch(id, n.text, n.images || []);
}
function resize() { const i = $('#in'); i.style.height = 'auto'; i.style.height = Math.min(i.scrollHeight, 220) + 'px'; }

/* @file mentions */
function tokenAt() {
  const i = $('#in'), before = i.value.slice(0, i.selectionStart), m = before.match(/(^|\s)@([^\s@]*)$/);
  return m ? { q:m[2], start:before.length - m[2].length - 1, end:i.selectionStart } : null;
}
function showFiles() {
  const p = $('#cmds');
  p.innerHTML = flist.map((f, i) => { const b = f.split('/').pop(); return `<div class="mi cmd ${i === fsel ? 'sel' : ''}" data-i="${i}"><b>${esc(b)}</b><small>${esc(f)}</small></div>`; }).join('');
  p.querySelectorAll('.mi').forEach(el => el.onmousedown = e => { e.preventDefault(); pickFile(+el.dataset.i); });
  p.style.display = 'block'; const s = p.querySelector('.sel'); if (s) s.scrollIntoView({block:'nearest'});
}
function pickFile(i) {
  const t = tokenAt(), inp = $('#in'); if (!t) return;
  const ins = '@' + flist[i] + ' ';
  inp.value = inp.value.slice(0, t.start) + ins + inp.value.slice(t.end); inp.selectionStart = inp.selectionEnd = t.start + ins.length;
  fmode = false; $('#cmds').style.display = 'none'; inp.focus(); resize();
}
