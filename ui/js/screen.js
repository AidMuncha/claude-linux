/* ---------- the reading hologram over the real screen (claude_linux/screenread.py drives it) ----------
   This page fills a see-through, click-through window placed over the monitor. Python sends the position of every word it found, then
   which words each spoken sentence covers and how long it lasts; a blue strip stretches through the words as they are spoken, and when he is
   done it turns green and fades. */
const SC = { words:[], items:[], finishing:false, raf:0, hls:[], hd:null, fadeT:[] };
const scHolo = document.createElement('div'); scHolo.className = 'holo'; document.body.appendChild(scHolo);
const scWeight = w => w.t.length + 1 + (/[.!?]["')\]]*$/.test(w.t) ? 6 : /[,;:]$/.test(w.t) ? 3 : 0);
function scReset() {
  SC.fadeT.forEach(clearTimeout); SC.fadeT = []; SC.items = []; SC.finishing = false; scHolo.className = 'holo'; scHolo.innerHTML = ''; SC.hls = []; SC.hd = null;
}
EXTRA.jarvis_screen = p => {
  if (p.ev === 'words') { scReset(); SC.words = p.words || []; if (!SC.raf) SC.raf = requestAnimationFrame(scFrame); }
  else if (p.ev === 'read') {
    const ws = SC.words.slice(p.a, p.b).map(scWeight), total = ws.reduce((a, b) => a + b, 0) || 1; let run = 0;
    SC.items.push({ a:p.a, b:p.b, cum:ws.map(x => (run += x) / total), start:performance.now() + (p.delay || 0) * 1000 - 15, dur:Math.max(120, (p.dur || .3) * 1000) });
  }
  else if (p.ev === 'finish') SC.finishing = true;
  else if (p.ev === 'abort' || p.ev === 'close') { scReset(); SC.words = []; }
};
function scLocate(it, now) {
  const p = Math.max(0, Math.min(1, (now - it.start) / it.dur / .96));
  let i = it.cum.findIndex(c => c >= p); if (i < 0) i = it.cum.length - 1;
  const prev = i ? it.cum[i - 1] : 0;
  return { k:it.a + i, frac:Math.max(0, Math.min(1, (p - prev) / ((it.cum[i] - prev) || 1))) };
}
function scDraw(k, frac) {
  const lines = new Map();
  for (let i = 0; i <= k && i < SC.words.length; i++) {
    const w = SC.words[i], right = i === k ? w.x + w.w * frac : w.x + w.w, l = lines.get(w.l);
    if (!l) lines.set(w.l, { l:w.x, r:right, t:w.y, h:w.h }); else { l.l = Math.min(l.l, w.x); l.r = Math.max(l.r, right); l.t = Math.min(l.t, w.y); l.h = Math.max(l.h, w.h); }
  }
  const ls = [...lines.values()];
  while (SC.hls.length < ls.length) { const e = document.createElement('i'); e.className = 'hl'; scHolo.appendChild(e); SC.hls.push(e); }
  SC.hls.forEach((e, i) => { const l = ls[i]; if (!l) { e.style.display = 'none'; return; } e.style.cssText = `left:${l.l - 3}px;top:${l.t - 2}px;width:${Math.max(4, l.r - l.l + 6)}px;height:${l.h + 4}px`; });
  const c = SC.words[Math.min(k, SC.words.length - 1)];
  if (c) { if (!SC.hd) { SC.hd = document.createElement('i'); SC.hd.className = 'hd'; scHolo.appendChild(SC.hd); } SC.hd.style.cssText = `left:${c.x - 3}px;top:${c.y - 2}px;width:${c.w + 6}px;height:${c.h + 4}px`; }
}
function scFrame(now) {
  SC.raf = requestAnimationFrame(scFrame);
  if (!SC.items.length || !SC.words.length) return;
  let pos = null;
  for (const it of SC.items) { if (now < it.start) break; pos = scLocate(it, now); }
  scDraw(pos ? pos.k : SC.items[0].a, pos ? pos.frac : 0);
  const last = SC.items[SC.items.length - 1];
  if (SC.finishing && now >= last.start + last.dur && !scHolo.classList.contains('done')) {
    scDraw(last.b - 1, 1); scHolo.classList.add('done'); SC.fadeT.push(setTimeout(() => scHolo.classList.add('fade'), 650));
  }
}
post({type:'jarvis_screen_ready'});
