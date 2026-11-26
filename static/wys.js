"use strict";
// The note editor: what you see is what you get, like Apple Notes, and the file stays Markdown.
// The note is split into blocks, one per line (a table, a code block, a callout or the frontmatter is one block).
// A block you don't touch is saved exactly as it was; only edited blocks are written back from what is on
// screen. What the editor doesn't draw (frontmatter, code, callouts, HTML) shows as its source text, editable.
// Needs md.js (esc, attachmentRel, imageUrl, resolveLink) and T() from i18n.js.

const Wys = (() => {
  const LIST = /^(\s*)([-*+]|\d+[.)])(\s+)(?:\[([ xX])\](\s+))?(.*)$/;
  const HEAD = /^(#{1,6})(\s+)(.*)$/;
  const HR = /^\s{0,3}([-*_])(\s*\1){2,}\s*$/;
  const ZW = /​/g;

  // ---------- Markdown → blocks
  function parse(md) {
    const L = md.split("\n"), out = [];
    let i = 0;
    const take = (k, n, extra) => { out.push(Object.assign({ k, md: L.slice(i, i + n).join("\n") }, extra || {})); i += n; };
    if (L[0] === "---") {                                  // frontmatter
      const end = L.indexOf("---", 1);
      if (end > 0) take("fm", end + 1);
    }
    while (i < L.length) {
      const l = L[i];
      let m;
      if (/^\s*(```|~~~)/.test(l)) {
        const f = l.trim().slice(0, 3);
        let j = i + 1;
        while (j < L.length && !L[j].trim().startsWith(f)) j++;
        take("raw", Math.min(j, L.length - 1) - i + 1, { label: T("程式碼") });
      } else if (/^\s*\$\$/.test(l)) {
        let j = i + (/^\s*\$\$.*\$\$\s*$/.test(l) && l.trim().length > 4 ? 0 : 1);
        while (j < L.length && j > i && !/\$\$\s*$/.test(L[j])) j++;
        take("raw", Math.min(j, L.length - 1) - i + 1, { label: T("數學式") });
      } else if (/^\s*>/.test(l)) {
        let j = i;
        while (j < L.length && /^\s*>/.test(L[j])) j++;
        take("raw", j - i, { label: /^\s*>\s*\[!/.test(l) ? T("標註") : T("引言") });
      } else if (/^\s*\|/.test(l) && i + 1 < L.length && /^\s*\|?\s*:?-+:?\s*(\||$)/.test(L[i + 1])) {
        let j = i;
        while (j < L.length && /^\s*\|/.test(L[j])) j++;
        take("table", j - i);
      } else if (/^\s*<(?!u>|\/u>|!--\s*p\.)[a-zA-Z!/]/.test(l)) {
        take("raw", 1, { label: "HTML" });
      } else if (HR.test(l) && l.trim()) {
        take("hr", 1);
      } else if ((m = l.match(HEAD))) {
        take("h", 1, { lv: m[1].length, sp: m[2], text: m[3] });
      } else if ((m = l.match(LIST))) {
        take("li", 1, { ind: m[1], mk: m[2], sp: m[3], ck: m[4] === undefined ? "" : m[4], sp2: m[5], text: m[6] });
      } else {
        take("p", 1, { text: l });
      }
    }
    if (!out.length) out.push({ k: "p", md: "", text: "" });
    return out;
  }

  // ---------- inline Markdown → HTML (atoms are links, embeds, code: kept whole, as written)
  function atomHtml(mdText, html, cls) {
    return '<span class="atom ' + (cls || "") + '" contenteditable="false" data-md="' + esc(mdText) + '">' + html + "</span>";
  }
  function inl(s) {
    const slots = [], srcs = [];
    const keep = (html, src) => { srcs.push(src === undefined ? html : src); return "\u0000" + (slots.push(html) - 1) + "\u0001"; };
    const unslot = x => x.replace(/\u0000(\d+)\u0001/g, (_, k) => unslot(srcs[+k]));
    const atom = (c, html, cls) => keep(atomHtml(unslot(c), html, cls), unslot(c));
    s = s.replace(/`[^`\n]+`/g, c => atom(c, "<code>" + esc(c.slice(1, -1)) + "</code>", "code"));
    s = s.replace(/\\[\\`*_{}\[\]()#+\-.!|~=<>$]/g, c => keep(esc(c), c));      // \* stays a star (shown as written)
    s = s.replace(/<!--[\s\S]*?-->/g, c => atom(c, /^<!--\s*p\.\d+/.test(c) ? esc(c.replace(/<!--\s*|\s*-->/g, "")) : "…", "cm"));
    s = s.replace(/!\[\[([^\]]+)\]\]/g, (c, t) => {
      const u = imageUrl(t), name = t.split("|")[0].trim();
      return u && /\.(png|jpe?g|gif|webp|svg|avif|bmp)$/i.test(attachmentRel(t))
        ? atom(c, '<img src="' + u + '" alt="' + esc(name) + '">', "img") : atom(c, "📎 " + esc(name), "wl");
    });
    s = s.replace(/!\[([^\]]*)\]\(([^)]*)\)/g, (c, alt, u) =>
      atom(c, /^https?:/.test(u.trim()) ? '<img src="' + esc(unslot(u).trim().split(/\s/)[0]) + '" alt="' + esc(unslot(alt)) + '" referrerpolicy="no-referrer">' : "🖼 " + esc(unslot(alt)), "img"));
    s = s.replace(/\[\[([^\]|]+)(?:\\?\|([^\]]+))?\]\]/g, (c, t, label) =>
      atom(c, esc(unslot(label || t.replace(/^raw\//, ""))), "wl" + (resolveLink(unslot(t)) ? "" : " missing")));
    s = s.replace(/\[([^\]]+)\]\(([^)\s]+)[^)]*\)/g, (c, t) => atom(c, t.replace(/\u0000(\d+)\u0001/g, (_, k) => slots[+k]).includes("<img") ? t : esc(unslot(t)), "url"));
    s = s.replace(/<\/?u>/g, c => keep(c));
    s = s.replace(/<\/?[a-zA-Z][^>\n]*>/g, c => atom(c, esc(c), "tag"));
    s = esc(s);
    // marks as Markdown pairs them: no space just inside; each remembers how it was written
    s = s.replace(/\*\*(?!\s)([^*\n]+?)(?<!\s)\*\*/g, "<b>$1</b>").replace(/(^|[^\w_])__(?!\s)([^_\n]+?)(?<!\s)__(?![\w_])/g, '$1<b data-m="__">$2</b>')
      .replace(/(^|[^*\w])\*(?![\s*])([^*\n]+?)(?<!\s)\*(?![*\w])/g, "$1<i>$2</i>").replace(/(^|[^\w_])_(?![\s_])([^_\n]+?)(?<!\s)_(?![\w_])/g, '$1<i data-m="_">$2</i>')
      .replace(/~~(?!\s)([^~\n]+?)(?<!\s)~~/g, "<s>$1</s>").replace(/==(?!\s)([^=\n]+?)(?<!\s)==/g, "<mark>$1</mark>");
    const expand = x => x.replace(/\u0000(\d+)\u0001/g, (_, k) => expand(slots[+k]));
    return expand(s) || "<br>";
  }

  // ---------- blocks → DOM
  function level(ind, unit) {
    const w = ind.replace(/\t/g, "    ").length;
    return w ? Math.max(1, Math.round(w / (unit === "\t" ? 4 : unit.length))) : 0;
  }
  function el(b, ed) {
    let e;
    if (b.k === "fm") {                                     // properties: a form, not YAML (props.js)
      e = document.createElement("div");
      e.className = "wb fm";
      e.contentEditable = "false";
      const L = (b.md || "---\n---").split("\n");
      Props.mount(e, L.slice(1, -1).join("\n"), {
        before: () => push(ed, true),
        after: () => { delete e._md; changed(ed); },
        open: name => ed._open && ed._open(name),
      });
      if (b.isNew) e._new = true;
    } else if (b.k === "raw") {
      e = document.createElement("pre");
      e.className = "wb raw";
      e.dataset.label = b.label || "";
      e.textContent = b.md;
    } else if (b.k === "hr") {
      e = document.createElement("div");
      e.className = "wb hr";
      e.contentEditable = "false";
    } else if (b.k === "table") {
      e = document.createElement("div");
      e.className = "wb table";
      const lines = b.md.split("\n"), rows = lines.filter((r, n) => n !== 1);
      e._sep = lines[1];
      e.innerHTML = "<table>" + rows.map((r, n) => "<tr>" + splitRow(r).map(c => (n ? "<td>" : "<th>") + inl(c) + (n ? "</td>" : "</th>")).join("") + "</tr>").join("") + "</table>";
      e.querySelectorAll("tr").forEach((tr, n) => { tr._md = rows[n]; tr._h = tr.innerHTML; });
    } else {
      e = document.createElement("div");
      e.className = "wb " + b.k;
      if (b.k === "h") e.dataset.lv = b.lv;
      if (b.sp && b.sp !== " ") e._sp = b.sp;                  // spacing after the marks, as written
      if (b.sp2 && b.sp2 !== " ") e._sp2 = b.sp2;
      if (b.k === "li") {
        e.dataset.ind = b.ind; e.dataset.mk = b.mk; e.dataset.ck = b.ck;
        e.style.setProperty("--lv", level(b.ind, ed._unit));
        if (b.ck) e.classList.add("ck");
        if (/x/i.test(b.ck)) e.classList.add("done");
      }
      e.innerHTML = inl(b.text || "");
    }
    if (b.md !== undefined) { e._md = b.md; e._h = e.innerHTML; e._a = sig(e); }
    return e;
  }
  const sig = e => [e.className, e.dataset.lv, e.dataset.ind, e.dataset.mk, e.dataset.ck, e.dataset.n].join("|");

  // ---------- DOM → Markdown
  function inlMd(node) {
    let s = "";
    for (const n of node.childNodes) {
      if (n.nodeType === 3) { s += n.nodeValue; continue; }
      if (n.nodeType !== 1) continue;
      if (n.dataset && n.dataset.md !== undefined) { s += n.dataset.md; continue; }
      const t = n.tagName, inner = inlMd(n);
      if (!inner.replace(ZW, "").trim() && t !== "BR") { s += inner; continue; }
      if (t === "B" || t === "STRONG") s += wrap(inner, n.dataset.m || "**");
      else if (t === "I" || t === "EM") s += wrap(inner, n.dataset.m || "*");
      else if (t === "S" || t === "STRIKE" || t === "DEL") s += wrap(inner, "~~");
      else if (t === "U") s += "<u>" + inner + "</u>";
      else if (t === "MARK") s += wrap(inner, "==");
      else if (t === "BR") s += "";
      else if (t === "DIV" || t === "P") s += (s ? " " : "") + inner;
      else s += inner;
    }
    return s.replace(ZW, "").replace(/ /g, " ");
  }
  // **x ** is not bold in Markdown: the spaces go outside the marks
  function wrap(inner, m) {
    const a = inner.match(/^\s*/)[0], z = inner.match(/\s*$/)[0];
    return a + m + inner.trim() + m + z;
  }
  function blockMd(e) {
    if (e._md !== undefined && e.innerHTML === e._h && sig(e) === e._a) return e._md;
    if (e.nodeType === 3) return e.nodeValue.replace(ZW, "");
    if (e.nodeType !== 1) return "";
    const c = e.classList;
    if (c.contains("fm")) {
      if (e._md !== undefined && !e._dirty) return e._md;
      const y = Props.value(e);
      return y.trim() ? "---\n" + y + "\n---" : e._new ? null : "---\n---";
    }
    if (c.contains("raw")) return e.innerText.replace(/\n$/, "");
    if (c.contains("hr")) return "---";
    if (c.contains("table")) {
      const trs = [...e.querySelectorAll("tr")];             // rows you didn't touch stay as written
      const rows = trs.map(tr => tr._md !== undefined && tr.innerHTML === tr._h ? tr._md
        : "| " + [...tr.children].map(td => inlMd(td).trim().replace(/(?<!\\)\|/g, "\\|")).join(" | ") + " |");
      if (!rows.length) return "";
      const w = trs[0].children.length, sep = e._sep && splitRow(e._sep).length === w ? e._sep : "| " + Array(w).fill("---").join(" | ") + " |";
      rows.splice(1, 0, sep);
      return rows.join("\n");
    }
    const text = inlMd(e);
    if (c.contains("h")) return "#".repeat(+e.dataset.lv || 1) + (e._sp || " ") + text;
    if (c.contains("li")) {
      const mk = /\d/.test(e.dataset.mk) ? (e.dataset.n || "1") + e.dataset.mk.slice(-1) : e.dataset.mk;
      return e.dataset.ind + mk + (e._sp || " ") + (e.dataset.ck ? "[" + (c.contains("done") ? "x" : " ") + "]" + (e._sp2 || " ") : "") + text;
    }
    return text;                                            // a paragraph, or something the browser made
  }
  function value(ed) {
    const v = [...ed.childNodes].filter(n => n.nodeType === 1 || n.nodeValue.trim()).map(blockMd).filter(x => x !== null).join("\n");
    return ed._eol && !v.endsWith("\n") ? v + "\n" : v;      // a file that ended with a newline still does
  }

  // ---------- helpers
  const blocks = ed => [...ed.children];
  function blockOf(ed, node) {
    while (node && node.parentNode !== ed) node = node.parentNode;
    return node && node.nodeType === 1 ? node : null;
  }
  function caret() {
    const s = getSelection();
    return s.rangeCount ? s.getRangeAt(0) : null;
  }
  function atStart(b, r) {
    const x = document.createRange();
    x.setStart(b, 0); x.setEnd(r.startContainer, r.startOffset);
    const f = x.cloneContents();
    return !f.textContent.replace(ZW, "") && !f.querySelector(".atom,img");
  }
  function atEnd(b, r) {
    const x = document.createRange();
    x.setStart(r.endContainer, r.endOffset); x.setEnd(b, b.childNodes.length);
    const f = x.cloneContents();
    return !f.textContent.replace(ZW, "") && !f.querySelector(".atom,img");
  }
  function place(node, start) {
    const r = document.createRange();
    if (start) r.setStart(node, 0); else r.selectNodeContents(node);
    r.collapse(!!start);
    const s = getSelection(); s.removeAllRanges(); s.addRange(r);
  }
  function fresh(b) { delete b._md; }
  function make(k, ed, extra) {
    const e = el(Object.assign({ k, text: "" }, extra || {}), ed);
    delete e._md;
    return e;
  }
  function renumber(ed) {
    const run = {};
    for (const b of blocks(ed)) {
      if (!b.classList.contains("li")) { for (const k in run) delete run[k]; continue; }
      const lv = b.style.getPropertyValue("--lv").trim() || "0";
      for (const k in run) if (+k > +lv) delete run[k];
      if (/\d/.test(b.dataset.mk)) {
        const n = run[lv] ? run[lv] + 1 : parseInt(b.dataset.mk, 10) || 1;
        run[lv] = n;
        if (b.dataset.n !== String(n)) b.dataset.n = n;
      } else delete run[lv];
    }
  }
  function changeType(ed, b, k, extra) {
    if (!b || /\b(raw|table|hr|fm)\b/.test(b.className)) return b;
    const e = make(k, ed, extra);
    e.innerHTML = b.innerHTML;
    b.replaceWith(e);
    return e;
  }
  function selectedBlocks(ed) {
    const r = caret();
    if (!r) return [];
    const a = blockOf(ed, r.startContainer), z = blockOf(ed, r.endContainer);
    if (!a) return [];
    const all = blocks(ed), i = all.indexOf(a), j = z ? all.indexOf(z) : i;
    return all.slice(i, j + 1);
  }

  // ---------- undo (the editor's own: structural changes bypass the browser's)
  function snap(ed) {
    const r = caret(), b = r && blockOf(ed, r.startContainer);
    let off = 0;
    if (b && r) { const x = document.createRange(); x.setStart(b, 0); x.setEnd(r.startContainer, r.startOffset); off = x.toString().length; }
    return { md: value(ed), at: b ? blocks(ed).indexOf(b) : -1, off };
  }
  function restore(ed, st) {
    mount(ed, st.md, true);
    const b = blocks(ed)[st.at];
    if (!b) return;
    const w = document.createTreeWalker(b, NodeFilter.SHOW_TEXT);
    let left = st.off, n;
    while ((n = w.nextNode())) {
      if (left <= n.length) { const r = document.createRange(); r.setStart(n, left); r.collapse(true); const s = getSelection(); s.removeAllRanges(); s.addRange(r); return; }
      left -= n.length;
    }
    place(b, false);
  }
  function push(ed, force, kind) {
    const now = Date.now();                                 // typing is one step per pause, per kind (typing / deleting)
    if (!force && now - ed._last < 900 && kind === ed._kind) return;
    ed._kind = kind;
    ed._last = now;
    ed._undo.push(snap(ed));
    if (ed._undo.length > 200) ed._undo.shift();
    ed._redo = [];
  }

  // ---------- actions
  function splitAt(ed, b, r) {
    const x = document.createRange();
    x.setStart(r.startContainer, r.startOffset); x.setEnd(b, b.childNodes.length);
    return x.extractContents();
  }
  function enter(ed, b, r) {
    if (b.classList.contains("raw")) { document.execCommand("insertText", false, "\n"); return; }
    if (b.classList.contains("table")) return tableEnter(ed, b, r);
    push(ed, true);
    if (!r.collapsed) r.deleteContents();
    const li = b.classList.contains("li"), empty = !b.textContent.replace(ZW, "").trim() && !b.querySelector(".atom");
    if (li && empty) {                                      // an empty item ends the list
      const e = b.dataset.ind ? b : changeType(ed, b, "p");
      if (e === b) { fresh(b); b.dataset.ind = b.dataset.ind.replace(/^(\t| {1,4})/, ""); b.style.setProperty("--lv", level(b.dataset.ind, ed._unit)); }
      place(e, true); return changed(ed);
    }
    if (atStart(b, r) && !empty) {                          // at the start: a new line above, same kind
      const e = li ? make("li", ed, { ind: b.dataset.ind, mk: b.dataset.mk, ck: b.dataset.ck ? " " : "" }) : make("p", ed);
      b.before(e); return changed(ed);
    }
    const tail = splitAt(ed, b, r);
    fresh(b);
    if (!b.childNodes.length || !b.textContent) b.innerHTML = b.querySelector(".atom") ? b.innerHTML : "<br>";
    const e = li ? make("li", ed, { ind: b.dataset.ind, mk: b.dataset.mk, ck: b.dataset.ck ? " " : "" }) : make("p", ed);
    e.innerHTML = "";
    e.append(tail);
    if (!e.textContent && !e.querySelector(".atom")) e.innerHTML = "<br>";
    b.after(e);
    place(e, true);
    changed(ed);
  }
  function tableEnter(ed, b, r) {
    const td = (r.startContainer.nodeType === 1 ? r.startContainer : r.startContainer.parentElement).closest("td,th");
    if (!td) return;
    push(ed, true);
    const tr = td.parentElement, i = [...tr.children].indexOf(td);
    let next = tr.nextElementSibling;
    if (!next) {
      next = document.createElement("tr");
      next.innerHTML = [...tr.children].map(() => "<td><br></td>").join("");
      tr.after(next);
    }
    place(next.children[i], true);
    changed(ed);
  }
  function backspace(ed, b, r, e) {
    if (!r.collapsed || !atStart(b, r) || b.classList.contains("raw")) return;
    if (b.classList.contains("table")) { const td = (r.startContainer.nodeType === 1 ? r.startContainer : r.startContainer.parentElement).closest("td,th"); if (td && atStart(td, r)) e.preventDefault(); return; }
    e.preventDefault();
    push(ed, true);
    if (b.classList.contains("li") || b.classList.contains("h")) {   // like Notes: first back to plain text
      if (b.classList.contains("li") && b.dataset.ind) return indent(ed, [b], -1);
      place(changeType(ed, b, "p"), true); return changed(ed);
    }
    const prev = b.previousElementSibling;
    if (!prev) return;
    if (/\b(raw|table|hr|fm)\b/.test(prev.className)) {
      if (!b.textContent.replace(ZW, "") && !b.querySelector(".atom")) { b.remove(); place(prev, false); }
      else if (prev.classList.contains("hr")) prev.remove();
      return changed(ed);
    }
    fresh(prev);
    const empty = !prev.textContent.replace(ZW, "") && !prev.querySelector(".atom");
    if (empty) { prev.innerHTML = ""; }
    const mark = document.createElement("span");
    prev.append(mark);
    while (b.firstChild) prev.append(b.firstChild);
    b.remove();
    if (prev.textContent.replace(ZW, "") || prev.querySelector(".atom")) prev.querySelectorAll(":scope > br").forEach(x => x.remove());
    const x = document.createRange(); x.setStartBefore(mark); x.collapse(true);
    mark.remove();
    const s = getSelection(); s.removeAllRanges(); s.addRange(x);
    changed(ed);
  }
  function del(ed, b, r, e) {                               // Delete at the end: the next line joins this one
    if (!r.collapsed || !atEnd(b, r) || !/\b(p|h|li)\b/.test(b.className)) return;
    const next = b.nextElementSibling;
    if (!next || !/\b(p|h|li)\b/.test(next.className)) return;
    e.preventDefault();
    push(ed, true);
    fresh(b);
    if (!b.textContent.replace(ZW, "") && !b.querySelector(".atom")) b.innerHTML = "";
    const mark = document.createElement("span");
    b.append(mark);
    while (next.firstChild) b.append(next.firstChild);
    next.remove();
    const x = document.createRange(); x.setStartBefore(mark); x.collapse(true);
    mark.remove();
    const s = getSelection(); s.removeAllRanges(); s.addRange(x);
    changed(ed);
  }
  function indent(ed, bs, d) {
    for (const b of bs) {
      if (!b.classList.contains("li")) continue;
      fresh(b);
      b.dataset.ind = d > 0 ? ed._unit + b.dataset.ind : b.dataset.ind.replace(/^(\t| {1,4})/, "");
      b.style.setProperty("--lv", level(b.dataset.ind, ed._unit));
    }
    changed(ed);
  }

  function tool(ed, t) {
    ed.focus();
    const bs = selectedBlocks(ed);
    push(ed, true);
    if (t === "b") document.execCommand("bold");
    else if (t === "i") document.execCommand("italic");
    else if (t === "u") document.execCommand("underline");
    else if (t === "s") document.execCommand("strikeThrough");
    else if (t === "indent" || t === "outdent") indent(ed, bs, t === "indent" ? 1 : -1);
    else if (t.startsWith("style:")) {
      const v = t.slice(6), out = bs.map(b => v === "p" ? changeType(ed, b, "p") : changeType(ed, b, "h", { lv: +v.slice(1) }));
      if (out[0]) place(out[out.length - 1], false);
    } else if (["ul", "dash", "ol", "check"].includes(t)) {
      const mk = { ul: "-", dash: "+", ol: "1.", check: "-" }[t];
      const same = bs.length && bs.every(b => b.classList.contains("li") && (t === "check" ? !!b.dataset.ck : !b.dataset.ck && (t === "ol" ? /\d/.test(b.dataset.mk) : b.dataset.mk === mk)));
      const out = bs.map(b => same ? changeType(ed, b, "p")
        : changeType(ed, b, "li", { ind: b.dataset.ind || "", mk, ck: t === "check" ? (b.classList.contains("done") ? "x" : " ") : "" }));
      if (out[0]) place(out[out.length - 1], false);
    } else if (t === "props") {                             // show the properties, or start them
      let fm = ed.querySelector(":scope > .wb.fm");
      if (!fm) { fm = el({ k: "fm", md: "---\n---", isNew: true }, ed); delete fm._md; ed.prepend(fm); }
      if (!fm._pp.open) fm.querySelector(".pp-toggle").click();
      const nb = fm.querySelector(".pp-new"); if (nb && !fm._pp.props.some(p => p.key)) nb.click();
      fm.scrollIntoView({ block: "nearest" });
      return;
    } else if (t === "table") {
      const b = bs[bs.length - 1];
      const inTable = b && b.classList.contains("table");
      if (inTable) {                                        // in a table: one more column
        fresh(b);
        b.querySelectorAll("tr").forEach((tr, n) => tr.insertAdjacentHTML("beforeend", n ? "<td><br></td>" : "<th>" + esc(T("欄")) + "</th>"));
      } else {
        const tb = el({ k: "table", md: "| " + T("欄 1") + " | " + T("欄 2") + " |\n| --- | --- |\n|   |   |" }, ed);
        delete tb._md;
        const p = make("p", ed);
        b ? b.after(tb) : ed.append(tb);
        tb.after(p);
        place(tb.querySelector("td"), true);
      }
    }
    changed(ed);
  }

  // Markdown typed at the start of a line: "# " heading, "- " list, "1. " numbered, "[] " checklist
  function autoformat(ed, b, r) {
    if (!b.classList.contains("p") || !r.collapsed) return false;
    const x = document.createRange(); x.setStart(b, 0); x.setEnd(r.startContainer, r.startOffset);
    const before = x.toString().replace(ZW, "");
    let m, e = null;
    if ((m = before.match(/^(#{1,3})$/))) e = { k: "h", lv: m[1].length };
    else if ((m = before.match(/^([-*+])$/))) e = { k: "li", mk: m[1], ck: "" };
    else if ((m = before.match(/^(\d+)([.)])$/))) e = { k: "li", mk: m[1] + m[2], ck: "" };
    else if (/^(-\s?)?\[\s?\]$/.test(before)) e = { k: "li", mk: "-", ck: " " };
    if (!e) return false;
    push(ed, true);
    x.deleteContents();
    const n = changeType(ed, b, e.k, Object.assign({ ind: "" }, e));
    if (!n.textContent) n.innerHTML = "<br>";
    place(n, true);
    changed(ed);
    return true;
  }

  function changed(ed) {
    renumber(ed);
    ed._last = 0;                                           // the next typing is a step of its own
    if (ed._on) ed._on();
  }

  // Lines of Markdown put in at the caret (a paste, attachments): the current line is split there
  function insertMd(ed, md) {
    push(ed, true);
    let r = caret(), b = r && blockOf(ed, r.startContainer);
    if (!b) { b = blocks(ed)[blocks(ed).length - 1]; place(b, false); r = caret(); }
    const lines = md.split("\n");
    if (lines.length === 1 && !/^(#|\s*[-*+]\s|\s*\d+[.)]\s|\|)/.test(md) && !b.classList.contains("raw")) {
      if (!r.collapsed) r.deleteContents();
      const tmp = document.createElement("span");
      tmp.innerHTML = inl(md);
      const frag = document.createDocumentFragment(), last = tmp.lastChild;
      while (tmp.firstChild) frag.append(tmp.firstChild);
      r.insertNode(frag);
      if (last) { const x = document.createRange(); x.setStartAfter(last); x.collapse(true); getSelection().removeAllRanges(); getSelection().addRange(x); }
      fresh(b);
      return changed(ed);
    }
    if (b.classList.contains("raw")) { document.execCommand("insertText", false, md); return changed(ed); }
    const tail = splitAt(ed, b, r);
    fresh(b);
    const news = parse(md).map(x => { const e = el(x, ed); delete e._md; return e; });
    let at = b;
    for (const e of news) { at.after(e); at = e; }
    if (tail.textContent.replace(ZW, "") || tail.querySelector && tail.querySelector(".atom")) {
      const e = make(b.classList.contains("li") ? "li" : "p", ed, { ind: b.dataset.ind || "", mk: b.dataset.mk || "-", ck: b.dataset.ck ? " " : "" });
      e.innerHTML = ""; e.append(tail); at.after(e);
    }
    if (!b.textContent.replace(ZW, "") && !b.querySelector(".atom") && b.classList.contains("p")) b.remove();
    place(at, false);
    changed(ed);
  }

  // ---------- mount
  function mount(ed, md, keepHistory) {
    const m = md.match(/^([ \t]+)(?:[-*+]|\d+[.)])\s/m);
    ed._unit = m && m[1] ? (m[1][0] === "\t" ? "\t" : m[1]) : "\t";
    ed._eol = md.endsWith("\n");
    ed.innerHTML = "";
    for (const b of parse(md)) ed.append(el(b, ed));
    renumber(ed);
    for (const b of blocks(ed)) if (b._md !== undefined) { b._h = b.innerHTML; b._a = sig(b); }
    if (!keepHistory) { ed._undo = []; ed._redo = []; ed._last = 0; }
  }

  function attach(ed, onChange) {
    ed._on = onChange;
    ed.addEventListener("beforeinput", e => {
      if (e.inputType === "historyUndo" || e.inputType === "historyRedo") { e.preventDefault(); undoRedo(ed, e.inputType === "historyUndo"); return; }
      // a new line is always the editor's own (enter()); the browser's would copy the block as it is,
      // and an input method's confirming Enter must not make one at all
      if (e.inputType === "insertParagraph" || e.inputType === "insertLineBreak") { e.preventDefault(); return; }
      push(ed, false, /^delete/.test(e.inputType) ? "del" : "ins");
    });
    // input methods (注音, 倉頡, pinyin…): Enter confirms the word, it must not split the line
    ed.addEventListener("compositionstart", () => { ed._composing = true; });
    ed.addEventListener("compositionend", () => { ed._composing = false; ed._compEnd = Date.now(); });
    ed.addEventListener("input", () => { if (ed._on) ed._on(); });
    ed.addEventListener("keydown", e => {
      if (e.isComposing || e.keyCode === 229 || ed._composing) return;   // Chinese/Japanese input: the IME owns Enter
      if (e.key === "Enter" && Date.now() - (ed._compEnd || 0) < 60) { e.preventDefault(); return; }   // Safari: the confirming Enter after compositionend
      const k = e.key.toLowerCase(), mod = e.metaKey || e.ctrlKey;
      if (mod && k === "z") { e.preventDefault(); undoRedo(ed, !e.shiftKey); return; }
      if (mod && k === "y") { e.preventDefault(); undoRedo(ed, false); return; }
      if (mod && e.shiftKey && k === "x") { e.preventDefault(); tool(ed, "s"); return; }
      if (mod && e.shiftKey && k === "l") { e.preventDefault(); tool(ed, "check"); return; }
      if (mod && ["b", "i", "u"].includes(k)) { e.preventDefault(); tool(ed, k); return; }
      const r = caret(), b = r && blockOf(ed, r.startContainer);
      if (!b) return;
      if (e.key === "Enter") { e.preventDefault(); enter(ed, b, r); }
      else if (e.key === "Backspace") backspace(ed, b, r, e);
      else if (e.key === "Delete") del(ed, b, r, e);
      else if (e.key === "Tab") {
        e.preventDefault();
        if (b.classList.contains("table")) {
          const cells = [...b.querySelectorAll("td,th")], td = (r.startContainer.nodeType === 1 ? r.startContainer : r.startContainer.parentElement).closest("td,th");
          const n = cells[cells.indexOf(td) + (e.shiftKey ? -1 : 1)];
          if (n) place(n, false);
        } else if (b.classList.contains("li")) { push(ed, true); indent(ed, selectedBlocks(ed), e.shiftKey ? -1 : 1); }
        else if (b.classList.contains("raw")) document.execCommand("insertText", false, "\t");
      } else if (e.key === " " && autoformat(ed, b, r)) e.preventDefault();
    });
    ed.addEventListener("mousedown", e => {                 // the checkbox (drawn left of the line) ticks
      const b = blockOf(ed, e.target);
      if (!b || !b.classList.contains("ck") || e.target !== b) return;
      if (e.clientX > b.getBoundingClientRect().left + parseFloat(getComputedStyle(b).paddingLeft)) return;
      e.preventDefault();
      push(ed, true);
      b.classList.toggle("done");
      changed(ed);
    });
    ed.addEventListener("click", e => {                     // ⌘-click a link opens it
      const a = e.target.closest(".atom.wl,.atom.url");
      if (!a || !(e.metaKey || e.ctrlKey)) return;
      e.preventDefault();
      const md = a.dataset.md, w = md.match(/\[\[([^\]|#^]+)/), u = md.match(/\]\((https?:[^)\s]+)/);
      if (w && ed._open) ed._open(w[1].trim());
      else if (u) window.open(u[1], "_blank", "noopener");
    });
    ed.addEventListener("paste", e => {
      const dt = e.clipboardData;
      if (!dt || (dt.files && dt.files.length)) return;     // files: the app saves them as attachments
      const text = dt.getData("text/plain");
      if (!text) return;
      e.preventDefault();
      insertMd(ed, text.replace(/\r\n?/g, "\n"));
    });
    ed.addEventListener("copy", e => {                      // copy whole lines as Markdown
      const bs = selectedBlocks(ed), r = caret();
      if (!r || r.collapsed || bs.length < 2) return;
      e.preventDefault();
      e.clipboardData.setData("text/plain", bs.map(blockMd).join("\n"));
    });
  }
  function undoRedo(ed, undo) {
    const from = undo ? ed._undo : ed._redo, to = undo ? ed._redo : ed._undo;
    if (!from.length) return;
    to.push(snap(ed));
    restore(ed, from.pop());
    ed._last = Date.now();
    if (ed._on) ed._on();
  }

  // ---------- toolbar
  const TOOLS = [["b", "<b>B</b>", "粗體 ⌘B"], ["i", "<i>I</i>", "斜體 ⌘I"], ["u", "<u>U</u>", "底線 ⌘U"], ["s", "<s>S</s>", "刪除線 ⇧⌘X"], null,
    ["ul", "•", "項目清單"], ["dash", "–", "虛線清單"], ["ol", "1.", "編號清單"], ["check", "◯", "核取清單 ⇧⌘L"], null,
    ["table", "▦", "表格（在表格裡按：多一欄）"], ["attach", "📎", "圖片或附件"], null, ["outdent", "⇤", "減少縮排"], ["indent", "⇥", "增加縮排"], null,
    ["props", "屬性", "筆記的屬性：標籤、別名、日期、來源…"]];
  function bar(ed, onAttach) {
    const el = document.createElement("div");
    el.className = "wys-bar";
    el.innerHTML = '<select data-t="style" title="' + esc(T("文字樣式")) + '"><option value="">' + esc(T("樣式")) + '</option><option value="h1">' + esc(T("標題")) +
      '</option><option value="h2">' + esc(T("副標題")) + '</option><option value="h3">' + esc(T("小標題")) + '</option><option value="p">' + esc(T("內文")) + "</option></select>" +
      TOOLS.map(t => !t ? '<span class="sep"></span>' : '<button type="button" data-t="' + t[0] + '" title="' + esc(T(t[2])) + '">' + T(t[1]) + "</button>").join("");
    el.addEventListener("mousedown", e => { if (e.target.closest("button")) e.preventDefault(); });
    el.addEventListener("click", e => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.t === "attach") return onAttach && onAttach();
      tool(ed, b.dataset.t);
    });
    const sel = el.querySelector("select");
    let saved = null;
    sel.addEventListener("mousedown", () => { const r = caret(); saved = r && ed.contains(r.startContainer) ? r.cloneRange() : null; });
    sel.addEventListener("change", () => {
      if (saved) { const s = getSelection(); s.removeAllRanges(); s.addRange(saved); }
      if (sel.value) tool(ed, "style:" + sel.value);
      sel.value = "";
    });
    return el;
  }

  return { mount, attach, value, insertMd, bar, parse };
})();
