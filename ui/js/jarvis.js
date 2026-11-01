/* ---------- Jarvis' window: the orb, captions and reading hologram. This page (hud.html) lives in its own always-on-top window over the desktop; the work happens in claude_linux/jarvis.py ---------- */
Object.assign(IC, {
  mic:'<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>', micoff:'<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M4 4l16 16"/>',
  spk:'<path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16.5 9a4 4 0 0 1 0 6"/>', spkoff:'<path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16 9l5 6M21 9l-5 6"/>',
  power:'<path d="M12 3v8M6.3 6.8a8 8 0 1 0 11.4 0"/>', eye:'<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
});
const JV = { share:false, watch:false, on:false, mode:'voice', state:'off', muted:false, voice:true, level:0, lv:0, ay:0, last:0, raf:0, col:[92, 225, 255], msg:null, fadeT:0, toolT:0 };
const JV_STATE = { waiting:['Waiting', [132, 168, 198]], listening:['Listening', [92, 225, 255]], hearing:['Listening', [150, 245, 255]], thinking:['Thinking…', [110, 210, 255]],
  acting:['Working…', [112, 192, 255]], speaking:['Speaking', [140, 240, 255]], idle:['Ready', [92, 225, 255]], muted:['Muted', [120, 130, 145]] };
const JV_LOOK = { waiting:[.12, .5, .5], listening:[.22, .85, .52], hearing:[.4, 1, .56], thinking:[1.2, 1, .72], acting:[.8, .95, .62], speaking:[.45, 1, .58], idle:[.18, .7, .5], muted:[.08, .3, .45] };   // spin, brightness, link distance
const JV_N = 104, JV_PTS = Array.from({length: JV_N}, (_, i) => {
  const y = 1 - 2 * (i + .5) / JV_N, r = Math.sqrt(1 - y * y), a = i * 2.399963, k = .8 + Math.random() * .2;
  return { x:Math.cos(a) * r * k, y:y * k, z:Math.sin(a) * r * k, ph:Math.random() * 6.283 };
});
let jvEl = null;

