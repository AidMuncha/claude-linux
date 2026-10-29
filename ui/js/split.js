/* ---------- split view: a second chat beside the main one ---------- */
S.split = null;
const splitOpen = {};      // tool card id -> opened by the user in the split pane
let splitT = 0, splitFresh = false;
function toggleSplit() { if (S.split) closeSplit(); else pickSplit(); }
function pickSplit() {
  const others = Object.values(chats).filter(c => c.id !== cur && c.items.length).sort((a, b) => b.t - a.t).slice(0, 14);
  if (!others.length) return toast('Start a second chat first, then split the view to see both');
  listMenu($('#splbtn'), [{ head:'Show beside this chat' }, ...others.map(c => ({ label:c.title, sub:kindOf(c) === 'chat' ? 'Chat' : ((c.cwd || '').split('/').filter(Boolean).pop() || ''), run:() => openSplit(c.id) }))], false, 340);
}
function openSplit(id) { S.split = id; splitFresh = true; renderSplit(); }
function closeSplit() { S.split = null; renderSplit(); }
function scheduleSplit() { if (splitT) return; splitT = setTimeout(() => { splitT = 0; renderSplit(); }, 250); }
function renderSplit() {
  const app = $('#app');
  if (S.split === cur) S.split = null;       // opening that chat in the main pane ends the split
  const c = S.split && chats[S.split];
  if (!c) { S.split = null; app.classList.remove('splitting'); $('#scol').innerHTML = ''; return; }
  app.classList.add('splitting'); $('#stitle').textContent = c.title + (c.busy ? '  ·  working…' : '');
  const sc = $('#sscroll'), col = $('#scol'), atEnd = splitFresh || sc.scrollHeight - sc.scrollTop - sc.clientHeight < 140, was = sc.scrollTop;
  col.innerHTML = '';
  for (const it of c.items.slice(-80)) {
    const d = document.createElement('div');
    if (it.k === 'user') { d.className = 'msg user'; d.textContent = it.text; }
    else if (it.k === 'text') { d.className = 'msg asst'; d.innerHTML = md(it.text); }
    else if (it.k === 'think') { d.className = 'msg'; d.innerHTML = `<details class="think"><summary>Thinking</summary><div>${esc(it.text)}</div></details>`; }
    else if (it.k === 'tool') { const [cls, html] = toolHTML(it), open = splitOpen[it.id] ?? OPEN_TOOL(it); d.className = 'msg ' + cls + (open ? ' open noanim' : ''); d.dataset.tid = it.id; d.innerHTML = html; }
    else if (it.k === 'perm') { if (it.status !== 'wait') continue; d.className = 'msg sys'; d.textContent = 'Waiting for your answer in that chat: ' + (it.tool || 'permission'); }
    else if (it.k === 'div') { d.className = 'msg divider'; d.textContent = it.text; }
    else if (it.k === 'err') { d.className = 'msg errtxt'; d.textContent = it.text; }
    else { d.className = 'msg sys'; d.textContent = it.text; }
    col.appendChild(d);
  }
  sc.scrollTop = atEnd ? sc.scrollHeight : was; splitFresh = false;
}
$('#scol').addEventListener('click', e => { const th = e.target.closest('.th'); if (th) { const el = th.parentElement; splitOpen[el.dataset.tid] = !el.classList.contains('open'); } });
$('#splbtn').innerHTML = ico('split'); $('#splbtn').onclick = e => { e.stopPropagation(); toggleSplit(); };
$('#sswap').innerHTML = ico('swap'); $('#sswap').onclick = () => { const o = S.split; if (!o) return; S.split = cur; tab = kindOf(chats[o]); select(o); };
$('#sclose').innerHTML = ico('x'); $('#sclose').onclick = closeSplit;
