/* ---------- "New Update Required": download and install a new version, with a progress bar ---------- */
Object.assign(IC, { download:'<path d="M12 4v11M7 11l5 5 5-5M5 20h14"/>' });
const UPD = { p:null };
const mb = n => (n / 1048576).toFixed(1) + ' MB';
function renderUpdate() {
  const p = UPD.p, m = $('#updmodal'), box = $('#updbox');
  if (!p || p.state === 'dismissed') { m.classList.remove('on'); return; }
  const required = p.required !== false, later = !required && p.state !== 'ready' && p.state !== 'downloading';
  const head = (t, s) => `<div class="uicon">${ico('download')}</div><h2>${t}</h2><p class="usub">${s}</p>`;
  const laterBtn = later ? '<button class="btn g" data-upd="later">Later</button>' : '';
  let h = '';
  if (p.state === 'available') {
    h = head(required ? 'New Update Required' : 'New update available', `Claude Linux ${esc(p.version)} is ready${p.current ? ` (you have ${esc(p.current)})` : ''}.`)
      + (p.notes ? `<div class="unotes">${esc(p.notes)}</div>` : '')
      + (p.canInstall === false ? `<p class="uerr">This copy was not set up with the installer, so it cannot update itself. Run the installer again to update.</p><div class="uact"><button class="btn g" data-upd="later">Close</button></div>`
        : `<div class="uact"><button class="btn" data-upd="download">Download now</button>${laterBtn}</div>`);
  } else if (p.state === 'downloading') {
    const pct = p.total ? Math.min(100, Math.round(p.done / p.total * 100)) : 0;
    h = head('Downloading update…', `Claude Linux ${esc(p.version || '')}`) + `<div class="ubar busy"><i style="width:${p.total ? pct : 8}%"></i></div><div class="unum">${p.total ? `${pct}%  ·  ${mb(p.done)} of ${mb(p.total)}` : mb(p.done || 0)}</div><div class="uact"><button class="btn" disabled>Downloading…</button></div>`;
  } else if (p.state === 'ready') {
    h = head('Update installed', `Claude Linux ${esc(p.version)} is ready. Restart to start using it.`) + `<div class="ubar"><i style="width:100%"></i></div><div class="unum">100%</div><div class="uact"><button class="btn" data-upd="restart">Restart now</button></div>`;
  } else if (p.state === 'error') {
    h = head(required ? 'Update Required' : 'Update problem', 'The update could not be installed.') + `<p class="uerr">${esc(p.message || 'Something went wrong.')}</p><div class="uact"><button class="btn" data-upd="${p.retry === 'check' ? 'check' : 'download'}">Try again</button>${required ? '<button class="btn g" data-upd="quit">Quit</button>' : laterBtn}</div>`;
  }
  box.innerHTML = h; m.classList.add('on');
  const barEl = box.querySelector('.ubar i'); if (barEl && p.state === 'downloading' && p.total) barEl.style.width = Math.min(100, p.done / p.total * 100) + '%';
}
EXTRA.update = p => {
  if (p.state === 'current') return toast('You have the latest version (' + p.version + ')');
  if (p.state === 'disabled') return toast('Updates are not set up for this copy');
  UPD.p = { ...(p.state === 'available' ? {} : UPD.p), ...p }; renderUpdate();
};
$('#updmodal').addEventListener('click', e => {
  const b = e.target.closest('[data-upd]'); if (!b) return; const a = b.dataset.upd;
  if (a === 'download') post({type:'update_download'});
  else if (a === 'restart') post({type:'update_restart'});
  else if (a === 'check') post({type:'update_check'});
  else if (a === 'quit') post({type:'quit'});
  else if (a === 'later') { UPD.p = null; renderUpdate(); }
});
PAGE_BIND.about = b => b.querySelectorAll('[data-upd="check"]').forEach(x => x.onclick = () => post({type:'update_check'}));