function jvBuild() {
  if (jvEl) return;
  jvEl = document.createElement('div'); jvEl.id = 'jv'; jvEl.dataset.mode = 'voice'; jvEl.dataset.state = 'waiting';
  jvEl.innerHTML = `<div id="jvpanel"><div id="jvhead"><i></i>J.A.R.V.I.S<small>TEXT MODE</small></div><div id="jvlog"></div><div id="jvtool"></div>
    <form id="jvform" autocomplete="off"><input id="jvin" placeholder="Ask Jarvis anything…" spellcheck="false"><button type="submit" id="jvsend" title="Send">${ico('send')}</button></form></div>
    <div id="jvdock"><canvas id="jvorb"></canvas><div id="jvtext"><div id="jvstate">Waiting</div><div id="jvsub"></div>
    <div id="jvbtns"><button id="jvmic"></button><button id="jvspk"></button><button id="jvshare"></button><button id="jvwatch"></button><button id="jvstop" title="Stop talking"></button><button id="jvoff" title="Power Jarvis down"></button></div></div></div>`;
  document.body.appendChild(jvEl);
  const cv = $('#jvorb'); cv.width = cv.height = Math.round(124 * (window.devicePixelRatio || 1));
  $('#jvstop').innerHTML = ico('stop'); $('#jvoff').innerHTML = ico('power');
  $('#jvmic').onclick = () => { JV.muted = !JV.muted; jvButtons(); post({type:'jarvis_mute', on:JV.muted}); };
  $('#jvspk').onclick = () => { JV.voice = !JV.voice; jvButtons(); post({type:'jarvis_voice', on:JV.voice}); };
  $('#jvshare').onclick = () => post({type:'jarvis_share', on:!JV.share});
  $('#jvwatch').onclick = () => post({type:'jarvis_watch', on:!JV.watch});
  $('#jvstop').onclick = () => post({type:'jarvis_interrupt'});
  $('#jvoff').onclick = () => post({type:'jarvis_stop'});
  cv.onclick = () => { if (JV.mode === 'voice') $('#jvmic').click(); else if (['thinking', 'acting', 'speaking'].includes(JV.state)) post({type:'jarvis_interrupt'}); };   // the orb is the mute button
  $('#jvform').onsubmit = e => { e.preventDefault(); const t = $('#jvin').value.trim(); if (!t) return; $('#jvin').value = ''; post({type:'jarvis_text', text:t}); };
  $('#jvin').onkeydown = e => { e.stopPropagation(); if (e.key === 'Escape') e.target.blur(); };
}
function jvButtons() {
  $('#jvmic').innerHTML = ico(JV.muted ? 'micoff' : 'mic'); $('#jvmic').title = JV.muted ? 'Unmute the microphone' : 'Mute the microphone'; $('#jvmic').classList.toggle('off', JV.muted);
  $('#jvshare').innerHTML = ico('remote'); $('#jvshare').title = JV.share ? 'Stop sharing your screen' : 'Share your screen with Jarvis (like a Discord stream)'; $('#jvshare').classList.toggle('on', JV.share);
  $('#jvwatch').innerHTML = ico('eye'); $('#jvwatch').title = JV.watch ? 'Stop his automatic commentary' : 'Let him comment on what he sees on his own'; $('#jvwatch').classList.toggle('on', JV.watch);
  $('#jvspk').innerHTML = ico(JV.voice ? 'spk' : 'spkoff'); $('#jvspk').title = JV.voice ? 'Turn his voice off' : 'Turn his voice on'; $('#jvspk').classList.toggle('off', !JV.voice);
}
function jvSetMode(mode) {
  JV.mode = mode; jvEl.dataset.mode = mode; $('#jvmic').style.display = mode === 'voice' ? '' : 'none';
  $('#jvhead small').textContent = mode === 'text' ? 'TEXT MODE' : 'VOICE'; jvButtons();
  if (mode === 'text') setTimeout(() => $('#jvin').focus(), 60);
}
function jvShow(mode) {
  JV.on = true; JV.state = 'waiting'; JV.muted = false; JV.voice = true; JV.share = JV.watch = false; JV.msg = null;
  $('#jvlog').innerHTML = ''; $('#jvsub').textContent = ''; $('#jvstate').textContent = 'Waiting'; jvEl.dataset.state = 'waiting'; jvEl.classList.remove('sharing');
  jvSetMode(mode); jvEl.classList.add('on');
  if (!JV.raf) JV.raf = requestAnimationFrame(jvLoop);
}
function jvHide() {
  JV.on = false; JV.state = 'off'; JV.share = JV.watch = false; if (jvEl) jvEl.classList.remove('on', 'sharing');
  jvStopReads(); cancelAnimationFrame(JV.raf); JV.raf = 0; clearTimeout(JV.fadeT);
}

/* ---------- what Python tells us ---------- */
EXTRA.jarvis = p => {
  if (p.ev === 'state' && p.state === 'off') return jvHide();
  if (p.ev === 'poweroff') return jvHide();
  if (!JV.on && p.ev === 'state') jvShow(p.mode || 'voice');
  if (!JV.on) return;
  if (p.ev === 'state') {
    JV.state = p.state; if ('muted' in p) JV.muted = p.muted; if ('voice' in p) JV.voice = p.voice;
    if (p.mode && p.mode !== JV.mode) jvSetMode(p.mode);
    jvEl.dataset.state = p.state; jvButtons();
    $('#jvstate').textContent = p.state === 'acting' && p.label ? p.label : (JV_STATE[p.state] || ['…'])[0];
    if (p.state !== 'waiting') $('#jvsub').textContent = '';
  }
  else if (p.ev === 'setup') $('#jvsub').textContent = p.text;
  else if (p.ev === 'level') JV.level = Math.sqrt(Math.min(1, p.v || 0));
  else if (p.ev === 'partial') jvLive(p.text);
  else if (p.ev === 'heard') jvYou(p.text);
  else if (p.ev === 'say') jvSay(p);
  else if (p.ev === 'stopsay') jvStopReads();
  else if (p.ev === 'tool') jvTool(p.detail || p.name);
  else if (p.ev === 'caption') jvTool('♪ ' + p.text);
  else if (p.ev === 'share') { JV.share = !!p.on; JV.watch = !!p.watch; jvEl.classList.toggle('sharing', JV.share); jvButtons(); }
  else if (p.ev === 'error') { toast(p.text, true); $('#jvsub').textContent = p.text.slice(0, 90); }
};

