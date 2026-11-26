"use strict";
// A note's properties (the frontmatter at the top of the file), shown as a short list of labelled values
// instead of YAML. Tags and aliases are chips; other values are edited in place; what a form can't show
// (nested data, multi-line text) stays as its own text. A property you don't touch is saved exactly as written.
// Needs esc (md.js) and T (i18n.js).

const Props = (() => {
  // friendly names for the common keys; any other key shows as written
  const LABEL = { title: "標題", tags: "標籤", tag: "標籤", aliases: "別名", alias: "別名", created: "建立日期", updated: "更新日期",
    date: "日期", author: "作者", source: "來源", url: "網址", published: "發布日期", description: "說明", summary: "摘要",
    type: "類型", pdf: "PDF", pages: "頁碼", book: "書", ocr: "文字辨識", sources: "參考來源", cssclasses: "樣式",
    status: "狀態", rating: "評分", category: "分類", categories: "分類", ingested: "整理日期", kind: "種類" };
  const LISTY = /^(tags?|aliases|alias|sources|cssclasses|categories|not_aliases)$/;
  const label = k => LABEL[k] ? T(LABEL[k]) : k;

  // ---------- YAML (the plain subset notes use) → properties
  function unq(v) {
    v = v.trim();
    if (/^".*"$/.test(v)) { try { return JSON.parse(v); } catch (e) { return v.slice(1, -1); } }
    if (/^'.*'$/.test(v)) return v.slice(1, -1).replace(/''/g, "'");
    return v.replace(/\s+#.*$/, "");
  }
  function splitInline(v) {                                 // [a, "b, c", 'd'] → items
    const s = v.trim().slice(1, -1), out = [];
    let cur = "", q = "";
    for (const ch of s) {
      if (q) { cur += ch; if (ch === q) q = ""; continue; }
      if (ch === '"' || ch === "'") { q = ch; cur += ch; continue; }
      if (ch === ",") { out.push(cur); cur = ""; continue; }
      cur += ch;
    }
    if (cur.trim() || out.length) out.push(cur);
    return out.map(unq).filter(x => x !== "");
  }
  function parse(yaml) {
    const props = [], L = yaml === "" ? [] : yaml.split("\n");
    let cur = null;
    for (const l of L) {
      const m = l.match(/^([^\s#\-][^:]*?):(?:\s+(.*)|\s*)$/);
      if (m) { cur = { key: m[1], first: m[2] || "", lines: [l], rest: [] }; props.push(cur); continue; }
      if (cur) { cur.lines.push(l); cur.rest.push(l); }
      else props.push({ key: null, lines: [l], kind: "keep" });   // a comment or blank line before any key
    }
    for (const p of props) {
      if (p.kind) continue;
      const v = p.first.trim(), rest = p.rest.filter(x => x.trim() && !/^\s*#/.test(x));
      if (!rest.length && /^\[.*\]$/.test(v)) { p.kind = "list"; p.style = "inline"; p.items = splitInline(v); }
      else if (!v && rest.length && rest.every(x => /^\s*-\s+\S/.test(x) && !/^\s*-\s+[^"'\[]*:\s/.test(x))) {
        p.kind = "list"; p.style = "block"; p.items = rest.map(x => unq(x.replace(/^\s*-\s+/, "")));
        p.ind = (rest[0].match(/^\s*/) || [""])[0];
      } else if (!v && !rest.length) { p.kind = LISTY.test(p.key) ? "list" : "text"; p.style = "inline"; p.items = []; p.value = ""; }
      else if (!rest.length && !/^[|>]/.test(v) && !/^\{/.test(v)) { p.kind = "text"; p.value = unq(v); p.q = /^"/.test(v) ? '"' : /^'/.test(v) ? "'" : ""; }
      else p.kind = "raw";                                  // nested data, multi-line text: shown as written
    }
    return props;
  }

  // ---------- properties → YAML (only what changed is rewritten)
  function quote(v, q) {
    if (q === "'") return "'" + v.replace(/'/g, "''") + "'";
    if (q === '"' || v === "" || /^[\s\-?:,\[\]{}#&*!|>'"%@`]|[\s]$|:\s|\s#|^(true|false|yes|no|null|~)$/i.test(v) || /^\[\[/.test(v)) return JSON.stringify(v);
    return v;
  }
  function lines(p) {
    if (!p.dirty) return p.lines;
    if (p.kind === "raw") return p.lines;
    if (p.kind === "text") return [p.key + ": " + quote(p.value, p.q)].map(x => p.value === "" && !p.q ? p.key + ":" : x);
    if (p.style === "block" && p.items.length) return [p.key + ":"].concat(p.items.map(i => (p.ind || "  ") + "- " + quote(i)));
    return [p.key + ": [" + p.items.map(i => quote(i, /[,\]]/.test(i) ? '"' : "")).join(", ") + "]"];
  }
  function yaml(props) {
    return props.flatMap(lines).join("\n");
  }

  // ---------- the panel
  const isUrl = v => /^https?:\/\/\S+$/.test(v);
  const linkName = v => { const m = String(v).match(/^\[\[([^\]|#^]+)/); return m ? m[1].trim() : null; };
  const shown = v => String(v).replace(/^\[\[([^\]|]+)\|?([^\]]*)\]\]$/, (_, a, b) => b || a);
  function rowHtml(p, i) {
    const key = p.isNew && !p.named ? '<input class="pp-key" placeholder="' + esc(T("名稱")) + '" size="8" value="' + esc(p.key) + '">'
      : '<span class="pp-k" title="' + esc(p.key) + '">' + esc(label(p.key)) + "</span>";
    let val;
    if (p.kind === "list") {
      val = '<span class="pp-v pp-list">' + p.items.map((x, j) => '<span class="pp-chip" title="' + esc(x) + '">' +
        esc(p.key.startsWith("tag") ? "#" + shown(x) : shown(x)) + '<button type="button" class="pp-x" data-rm="' + j + '" title="' + esc(T("移除")) + '">×</button></span>').join("") +
        '<input class="pp-add" placeholder="' + esc(T("新增…")) + '" size="6"></span>';
    } else if (p.kind === "text") {
      const go = isUrl(p.value) || linkName(p.value);
      const lk = /^\[\[[^\]|]+\]\]$/.test(p.value);        // [[Page]]: edited as the name, saved with its brackets
      if (lk) p.link = true;
      const v = lk ? p.value.slice(2, -2) : p.value;
      val = '<span class="pp-v"><input class="pp-in' + (lk ? " pp-wl" : "") + '" value="' + esc(v) + '" size="' + Math.max(4, Math.min(60, [...String(v)].length + 1)) + '">' +
        (go ? '<button type="button" class="pp-go" title="' + esc(T("打開")) + '">↗</button>' : "") + "</span>";
    } else {
      val = '<span class="pp-v"><textarea class="pp-raw" rows="' + Math.min(8, p.lines.length) + '" spellcheck="false">' + esc(p.lines.join("\n")) + "</textarea></span>";
    }
    return '<div class="pp-row" data-i="' + i + '">' + key + val + '<button type="button" class="pp-del" title="' + esc(T("刪除這個屬性")) + '">×</button></div>';
  }
  function render(box) {
    const st = box._pp, n = st.props.filter(p => p.key).length;
    const open = st.open;
    let h = '<div class="pp-head"><button type="button" class="pp-toggle">' + (open ? "▾" : "▸") + " " + esc(T("屬性")) + '</button><span class="pp-sum">' +
      (open ? "" : summary(st.props)) + "</span></div>";
    if (open) {
      if (st.raw) h += '<textarea class="pp-yaml" spellcheck="false" rows="' + Math.min(16, st.props.flatMap(lines).length + 1) + '">' + esc(yaml(st.props)) + "</textarea>";
      else h += st.props.map((p, i) => p.key || p.isNew ? rowHtml(p, i) : "").join("");
      h += '<div class="pp-foot">' + (st.raw ? "" : '<button type="button" class="pp-new">＋ ' + esc(T("新增屬性")) + "</button>") +
        '<button type="button" class="pp-mode">' + esc(st.raw ? T("用表單編輯") : T("編輯原文")) + "</button></div>";
    }
    box.innerHTML = h;
    box.classList.toggle("open", open);
    if (!n && !open) box.querySelector(".pp-sum").textContent = T("沒有屬性");
  }
  function summary(props) {
    const bits = [];
    for (const p of props) {
      if (!p.key || bits.length >= 4) continue;
      if (p.kind === "list" && p.items.length) bits.push(p.items.slice(0, 4).map(x => p.key.startsWith("tag") ? "#" + shown(x) : shown(x)).join(" "));
      else if (p.kind === "text" && p.value && p.value.length < 40) bits.push(label(p.key) + " " + shown(p.value));
    }
    return esc(bits.join(" · "));
  }

  // box: the editor's block; onChange(before) is called before each change (for undo) and after (dirty)
  function mount(box, yamlText, hooks) {
    box._pp = { props: parse(yamlText), open: openPref(), raw: false };
    render(box);
    const st = box._pp;
    const touch = p => { hooks.before(); if (p) p.dirty = true; box._dirty = true; };
    const done = () => hooks.after();
    box.addEventListener("click", e => {
      const row = e.target.closest(".pp-row"), p = row && st.props[+row.dataset.i];
      if (e.target.closest(".pp-toggle")) { st.open = !st.open; openPref(st.open); render(box); return; }
      if (e.target.closest(".pp-head") && !st.open) { st.open = true; openPref(true); render(box); return; }
      if (e.target.closest(".pp-mode")) {
        if (st.raw) { const ta = box.querySelector(".pp-yaml"); if (ta && ta.value !== yaml(st.props)) { touch(); st.props = parse(ta.value).map(x => Object.assign(x, { dirty: true })); done(); } }
        st.raw = !st.raw; render(box); return;
      }
      if (e.target.closest(".pp-new")) {
        touch();
        st.props.push({ key: "", kind: "text", value: "", dirty: true, isNew: true, lines: [] });
        render(box);
        const keys = box.querySelectorAll(".pp-key");
        if (keys.length) keys[keys.length - 1].focus();
        done(); return;
      }
      if (!p) return;
      if (e.target.closest(".pp-del")) { touch(); st.props.splice(+row.dataset.i, 1); render(box); done(); return; }
      const rm = e.target.closest(".pp-x");
      if (rm) { touch(p); p.items.splice(+rm.dataset.rm, 1); render(box); done(); return; }
      if (e.target.closest(".pp-go")) {
        const v = p.value, w = linkName(v);
        if (w && hooks.open) hooks.open(w); else if (isUrl(v)) window.open(v, "_blank", "noopener");
      }
    });
    box.addEventListener("keydown", e => {
      e.stopPropagation();                                  // the inputs' own keys, not the editor's
      if (e.isComposing || e.keyCode === 229) return;
      const row = e.target.closest(".pp-row"), p = row && st.props[+row.dataset.i];
      if (e.key === "Enter" && e.target.classList.contains("pp-add") && p) {
        e.preventDefault();
        const v = e.target.value.trim().replace(/^#/, "");
        if (v && !p.items.includes(v)) { touch(p); p.items.push(v); render(box); done(); box.querySelector('.pp-row[data-i="' + row.dataset.i + '"] .pp-add').focus(); }
        else e.target.value = "";
      } else if (e.key === "Backspace" && e.target.classList.contains("pp-add") && !e.target.value && p && p.items.length) {
        e.preventDefault(); touch(p); p.items.pop(); render(box); done();
        box.querySelector('.pp-row[data-i="' + row.dataset.i + '"] .pp-add').focus();
      } else if ((e.key === "Enter" || e.key === "Tab") && e.target.classList.contains("pp-key") && row && p) {
        e.preventDefault();
        if (!p.key) return;
        p.named = true;                                     // named: tags, aliases… become chips
        if (LISTY.test(p.key) && p.kind === "text") { p.kind = "list"; p.style = "inline"; p.items = p.value ? [p.value] : []; }
        render(box);
        const v = box.querySelector('.pp-row[data-i="' + row.dataset.i + '"] .pp-in, .pp-row[data-i="' + row.dataset.i + '"] .pp-add');
        if (v) v.focus();
      } else if (e.key === "Enter" && e.target.classList.contains("pp-in")) {
        e.preventDefault(); e.target.blur();
      }
    });
    box.addEventListener("input", e => {
      e.stopPropagation();
      const row = e.target.closest(".pp-row"), p = row && st.props[+row.dataset.i];
      if (e.target.classList.contains("pp-add")) return;
      if (!p && !e.target.classList.contains("pp-yaml")) return;
      if (!box._typing) { touch(p); box._typing = true; }
      if (p) p.dirty = true;
      if (e.target.classList.contains("pp-in")) { p.value = p.link && e.target.value.trim() ? "[[" + e.target.value.trim() + "]]" : e.target.value; e.target.size = Math.max(4, Math.min(60, [...e.target.value].length + 1)); }
      else if (e.target.classList.contains("pp-key")) { p.key = e.target.value.trim().replace(/[:\s]+/g, "_"); }
      else if (e.target.classList.contains("pp-raw")) { p.lines = e.target.value.split("\n"); }
      done();
    });
    box.addEventListener("focusout", () => { box._typing = false; });
    ["beforeinput", "paste", "copy", "cut", "mousedown"].forEach(t => box.addEventListener(t, e => e.stopPropagation()));
  }
  // the YAML to save: "" props with no key (an unfinished new row) are left out
  function value(box) {
    const st = box._pp;
    if (st.raw) { const ta = box.querySelector(".pp-yaml"); if (ta) return ta.value; }
    return yaml(st.props.filter(p => p.key || !p.isNew));
  }
  function openPref(v) {
    try { if (v === undefined) return localStorage.getItem("lumen.props-open") !== "0"; localStorage.setItem("lumen.props-open", v ? "1" : "0"); } catch (e) {}
    return true;
  }
  return { mount, value, parse, yaml, label };
})();
