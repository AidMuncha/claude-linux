/* ---------- settings pages: Appearance and Desktop ---------- */
PAGES.splice(1, 0, ['appearance', 'Appearance', 'palette']);
PAGES.splice(PAGES.findIndex(p => p[0] === 'advanced'), 0, ['desktop', 'Desktop', 'remote']);

const SYNTAX_THEMES = [['auto', 'Match the theme'], ['monokai', 'Monokai'], ['github', 'GitHub'], ['onedark', 'One Dark'], ['dracula', 'Dracula'], ['nord', 'Nord'], ['solarized', 'Solarized'], ['catppuccin', 'Catppuccin']];
const SYNTAX_DEMO = '```python\n# greet someone\nclass Greeter:\n    def hello(self, name):\n        return f"Hi {name}! {42}"\n```';
const range = (key, lo, hi, step, val, fmtv) => `<input type="range" data-ap-range="${key}" min="${lo}" max="${hi}" step="${step}" value="${val}"><span class="val" data-val="${key}">${fmtv(val)}</span>`;
const apRow = (t, d, c) => `<div class="ap-row"><div class="tx"><b>${t}</b>${d ? `<small>${d}</small>` : ''}</div>${c}</div>`;

function themeTile(id, name, cols, on, adaptive) {
  return `<div class="tc ${adaptive ? 'ad ' : ''}${on ? 'on' : ''}" data-ap-theme="${id}"><div class="pv"><i style="background:${cols[0] || 'var(--bg)'}"></i><i style="background:${cols[1] || 'var(--card)'}"></i><i style="background:${cols[2] || 'var(--accent)'}"></i></div><b>${esc(name)}</b></div>`;
}