/* ---------- the captions ---------- */
function jvScroll() { const l = $('#jvlog'); l.scrollTop = l.scrollHeight; }
function jvTouch() {
  const l = $('#jvlog'); l.classList.remove('faded'); clearTimeout(JV.fadeT);
  if (JV.mode === 'voice') JV.fadeT = setTimeout(() => { l.classList.add('faded'); setTimeout(() => { if (l.classList.contains('faded')) { l.innerHTML = ''; JV.msg = null; } }, 1000); }, 12000);
}
function jvLive(text) {
  jvTouch(); const l = $('#jvlog'); let d = l.querySelector('.jvu.live');
  if (!d) { if (JV.mode === 'voice') l.innerHTML = ''; d = document.createElement('div'); d.className = 'jvu live'; l.appendChild(d); JV.msg = null; }
  d.textContent = text; jvScroll();
}
function jvYou(text) {
  jvTouch(); const l = $('#jvlog'); l.querySelectorAll('.jvu.live').forEach(x => x.remove()); if (JV.mode === 'voice') l.innerHTML = '';
  const d = document.createElement('div'); d.className = 'jvu'; d.textContent = text; l.appendChild(d); JV.msg = null; jvScroll();
}
function jvMsg() {
  if (JV.msg && JV.msg.isConnected) return JV.msg;
  const l = $('#jvlog'); if (JV.mode === 'voice') [...l.querySelectorAll('.jvm')].forEach(x => x.remove());
  JV.msg = document.createElement('div'); JV.msg.className = 'jvm'; l.appendChild(JV.msg); return JV.msg;
}
function jvTool(text) {
  const t = $('#jvtool'); t.textContent = '⌁ ' + text; t.classList.add('on'); clearTimeout(JV.toolT); JV.toolT = setTimeout(() => t.classList.remove('on'), 6000);
}

/* ---------- captions: each sentence appears as he says it ---------- */
const jvTimers = new Set();
function jvSay(p) {
  const show = () => {
    if (!JV.on) return; jvTouch(); const m = jvMsg(), s = document.createElement('span');
    if (m.querySelector('.jvs')) m.appendChild(document.createTextNode(' '));
    s.className = 'jvs'; s.textContent = p.text; m.appendChild(s); jvScroll();
  };
  const t = setTimeout(() => { jvTimers.delete(t); show(); }, Math.max(0, (+p.delay || 0) * 1000)); jvTimers.add(t);
}
function jvStopReads() { jvTimers.forEach(clearTimeout); jvTimers.clear(); }

