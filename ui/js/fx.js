/* ---------- motion and effects: ripples, backgrounds, celebrations, taskbar status ---------- */
const motionOff = () => document.documentElement.dataset.motion === 'reduced';

/* press ripples */
const RIPPLE_SEL = '.btn,#new,#sendb,.pill,.seg button,#tabs button,.opt,.ib,.tc';
document.addEventListener('pointerdown', e => {
  if (motionOff() || e.button > 0) return;
  const t = e.target.closest && e.target.closest(RIPPLE_SEL); if (!t || t.disabled) return;
  const r = t.getBoundingClientRect(), d = Math.max(r.width, r.height) * 2;
  const s = document.createElement('span'); s.className = 'ripple';
  s.style.cssText = `width:${d}px;height:${d}px;left:${e.clientX - r.left - d / 2}px;top:${e.clientY - r.top - d / 2}px`;
  t.appendChild(s); setTimeout(() => s.remove(), 800);
});

/* animated or image background behind the whole app */
const GRADIENTS = { dusk:['#2b1055', '#7597de', '#d97757'], ocean:['#0f2027', '#2c5364', '#4ca1af'], forest:['#0b3d2e', '#2d6a4f', '#95d5b2'], ember:['#1a0000', '#8a1c1c', '#ff7a18'],
  mono:['#0d0d0d', '#2a2a2a', '#555555'], neon:['#0d0221', '#541388', '#ff2a6d'], sakura:['#3a1c71', '#d76d77', '#ffaf7b'] };
