/* ---------- /jarvis and /jarvistextmode: the commands live here, the orb lives in its own window (hud.html, js/jarvis.js) ---------- */
LOCAL.jarvis = ['Jarvis: talk to your PC. /jarvis share = he sees your screen, /jarvis watch = he watches along, /jarvis off = stop', a => {
  const x = (a || '').toLowerCase().trim();
  if (/^(off|stop|exit)$/.test(x)) return post({type:'jarvis_stop'});
  const extra = x === 'share' || x === 'watch' || x === 'unshare';
  post({type:'jarvis_start', mode:extra ? 'keep' : 'voice'}); sys('Jarvis Mode Activated');
  if (x === 'share' || x === 'watch') post({type:'jarvis_share', on:true, watch:x === 'watch'}); else if (x === 'unshare') post({type:'jarvis_share', on:false});
}];
LOCAL.jarvistextmode = ['Jarvis in text mode: type to him instead of talking', () => { post({type:'jarvis_start', mode:'text'}); sys('Jarvis Mode Activated'); }];
