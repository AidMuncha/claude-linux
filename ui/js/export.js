/* ---------- export a chat: Markdown (done in Python), HTML, or PDF ---------- */
const DOC_CSS = `
.pdoc { font:11pt/1.55 "Inter","Noto Sans",system-ui,sans-serif; color:#1b1b1b; max-width:820px; margin:0 auto; }
.pdoc h1 { font-size:20pt; margin:0 0 4px; } .pdoc h2 { font-size:15pt; } .pdoc h3 { font-size:12.5pt; } .pdoc h2, .pdoc h3 { margin:1em 0 .4em; }
.pdoc .meta { color:#777; font-size:9.5pt; margin-bottom:14px; }
.pdoc .u { background:#f1efe8; border-radius:8px; padding:8px 12px; margin:12px 0; break-inside:avoid; }
.pdoc .u b { display:block; font-size:8.5pt; color:#9a5b3f; text-transform:uppercase; letter-spacing:.05em; }
.pdoc .a { margin:10px 0; } .pdoc .a p { margin:0 0 .7em; } .pdoc ul, .pdoc ol { padding-left:1.4em; } .pdoc a { color:#9a5b3f; }
.pdoc code { font:9.5pt "JetBrains Mono","DejaVu Sans Mono",monospace; background:#f3f1ea; padding:0 4px; border-radius:3px; border:0; }
.pdoc .cb { border:1px solid #ddd; border-radius:6px; margin:.6em 0; background:#f7f6f1; overflow:hidden; }
.pdoc .cb .ch { display:flex; justify-content:space-between; font-size:8.5pt; color:#777; padding:3px 10px; border-bottom:1px solid #e4e1d6; } .pdoc .cb .copy { display:none; }
.pdoc pre { margin:0; padding:8px 12px; white-space:pre-wrap; word-break:break-word; font:9pt/1.45 "JetBrains Mono","DejaVu Sans Mono",monospace; }
.pdoc .cb pre code { background:none; padding:0; font-size:inherit; }
.pdoc .tk-c { color:#6e7781; font-style:italic; } .pdoc .tk-s { color:#1a7f37; } .pdoc .tk-n { color:#9a6700; } .pdoc .tk-k { color:#b4452a; } .pdoc .tk-f { color:#6639ba; } .pdoc .tk-t, .pdoc .tk-v { color:#0a6ea8; }
.pdoc .tk-a { background:#e6f6ea; display:inline-block; width:100%; } .pdoc .tk-d { background:#fde8e8; display:inline-block; width:100%; }
.pdoc .tl { font-size:9.5pt; margin:6px 0; color:#444; break-inside:avoid; } .pdoc .tl pre { background:#f7f6f1; border:1px solid #e4e1d6; border-radius:5px; margin-top:3px; font-size:8.5pt; color:#555; }
.pdoc .e { color:#b00020; border:1px solid #e9b5be; border-radius:6px; padding:6px 10px; } .pdoc details.t { color:#666; font-size:9.5pt; margin:6px 0; } .pdoc hr { border:0; border-top:1px dashed #ccc; margin:16px 0; }
`;
function chatHTML(c) {
  const out = [`<h1>${esc(c.title)}</h1><div class="meta">${esc(new Date(c.t).toLocaleString())}${c.cwd && kindOf(c) !== 'chat' ? ' · ' + esc(c.cwd) : ''}</div>`];
  for (const it of c.items) {
    if (it.k === 'user') out.push(`<div class="u"><b>You</b>${esc(it.text).replace(/\n/g, '<br>')}</div>`);
    else if (it.k === 'text') out.push(`<div class="a">${md(it.text)}</div>`);
    else if (it.k === 'think') out.push(`<details class="t"><summary>Thinking</summary><div>${esc(it.text)}</div></details>`);
    else if (it.k === 'tool') out.push(`<div class="tl"><b>${esc(it.name)}</b> <code>${esc(String(toolArg(it.input || {})).slice(0, 200))}</code>${it.result ? `<pre>${esc(trimLines(String(it.result), 25))}</pre>` : ''}</div>`);
    else if (it.k === 'err') out.push(`<div class="e">${esc(it.text)}</div>`);
    else if (it.k === 'div') out.push(`<hr><div class="meta">${esc(it.text)}</div>`);
    else if (it.k === 'sys') out.push(`<div class="meta">${esc(it.text)}</div>`);
  }
  return out.join('\n');
}
const fullHTML = c => `<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(c.title)}</title>\n<style>body{margin:0;padding:28px 18px;background:#fff}${DOC_CSS}</style></head>\n<body><div class="pdoc">${chatHTML(c)}</div></body></html>\n`;
function endPrint() { for (const s of ['#printdoc', '#printstyle']) { const e = $(s); if (e) e.remove(); } }
function printChat(c) {
  endPrint();
  const st = document.createElement('style'); st.id = 'printstyle'; st.textContent = DOC_CSS; document.head.appendChild(st);
  const d = document.createElement('div'); d.id = 'printdoc'; d.className = 'pdoc'; d.innerHTML = chatHTML(c); document.body.appendChild(d);
  toast('Creating the PDF…'); post({type:'pdf', name:c.title});
}
function exportChat(fmt) {
  const c = chats[cur]; if (!c || !c.items.length) return toast('Nothing to export yet', true);
  fmt = String(fmt || 'md').trim().toLowerCase();
  if (fmt === 'md' || fmt === 'markdown') return post({type:'export', chat:cur});
  if (fmt === 'html') return post({type:'savetext', name:c.title, ext:'.html', text:fullHTML(c)});
  if (fmt === 'pdf') return printChat(c);
  toast('Use /export md, /export html or /export pdf', true);
}
EXTRA.pdf_done = p => { endPrint(); toast(p.text, !p.ok); };
