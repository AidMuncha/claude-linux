
/* permission / question / plan cards */
/* rewind */
const rewindPending = {};
function restoreConv(id, uid) {
  const c = chats[id], idx = c ? c.items.findIndex(x => x.k === 'user' && x.uid === uid) : -1; if (idx < 0) return toast('That message is no longer in this chat', true);
  const it = c.items[idx]; c.items.splice(idx);
  if (it.after) c.resumeAt = it.after; else { c.session = null; c.resumeAt = null; }
  c.lastAsst = it.after || null; c.tasks = {}; delete st[id]; setBusy(id, false);
  post({type:'resetproc', chat:id}); persistChat(id); renderAll();
  if (id === cur) { $('#in').value = it.text || ''; resize(); $('#in').focus(); }
  toast('Conversation restored. Edit the message and send it again');
}
function rewindResult(id, p) {
  if (!p.dry) { const mode = rewindPending[p.uid]; delete rewindPending[p.uid]; if (!p.ok) return toast(p.error || 'Could not restore files', true); toast('Files restored'); if (mode === 'both') restoreConv(id, p.uid); return; }
  const canFiles = p.ok && p.files.length, n = p.files.length, d = document.createElement('div'); d.className = 'msg pc';
  d.innerHTML = `<div class="ph2"><span>Rewind to before this message?</span><small>${canFiles ? n + ' file' + (n === 1 ? '' : 's') + ' changed since' : p.ok ? 'no file changes since' : esc(p.error || 'files unavailable')}</small></div>${canFiles ? `<div class="pbody"><pre class="cmd">${esc(p.files.map(f => f.replace(home, '~')).join('\n'))}</pre></div>` : ''}<div class="opts"></div>`;
  const o = d.querySelector('.opts'), btn = (t, fn, pr) => { const b = document.createElement('button'); b.className = 'opt' + (pr ? ' primary' : ''); b.textContent = t; b.onclick = () => { d.remove(); fn(); }; o.appendChild(b); };
  if (canFiles) btn('Restore code and conversation', () => { rewindPending[p.uid] = 'both'; post({type:'rewind', chat:id, uid:p.uid, dry:false}); }, true);
  if (canFiles) btn('Restore code only', () => post({type:'rewind', chat:id, uid:p.uid, dry:false}));
  btn('Restore conversation only', () => restoreConv(id, p.uid), !canFiles); btn('Cancel', () => {});
  if (id === cur) { $('#col').appendChild(d); scrollEnd(true); }
}