let bgKey = '', pRaf = 0, pOnResize = null;
const fileUrl = p => 'file://' + String(p).split('/').map(encodeURIComponent).join('/');
function stopParticles() { cancelAnimationFrame(pRaf); pRaf = 0; if (pOnResize) { removeEventListener('resize', pOnResize); pOnResize = null; } }
function applyBackground() {
  const s = S.settings || {}, root = document.documentElement, mode = ['aurora', 'particles', 'gradient', 'image'].includes(s.bgMode) ? s.bgMode : 'none';
  const acc = varRGB('--accent') || [217, 119, 87];
  const key = JSON.stringify([mode, s.bgGradient, s.bgImage, s.bgDim, mode === 'particles' ? acc : 0, root.dataset.motion]);
  if (key === bgKey) return; bgKey = key;
  stopParticles(); let el = $('#bgfx');
  if (mode === 'none' || (mode === 'image' && !s.bgImage)) { root.classList.remove('fx'); if (el) el.remove(); return; }
  if (!el) { el = document.createElement('div'); el.id = 'bgfx'; document.body.prepend(el); }
  root.classList.add('fx'); el.className = mode; el.innerHTML = ''; el.style.cssText = '';
  el.style.setProperty('--dim', String(clamp(+s.bgDim || 0, 0, .9)));
  root.style.setProperty('--sa', mode === 'image' || mode === 'gradient' ? '.66' : '.8');
  if (mode === 'aurora') el.innerHTML = '<i></i><i></i><i></i>';
  else if (mode === 'gradient') { const g = GRADIENTS[s.bgGradient] || GRADIENTS.dusk; el.style.background = `linear-gradient(135deg,${g[0]},${g[1]},${g[2]},${g[0]})`; el.style.backgroundSize = '300% 300%'; }
  else if (mode === 'image') el.style.backgroundImage = `url("${fileUrl(s.bgImage)}")`;
  else if (mode === 'particles') startParticles(el, acc);
}
function startParticles(host, rgb) {
  const cv = document.createElement('canvas'); host.appendChild(cv); const g = cv.getContext('2d'); let w = 0, h = 0, last = 0;
  const dpr = Math.min(devicePixelRatio || 1, 2), dots = [];
  const size = () => { w = cv.width = Math.round(innerWidth * dpr); h = cv.height = Math.round(innerHeight * dpr); };
  size(); pOnResize = size; addEventListener('resize', size);
  for (let i = 0; i < 70; i++) dots.push({ x:Math.random() * w, y:Math.random() * h, r:(.7 + Math.random() * 1.9) * dpr, vy:-(.08 + Math.random() * .3) * dpr, vx:(Math.random() - .5) * .12 * dpr, p:Math.random() * 6.28 });
  const draw = (t, move) => {
    g.clearRect(0, 0, w, h);
    for (const d of dots) {
      if (move) { d.x += d.vx; d.y += d.vy; if (d.y < -10) { d.y = h + 10; d.x = Math.random() * w; } }
      g.fillStyle = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${(.18 + .32 * (.5 + .5 * Math.sin(t / 900 + d.p))).toFixed(3)})`;
      g.beginPath(); g.arc(d.x, d.y, d.r, 0, 6.2832); g.fill();
    }
  };
  if (motionOff()) { draw(0, false); return; }
  const frame = t => {
    if (!cv.isConnected) return; pRaf = requestAnimationFrame(frame);
    if (document.hidden || t - last < 33) return;   // about 30 fps, and nothing while the window is hidden
    last = t; draw(t, true);
  };
  pRaf = requestAnimationFrame(frame);
}

/* celebrating a finished long task */
function confetti() {
  if (motionOff()) return;
  const cv = document.createElement('canvas'); cv.id = 'confetti'; document.body.appendChild(cv);
  const dpr = Math.min(devicePixelRatio || 1, 2), W = cv.width = Math.round(innerWidth * dpr), H = cv.height = Math.round(innerHeight * dpr), g = cv.getContext('2d');
  const base = varRGB('--accent') || [217, 119, 87], pal = [toHex(base), '#ffd166', '#06d6a0', '#118ab2', '#ef476f', '#ffffff'];
  const sb = $('#sendb').getBoundingClientRect(), ox = (sb.left + sb.width / 2) * dpr, oy = sb.top * dpr;
  const ps = Array.from({ length:110 }, () => { const a = -Math.PI / 2 + (Math.random() - .5) * 1.5, v = (6 + Math.random() * 10) * dpr;
    return { x:ox, y:oy, vx:Math.cos(a) * v, vy:Math.sin(a) * v, w:(5 + Math.random() * 6) * dpr, h:(3 + Math.random() * 5) * dpr, r:Math.random() * 6.28, vr:(Math.random() - .5) * .4, c:pal[(Math.random() * pal.length) | 0] }; });
  const t0 = performance.now(); setTimeout(() => cv.remove(), 4000);
  (function frame(t) {
    const k = t - t0; g.clearRect(0, 0, W, H);
    for (const p of ps) { p.vy += .35 * dpr; p.vx *= .99; p.x += p.vx; p.y += p.vy; p.r += p.vr; g.save(); g.globalAlpha = Math.max(0, 1 - k / 2200); g.translate(p.x, p.y); g.rotate(p.r); g.fillStyle = p.c; g.fillRect(-p.w / 2, -p.h / 2, p.w, p.h); g.restore(); }
    if (k < 2200 && cv.isConnected) requestAnimationFrame(frame); else cv.remove();
  })(t0);
}
function celebrate(id) {
  const mode = (S.settings || {}).celebrate ?? 'glow';
  if (mode === 'off' || id !== cur || motionOff()) return;
  if (Date.now() - (spinStart[id] || Date.now()) < (celebrate.minMs ?? 6000)) return;   // only for runs that took a while
  for (const el of [$('#box'), $('#sendb')]) { el.classList.remove('glow'); void el.offsetWidth; el.classList.add('glow'); setTimeout(() => el.classList.remove('glow'), 1600); }
  if (mode === 'confetti') confetti();
}

/* what the desktop shows: taskbar badge and progress, tray attention */
let lastStatus = '', statusT = 0;
function reportStatus() {
  const cs = Object.values(chats), busy = cs.filter(c => c.busy).length;
  const waiting = cs.filter(c => c.items.some(x => x.k === 'perm' && x.status === 'wait')).length;
  let progress = null; const pick = chats[cur] && chats[cur].busy ? chats[cur] : cs.find(c => c.busy);
  if (pick) {                                  // real progress, when Claude keeps a todo list
    const td = [...pick.items].reverse().find(x => x.k === 'tool' && x.name === 'TodoWrite'), todos = td && td.input && td.input.todos;
    if (Array.isArray(todos) && todos.length) progress = todos.filter(t => t.status === 'completed').length / todos.length;
  }
  const key = busy + '|' + waiting + '|' + progress; if (key === lastStatus) return; lastStatus = key;
  post({type:'status', busy, waiting, progress});
}
function reportStatusSoon() { clearTimeout(statusT); statusT = setTimeout(reportStatus, 250); }

EXTRA.newsession = () => newChat();
EXTRA.appstate = p => { S.appstate = p; };

$('#sbtn').innerHTML = ico('sidebar'); $('#sbtn').onclick = () => toggleSidebar();
