/* ---------- drop files anywhere on the window: images are attached, other files become @mentions ---------- */
let dragDepth = 0;
const hasFiles = e => e.dataTransfer && [...(e.dataTransfer.types || [])].some(t => t === 'Files' || t === 'text/uri-list');
function dropPaths(dt) {
  return (dt.getData('text/uri-list') || '').split(/\r?\n/).map(l => l.trim()).filter(l => l.startsWith('file://'))
    .map(l => { try { return decodeURIComponent(new URL(l).pathname); } catch (e) { return ''; } }).filter(Boolean);
}
function mentionPaths(paths) {
  const cwd = (chats[cur] || {}).cwd || home, inp = $('#in');
  const toks = paths.map(p => { const r = p.startsWith(cwd + '/') ? p.slice(cwd.length + 1) : p; return /\s/.test(r) ? '@"' + r + '"' : '@' + r; });
  inp.value += (inp.value && !/\s$/.test(inp.value) ? ' ' : '') + toks.join(' ') + ' '; resize(); inp.focus();
  if (tab === 'chat') toast('Added the path. Chat mode cannot read files; switch to Code to let Claude open them.');
}
function handleDrop(dt) {
  const files = [...dt.files], imgs = files.filter(f => f.type.startsWith('image/')); if (imgs.length) addFiles(imgs);
  const names = new Set(imgs.map(f => f.name)), paths = dropPaths(dt).filter(p => !names.has(p.split('/').pop()));
  if (paths.length) mentionPaths(paths);
  else if (!imgs.length && files.length) toast('Could not read where that file lives. Drag it from the file manager.', true);
}
document.addEventListener('dragenter', e => { if (hasFiles(e)) { dragDepth++; $('#dropz').classList.add('on'); } });
document.addEventListener('dragleave', e => { if (hasFiles(e) && --dragDepth <= 0) { dragDepth = 0; $('#dropz').classList.remove('on'); } });
document.addEventListener('dragover', e => { if (hasFiles(e)) e.preventDefault(); });
document.addEventListener('drop', e => { if (!hasFiles(e)) return; e.preventDefault(); dragDepth = 0; $('#dropz').classList.remove('on'); handleDrop(e.dataTransfer); });