const permEls = new Map(), permOpts = new Map();
function expirePerms(id) { const c = chats[id]; if (!c) return; for (const it of c.items) if (it.k === 'perm' && it.status === 'wait') { it.status = 'gone'; redrawPerm(it); } }
function redrawPerm(it) { const old = permEls.get(it.rid); if (old && old.isConnected) old.replaceWith(permEl(it)); }
function answerPerm(it, allow, o) {
  o = o || {}; const c = chats[it.chat]; if (!c || it.status !== 'wait') return;
  post({type:'perm_reply', chat:it.chat, rid:it.rid, allow, input:o.input || it.input, perms:o.perms, message:o.message});
  it.status = allow ? 'allow' : 'deny'; it.summary = o.summary || (allow ? 'Allowed' : 'Denied');
  if (o.mode) { c.mode = o.mode; post({type:'setmode', chat:it.chat, mode:o.mode}); renderComposer(); }
  permOpts.delete(it.rid); redrawPerm(it); renderList(); persistChat(it.chat); if (it.chat === cur) $('#in').focus();
}
const ruleOf = sg => sg.rules.map(r => r.ruleContent ? `${r.toolName}(${r.ruleContent})` : r.toolName).join(', ');
function permEl(it) {
  const d = document.createElement('div'), inp = it.input || {}; permEls.set(it.rid, d);
  const waiting = it.status === 'wait'; d.className = 'msg pc' + (waiting ? '' : ' done');
  const ask = it.tool === 'AskUserQuestion', plan = it.tool === 'ExitPlanMode';
  const title = ask ? 'Claude has a question' : plan ? 'Ready to code?' : `Allow <b>${esc(it.tool)}</b>?`;
  let sub = ask ? '' : plan ? 'Review the plan below' : esc(it.desc && it.tool !== 'Bash' ? it.desc : it.blocked ? it.blocked : '');
  let body = '';
  if (ask) {
    it.sel = it.sel || {}; it.other = it.other || {};
    body = (inp.questions || []).map((q, qi) => `<div class="q" data-qi="${qi}"><h4>${q.header ? `<span class="chipx">${esc(q.header)}</span>` : ''}${esc(q.question)}</h4>` +
      (q.options || []).map(o => `<div class="qo ${q.multiSelect ? 'multi' : ''} ${(it.sel[qi] || []).includes(o.label) ? 'on' : ''}" data-l="${esc(o.label)}"><i></i><span><b>${esc(o.label)}</b>${o.description ? `<small>${esc(o.description)}</small>` : ''}</span></div>`).join('') +
      `<input class="why" data-o="${qi}" placeholder="Other…" value="${esc(it.other[qi] || '')}"></div>`).join('');
  } else if (plan) body = `<div class="plan">${md(inp.plan || '')}</div>`;
  else if (it.tool === 'Bash') body = `<pre class="cmd">${esc(inp.command || '')}</pre>${it.desc ? `<div style="color:var(--dim);font-size:12.5px">${esc(it.desc)}</div>` : ''}`;
  else if (EDIT_TOOLS[it.tool]) { const df = toolDiff({name:it.tool, input:inp}); sub = esc(inp.file_path || ''); body = `<div class="df">${df.html}</div>`; }
  else body = `<pre class="cmd">${esc(JSON.stringify(inp, null, 2).slice(0, 1500))}</pre>`;
  if (!waiting) {
    const sum = it.status === 'gone' ? 'Expired (the run ended before this was answered)' : ask && it.status === 'allow' ? 'Answered' : (it.status === 'allow' ? '✓ ' : '✕ ') + (it.summary || '');
    d.innerHTML = `<div class="ph2"><span>${title}</span>${sub ? `<small>${sub}</small>` : ''}</div><div class="pbody">${ask ? '' : body}</div><div class="res">${esc(sum)}</div>`;
    if (ask && it.status === 'allow') d.querySelector('.pbody').innerHTML = (inp.questions || []).map(q => `<div class="q"><h4>${esc(q.question)}</h4><div style="color:var(--dim)">→ ${esc((it.answers || {})[q.question] || '')}</div></div>`).join('');
    if (plan) d.querySelector('.plan').style.maxHeight = '160px';
    return d;
  }
  d.innerHTML = `<div class="ph2"><span>${title}</span>${sub ? `<small>${sub}</small>` : ''}</div><div class="pbody">${body}</div><div class="opts"></div>`;
  const opts = d.querySelector('.opts'), fns = [];
  const add = (label, fn, primary) => { const b = document.createElement('button'); b.className = 'opt' + (primary ? ' primary' : ''); b.innerHTML = `<kbd>${fns.length + 1}</kbd><span>${label}</span>`; b.onclick = fn; opts.appendChild(b); fns.push(fn); };
  const why = ph => { const w = document.createElement('input'); w.className = 'why'; w.placeholder = ph; opts.appendChild(w); return w; };
  if (ask) {
    d.querySelectorAll('.q').forEach(qe => {
      const qi = +qe.dataset.qi, q = inp.questions[qi];
      qe.querySelectorAll('.qo').forEach(el => el.onclick = () => {
        const l = el.dataset.l, cur2 = it.sel[qi] || [];
        if (q.multiSelect) it.sel[qi] = cur2.includes(l) ? cur2.filter(x => x !== l) : [...cur2, l]; else { it.sel[qi] = [l]; it.other[qi] = ''; qe.querySelector('.why').value = ''; }
        qe.querySelectorAll('.qo').forEach(o => o.classList.toggle('on', it.sel[qi].includes(o.dataset.l)));
      });
      qe.querySelector('.why').oninput = e => { it.other[qi] = e.target.value; if (!q.multiSelect && e.target.value) { it.sel[qi] = []; qe.querySelectorAll('.qo').forEach(o => o.classList.remove('on')); } };
    });
    const submit = () => {
      const answers = {}; let ok = true;
      (inp.questions || []).forEach((q, qi) => { const parts = [...(it.sel[qi] || [])]; if ((it.other[qi] || '').trim()) parts.push(it.other[qi].trim()); if (!parts.length) ok = false; answers[q.question] = parts.join(', '); });
      if (!ok) return toast('Answer every question first', true);
      it.answers = answers; answerPerm(it, true, {input:{...inp, answers}, summary:'Answered'});
    };
    add('Submit answers', submit, true);
    add('Skip', () => answerPerm(it, false, {message:'The user skipped this question.', summary:'Skipped'}));
    d.querySelectorAll('.why').forEach(w => w.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); submit(); } });
  } else if (plan) {
    add('Yes, and auto-accept edits', () => answerPerm(it, true, {perms:[{type:'setMode', mode:'acceptEdits', destination:'session'}], mode:'acceptEdits', summary:'Plan approved, edits auto-accepted'}), true);
    add('Yes, and manually approve edits', () => answerPerm(it, true, {perms:[{type:'setMode', mode:'default', destination:'session'}], mode:'default', summary:'Plan approved, edits need approval'}));
    const w = why('No, keep planning: tell Claude what to change (Enter)');
    w.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); answerPerm(it, false, {message:'The user rejected the plan' + (w.value.trim() ? ': ' + w.value.trim() : '. Keep planning.'), summary:w.value.trim() || 'Plan rejected'}); } };
    fns.push(() => w.focus());
  } else {
    add('Yes', () => answerPerm(it, true), true);
    const rule = (it.sugg || []).find(x => x.type === 'addRules'), mode = (it.sugg || []).find(x => x.type === 'setMode');
    if (rule) add(`Yes, and don't ask again for <code>${esc(ruleOf(rule).slice(0, 80))}</code>`, () => answerPerm(it, true, {perms:[rule], summary:"Allowed, won't ask again"}));
    if (mode) add(mode.mode === 'acceptEdits' ? 'Yes, allow all edits this session' : `Yes, and switch to ${esc(modeName(mode.mode))} for this session`, () => answerPerm(it, true, {perms:[mode], mode:mode.mode, summary:'Allowed (' + modeName(mode.mode) + ')'}));
    const w = why("No: tell Claude what to do differently (Enter)");
    const deny = () => answerPerm(it, false, {message:"The user doesn't want to proceed with this tool use." + (w.value.trim() ? ' User feedback: ' + w.value.trim() : ''), summary:w.value.trim() ? 'Denied: ' + w.value.trim() : 'Denied'});
    w.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); deny(); } };
    fns.push(() => w.focus());
  }
  permOpts.set(it.rid, fns);
  return d;
}
document.addEventListener('keydown', e => {
  if (/^[1-9]$/.test(e.key) && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName) && $('#modal').style.display !== 'flex') {
    const c = chats[cur], it = c && [...c.items].reverse().find(x => x.k === 'perm' && x.status === 'wait');
    const fns = it && permOpts.get(it.rid); if (fns && fns[+e.key - 1] && it.tool !== 'AskUserQuestion') { e.preventDefault(); fns[+e.key - 1](); }
  }
});

