
/* ---------- busy / spinner ---------- */
const verbs = ['Thinking', 'Pondering', 'Cogitating', 'Noodling', 'Working', 'Computing'];
function renderBusy() {
  clearInterval(spinT); const c = chats[cur];
  renderComposer();
  if (!c || !c.busy) { $('#status').innerHTML = ''; return; }
  const v = verbs[Math.floor(Math.random() * verbs.length)];
  $('#status').innerHTML = '<span class="st">' + LOGO_CC + '</span><span class="shim"></span><span class="el"></span>';
  const [a, b, t] = $('#status').children, tick = () => {
    const w = (c.items.some(x => x.k === 'perm' && x.status === 'wait') ? 'Waiting for you' : v) + '…'; if (b.textContent !== w) b.textContent = w;
    t.textContent = Math.floor((Date.now() - (spinStart[cur] || Date.now())) / 1000) + 's · esc to interrupt';
  };
  tick(); spinT = setInterval(tick, 250);
}
function setBusy(id, on) {
  const c = chats[id]; if (!c) return; c.busy = on;
  if (on) spinStart[id] = Date.now();
  else { delete spinStart[id]; endLive(id); }
  renderList(); if (id === cur) renderBusy();
}

/* ---------- typewriter reveal for streaming answers ---------- */
function typeTick() {
  pending = 0; const q = st[cur]; if (!q || !q.el) return;
  const back = q.raw.length - q.shown; if (back <= 0) return;
  q.shown += Math.max(1, Math.ceil(back / 14));
  if (/[\ud800-\udbff]/.test(q.raw[q.shown - 1] || '')) q.shown++;
  // finished paragraphs are rendered once; only the unfinished tail is re-rendered per frame
  if (!q.tail || !q.el.contains(q.tail)) {
    q.el.innerHTML = '<div class="stable"></div><div class="tail"></div>';
    q.stable = q.el.firstChild; q.tail = q.el.lastChild; q.cut = 0;
  }
  const text = q.raw.slice(0, q.shown), at = text.lastIndexOf('\n\n') + 2;
  if (at > q.cut && (text.slice(0, at).match(/```/g) || []).length % 2 === 0) {
    q.stable.insertAdjacentHTML('beforeend', md(text.slice(q.cut, at))); q.cut = at;
  }
  q.tail.innerHTML = md(text.slice(q.cut)); scrollEnd();
  if (q.shown < q.raw.length) pending = requestAnimationFrame(typeTick);
}
function endLive(id) {
  const s = st[id];
  if (s && s.el) { if (s.shown < s.raw.length) { s.el.innerHTML = md(s.raw); s.shown = s.raw.length; } s.el.classList.remove('live'); }
  delete st[id];
}

// a tool that never got a result (denied, interrupted, crashed) must not look like it is still running or succeeded
function settleTools(id, why, only) {
  const c = chats[id]; if (!c) return;
  for (const it of c.items) if (it.k === 'tool' && it.result == null && !it.bang && (!only || it.id === only)) {
    it.result = why; it.err = true;
    const el = id === cur && toolEls[it.id];
    if (el) reTool(el, it);
  }
}
