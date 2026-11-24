"use strict";
// Markdown for the note view: Obsidian-flavoured subset (wikilinks, embeds, callouts, page markers).
// Needs window.TREE (names, images) from app.js.

const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function resolveLink(target) {
  const t = target.split(/[#^]/)[0].trim().replace(/\.md$/i, "");
  if (!t) return null;
  return TREE.names[t.toLowerCase()] || null;
}

function attachmentRel(name) {
  const base = name.split("|")[0].split(/[#^]/)[0].trim();
  return TREE.images[base.split("/").pop().toLowerCase()] || null;
}
function imageUrl(name) {
  const rel = attachmentRel(name);
  return rel ? "/file?path=" + encodeURIComponent(rel) : null;
}
// a link to an attachment opens it as a tab in the app (app.js handles a.att)
const attLink = (rel, text) => '<a class="att" data-file="' + esc(rel) + '" href="/file?path=' + encodeURIComponent(rel) + '">📎 ' + text + "</a>";

function inline(s) {
  const slots = [];
  const keep = html => "\u0000" + (slots.push(html) - 1) + "\u0001";
  s = s.replace(/`([^`\n]+)`/g, (_, c) => keep("<code>" + esc(c) + "</code>"));
  s = s.replace(/<!--\s*p\.(\d+)\s*-->/g, (_, n) => keep('<span class="pg">p.' + n + "</span>"));
  s = s.replace(/<!--[\s\S]*?-->/g, "");
  s = s.replace(/!\[\[([^\]]+)\]\]/g, (_, t) => {
    const rel = attachmentRel(t), u = imageUrl(t), name = t.split("|")[0].trim();
    if (!rel) return keep(resolveLink(t) ? '<a class="wl" data-path="' + esc(resolveLink(t)) + '">' + esc(name) + "</a>" : '<span class="wl missing" title="找不到這個附件">［' + esc(name) + "］</span>");
    if (/\.(png|jpe?g|gif|webp|svg|avif|bmp)$/i.test(rel)) return keep('<img loading="lazy" src="' + u + '" alt="' + esc(name) + '">');
    if (/\.(mp3|m4a|wav|ogg)$/i.test(rel)) return keep('<audio controls preload="none" src="' + u + '"></audio>');
    if (/\.(mp4|mov|webm)$/i.test(rel)) return keep('<video controls preload="metadata" src="' + u + '"></video>');
    return keep(attLink(rel, esc(name)));
  });
  s = s.replace(/!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?[^)]*\)/g, (_, alt, u) =>
    keep(/^https?:/.test(u) ? '<img loading="lazy" referrerpolicy="no-referrer" src="' + esc(u) + '" alt="' + esc(alt) + '">' : ""));
  s = s.replace(/\[\[([^\]|]+)(?:\\?\|([^\]]+))?\]\]/g, (_, t, label) => {
    const rel = resolveLink(t);
    const text = esc(label || t.replace(/^raw\//, ""));
    const file = !rel && attachmentRel(t);                  // an attachment (PDF…) opens as a tab
    if (file) return keep(attLink(file, text));
    return keep(rel ? '<a class="wl" data-path="' + esc(rel) + '">' + text + "</a>" : '<span class="wl missing" title="還沒有這一頁">' + text + "</span>");
  });
  s = s.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, (_, t, u) => keep('<a href="' + esc(u) + '" target="_blank" rel="noopener">' + esc(t) + "</a>"));
  s = s.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, (_, pre, u) => pre + keep('<a href="' + esc(u) + '" target="_blank" rel="noopener">' + esc(u) + "</a>"));
  s = s.replace(/<(\/?)(sup|sub|i|b|em|strong|u|br)\s*\/?>/gi, (_, c, t) => keep("<" + c + t.toLowerCase() + ">"));
  s = s.replace(/<\/?[a-zA-Z][^>\n]*>/g, "");   // other HTML (span, font, div…): keep the text, drop the tag
  s = esc(s);
  s = s.replace(/__([^_\n]+)__/g, "<strong>$1</strong>").replace(/(^|[^\w_])_([^_\n]+)_(?![\w_])/g, "$1<em>$2</em>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/(^|[^*\w])\*([^*\n]+)\*(?!\w)/g, "$1<em>$2</em>")
       .replace(/==([^=]+)==/g, "<mark>$1</mark>").replace(/~~([^~]+)~~/g, "<del>$1</del>");
  return s.replace(/\u0000(\d+)\u0001/g, (_, i) => slots[+i]);
}

function splitRow(line) {
  return line.trim().replace(/^\||\|$/g, "").split(/(?<!\\)\|/).map(c => c.replace(/\\\|/g, "|").trim());
}

function md(src) {
  const lines = src.replace(/\r/g, "").split("\n");
  const out = [];
  let i = 0;
  const para = [];
  const flush = () => { if (para.length) { out.push("<p>" + inline(para.join("\n")).replace(/\n/g, "<br>") + "</p>"); para.length = 0; } };
  while (i < lines.length) {
    const l = lines[i];
    if (/^```/.test(l)) {
      flush(); const buf = []; i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      i++; out.push("<pre><code>" + esc(buf.join("\n")) + "</code></pre>"); continue;
    }
    let m;
    if ((m = l.match(/^(#{1,6})\s+(.*)$/))) { flush(); const n = Math.min(m[1].length + 1, 4); out.push("<h" + n + ">" + inline(m[2]) + "</h" + n + ">"); i++; continue; }
    if (/^\s*(---|\*\*\*|___)\s*$/.test(l)) { flush(); out.push("<hr>"); i++; continue; }
    if (/^>/.test(l)) {
      flush(); const buf = [];
      while (i < lines.length && /^>/.test(lines[i])) buf.push(lines[i++].replace(/^> ?/, ""));
      const c = buf[0] && buf[0].match(/^\[!(\w+)\][-+]?\s*(.*)$/);
      if (c) {
        const kind = c[1].toLowerCase();
        out.push('<div class="callout ' + esc(kind) + '"><div class="ct">' + inline(c[2] || kind) + "</div>" + md(buf.slice(1).join("\n")) + "</div>");
      } else out.push("<blockquote>" + md(buf.join("\n")) + "</blockquote>");
      continue;
    }
    if (/^\s*\|/.test(l) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      flush(); const head = splitRow(l); i += 2; const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(splitRow(lines[i++]));
      out.push("<table><thead><tr>" + head.map(h => "<th>" + inline(h) + "</th>").join("") + "</tr></thead><tbody>" +
        rows.map(r => "<tr>" + r.map(c => "<td>" + inline(c) + "</td>").join("") + "</tr>").join("") + "</tbody></table>");
      continue;
    }
    if (/^\s*([-*+]|\d+[.)])\s+/.test(l)) {
      flush(); const items = [];
      while (i < lines.length && (/^\s*([-*+]|\d+[.)])\s+/.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && items.length))) {
        const ln = lines[i++];
        const im = ln.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
        if (im) items.push({ indent: im[1].replace(/\t/g, "    ").length, tag: /\d/.test(im[2]) ? "ol" : "ul", text: im[3] });
        else items[items.length - 1].text += " " + ln.trim();
      }
      // nesting follows each level's real indentation (2 or 4 spaces, tabs), each level with its own list type
      const stack = [];
      let html = "";
      for (const it of items) {
        if (!stack.length) { html += "<" + it.tag + ">"; stack.push(it); }
        else if (it.indent > stack[stack.length - 1].indent) { html += "<" + it.tag + ">"; stack.push(it); }
        else {
          html += "</li>";
          while (stack.length > 1 && it.indent < stack[stack.length - 1].indent) html += "</" + stack.pop().tag + "></li>";
        }
        const t = it.text.replace(/^\[( |x)\]\s*/i, (_, x) => (x.trim() ? "☑ " : "☐ "));
        html += "<li>" + inline(t);
      }
      html += "</li>";
      while (stack.length) html += "</" + stack.pop().tag + ">" + (stack.length ? "</li>" : "");
      out.push(html); continue;
    }
    if ((m = l.trim().match(/^<!--\s*p\.(\d+)\s*-->$/))) { flush(); out.push('<div class="pgbreak"><span>p. ' + m[1] + "</span></div>"); i++; continue; }
    if (/^\s*$/.test(l)) { flush(); i++; continue; }
    if (/^<[^>]+>\s*$/.test(l.trim()) && !/^<!--/.test(l.trim())) { i++; continue; }
    para.push(l); i++;
  }
  flush();
  return out.join("\n");
}

function splitFrontmatter(text) {
  const m = text.match(/^---\n([\s\S]*?)\n---\n?/);
  if (!m) return { fm: {}, body: text };
  const fm = {};
  for (const line of m[1].split("\n")) {
    const kv = line.match(/^([A-Za-z_][\w-]*):\s*(.*)$/);
    if (kv) fm[kv[1]] = kv[2].replace(/^["']|["']$/g, "");
  }
  return { fm, body: text.slice(m[0].length) };
}

// ---------- PDF-converted notes, tidied for reading (display only; the file stays as converted)
// pdf2raw writes one block per PDF text block: lines broken mid-sentence, paragraphs split by page breaks,
// running heads and feet on every page, and the OCR of pictures. This joins what belongs together and
// drops the repeats. Page markers stay (inline where a paragraph runs across a page).

const CJK = "⺀-鿿豈-﫿＀-￯　-〿";
const ENDS = new RegExp("[.!?。！？」』”\"'’)）\\]:：…]$");
const CJK_END = new RegExp("[" + CJK + "]$"), CJK_START = new RegExp("^[" + CJK + "]");
const STRUCT = /^(#|\s*[-*+]\s|\s*\d+[.)]\s|\s*\||>|!\[|```|<!--|\$\$)/;

function tidyPdf(body) {
  // the OCR of pictures (figure labels, logos) is noise, unless it is most of the note (a scan kept as images)
  const PIC = /<!--\s*Start of picture text\s*-->([\s\S]*?)<!--\s*End of picture text\s*-->/g;
  const picLen = [...body.matchAll(PIC)].reduce((n, m) => n + m[1].length, 0);
  body = picLen > (body.length - picLen) ? body.replace(PIC, (_, t) => t.replace(/<br>/g, "\n")) : body.replace(PIC, "");
  body = body.replace(/[ \t]*(<!--\s*p\.\d+\s*-->)[ \t]*\n?/g, "\n\n$1\n\n");
  let blocks = body.split(/\n[ \t]*\n/).map(b => b.replace(/[ \t]+$/gm, "").trim()).filter(Boolean);
  const isPg = b => /^<!--\s*p\.\d+\s*-->$/.test(b);
  // running heads and feet: short blocks at the top or bottom of a page that recur there on many pages.
  // Only those positions count, so a line repeated inside the text (a dialogue's "Yes.") is never dropped.
  const pages = blocks.filter(isPg).length;
  if (pages >= 4) {
    // OCR spells a footer a little differently on each page: compare the start, digits and spaces left out
    const key = b => b.replace(/[\d\s]+/g, "").toLowerCase().slice(0, 24);
    const edge = new Array(blocks.length).fill(false);
    blocks.forEach((b, i) => {
      if (!isPg(b)) return;
      for (const j of [i - 2, i - 1, i + 1, i + 2])
        if (j >= 0 && j < blocks.length && !isPg(blocks[j]) && blocks[j].length < 160 && !/!\[|<img/.test(blocks[j])) edge[j] = true;   // never an image
    });
    const n = new Map();
    blocks.forEach((b, i) => { if (edge[i]) n.set(key(b), (n.get(key(b)) || 0) + 1); });
    const min = Math.max(3, pages * 0.3);
    blocks = blocks.filter((b, i) => !edge[i] || !(/^\d{1,4}$/.test(b) || (key(b) && n.get(key(b)) >= min)));
  }
  const joinLines = (a, b) => {
    if (/[a-z]-$/.test(a) && /^[a-z]/.test(b)) return a.slice(0, -1) + b;     // hyphenated at the line end
    return a + (CJK_END.test(a) && CJK_START.test(b) ? "" : " ") + b;
  };
  // inside a plain paragraph block, lines are the PDF's line breaks
  blocks = blocks.map(b => b.includes("\n") && !b.split("\n").some(l => STRUCT.test(l)) ? b.split("\n").reduce(joinLines) : b);
  const continues = (a, b) => {
    if (STRUCT.test(a) || STRUCT.test(b) || ENDS.test(a)) return false;
    if (/^[a-z]/.test(b) || /[a-z]-$/.test(a)) return /[a-z,;-]$/.test(a);                    // Latin, mid-sentence
    return CJK_START.test(b) && (/[，、；：「『（《]$/.test(a) || (CJK_END.test(a) && a.length >= 20));
  };
  const out = [];
  let pend = [];                    // page markers between two blocks that may join
  for (const b of blocks) {
    if (isPg(b)) { pend.push(b); continue; }
    const last = out.length ? out[out.length - 1] : null;
    if (last != null && continues(last, b)) out[out.length - 1] = joinLines(last + (pend.length ? " " + pend.join(" ") : ""), b);
    else { out.push(...pend); out.push(b); }
    pend = [];
  }
  out.push(...pend);
  return out.join("\n\n");
}