$('#in').addEventListener('input', () => {
  csel = 0; resize(); showCmds();
  const v = $('#in').value; $('#box').classList.toggle('bang', v[0] === '!' && isCode(chats[cur]));
  const t = tokenAt(); if (t && v[0] !== '/' && isCode(chats[cur])) post({type:'files', chat:cur, cwd:(chats[cur] || {}).cwd || home, q:t.q});
});
$('#in').addEventListener('paste', e => { const fs = [...(e.clipboardData.files || [])].filter(f => f.type.startsWith('image/')); if (fs.length) { e.preventDefault(); addFiles(fs); } });
$('#attbtn').innerHTML = ico('clip'); $('#attbtn').onclick = () => $('#attfile').click();
$('#attfile').onchange = e => { addFiles(e.target.files); e.target.value = ''; };
const MODE_CYCLE = ['default', 'acceptEdits', 'plan'];
$('#in').addEventListener('keydown', e => {
  const open = $('#cmds').style.display === 'block', inp = $('#in');
  if (fmode && open) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); fsel = (fsel + (e.key === 'ArrowDown' ? 1 : flist.length - 1)) % flist.length; showFiles(); return; }
    if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) { e.preventDefault(); e.stopImmediatePropagation(); pickFile(fsel); return; }
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); fmode = false; $('#cmds').style.display = 'none'; return; }
  }
  if (e.key === 'Tab' && e.shiftKey && !open) {
    e.preventDefault(); const c = chats[cur]; if (!isCode(c)) return;
    const m = c.mode || S.settings.mode, n = MODE_CYCLE[(MODE_CYCLE.indexOf(m) + 1) % MODE_CYCLE.length];
    c.mode = n; persist(); renderComposer(); post({type:'setmode', chat:cur, mode:n}); toast('Permission mode: ' + modeName(n)); return;
  }
  if (!open && e.key === 'ArrowUp' && inp.selectionStart === 0 && inp.selectionEnd === 0 && hist.length && hi < hist.length - 1) { e.preventDefault(); hi++; inp.value = hist[hist.length - 1 - hi]; resize(); return; }
  if (!open && e.key === 'ArrowDown' && hi >= 0 && inp.selectionStart === inp.value.length) { e.preventDefault(); hi--; inp.value = hi < 0 ? '' : hist[hist.length - 1 - hi]; resize(); return; }
  if (open && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) { e.preventDefault(); csel = (csel + (e.key === 'ArrowDown' ? 1 : clist.length - 1)) % clist.length; showCmds(); return; }
  if (open && (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey && inp.value.slice(1) !== clist[csel][0]))) { e.preventDefault(); inp.value = '/' + clist[csel][0] + ' '; $('#cmds').style.display = 'none'; return; }
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') { if ($('#modal').style.display === 'flex') closePanel(); else if (chats[cur] && chats[cur].busy) stopChat(); } });
$('#sendb').onclick = send; $('#new').onclick = newChat;
document.querySelectorAll('#tabs button').forEach(b => b.onclick = () => { tab = b.dataset.t; const n = visible().find(c => c.items.length); n ? select(n.id) : newChat(); });