PAGE.appearance = s => {
  const k = KDE.scheme, ct = { ...CUSTOM_DEFAULT, ...(s.customTheme || {}) }, themeOpts = THEMES.map(t => [t[0], t[1]]);
  const adaptivePreview = { system:k ? [k.view, k.button, k.accent || k.fg] : [], auto:['#262624', '#faf9f5', '#d97757'], custom:[ct.bg, ct.card, ct.accent] };
  const accOn = safeColor(s.accent);
  return `<div class="ph">Appearance</div><p class="pd">Colors, fonts, background and motion. Changes apply immediately.</p>
    <div class="sec" style="margin-top:0">Theme</div>
    <div class="themes">${ADAPTIVE.map(([id, n]) => themeTile(id, n, adaptivePreview[id], s.theme === id, true)).join('')}</div>
    <div class="tgroup">Built in</div>
    <div class="themes">${THEMES.map(([id, n, c]) => themeTile(id, n, c, s.theme === id, false)).join('')}</div>
    ${s.theme === 'auto' ? `<div class="card" style="margin-top:12px">${apRow('When Plasma is dark', 'Theme used with a dark color scheme', selH('autoDark', themeOpts, s.autoDark || 'dark'))}${apRow('When Plasma is light', 'Theme used with a light color scheme', selH('autoLight', themeOpts, s.autoLight || 'light'))}</div>` : ''}
    ${s.theme === 'system' ? `<div class="card" style="margin-top:12px">${apRow('Colors come from Plasma', k ? 'Scheme: ' + esc(k.name || 'unnamed') + '. Change it in System Settings and this window follows.' : 'Plasma\'s colors could not be read, so Dark or Light is used instead.', '')}${apRow('Use Plasma\'s accent color', 'Otherwise the accent stays orange (or the one you pick below)', swH('kdeAccent', !!s.kdeAccent))}</div>` : ''}

    <div class="sec">Accent color</div>
    <div class="card"><div class="swatches"><button class="swc none ${accOn ? '' : 'on'}" data-ap-accent="" title="Theme default"></button>${ACCENTS.map(c => `<button class="swc ${accOn === c ? 'on' : ''}" style="background:${c}" data-ap-accent="${c}" title="${c}"></button>`).join('')}
      <label style="display:flex;align-items:center;gap:8px;margin-left:6px;color:var(--dim);font-size:13px">Custom <input type="color" data-id="accent" value="${accOn || '#d97757'}"></label></div>
      <div class="note">Right-click a chat in the sidebar to give that chat, or every chat in its folder, its own color.</div></div>

    <div class="sec">Custom theme</div>
    <div class="card"><div class="cgrid">${BASE_KEYS.map(key => `<label>${BASE_LABELS[key]}<input type="color" data-ap-ct="${key}" value="${ct[key]}"></label>`).join('')}</div>
      <div style="padding:0 16px 14px;display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn" data-ap-act="use-custom">Use custom theme</button><button class="btn g" data-ap-act="from-current">Start from current colors</button>
        <button class="btn g" data-ap-act="export">Export as file</button><button class="btn g" data-ap-act="import-file">Import file…</button></div>
      <div style="padding:0 16px 14px"><textarea class="ta" id="imptext" rows="2" placeholder="Or paste a theme here (JSON) and press Import"></textarea><div style="margin-top:8px"><button class="btn g" data-ap-act="import-paste">Import pasted theme</button></div></div></div>

    <div class="sec">Typography and layout</div>
    <div class="card">
      ${apRow('Font', 'Any installed font. Leave empty for Inter.', `<input class="txt" list="fontlist" data-id="font" value="${esc(s.font || '')}" placeholder="Inter"><datalist id="fontlist">${(S.fonts || []).map(f => `<option value="${esc(f)}">`).join('')}</datalist>`)}
      ${apRow('Code font', 'Used for code and the terminal-style theme', `<input class="txt" list="fontlist" data-id="monoFont" value="${esc(s.monoFont || '')}" placeholder="JetBrains Mono">`)}
      ${apRow('Text size', 'Also Ctrl+= and Ctrl+-', range('fontSize', 12, 20, 1, +s.fontSize || 15, v => v + ' px'))}
      ${apRow('Chat width', 'How wide the conversation column is', range('chatWidth', 560, 1200, 20, +s.chatWidth || 800, v => v + ' px'))}</div>

    <div class="sec">Background and window</div>
    <div class="card">
      ${apRow('Background', 'Drawn behind the whole window', selH('bgMode', [['none', 'None'], ['aurora', 'Aurora (drifting glow)'], ['particles', 'Particles'], ['gradient', 'Gradient'], ['image', 'Picture']], s.bgMode || 'none'))}
      ${s.bgMode === 'gradient' ? apRow('Gradient', '', selH('bgGradient', Object.keys(GRADIENTS).map(g => [g, g[0].toUpperCase() + g.slice(1)]), s.bgGradient || 'dusk')) : ''}
      ${s.bgMode === 'image' ? apRow('Picture', esc(s.bgImage ? s.bgImage.split('/').pop() : 'No picture chosen'), '<button class="btn g" data-ap-act="pick-bg">Choose…</button>') : ''}
      ${s.bgMode === 'image' || s.bgMode === 'gradient' ? apRow('Dim the background', 'Makes text easier to read', range('bgDim', 0, 0.9, 0.05, +s.bgDim || 0, v => Math.round(v * 100) + '%')) : ''}
      ${apRow('See-through window', 'The window lets your desktop show through. If your desktop blurs windows behind them (KDE\'s Blur effect), this looks frosted.', swH('glass', !!s.glass))}
      ${s.glass ? apRow('Window opacity', '', range('glassOpacity', 0.4, 1, 0.02, +s.glassOpacity || 0.82, v => Math.round(v * 100) + '%')) : ''}</div>

    <div class="sec">Animation</div>
    <div class="card">
      ${apRow('Motion', 'Reduced turns animations off. "Follow system" respects your desktop\'s animation setting.', selH('motion', [['system', 'Follow system'], ['full', 'Full'], ['reduced', 'Reduced']], s.motion || 'system'))}
      ${apRow('Animation speed', '1× is normal; higher is faster', range('animSpeed', 0.5, 2, 0.25, +s.animSpeed || 1, v => (+v).toFixed(2).replace(/\.?0+$/, '') + '×'))}
      ${apRow('When a long task finishes', 'Only for runs that took more than a few seconds', selH('celebrate', [['glow', 'Soft glow'], ['confetti', 'Confetti'], ['off', 'Nothing']], s.celebrate ?? 'glow'))}</div>

    <div class="sec">Code blocks</div>
    <div class="card">
      ${apRow('Syntax colors', 'Dark-only schemes fall back to the theme on light themes', selH('syntax', SYNTAX_THEMES, s.syntax || 'auto'))}
      ${apRow('Line numbers', '', swH('codeNums', !!s.codeNums))}${apRow('Wrap long lines', '', swH('codeWrap', !!s.codeWrap))}
      <div style="padding:0 16px 14px" class="demo">${md(SYNTAX_DEMO)}</div></div>`;
};

PAGE.desktop = s => {
  const k = KDE.scheme, hk = S.hotkeyState;
  const hkText = !s.hotkey ? 'Off' : !hk ? 'Asking your desktop…' : !hk.ok ? esc(hk.msg || 'Your desktop declined') : hk.msg ? 'Key: ' + esc(hk.msg) : 'Registered. Choose the key with the button, or in System Settings > Shortcuts > Claude Linux.';
  return `<div class="ph">Desktop</div><p class="pd">How Claude Linux fits into Plasma.</p>
    <div class="sec" style="margin-top:0">Tray and taskbar</div><div class="card">
      ${setRow('Tray icon', 'Shows in the system tray. It turns to "needs attention" when Claude is waiting for you.', swH('tray', s.tray !== false))}
      ${setRow('Close to the tray', 'Closing the window keeps Claude (and running tasks) alive in the tray. Needs the tray icon.', swH('closeToTray', !!s.closeToTray))}
      ${setRow('Taskbar badge and progress', 'The number of running chats, a progress bar from Claude\'s todo list, and a highlight when it needs you', swH('taskbar', s.taskbar !== false))}</div>
    <div class="sec">Global shortcut</div><div class="card">
      ${setRow('Show or hide with a key', hkText, swH('hotkey', !!s.hotkey))}
      ${s.hotkey && hk && hk.ok ? setRow('Change the key', 'Opens the desktop\'s own shortcut dialog', '<button class="btn g" data-ap-act="hotkey-config">Choose key…</button>') : ''}</div>
    <div class="sec">Notifications</div><div class="card">
      ${setRow('Desktop notifications', 'When Claude needs you or finishes a long task while this window is in the background', swH('notify', s.notify !== false))}</div>
    <div class="sec">Plasma</div><div class="card">
      ${setRow('Color scheme', k ? esc(k.name || 'unnamed') + (k.dark ? ' (dark)' : ' (light)') : 'Not found', '')}
      ${setRow('Window buttons', 'Taken from your KDE titlebar settings: ' + (esc(KDE.buttons || '') || 'defaults'), '')}</div>
    <p class="pd" style="margin-top:14px">Tip: <code>run.sh --new</code> (or the "New session" entry when you right-click the launcher) opens a fresh session in the running window.</p>`;
};

