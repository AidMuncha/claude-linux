const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const IC = {
  clip:'<path d="M20 12l-8 8a5 5 0 0 1-7-7l9-9a3.5 3.5 0 0 1 5 5l-9 9a2 2 0 0 1-3-3l8-8"/>', plus:'<path d="M12 5v14M5 12h14"/>', gear:'<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>',
  send:'<path d="M12 19V5M5 12l7-7 7 7"/>', stop:'<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>', folder:'<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  chev:'<path d="M9 6l6 6-6 6"/>', down:'<path d="M6 9l6 6 6-6"/>', check:'<path d="M5 12l5 5 9-10"/>', x:'<path d="M6 6l12 12M18 6L6 18"/>', refresh:'<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>',
  shield:'<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>', remote:'<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
  cog:'<path d="M4 6h10M18 6h2M4 12h2M10 12h10M4 18h12"/><circle cx="16" cy="6" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
  panel:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',
  cpu:'<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>', gauge:'<path d="M4 18a8 8 0 1 1 16 0"/><path d="M12 18l4-5"/>', doc:'<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/>', code:'<path d="M8 8l-5 4 5 4M16 8l5 4-5 4"/>', info:'<circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v5"/>', tool:'<path d="M14 6a4 4 0 0 0 4 4l-9 9a2.1 2.1 0 0 1-3-3z"/>',
};
const ico = (n, cls) => `<svg class="i ${cls || ''}" viewBox="0 0 24 24">${IC[n]}</svg>`;
const LOGO = '<svg viewBox="0 0 24 24"><path fill="#d97757" d="%%LOGO%%"/></svg>';
const LOGO_CC = LOGO.replace('fill="#d97757"', 'fill="currentColor"');
const EXTRA = {};   // handlers for messages from Python that live in other modules: EXTRA.name = payload => ...

let S = { settings:{}, usage:null, cmds:[], skills:[], files:{}, model:'', version:'', account:null, drawer:false };
const mine = new Set();
let chats = {}, cur = null, tab = 'code', home = '', st = {}, toolEls = {}, pending = 0, pt = 0, spinT = null, spinStart = {}, panel = 'general';
const post = m => window.webkit.messageHandlers.bridge.postMessage(m);
window.onerror = (msg, src, line) => post({type:'jserr', text: msg + ' @' + line});