/* ---------- the orb: a rotating web of glowing nodes that breathes with the room's sound and Jarvis' voice ---------- */
function jvOrb(t, dt) {
  const cv = $('#jvorb'), ctx = cv.getContext('2d'), S = cv.width, c = S / 2, R = S * .34, dpr = S / 124;
  const look = JV_LOOK[JV.state] || [.2, .7, .5], target = (JV_STATE[JV.state] || JV_STATE.idle)[1], slow = motionOff() ? .25 : 1;
  const tl = JV.state === 'hearing' || JV.state === 'listening' ? JV.level : JV.state === 'speaking' ? .3 + .2 * Math.sin(t / 90) * Math.sin(t / 230) + .1 * Math.sin(t / 37) : JV.state === 'thinking' ? .16 : 0;
  JV.lv += (tl - JV.lv) * .22; JV.level *= .93; JV.ay += look[0] * slow * dt / 500;
  for (let i = 0; i < 3; i++) JV.col[i] += (target[i] - JV.col[i]) * .08;
  const col = JV.col.map(Math.round).join(','), bright = look[1], th = look[2], lv = JV.lv;
  const ax = .45 + Math.sin(t / 4000) * .18, ca = Math.cos(ax), sa = Math.sin(ax), cy = Math.cos(JV.ay), sy = Math.sin(JV.ay);
  const breath = 1 + Math.sin(t / (JV.state === 'waiting' ? 900 : 600)) * .03;
  ctx.clearRect(0, 0, S, S); ctx.globalCompositeOperation = 'lighter';
  const g = ctx.createRadialGradient(c, c, 0, c, c, R * 1.05);
  g.addColorStop(0, `rgba(225,255,255,${(.5 + lv * .5) * bright})`); g.addColorStop(.35, `rgba(${col},${.22 * bright + lv * .2})`); g.addColorStop(1, `rgba(${col},0)`);
  ctx.fillStyle = g; ctx.fillRect(0, 0, S, S);
  const q = JV_PTS.map(p => {
    const k = breath * (1 + lv * .4 * Math.sin(p.ph + t / 110)), x0 = p.x * k, y0 = p.y * k, z0 = p.z * k;
    const x1 = x0 * cy + z0 * sy, z1 = -x0 * sy + z0 * cy, y2 = y0 * ca - z1 * sa, z2 = y0 * sa + z1 * ca, f = 1 / (1 - z2 * .28);
    return { x:x1, y:y2, z:z2, sx:c + x1 * R * f, sy:c + y2 * R * f, d:(z2 + 1) / 2 };
  });
  const bk = [[], [], [], [], []];
  for (let i = 0; i < JV_N; i++) for (let j = i + 1; j < JV_N; j++) {
    const a = q[i], b = q[j], dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z, d2 = dx * dx + dy * dy + dz * dz;
    if (d2 > th * th) continue;
    const al = (1 - Math.sqrt(d2) / th) * bright * (.35 + .65 * (a.d + b.d) / 2);
    bk[Math.min(4, Math.floor(al * 5))].push(a.sx, a.sy, b.sx, b.sy);
  }
  ctx.lineWidth = Math.max(1, .85 * dpr);
  bk.forEach((seg, n) => {
    if (!seg.length) return; ctx.beginPath();
    for (let i = 0; i < seg.length; i += 4) { ctx.moveTo(seg[i], seg[i + 1]); ctx.lineTo(seg[i + 2], seg[i + 3]); }
    ctx.strokeStyle = `rgba(${col},${(n + 1) / 5 * .8})`; ctx.stroke();
  });
  q.forEach(p => { ctx.fillStyle = `rgba(215,250,255,${(.3 + .7 * p.d) * Math.min(1, bright + .2)})`; ctx.beginPath(); ctx.arc(p.sx, p.sy, (.9 + 1.5 * p.d) * dpr * (1 + lv * .5), 0, 6.283); ctx.fill(); });
  if (JV.state === 'thinking' || JV.state === 'acting') {
    ctx.lineWidth = dpr; ctx.strokeStyle = `rgba(${col},.55)`;
    for (let i = 0; i < 2; i++) { ctx.beginPath(); ctx.ellipse(c, c, R * 1.22, R * (.45 + i * .12), JV.ay * (1.4 + i * .5) + i * 2, 0, 3.6); ctx.stroke(); }
  }
}
function jvLoop(now) {
  JV.raf = 0; if (!JV.on) return;
  const dt = Math.min(64, now - (JV.last || now)); JV.last = now;
  jvOrb(now, dt);
  JV.raf = requestAnimationFrame(jvLoop);
}

/* the window is bigger than what is drawn; tell Python where the drawing is so clicks anywhere else pass through to the desktop */
function jvReport() {
  if (!jvEl || !jvEl.classList.contains('on')) return;
  // only the orb, the close button and (text mode) the chat panel take clicks; the rest of the window lets them through to what is underneath
  const rects = [$('#jvorb'), $('#jvstop'), $('#jvoff'), jvEl.dataset.mode === 'text' ? $('#jvpanel') : null].filter(Boolean).map(e => e.getBoundingClientRect()).filter(r => r.width > 0 && r.height > 0)
    .map(r => ({x:Math.floor(r.left) - 2, y:Math.floor(r.top) - 2, w:Math.ceil(r.width) + 4, h:Math.ceil(r.height) + 4}));
  post({type:'jarvis_hudrect', rects});
}
jvBuild();
new ResizeObserver(jvReport).observe(jvEl);
new MutationObserver(jvReport).observe(jvEl, { attributes:true, attributeFilter:['class', 'data-mode'] });
