/* ---------- helpers ---------- */
function toast(t, err) { const e = $('#toast'); e.textContent = t; e.className = err ? 'err' : ''; e.style.display = 'block'; clearTimeout(toast.t); toast.t = setTimeout(() => e.style.display = 'none', 3200); }
function inline(s) {
  return s.replace(/`([^`\n]+)`/g, '<code>$1</code>').replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>').replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<i>$2</i>')
          .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2">$1</a>');
}
const KWS = 'if|else|elif|for|while|return|function|const|let|var|class|def|import|from|export|default|async|await|try|catch|except|finally|throw|raise|new|in|of|is|not|and|or|None|null|undefined|true|false|True|False|self|this|fn|pub|use|struct|impl|match|mut|func|type|interface|package|public|private|static|void|int|string|then|fi|do|done|case|esac|switch|break|continue|with|as|lambda|yield|enum|trait|where|extends|implements';
const STR = '("(?:[^"\\\\\\n]|\\\\.)*"|\'(?:[^\'\\\\\\n]|\\\\.)*\'';
const HL = {
  slash: { re: new RegExp('(\\/\\/[^\\n]*|\\/\\*[\\s\\S]*?\\*\\/)|' + STR + '|`(?:[^`\\\\]|\\\\.)*`)|(\\b\\d[\\d_.]*\\b)|\\b(' + KWS + ')\\b|(\\b[A-Za-z_$][\\w$]*(?=\\())|(\\b[A-Z][A-Za-z0-9_]*\\b)', 'g'), map: ['c', 's', 'n', 'k', 'f', 't'] },
  hash: { re: new RegExp('(#[^\\n]*)|' + STR + ')|(\\$\\{?\\w+\\}?)|(\\b\\d[\\d_.]*\\b)|\\b(' + KWS + ')\\b|(\\b[A-Za-z_][\\w]*(?=\\())|(\\b[A-Z][A-Za-z0-9_]*\\b)', 'g'), map: ['c', 's', 'v', 'n', 'k', 'f', 't'] },
};
// one <span class="ln"> per line, so line numbers and wrapping can be switched on in CSS; textContent stays the original code
const byLine = html => html.split('\n').map((l, i, a) => `<span class="ln">${l}${i < a.length - 1 ? '\n' : ''}</span>`).join('');
function hl(code, lang) {
  lang = (lang || '').toLowerCase();
  if (!lang || code.length > 20000 || /^(text|txt|csv|log|output|console)$/.test(lang)) return byLine(esc(code));
  const tok = (cls, text) => text.split('\n').map(p => p ? `<span class="tk-${cls}">${esc(p)}</span>` : '').join('\n');
  if (lang === 'diff' || lang === 'patch') return byLine(code.split('\n').map(l => l ? `<span class="${l[0] === '+' ? 'tk-a' : l[0] === '-' ? 'tk-d' : ''}">${esc(l)}</span>` : '').join('\n'));
  const h = /^(py|python|sh|bash|shell|zsh|yaml|yml|toml|rb|ruby|make|makefile|dockerfile|conf|ini)$/.test(lang) ? HL.hash : HL.slash, re = h.re;
  re.lastIndex = 0; let out = '', last = 0, m;
  while ((m = re.exec(code))) {
    out += esc(code.slice(last, m.index));
    let g = 1; while (g < m.length && m[g] == null) g++;
    out += tok(h.map[g - 1], m[0]); last = re.lastIndex; if (m[0] === '') re.lastIndex++;
  }
  return byLine(out + esc(code.slice(last)));
}
function md(src) {
  const out = [], parts = src.split(/```(\w*)\n?([\s\S]*?)(?:```|$)/g);
  for (let i = 0; i < parts.length; i += 3) {
    let list = null, para = [];
    const close = () => { if (list) { out.push(`</${list}>`); list = null; } };
    const flush = () => { if (para.length) { out.push('<p>' + inline(esc(para.join('\n'))) + '</p>'); para = []; } };
    for (const line of parts[i].split('\n')) {
      let m;
      if ((m = line.match(/^(#{1,3})\s+(.*)/))) { flush(); close(); out.push(`<h${m[1].length}>${inline(esc(m[2]))}</h${m[1].length}>`); }
      else if ((m = line.match(/^\s*[-*]\s+(.*)/))) { flush(); if (list !== 'ul') { close(); out.push('<ul>'); list = 'ul'; } out.push('<li>' + inline(esc(m[1])) + '</li>'); }
      else if ((m = line.match(/^\s*\d+[.)]\s+(.*)/))) { flush(); if (list !== 'ol') { close(); out.push('<ol>'); list = 'ol'; } out.push('<li>' + inline(esc(m[1])) + '</li>'); }
      else if (!line.trim()) { flush(); close(); }
      else { close(); para.push(line); }
    }
    flush(); close();
    if (i + 2 < parts.length) out.push(`<div class="cb"><div class="ch"><span>${esc(parts[i + 1] || 'text')}</span><button class="copy">Copy</button></div><pre><code>${hl(parts[i + 2].replace(/\n$/, ''), parts[i + 1])}</code></pre></div>`);
  }
  return out.join('');
}
document.addEventListener('click', e => {
  const c = e.target.closest('.copy');
  if (c) { navigator.clipboard.writeText(c.closest('.cb').querySelector('code').textContent).then(() => { c.textContent = 'Copied'; setTimeout(() => c.textContent = 'Copy', 1400); }).catch(() => { }); return; }
  const th = e.target.closest('.th'); if (th) th.parentElement.classList.toggle('open');
  const a = e.target.closest('a[href^="http"]'); if (a) { e.preventDefault(); post({type:'open_url', url:a.href}); }
});
function persistChat(id) { if (id === S.split) scheduleSplit(); reportStatusSoon(); clearTimeout(pt); pt = setTimeout(() => chats[id] && post({type:'save', id, chat:chats[id]}), 400); }
const persist = () => cur && persistChat(cur);
function setSetting(k, v) { S.settings[k] = v; post({type:'setsettings', patch:{[k]: v}}); renderComposer(); if (APPEARANCE_KEYS.has(k)) applyAppearance(); }
function cset(key, value) { post({type:'cset', key, value: value === '' ? null : value}); }
const cfg = () => { try { return JSON.parse((S.files.settings || {}).text || '{}') || {}; } catch (e) { return {}; } };
const pick = (o, path) => path.split('.').reduce((a, k) => a == null ? a : a[k], o);

