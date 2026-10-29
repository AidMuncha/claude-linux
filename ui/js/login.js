/* ---------- sign in: start `claude auth login`, wait in the browser, come back to the app ---------- */
const LG = { s:'idle', url:'', msg:'', line:'', retry:'', needCode:false };
const needLogin = () => { const a = S.account; return !!a && (a.loggedIn === false || a.missing === true); };
function renderLogin() {
  const el = $('#loginpage'), box = $('#loginbox'), missing = !!(S.account && S.account.missing);
  if (!needLogin() && LG.s !== 'done') { el.classList.remove('on', 'leaving'); return; }
  const logo = spin => `<div class="llogo ${spin ? 'spin' : ''}">${LOGO_CC}</div>`;
  let h = '';
  if (LG.s === 'done') h = `<div class="ltick">${ico('check')}</div><h1>You're signed in</h1><p class="lsub">Taking you back…</p>`;
  else if (LG.s === 'installing') h = `${logo(true)}<h1>Installing Claude Code…</h1><p class="lsub">This takes a minute. You only do this once.</p><div class="lline">${esc(LG.line)}</div>`;
  else if (LG.s === 'waiting') h = `${logo(true)}<h1>Finish signing in</h1><p class="lsub">A browser window opened. Sign in there and this window will take over by itself.</p>
      ${LG.needCode ? `<p class="lsub" style="margin:-8px 0 12px">Your browser could not hand the sign-in back by itself. Copy the code the page shows and paste it here.</p><div class="lrow" style="margin-bottom:14px"><input class="txt" id="lgcode" placeholder="Paste the code" spellcheck="false" autocomplete="off" style="min-width:230px"><button class="btn" data-lg="code" style="min-width:110px">Continue</button></div>` : ''}
      <div class="lrow">${LG.url ? '<button class="btn g" data-lg="open">Open the page again</button><button class="btn g" data-lg="copy">Copy link</button>' : ''}<button class="btn g" data-lg="cancel">Cancel</button></div>
      <div class="lnote">${LG.url ? 'Browser did not open? Use the buttons above.' : 'Starting the sign-in…'}</div>`;
  else if (LG.s === 'error') h = `${logo(false)}<h1>${LG.retry === 'install' ? 'Install problem' : 'Sign-in problem'}</h1><p class="lerr">${esc(LG.msg)}</p><button class="btn" data-lg="${LG.retry === 'install' ? 'install' : 'login'}">Try again</button>`;
  else if (missing) h = `${logo(false)}<h1>One more thing</h1><p class="lsub">Claude Linux needs Claude Code, which isn't installed on this computer yet. One click installs it.</p><button class="btn" data-lg="install">Install Claude Code</button>
      <div class="lnote">Runs Anthropic's official installer (claude.ai/install.sh). Prefer a terminal? Run: <code>curl -fsSL https://claude.ai/install.sh | bash</code></div>`;
  else h = `${logo(false)}<h1>Welcome to Claude Linux</h1><p class="lsub">Sign in with your Claude account to get started.</p><button class="btn" data-lg="login">Sign in with Claude</button>
      <button class="lalt" data-lg="console">Use an Anthropic Console account (API billing) instead</button>
      <div class="lnote">This opens your browser. When you're done you land right back here.</div>`;
  const keep = ($('#lgcode') || {}).value; box.innerHTML = h; el.classList.remove('leaving'); el.classList.add('on');
  const ci = $('#lgcode'); if (ci) { if (keep) ci.value = keep; ci.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); box.querySelector('[data-lg=code]').click(); } }; if (!keep) ci.focus(); }
}
EXTRA.login = p => {
  if (p.state === 'done') {
    LG.s = 'done'; S.account = { ...(S.account || {}), loggedIn:true, missing:false }; renderLogin();
    setTimeout(() => { $('#loginpage').classList.add('leaving'); setTimeout(() => { LG.s = 'idle'; LG.url = ''; renderLogin(); $('#in').focus(); }, motionOff() ? 0 : 500); }, motionOff() ? 100 : 1100);
    return;
  }
  LG.s = p.state; if (p.url) LG.url = p.url; if (p.state === 'idle') LG.url = ''; LG.needCode = !!p.needCode || (p.state === 'waiting' && LG.needCode); if (p.state !== 'waiting') LG.needCode = false; LG.msg = p.message || ''; LG.line = p.line || ''; LG.retry = p.retry || '';
  renderLogin();
};
$('#loginpage').addEventListener('click', e => {
  const b = e.target.closest('[data-lg]'); if (!b) return; const a = b.dataset.lg;
  if (a === 'login' || a === 'console') { LG.s = 'waiting'; LG.url = ''; LG.needCode = false; renderLogin(); post({type:'login', mode:a === 'console' ? 'console' : 'claudeai'}); }
  else if (a === 'cancel') post({type:'login_cancel'});
  else if (a === 'code') { const v = ($('#lgcode') || {}).value || ''; if (v.trim()) post({type:'login_code', code:v.trim()}); }
  else if (a === 'open' && LG.url) post({type:'open_url', url:LG.url});
  else if (a === 'copy' && LG.url) navigator.clipboard.writeText(LG.url).then(() => toast('Link copied')).catch(() => toast(LG.url));
  else if (a === 'install') post({type:'install_cli'});
});