EXTRA.hotkey = p => { S.hotkeyState = p; if ($('#modal').style.display === 'flex' && panel === 'desktop') showPage(true); };
EXTRA.fonts = p => { S.fonts = p.fonts || []; const dl = $('#fontlist'); if (dl) dl.innerHTML = S.fonts.map(f => `<option value="${esc(f)}">`).join(''); };
EXTRA.bgimage = p => { setSetting('bgImage', p.path); setSetting('bgMode', 'image'); if ($('#modal').style.display === 'flex' && panel === 'appearance') showPage(true); };

const refreshAppearancePage = () => { if ($('#modal').style.display === 'flex' && panel === 'appearance') showPage(true); };
PAGE_BIND.desktop = b => {
  b.querySelectorAll('[data-ap-act="hotkey-config"]').forEach(x => x.onclick = () => post({type:'hotkey_configure'}));
  b.querySelectorAll('[data-id="hotkey"]').forEach(x => x.addEventListener('change', () => { S.hotkeyState = null; setTimeout(() => panel === 'desktop' && showPage(true), 50); }));
};
PAGE_BIND.appearance = b => {
  if (!S.fonts && !S.fontsAsked) { S.fontsAsked = true; post({type:'fonts'}); }
  b.querySelectorAll('[data-ap-theme]').forEach(t => t.onclick = () => { applyTheme(t.dataset.apTheme); showPage(true); });
  b.querySelectorAll('[data-ap-accent]').forEach(t => t.onclick = () => { setSetting('accent', t.dataset.apAccent); showPage(true); });
  // sliders: preview while dragging, save when released
  b.querySelectorAll('[data-ap-range]').forEach(r => {
    const key = r.dataset.apRange, label = b.querySelector(`[data-val="${key}"]`), f = { fontSize:v => v + ' px', chatWidth:v => v + ' px', bgDim:v => Math.round(v * 100) + '%', glassOpacity:v => Math.round(v * 100) + '%', animSpeed:v => (+v).toFixed(2).replace(/\.?0+$/, '') + '×' }[key];
    r.oninput = () => { S.settings[key] = +r.value; label.textContent = f(+r.value); applyAppearance(); };
    r.onchange = () => setSetting(key, +r.value);
  });
  b.querySelectorAll('select[data-id]').forEach(sel => sel.addEventListener('change', () => { if (['bgMode', 'glass', 'autoDark', 'autoLight'].includes(sel.dataset.id)) setTimeout(refreshAppearancePage, 30); }));
  b.querySelectorAll('input[data-id="glass"],input[data-id="kdeAccent"]').forEach(x => x.addEventListener('change', () => setTimeout(refreshAppearancePage, 30)));
  // custom theme colors: live preview, saved on change
  b.querySelectorAll('[data-ap-ct]').forEach(inp => {
    inp.oninput = () => { S.settings.customTheme = { ...CUSTOM_DEFAULT, ...(S.settings.customTheme || {}), [inp.dataset.apCt]: inp.value }; if (S.settings.theme === 'custom') applyAppearance(); };
    inp.onchange = () => setSetting('customTheme', { ...CUSTOM_DEFAULT, ...(S.settings.customTheme || {}), [inp.dataset.apCt]: inp.value });
  });
  const act = {
    'use-custom':() => { setSetting('customTheme', { ...CUSTOM_DEFAULT, ...(S.settings.customTheme || {}) }); applyTheme('custom'); showPage(true); },
    'from-current':() => { setSetting('customTheme', currentPalette()); applyTheme('custom'); showPage(true); toast('Copied the current colors into your custom theme'); },
    'export':exportTheme,
    'import-file':() => post({type:'pickjson'}),
    'import-paste':() => importThemeText(($('#imptext') || {}).value || ''),
    'pick-bg':() => post({type:'pickimage'}),
  };
  b.querySelectorAll('[data-ap-act]').forEach(x => { const f = act[x.dataset.apAct]; if (f) x.onclick = f; });
};
