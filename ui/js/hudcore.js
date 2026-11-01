/* ---------- the few things the main page normally provides, for Jarvis' own window ---------- */
const motionOff = () => document.documentElement.dataset.motion === 'reduced';
const toast = () => {};
window.fromPyBatch = items => { for (const [n, p] of items) { try { if (EXTRA[n]) EXTRA[n](p); } catch (e) { post({type:'jserr', text:String(e && e.stack || e)}); } } };
