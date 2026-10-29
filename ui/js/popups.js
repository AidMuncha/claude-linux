
/* ---------- popups ---------- */
function closePops() { document.querySelectorAll('.pop').forEach(p => p.id !== 'cmds' && (p.style.display = 'none')); }
document.addEventListener('click', closePops);
function place(m, anchor, up) {
  const r = anchor.getBoundingClientRect(); m.style.display = 'block';
  m.style.left = Math.max(8, Math.min(r.left, innerWidth - m.offsetWidth - 8)) + 'px';
  m.style.top = up ? Math.max(8, r.top - m.offsetHeight - 8) + 'px' : (r.bottom + 8) + 'px';
}
function listMenu(anchor, items, up, width) {
  closePops(); const m = $('#menu'); m.style.width = (width || 300) + 'px'; m.innerHTML = ''; m.onclick = null;
  items.forEach(it => {
    if (it.sep) return m.insertAdjacentHTML('beforeend', '<div class="msep"></div>');
    if (it.head) return m.insertAdjacentHTML('beforeend', `<div class="mhead">${esc(it.head)}</div>`);
    const d = document.createElement('div'); d.className = 'mi' + (it.accent ? ' acc' : '');
    d.innerHTML = `<div class="tx"><b>${esc(it.label)}</b>${it.sub ? `<small>${esc(it.sub)}</small>` : ''}</div><span class="ck">${it.on ? ico('check') : ''}</span>`;
    d.onclick = e => { e.stopPropagation(); m.style.display = 'none'; it.run(); }; m.appendChild(d);
  });
  place(m, anchor, up);
}
function modelMenu() {
  closePops(); const m = $('#menu'), s = S.settings; m.style.width = '350px';
  m.innerHTML = '<div class="mhead">Model</div>' + MODELS.map(([id, name, d]) =>
    `<div class="mi" data-m="${id}"><div class="tx"><b>${esc(name)}</b><small>${esc(id ? d : (S.model ? 'Currently ' + modelName(S.model) : d))}</small></div><span class="ck">${(s.model || '') === id ? ico('check') : ''}</span></div>`).join('') +
    `<div class="msep"></div><div class="swrow"><div><b style="font-weight:500;display:block">Extended context</b><small style="color:var(--dim);font-size:12px">1M-token window</small></div><label class="sw"><input type="checkbox" id="long" ${s.long ? 'checked' : ''}><i></i></label></div>
     <div class="msep"></div><div class="mhead">Reasoning effort</div><div class="seg">${EFFORTS.map(([v, l]) => `<button data-e="${v}" class="${(s.effort || '') === v ? 'on' : ''}">${l}</button>`).join('')}</div>`;
  const redo = () => { modelMenu(); };
  m.querySelectorAll('[data-m]').forEach(el => el.onclick = e => { e.stopPropagation(); setSetting('model', el.dataset.m); redo(); });
  m.querySelector('#long').onclick = e => { e.stopPropagation(); setSetting('long', e.target.checked); };
  m.querySelectorAll('[data-e]').forEach(el => el.onclick = e => { e.stopPropagation(); setSetting('effort', el.dataset.e); redo(); });
  m.onclick = e => e.stopPropagation(); place(m, $('#modelbtn'), true);
}
$('#modelbtn').onclick = e => { e.stopPropagation(); modelMenu(); };
$('#modebtn').onclick = e => { e.stopPropagation(); const c = chats[cur]; listMenu($('#modebtn'), [{head:'Permission mode'}, ...MODES.map(([v, l, d]) => ({label:l, sub:d, on:(c.mode || S.settings.mode) === v, run: () => { c.mode = v; persist(); renderComposer(); post({type:'setmode', chat:cur, mode:v}); }}))], true, 360); };
$('#dirbtn').onclick = e => {
  e.stopPropagation(); const rec = [...new Set([home, ...Object.values(chats).map(c => c.cwd).filter(Boolean)])];
  listMenu($('#dirbtn'), [{label:'Choose a folder…', accent:true, run: () => post({type:'pickdir', start:(chats[cur] || {}).cwd})}, {sep:1}, {head:'Recent'}, ...rec.map(r => ({label: r.split('/').filter(Boolean).pop() || '/', sub:r, on:(chats[cur] || {}).cwd === r, run: () => setCwd(r)}))], true, 380);
};
function setCwd(p) { if (chats[cur]) { chats[cur].cwd = p; persist(); renderComposer(); if (!chats[cur].items.length) renderChat(); } }

