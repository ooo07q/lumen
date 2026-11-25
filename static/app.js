"use strict";
// Three-column notes prototype: tree | note tabs | links & suggestions. Talks to app/server.py.
// md.js (loaded first) renders Markdown and reads window.TREE.

const $ = (s, el = document) => el.querySelector(s);
const TYPE_ZH = { concept: "概念", entity: "人物・實體", source: "來源", analysis: "分析", overview: "總覽" };
const TYPE_ORDER = ["concept", "entity", "source", "analysis", "overview"];
const QUEUE_LABEL = { "ingest": "建議整理", "continue a work": "接著整理（同一本書已開始）", "check": "要先看一下值不值得整理",
  "duplicate?": "可能和別篇重複", "reconvert": "轉檔不完整，要重新轉", "skip (no content)": "沒有內容" };
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
};
const S = {
  tree: null, rawRoot: null, sideTab: store.get("side-tab", "raw"), rawMode: store.get("raw-mode", "tree"), results: null,
  open: new Set(store.get("open-folders", [])), queueOpen: new Set(),
  kbType: store.get("kb-type", "concept"), jevOn: store.get("jev-on", true), pdfTidy: store.get("pdf-tidy", true),
  tabs: [], active: -1, checking: new Set(), panelFor: null, sigs: null,
};
window.TREE = { names: {}, images: {} };

async function api(path, body) {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const j = await r.json().catch(() => ({ error: "bad response" }));
  if (r.status === 401 && j.nokey) showStart("nokey");
  else if (r.status === 409 && j.novault) showStart();
  if (!r.ok) { const e = new Error(j.error || r.status); e.data = j; throw e; }
  return j;
}

let toastTimer;
function toast(msg, action) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  if (action) {
    const b = document.createElement("button"); b.textContent = action.label;
    b.onclick = () => { t.hidden = true; action.fn(); };
    t.append(" ", b);
  }
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), action ? 8000 : 3500);
}

// a small dialog in place of confirm(): resolves true on OK
function dialog(title, html, ok = "確定", danger = false) {
  return new Promise(res => {
    $("#modal-title").textContent = title; $("#modal-body").innerHTML = html;
    const okb = $("#modal-ok"); okb.textContent = ok; okb.classList.toggle("danger", danger);
    $("#modal").hidden = false; okb.focus();
    const done = v => { $("#modal").hidden = true; document.removeEventListener("keydown", key, true); res(v); };
    const key = e => { if (e.key === "Escape") { e.preventDefault(); done(false); } else if (e.key === "Enter") { e.preventDefault(); done(true); } };
    document.addEventListener("keydown", key, true);
    okb.onclick = () => done(true); $("#modal-cancel").onclick = () => done(false);
    $("#modal").onclick = e => { if (e.target.id === "modal") done(false); };
  });
}

const jevUsable = () => S.tree && S.tree.jev && S.jevOn;
const baseName = p => p.split("/").pop().replace(/\.md$/, "");
const tab = () => S.tabs[S.active];

// ============================================================ left column
// Four sections: 日記 (the journal folder), 筆記 (the rest of the human's notes, by folder or as the to-do
// queue), 附件 (the attachment folder), 知識庫 (wiki/, by type). Search results get a fifth tab when used.
// The notes are raw/ in a vault laid out that way (S.tree.notes_root = "raw"), else the whole vault except
// wiki/ (notes_root = "").

const SKIP_DECISIONS = new Set(["reconvert", "skip (no content)"]);
const inJournal = p => S.tree && p.startsWith(S.tree.journal + "/");
const ROOT = () => (S.tree && S.tree.notes_root) || "";
const joinPath = (a, b) => a ? a + "/" + b : b;
const notesRel = p => ROOT() && p.startsWith(ROOT() + "/") ? p.slice(ROOT().length + 1) : p;    // path inside the notes
const unitOf = p => { const r = notesRel(p).split("/"); return r.length === 1 ? p : joinPath(ROOT(), r[0]); };

function buildRawTree(files) {
  const root = { dirs: {}, files: [], total: 0, todo: 0 };
  for (const f of files) {
    if (inJournal(f.path)) continue;                       // the journal has its own section
    const parts = notesRel(f.path).split("/");
    let node = root;
    node.total++; if (!f.done) node.todo++;
    for (const d of parts.slice(0, -1)) {
      node = node.dirs[d] = node.dirs[d] || { dirs: {}, files: [], total: 0, todo: 0 };
      node.total++; if (!f.done) node.todo++;
    }
    node.files.push(f);
  }
  return root;
}

const TRASH_SVG = '<svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.5h5.8l.6-8.5" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>';
// the human's files (movable, deletable): not wiki/ (the AI's), the tools, templates or hidden folders
const mine = p => ROOT() ? p.startsWith(ROOT() + "/") : !/^(wiki|tools|templates)\//.test(p) && !/(^|\/)\./.test(p);
function rowFile(path, label, extra = "", pre = "") {
  const t = tab();
  const on = t && (t.path === path);
  const own = mine(path) && !S.tree.read_only;
  return '<div class="row' + (on ? " active" : "") + '" data-path="' + esc(path) + '"' + (own ? ' draggable="true"' : "") + '><span class="caret">' + pre + '</span><span class="name">' + esc(label) + "</span>" + extra +
    (own ? '<button class="row-del" data-del="' + esc(path) + '" title="刪除（移到垃圾桶，可復原）">' + TRASH_SVG + "</button>" : "") + "</div>";
}
// The one to-do marker, used everywhere a raw note is listed: orange = waiting to be organised,
// grey = Jev found nothing to organise (empty or broken conversion).
function dot(f) {
  if (f.done) return "";
  const skip = SKIP_DECISIONS.has(f.d);
  return '<span class="new' + (skip ? " skip" : "") + '" title="' + (skip ? "不用整理：" + esc(QUEUE_LABEL[f.d]) : "待整理" + (f.d ? "：Jev 建議「" + esc(QUEUE_LABEL[f.d] || f.d) + "」" : "")) + '"></span>';
}

function renderRawNode(node, prefix, filter) {
  let html = "";
  for (const d of Object.keys(node.dirs).sort((a, b) => a.localeCompare(b))) {
    const key = joinPath(prefix, d), child = node.dirs[d];
    const inner = filter ? renderRawNode(child, key, filter) : "";
    if (filter && !inner && !d.toLowerCase().includes(filter)) continue;
    const open = S.open.has(key) || (filter && inner);
    html += '<div class="folder"><div class="row" data-folder="' + esc(key) + '"><span class="caret">' + (open ? "▾" : "▸") + '</span><span class="name">' + esc(d) +
      '</span><span class="count" title="' + (child.todo ? child.todo + " 篇待整理，共 " : "共 ") + child.total + ' 篇">' + (child.todo ? '<span class="new"></span>' + child.todo + " / " : "") + child.total + "</span></div>" +
      (open ? '<div class="kids">' + (inner || renderRawNode(child, key, "")) + "</div>" : "") + "</div>";
  }
  for (const f of node.files) {
    const name = baseName(f.path);
    if (filter && !name.toLowerCase().includes(filter)) continue;
    html += rowFile(f.path, name, dot(f));
  }
  return html;
}

function renderSub() {
  const el = $("#sub");
  if (S.sideTab === "wiki") {
    const counts = {};
    for (const p of S.tree.pages) counts[p.type] = (counts[p.type] || 0) + 1;
    el.innerHTML = TYPE_ORDER.filter(t => counts[t]).map(t =>
      '<button data-type="' + t + '" class="' + (S.kbType === t ? "on" : "") + '">' + TYPE_ZH[t] + ' <span>' + counts[t] + "</span></button>").join("") +
      '<button data-type="all" class="' + (S.kbType === "all" ? "on" : "") + '">全部</button>';
  } else if (S.sideTab === "raw") {
    const todo = S.tree.raw.filter(f => !f.done && !inJournal(f.path) && !SKIP_DECISIONS.has(f.d)).length;
    el.innerHTML = '<div class="seg"><button data-mode="tree" class="' + (S.rawMode === "tree" ? "on" : "") + '">資料夾</button>' +
      '<button data-mode="todo" class="' + (S.rawMode === "todo" ? "on" : "") + '"><span class="new"></span>待整理 <span>' + todo + "</span></button></div>";
  } else { el.hidden = true; return; }
  el.hidden = false;
}

function renderTree() {
  const el = $("#tree"), filter = $("#filter").value.trim().toLowerCase();
  document.querySelectorAll(".tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === S.sideTab));
  $("#filter").placeholder = { journal: "篩選日期", raw: "篩選筆記", assets: "篩選附件", wiki: "篩選頁名", results: "篩選" }[S.sideTab];
  renderSub();
  if (S.sideTab === "journal") renderJournal(el, filter);
  else if (S.sideTab === "raw" && S.rawMode === "todo") renderQueue(el, filter);
  else if (S.sideTab === "raw") {
    const notes = S.tree.raw.filter(f => !inJournal(f.path));
    el.innerHTML = '<div class="hint">' + notes.length + " 篇筆記，" + notes.filter(f => f.done).length + ' 篇已整理進知識庫。<span class="new"></span> 待整理。</div>' + renderRawNode(S.rawRoot, ROOT(), filter);
  } else if (S.sideTab === "assets") renderAssets(el, filter);
  else if (S.sideTab === "wiki") {
    const types = S.kbType === "all" ? TYPE_ORDER : [S.kbType];
    let html = "";
    for (const t of types) {
      const ps = S.tree.pages.filter(p => p.type === t && (!filter || p.title.toLowerCase().includes(filter)));
      if (!ps.length) continue;
      if (types.length > 1) html += '<div class="group sticky">' + TYPE_ZH[t] + " · " + ps.length + "</div>";
      html += ps.map(p => rowFile(p.path, p.title)).join("");
    }
    el.innerHTML = html || '<div class="hint">沒有符合的頁面。</div>';
  } else if (S.sideTab === "results") renderResults(el);
}

// ---------- 日記

const WEEK = ["日", "一", "二", "三", "四", "五", "六"];
function renderJournal(el, filter) {
  const js = S.tree.raw.filter(f => inJournal(f.path)).map(f => ({ ...f, name: baseName(f.path) }))
    .filter(f => !filter || f.name.toLowerCase().includes(filter)).sort((a, b) => b.name.localeCompare(a.name));
  let html = '<div class="hint">' + js.length + " 篇，在 <code>" + esc(S.tree.journal) + "/</code>。日記只留在本機，不送 Jev。</div>";
  if (!js.length) html += '<div class="hint">還沒有日記。按上面的「＋ 今天的日記」開始寫。</div>';
  let month = null;
  for (const f of js) {
    const m = f.name.match(/^(\d{4})-(\d{2})-(\d{2})/);
    const mk = m ? m[1] + " 年 " + (+m[2]) + " 月" : "其他";
    if (mk !== month) { html += '<div class="group">' + mk + "</div>"; month = mk; }
    const label = m ? (+m[3]) + " 日　星期" + WEEK[new Date(+m[1], +m[2] - 1, +m[3]).getDay()] : f.name;
    html += rowFile(f.path, label + (m && f.name.length > 10 ? " " + f.name.slice(10) : ""));
  }
  el.innerHTML = html;
}

// ---------- 筆記 › 待整理 (triage order; the same notes the orange dots mark)

let queueData = null;
async function renderQueue(el, filter) {
  if (!queueData) {
    el.innerHTML = '<div class="hint"><span class="spin"></span> 讀取中…</div>';
    try { queueData = await api("/api/queue"); } catch (e) { el.innerHTML = '<div class="hint">' + esc(e.message) + "</div>"; return; }
    if (S.sideTab !== "raw" || S.rawMode !== "todo") return;
  }
  const q = queueData, judged = new Set(q.units.map(u => u.unit));
  // notes and books waiting that triage hasn't ranked yet
  const unranked = new Map();
  for (const f of S.tree.raw) {
    if (f.done || inJournal(f.path)) continue;
    const unit = unitOf(f.path);
    if (!judged.has(unit)) unranked.set(unit, (unranked.get(unit) || 0) + 1);
  }
  const units = [...q.units, ...[...unranked].map(([unit, files]) => ({ unit, files, decision: "unranked" }))];
  let html = '<div class="hint">左邊有 <span class="new"></span> 的筆記都在這裡，依 Jev 建議的順序排。整理（寫成來源頁、更新概念頁）要 agent 來做。</div>';
  let last = null;
  for (const u of units.filter(u => !filter || u.unit.toLowerCase().includes(filter))) {
    if (u.decision !== last) { html += '<div class="group">' + esc(u.decision === "unranked" ? "還沒排順序（下次 triage 會排）" : QUEUE_LABEL[u.decision] || u.decision) + "</div>"; last = u.decision; }
    const name = notesRel(u.unit).replace(/\.md$/, "");
    const pr = u.priority != null ? "P" + u.priority : "";
    if (/\.md$/.test(u.unit)) { html += rowFile(u.unit, name, '<span class="count">' + pr + "</span>", u.decision === "unranked" ? "" : ""); continue; }
    const open = S.queueOpen.has(u.unit);
    html += '<div class="folder"><div class="row" data-queue-folder="' + esc(u.unit) + '"><span class="caret">' + (open ? "▾" : "▸") + '</span><span class="name">' + esc(name) +
      '</span><span class="count">' + u.files + " 篇" + (pr ? " · " + pr : "") + "</span></div>";
    if (open) html += '<div class="kids">' + S.tree.raw.filter(f => f.path.startsWith(u.unit + "/")).map(f => rowFile(f.path, f.path.slice(u.unit.length + 1).replace(/\.md$/, ""), dot(f))).join("") + "</div>";
    html += "</div>";
  }
  el.innerHTML = html;
}

// ---------- 附件

let assetsData = null;
const FILE_KIND = [[/\.(png|jpe?g|gif|webp|svg|avif|bmp)$/i, "圖片", "🖼"], [/\.pdf$/i, "PDF", "📄"], [/\.(mp3|m4a|wav|ogg)$/i, "音訊", "🎵"],
  [/\.(mp4|mov|webm)$/i, "影片", "🎬"], [/\.html?$/i, "網頁", "🌐"], [/\.(txt|csv|tsv|json|js|css|py|xml|ya?ml|tex|bib|log)$/i, "文字", "📃"]];
const fileKind = p => (FILE_KIND.find(([rx]) => rx.test(p)) || [null, "檔案", "📎"]).slice(1);
const fmtSize = n => n < 1024 ? n + " B" : n < 1048576 ? (n / 1024).toFixed(0) + " KB" : (n / 1048576).toFixed(1) + " MB";

async function loadAssets(force) {
  if (!assetsData || force) assetsData = await api("/api/attachments");
  return assetsData;
}

async function renderAssets(el, filter) {
  if (!assetsData) {
    el.innerHTML = '<div class="hint"><span class="spin"></span> 讀取中…</div>';
    try { await loadAssets(); } catch (e) { el.innerHTML = '<div class="hint">' + esc(e.message) + "</div>"; return; }
    if (S.sideTab !== "assets") return;
  }
  const fs = assetsData.files.filter(f => !filter || f.path.toLowerCase().includes(filter));
  let html = '<div class="hint">' + assetsData.files.length + " 個檔案，在 <code>" + esc(assetsData.dir) + "/</code>。把檔案拖進筆記或在編輯時貼上，會自動存到這裡並連結到那篇筆記。</div>";
  if (!assetsData.files.length) html += '<div class="hint">還沒有附件。' + (S.tree.vault ? "" : "") + "</div>";
  let folder = null;
  for (const f of fs) {
    const inside = f.path.startsWith(assetsData.dir + "/");     // or next to a note, as Obsidian allows
    const sub = inside ? f.path.slice(assetsData.dir.length + 1).split("/").slice(0, -1).join(" / ")
      : "筆記資料夾裡：" + (dirOf(notesRel(f.path)).split("/").join(" / ") || "最上層");
    if (sub !== folder) {
      if (sub || folder !== null) html += '<div class="group" data-dir="' + esc(inside ? assetsData.dir + (sub ? "/" + sub.split(" / ").join("/") : "") : dirOf(f.path)) + '">' + esc(sub || "（最上層）") + "</div>";
      folder = sub;
    }
    const [, icon] = fileKind(f.path);
    html += rowFile(f.path, f.path.split("/").pop(), '<span class="count">' + (f.used_by.length ? "" : '<span class="unused">沒有筆記用到</span> ') + fmtSize(f.size) + "</span>", icon);
  }
  el.innerHTML = html;
}

$("#tree").addEventListener("click", e => {
  const del = e.target.closest("[data-del]");
  if (del) { e.stopPropagation(); deleteFile(del.dataset.del); return; }
  const row = e.target.closest(".row");
  if (!row) return;
  if (row.dataset.folder) {
    const k = row.dataset.folder;
    S.open.has(k) ? S.open.delete(k) : S.open.add(k);
    store.set("open-folders", [...S.open]); renderTree(); return;
  }
  if (row.dataset.queueFolder) {
    const k = row.dataset.queueFolder;
    S.queueOpen.has(k) ? S.queueOpen.delete(k) : S.queueOpen.add(k);
    renderTree(); return;
  }
  if (row.dataset.path) openAny(row.dataset.path, { newTab: e.metaKey || e.ctrlKey });
});
$("#tree").addEventListener("auxclick", e => {
  const row = e.target.closest(".row[data-path]");
  if (row && e.button === 1) { e.preventDefault(); openAny(row.dataset.path, { newTab: true, background: true }); }
});
document.querySelectorAll(".tabs button").forEach(b => b.addEventListener("click", () => {
  S.sideTab = b.dataset.tab; if (S.sideTab !== "results") store.set("side-tab", S.sideTab);
  $("#filter").value = ""; renderTree(); $("#tree").scrollTop = 0;
}));
$("#sub").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.type) { S.kbType = b.dataset.type; store.set("kb-type", S.kbType); }
  if (b.dataset.mode) { S.rawMode = b.dataset.mode; store.set("raw-mode", S.rawMode); }
  renderTree(); $("#tree").scrollTop = 0;
});
let filterTimer;
$("#filter").addEventListener("input", () => { clearTimeout(filterTimer); filterTimer = setTimeout(renderTree, 150); });

$("#journal-btn").onclick = async () => {
  try {
    const r = await api("/api/journal", {});
    await refreshTree();
    S.sideTab = "journal"; store.set("side-tab", "journal"); renderTree();
    await openNote(r.path, { edit: true });
    toast(r.created ? "建立了今天的日記。日記不送 Jev。" : "打開今天的日記。");
  } catch (e) { toast("沒辦法建立日記：" + e.message); }
};

// ---------- moving, importing and deleting files (raw/ only; wiki pages belong to the AI)

const sectionRoot = () => ({ journal: S.tree.journal, assets: S.tree.assets }[S.sideTab] ?? ROOT());
const dirOf = p => p.split("/").slice(0, -1).join("/");
function dropDir(target) {
  const f = target.closest("[data-folder]"); if (f) return f.dataset.folder;
  const d = target.closest("[data-dir]"); if (d) return d.dataset.dir;
  const r = target.closest(".row[data-path]"); if (r && mine(r.dataset.path)) return dirOf(r.dataset.path);
  return sectionRoot();
}
const tree = $("#tree");
let dragPath = null;
tree.addEventListener("dragstart", e => {
  const r = e.target.closest(".row[data-path][draggable]");
  if (!r) return;
  dragPath = r.dataset.path;
  e.dataTransfer.effectAllowed = "move";
  e.dataTransfer.setData("application/x-vault-path", dragPath);
  e.dataTransfer.setData("text/plain", "[[" + baseName(dragPath) + "]]");   // dropped into the editor: a link
});
tree.addEventListener("dragend", () => { dragPath = null; clearDrop(); });
const clearDrop = () => document.querySelectorAll(".drop-target").forEach(x => x.classList.remove("drop-target"));
tree.addEventListener("dragover", e => {
  const files = [...e.dataTransfer.types].includes("Files");
  if ((!dragPath && !files) || S.sideTab === "wiki" || S.sideTab === "results" || S.tree.read_only) return;
  e.preventDefault();
  e.dataTransfer.dropEffect = dragPath ? "move" : "copy";
  clearDrop();
  (e.target.closest("[data-folder]") || e.target.closest("[data-dir]") || tree).classList.add("drop-target");
});
tree.addEventListener("dragleave", e => { if (e.target === tree) clearDrop(); });
tree.addEventListener("drop", async e => {
  if (S.sideTab === "wiki" || S.sideTab === "results") return;
  e.preventDefault(); clearDrop();
  const dir = dropDir(e.target);
  if (dragPath) { const p = dragPath; dragPath = null; return moveFile(p, dir); }
  const files = [...e.dataTransfer.files];
  if (files.length) importFiles(files, dir);
});

async function moveFile(path, dir) {
  if (dirOf(path) === dir) return;
  const f = S.tree.raw.find(x => x.path === path);
  if (f && f.done && !(await dialog("搬移已整理的筆記？", "<p>「" + esc(baseName(path)) + "」已經整理成知識庫的來源頁，來源頁用路徑記住它（<code>source_path</code>）。</p><p>搬到「" + esc(dir) +
    "」之後，這篇會暫時顯示成待整理，直到 agent 更新來源頁。連到它的 <code>[[連結]]</code> 用檔名，不受影響。</p>", "搬移"))) return;
  try {
    const r = await api("/api/move", { path, dir });
    for (const t of S.tabs) if (t.path === path) { t.path = r.path; }
    if (tab() && tab().path === r.path) history.replaceState(Object.assign({}, history.state, { path: r.path }), "", "#" + encodeURIComponent(r.path));
    if (dir && dir !== ROOT() && S.sideTab === "raw") S.open.add(dir);
    await refreshTree();
    toast("搬到 " + (notesRel(dir) && dir !== ROOT() ? notesRel(dir) + "/" : "筆記最上層"), { label: "復原", fn: () => moveFile(r.path, dirOf(path)) });
  } catch (e) { toast("沒搬成：" + e.message); }
}

async function importFiles(files, dir) {
  let notes = 0, atts = 0, last = null;
  for (const f of files) {
    if (f.size > 200 * 1048576) { toast("「" + f.name + "」超過 200MB"); continue; }
    try {
      const r = await api("/api/import", { name: f.name, dir, data: await fileToBase64(f) });
      r.note ? notes++ : atts++; last = r.path;
    } catch (e) { toast("「" + f.name + "」沒匯入：" + e.message); }
  }
  if (!last) return;
  await refreshTree();
  toast("匯入 " + (notes ? notes + " 篇筆記" : "") + (notes && atts ? "、" : "") + (atts ? atts + " 個附件" : "") + "。");
  if (files.length === 1) openNote(last);
}

async function deleteFile(path) {
  if (!mine(path)) { toast("知識庫的頁是 AI 維護的，不能從這裡刪。"); return; }
  let warn = [];
  try { warn = (await api("/api/delete", { path, dry: true })).warnings; } catch (e) {}
  const name = path.split("/").pop();
  let body = "<p>會移到筆記庫的 <code>.trash/</code>（Obsidian 的垃圾桶），之後可以復原。</p>";
  if (warn.includes("processed")) body += "<p>這篇已經整理成知識庫的來源頁。刪掉後來源頁和概念頁都還在，只是連不回原文。</p>";
  const used = warn.find(w => w.startsWith("used:"));
  if (used) body += "<p>有 " + used.slice(5) + " 篇筆記用到這個附件，刪掉後那些地方會顯示找不到。</p>";
  const t = S.tabs.find(x => x.path === path);
  if (t && t.dirty) body += "<p>這篇還有沒儲存的修改，會一起丟掉。</p>";
  if (!(await dialog("刪除「" + name + "」？", body, "刪除", true))) return;
  try {
    const r = await api("/api/delete", { path });
    for (let i = S.tabs.length - 1; i >= 0; i--) if (S.tabs[i].path === path) { S.tabs[i].dirty = false; closeTab(i); }
    await refreshTree();
    toast("已刪除「" + name + "」。", { label: "復原", fn: async () => {
      try { await api("/api/restore", { trash: r.trash, path: r.path }); await refreshTree(); toast("已復原。"); }
      catch (e) { toast("沒辦法復原：" + e.message); }
    } });
  } catch (e) { toast("沒刪成：" + e.message); }
}

async function htmlToNote(path, btn) {
  if (btn) { btn.disabled = true; btn.textContent = "轉換中…"; }
  try {
    const r = await api("/api/html2note", { path });
    await refreshTree(); await loadAssets(true);
    if (tab() && tab().path === path) renderView();
    await openNote(r.path, { newTab: true });
    toast(r.existing ? "這個網頁之前已經轉成筆記了，打開那一篇。" : "轉成筆記了，在筆記最上層。可以拖到別的資料夾。");
  } catch (e) { toast("沒轉成：" + e.message); if (btn) { btn.disabled = false; btn.textContent = "轉成筆記"; } }
}

// right-click menu on files and tabs
function showMenu(x, y, items) {
  const m = $("#menu");
  m.innerHTML = items.map((it, i) => it ? '<button data-i="' + i + '"' + (it.danger ? ' class="danger"' : "") + ">" + esc(it.label) + "</button>" : "<hr>").join("");
  m.hidden = false;
  const r = m.getBoundingClientRect();
  m.style.left = Math.min(x, innerWidth - r.width - 8) + "px"; m.style.top = Math.min(y, innerHeight - r.height - 8) + "px";
  m.onclick = e => { const b = e.target.closest("button"); if (b) { m.hidden = true; items[+b.dataset.i].fn(); } };
}
document.addEventListener("mousedown", e => { if (!e.target.closest("#menu")) $("#menu").hidden = true; });
document.addEventListener("scroll", () => ($("#menu").hidden = true), true);
tree.addEventListener("contextmenu", e => {
  const f = e.target.closest(".row[data-folder]");
  if (f && !S.tree.read_only) {
    e.preventDefault();
    showMenu(e.clientX, e.clientY, [{ label: "在這裡新增筆記", fn: () => newNote(f.dataset.folder) }]);
    return;
  }
  const r = e.target.closest(".row[data-path]");
  if (!r) return;
  e.preventDefault();
  const p = r.dataset.path, items = [{ label: "打開", fn: () => openNote(p) }, { label: "在新分頁打開", fn: () => openNote(p, { newTab: true }) }];
  if (/\.html?$/i.test(p) && mine(p) && !S.tree.read_only) items.push({ label: "轉成筆記", fn: () => htmlToNote(p) });
  if (mine(p) && !S.tree.read_only) {
    items.push(null, { label: "改名…", fn: () => renameFile(p) });
    if (/\.md$/.test(p)) items.push({ label: "版本紀錄…", fn: () => showHistory(p) });
    items.push({ label: "刪除…", danger: true, fn: () => deleteFile(p) });
  }
  showMenu(e.clientX, e.clientY, items);
});

// ============================================================ tabs

function renderTabbar() {
  const bar = $("#tabbar");
  bar.hidden = S.tabs.length === 0;
  bar.innerHTML = S.tabs.map((t, i) => '<div class="tab' + (i === S.active ? " on" : "") + '" draggable="true" data-i="' + i + '" title="' + esc(t.path || "") + '">' +
    (t.kind === "compare" ? '<span class="tab-kind">比較</span>' : t.kind === "file" ? '<span class="tab-kind file">' + fileKind(t.path)[1] + "</span>" : "") + '<span class="tab-title">' + esc(t.title) + "</span>" +
    (t.dirty ? '<span class="tab-dirty" title="還沒儲存">●</span>' : "") + '<button class="tab-x" data-close="' + i + '" title="關閉">×</button></div>').join("");
}

$("#tabbar").addEventListener("click", e => {
  const x = e.target.closest("[data-close]");
  if (x) { closeTab(+x.dataset.close); return; }
  const t = e.target.closest(".tab");
  if (t) activate(+t.dataset.i);
});
$("#tabbar").addEventListener("auxclick", e => {
  const t = e.target.closest(".tab");
  if (t && e.button === 1) closeTab(+t.dataset.i);
});
$("#tabbar").addEventListener("contextmenu", e => {
  const el = e.target.closest(".tab");
  if (!el) return;
  e.preventDefault();
  const i = +el.dataset.i, t = S.tabs[i];
  showMenu(e.clientX, e.clientY, [{ label: "關閉", fn: () => closeTab(S.tabs.indexOf(t)) },
    { label: "關閉其他分頁", fn: () => { for (let j = S.tabs.length - 1; j >= 0; j--) if (S.tabs[j] !== t && !S.tabs[j].dirty) closeTab(j); } },
    { label: "關閉右邊的分頁", fn: () => { for (let j = S.tabs.length - 1; j > S.tabs.indexOf(t); j--) if (!S.tabs[j].dirty) closeTab(j); } }]);
});
// drag a tab to reorder; the active tab stays active wherever it goes
let dragTab = null;
$("#tabbar").addEventListener("dragstart", e => {
  const t = e.target.closest(".tab");
  if (!t) return;
  dragTab = +t.dataset.i;
  e.dataTransfer.effectAllowed = "move";
  e.dataTransfer.setData("application/x-note-tab", String(dragTab));
  t.classList.add("dragging");
});
$("#tabbar").addEventListener("dragover", e => {
  if (dragTab == null) return;
  e.preventDefault();
  const t = e.target.closest(".tab");
  $("#tabbar").querySelectorAll(".tab").forEach(x => x.classList.remove("drop-before", "drop-after"));
  if (!t || +t.dataset.i === dragTab) return;
  const r = t.getBoundingClientRect();
  t.classList.add(e.clientX < r.left + r.width / 2 ? "drop-before" : "drop-after");
});
$("#tabbar").addEventListener("drop", e => {
  if (dragTab == null) return;
  e.preventDefault();
  const t = e.target.closest(".tab");
  let to = S.tabs.length;
  if (t) { const r = t.getBoundingClientRect(); to = +t.dataset.i + (e.clientX < r.left + r.width / 2 ? 0 : 1); }
  const cur = tab(), [moved] = S.tabs.splice(dragTab, 1);
  if (to > dragTab) to--;
  S.tabs.splice(to, 0, moved);
  S.active = S.tabs.indexOf(cur);
  dragTab = null; renderTabbar();
});
$("#tabbar").addEventListener("dragend", () => { dragTab = null; renderTabbar(); });

function stash() {
  const t = tab();
  if (!t) return;
  t.scroll = $(".center").scrollTop;
  const ed = $("#editor");
  if (t.editing && ed) t.editText = ed.value;
}

// ---------- back / forward
// Every note or tab you go to is a browser history entry {i, tab, path}, so the browser's back and
// forward buttons, ⌘[ ⌘], the mouse's side buttons and the ← → buttons in the header all work.
const NAV = { i: 0, max: 0, restoring: false };
try { NAV.max = +sessionStorage.getItem("nav-max") || 0; } catch (e) {}
function navRecord() {
  const t = tab();
  if (NAV.restoring || !t) return;
  const st = { i: NAV.i, tab: t.id, path: t.path || null };
  const cur = history.state, url = t.path ? "#" + encodeURIComponent(t.path) : location.pathname;
  if (!cur || cur.tab == null) history.replaceState(st, "", url);                // first page: no empty entry before it
  else if (cur.tab !== st.tab || cur.path !== st.path) {
    st.i = ++NAV.i; NAV.max = NAV.i;
    history.pushState(st, "", url);
  }
  try { sessionStorage.setItem("nav-max", NAV.max); } catch (e) {}
  renderNav();
}
function renderNav() {
  $("#nav-back").disabled = NAV.i <= 0;
  $("#nav-fwd").disabled = NAV.i >= NAV.max;
}
window.addEventListener("popstate", async e => {
  const st = e.state;
  if (!st) return;
  NAV.i = st.i || 0; NAV.restoring = true;
  try {
    const i = S.tabs.findIndex(t => t.id === st.tab);
    if (i >= 0) {
      if (i !== S.active) activate(i, false);
      if (st.path && S.tabs[i].path !== st.path) await openNote(st.path);   // that tab went on to another note
    } else if (st.path) await openNote(st.path);                           // the tab was closed since
  } finally { NAV.restoring = false; renderNav(); }
});
$("#nav-back").onclick = () => history.back();
$("#nav-fwd").onclick = () => history.forward();

function activate(i, push = true) {
  if (i === S.active && $("#view").dataset.tab === String(tab() && tab().id)) return;
  stash();
  S.active = i;
  const t = tab();
  renderTabbar(); renderView(); renderTree(); loadPanel();
  if (push) navRecord();
}

function closeTab(i) {
  const t = S.tabs[i];
  if (t.dirty && !confirm("「" + t.title + "」還沒儲存，確定關閉？")) return;
  stash();
  S.tabs.splice(i, 1);
  if (S.active >= S.tabs.length) S.active = S.tabs.length - 1;
  else if (i < S.active) S.active--;
  renderTabbar(); renderView(); renderTree(); loadPanel();
  const n = tab();                                   // closing isn't a step back: just fix the address
  history.replaceState(Object.assign({}, history.state, n ? { tab: n.id, path: n.path || null } : { tab: null, path: null }), "",
    n && n.path ? "#" + encodeURIComponent(n.path) : location.pathname);
}

let tabSeq = 0;
const openAny = (path, opt) => openNote(path, opt);
async function openNote(path, opt = {}) {
  const kind = /\.md$/i.test(path) ? "note" : "file";
  const existing = S.tabs.findIndex(t => t.kind === kind && t.path === path);
  if (existing >= 0) { if (!opt.background) activate(existing); if (opt.edit) startEdit(); return; }
  const t = { id: ++tabSeq, kind, path, title: kind === "note" ? baseName(path) : path.split("/").pop(), note: null, loading: kind === "note" };
  const cur = tab();
  if (opt.newTab || !cur || cur.dirty || cur.editing || cur.kind !== "note") {
    S.tabs.push(t);
    if (!opt.background) { stash(); S.active = S.tabs.length - 1; }
  } else { stash(); t.id = cur.id; S.tabs[S.active] = t; }       // same tab, new note: keeps its id for back/forward
  renderTabbar();
  if (!opt.background) { navRecord(); renderView(); renderTree(); }
  if (kind === "file") { if (!opt.background) loadPanel(); return; }
  try { t.note = await api("/api/note?path=" + encodeURIComponent(path)); }
  catch (e) { t.error = e.message; }
  t.loading = false;
  if (t.note) t.title = t.note.page ? t.note.page.title : (splitFrontmatter(t.note.text).fm.title || baseName(path));
  renderTabbar();
  if (tab() === t) { renderView(); loadPanel(); if (opt.edit) startEdit(); }
}

function openCompare(s) {
  stash();
  const key = "compare:" + s.key;
  const i = S.tabs.findIndex(t => t.id === key);
  if (i >= 0) { activate(i); return; }
  const t = { id: key, kind: "compare", title: s.topic.title + "：兩種說法", s, notes: [null, null] };
  S.tabs.push(t); S.active = S.tabs.length - 1; navRecord();
  renderTabbar(); renderView(); loadPanel();
  Promise.all([s.a.path, s.b.path].map(p => api("/api/note?path=" + encodeURIComponent(p)).catch(e => ({ error: e.message })))).then(ns => {
    t.notes = ns;
    if (tab() === t) renderView();
  });
}

// ============================================================ center

const RENDER_MAX = 250000;

function headHtml(n, t) {
  const { fm } = splitFrontmatter(n.text);
  const title = n.page ? n.page.title : (fm.title || baseName(n.path));
  const renamable = n.editable;           // your own note: click the title to rename (file name, and `title:` if it has one)
  const chips = [];
  if (n.page) {
    chips.push('<span class="chip ai">AI 整理 · ' + esc(TYPE_ZH[n.page.type] || n.page.type) + "</span>");
    if (n.page.updated) chips.push("更新 " + esc(n.page.updated));
    if (n.page.aliases.length) chips.push("又名 " + n.page.aliases.slice(0, 6).map(esc).join("、"));
  } else {
    chips.push('<span class="chip">你的筆記</span>');
    if (fm.author) chips.push(esc(fm.author.replace(/[\[\]"]/g, "")));
    if (fm.source && /^https?:/.test(fm.source)) chips.push('<a href="' + esc(fm.source) + '" target="_blank" rel="noopener">原文</a>');
    if (fm.pdf) {
      const rel = attachmentRel(fm.pdf.replace(/^\[\[|\]\]$/g, ""));
      if (rel) chips.push(attLink(rel, "原始 PDF"));
      chips.push('<button class="link-btn" data-act="pdf-layout" title="PDF 轉出來的筆記常有斷行、頁首頁尾和圖中文字。整理只影響顯示，檔案不變。">' + (S.pdfTidy ? "顯示原始排版" : "整理排版") + "</button>");
    }
    if (n.private) chips.push('<span class="chip todo">日記：不送 Jev</span>');
  }
  chips.push('<span title="' + esc(n.path) + '">' + esc(n.path.split("/").slice(0, -1).join(" / ")) + "</span>");
  return (renamable ? '<h1 class="renamable" data-act="rename" title="點一下改名">' : "<h1>") + esc(title) + '</h1><div class="meta">' + chips.join("<span>·</span>") + "</div>" +
    (n.page && n.page.summary ? '<p class="summary">' + esc(n.page.summary) + "</p>" : "");
}

function bodyHtml(n, full) {
  let { body } = splitFrontmatter(n.text);
  const h1 = body.match(/^\s*# +(.+)\n/);
  if (h1 && n.page && h1[1].trim() === n.page.title) body = body.slice(h1[0].length);
  if (S.pdfTidy && /^---\n[\s\S]*?\npdf:/.test(n.text)) body = tidyPdf(body);
  if (!full && body.length > RENDER_MAX) return md(body.slice(0, RENDER_MAX)) + '<div class="truncated">這篇很長，先顯示前 ' + Math.round(RENDER_MAX / 1000) + 'k 字元。<button data-show-all>全部顯示</button></div>';
  return md(body);
}

function renderView() {
  const v = $("#view"), t = tab();
  v.dataset.tab = t ? String(t.id) : "";
  if (!t) {
    v.innerHTML = '<div class="empty"><h2>從左邊打開一篇筆記</h2><p class="muted">⌘／Ctrl＋點擊在新分頁打開。</p></div>';
    $("#panel").innerHTML = '<div class="panel-empty muted">打開筆記後，這裡會出現連結和建議。</div>';
    return;
  }
  if (t.kind === "compare") return renderCompare(v, t);
  if (t.kind === "file") return renderFile(v, t);
  if (t.loading) { v.innerHTML = '<p class="muted pad"><span class="spin"></span></p>'; return; }
  if (t.error) { v.innerHTML = '<p class="muted pad">' + esc(t.error) + "</p>"; return; }
  const n = t.note;
  let tools = "";
  if (n.editable) tools = '<div class="note-tools">' + '<button data-act="history" class="ghost" title="這篇以前的版本，可以還原">版本</button>' +
    '<button data-act="delete" class="ghost" title="移到垃圾桶，可復原">' + TRASH_SVG + " 刪除</button>" + (t.editing ? '<button data-act="preview">預覽</button><button data-act="save" class="primary">儲存</button><button data-act="revert">放棄修改</button>' :
    '<button data-act="edit">編輯</button>' + (t.dirty ? '<button data-act="save" class="primary">儲存</button><button data-act="revert">放棄修改</button>' : "")) + '<span class="muted save-msg">' + esc(t.msg || (t.editing ? "⌘S 儲存 · 拖進或貼上檔案會存成附件" : "")) + "</span></div>";
  if (t.external) tools += '<div class="banner">這篇在別處被改過。<button data-act="reload">載入新版本</button>（你這裡的修改會不見）</div>';
  v.innerHTML = '<div class="note-head">' + headHtml(n, t) + "</div>" + tools +
    (t.editing ? '<textarea id="editor" class="editor" spellcheck="false"></textarea>' : '<article id="note" class="note">' + bodyHtml(n, t.full) + "</article>");
  if (t.editing) {
    const ed = $("#editor");
    ed.value = t.editText ?? n.text;
    ed.addEventListener("input", () => { t.editText = ed.value; if (!t.dirty) { t.dirty = true; renderTabbar(); } });
  }
  $(".center").scrollTop = t.scroll || 0;
  if (t.renameNow) { t.renameNow = false; startTitleRename(t); }
  updateAICtx();
}

function renderCompare(v, t) {
  const s = t.s;
  const col = (n, side, card) => {
    if (!n) return '<div class="cmp-col"><p class="muted"><span class="spin"></span></p></div>';
    if (n.error) return '<div class="cmp-col"><p class="muted">' + esc(n.error) + "</p></div>";
    return '<div class="cmp-col" data-side="' + side + '"><div class="cmp-tag">' + side + '</div><div class="note-head">' + headHtml(n) + '</div><article class="note small">' + bodyHtml(n, true) + "</article></div>";
  };
  v.innerHTML = '<div class="cmp-head">Jev 認為這兩個來源對 <a data-open="' + esc(s.topic.path) + '">' + esc(s.topic.title) + "</a> 的說法可能衝突（" + s.p.toFixed(2) +
    "）。兩邊提到它的地方已經標出來。" + '<button data-act="next-hl">下一處</button></div><div class="cmp">' + col(t.notes[0], "A") + '<div class="gutter cmp-g" title="拖曳調整，雙擊回到一半"></div>' + col(t.notes[1], "B") + "</div>";
  if (t.notes[0] && t.notes[1]) {
    const names = [s.topic.title, ...(s.topic.aliases || [])];
    v.querySelectorAll(".cmp-col .note").forEach(el => highlight(names, el, false));
  }
}

function renderFile(v, t) {
  const u = "/file?path=" + encodeURIComponent(t.path), [kind] = fileKind(t.path);
  const info = assetsData && assetsData.files.find(f => f.path === t.path);
  let body;
  if (kind === "圖片") body = '<img class="file-img" src="' + u + '" alt="">';
  else if (kind === "PDF") body = '<iframe class="file-frame" src="' + u + '"></iframe>';
  else if (kind === "網頁") {
    const made = info && info.note;
    body = '<div class="to-note">' + (made
      ? '<div><strong>已經轉成筆記</strong>：<a class="wl" data-path="' + esc(made) + '">' + esc(baseName(made)) + "</a></div>" +
        '<div class="muted">網頁的文字已經在那篇筆記裡，可以搜尋、找連結、交給 agent 整理。這裡的預覽是原始網頁的樣子。</div>'
      : '<div class="to-note-row"><div><strong>這裡只是預覽</strong>：網頁還只是一個附件，裡面的文字不會被搜尋、不會找連結，agent 也不會整理它。</div>' +
        (S.tree.read_only ? "" : '<button data-act="html2note" class="primary">轉成筆記</button>') + "</div>" +
        '<div class="muted">轉成筆記：把網頁的正文（去掉選單、側欄、廣告和程式）存成一篇筆記，格式跟 Web Clipper 剪下來的一樣，並連回這個原檔。原檔留在附件裡。</div>') +
      '</div><iframe class="file-frame" sandbox src="' + u + '"></iframe><div class="note-line">預覽在隔離的框裡，網頁的程式不會執行，碰不到你的筆記。</div>';
  }
  else if (kind === "音訊") body = '<audio controls src="' + u + '"></audio>';
  else if (kind === "影片") body = '<video class="file-img" controls src="' + u + '"></video>';
  else if (kind === "文字") body = '<iframe class="file-frame text" src="' + u + '"></iframe>';
  else body = '<p class="muted">這種檔案沒辦法在這裡預覽。</p>';
  v.innerHTML = '<div class="note-head"><h1>' + esc(t.title) + '</h1><div class="meta"><span class="chip">附件 · ' + kind + "</span>" +
    (info ? "<span>·</span>" + fmtSize(info.size) : "") + "<span>·</span><span>" + esc(t.path.split("/").slice(0, -1).join(" / ")) + "</span><span>·</span>" +
    '<a href="' + u + '" target="_blank" rel="noopener">在新視窗打開</a>' + (kind === "檔案" ? '<span>·</span><a href="' + u + '" download>下載</a>' : "") +
    (!S.tree.read_only ? '<span>·</span><a data-act="delete">刪除</a>' : "") + '</div></div><div class="file-body">' + body + "</div>";
}

function startEdit() {
  const t = tab();
  if (!t || t.kind !== "note" || !t.note || !t.note.editable) return;
  t.editing = true; t.msg = ""; renderView(); $("#editor").focus();
}

let RENAMING = null;           // a rename in flight: a save waits for it, so it goes to the new name
async function save() {
  if (RENAMING) await RENAMING.catch(() => {});
  return saveTab(tab());
}
async function saveTab(t) {
  if (!t || t.kind !== "note" || !(t.editing || t.dirty)) return;
  const text = t.editing ? $("#editor").value : t.editText;
  try {
    const r = await api("/api/save", { path: t.path, text, mtime: t.note.mtime });
    t.note.text = text; t.note.mtime = r.mtime; t.dirty = false; t.editText = text; t.external = false;
    const d = new Date();
    t.msg = "已儲存 " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
    renderTabbar(); renderView(); loadPanel(true);
  } catch (e) { t.msg = "沒存成：" + e.message; renderView(); }
}

async function reloadTab(t) {
  try {
    const n = await api("/api/note?path=" + encodeURIComponent(t.path));
    Object.assign(t, { note: n, dirty: false, editText: undefined, external: false });
    if (!t.editing) t.msg = "";
    if (tab() === t) { renderTabbar(); renderView(); loadPanel(true); }
  } catch (e) {}
}

$("#view").addEventListener("click", e => {
  const att = e.target.closest("a.att");
  if (att) { e.preventDefault(); openNote(att.dataset.file, { newTab: e.metaKey || e.ctrlKey || tab().kind === "compare" }); return; }
  const a = e.target.closest("a.wl");
  if (a && a.dataset.path) { e.preventDefault(); openNote(a.dataset.path, { newTab: e.metaKey || e.ctrlKey || tab().kind === "compare" }); return; }
  const o = e.target.closest("[data-open]");
  if (o) { openNote(o.dataset.open, { newTab: true }); return; }
  if (e.target.closest("[data-show-all]")) { tab().full = true; renderView(); return; }
  const b = e.target.closest("[data-act]");
  if (!b) return;
  const t = tab();
  const act = b.dataset.act;
  if (act === "edit") startEdit();
  else if (act === "preview") { t.editText = $("#editor").value; t.editing = false; t.note = Object.assign({}, t.note, { text: t.editText }); renderView(); }
  else if (act === "save") save();
  else if (act === "revert") { if (!t.dirty || confirm("放棄還沒儲存的修改？")) { t.editing = false; reloadTab(t); } }
  else if (act === "reload") reloadTab(t);
  else if (act === "next-hl") nextHighlight();
  else if (act === "delete") deleteFile(t.path);
  else if (act === "history") showHistory(t.path);
  else if (act === "rename") startTitleRename(t);
  else if (act === "pdf-layout") { S.pdfTidy = !S.pdfTidy; store.set("pdf-tidy", S.pdfTidy); renderView(); }
  else if (act === "html2note") htmlToNote(t.path, b);
});

document.addEventListener("keydown", e => {
  if ((e.metaKey || e.ctrlKey) && e.key === "s") { e.preventDefault(); save(); }
  if ((e.metaKey || e.ctrlKey) && e.key === "w" && tab()) { e.preventDefault(); closeTab(S.active); }
});
window.addEventListener("beforeunload", e => { if (S.tabs.some(t => t.dirty)) { e.preventDefault(); e.returnValue = ""; } });

// ---------- attachments: drop or paste files into a note

function fileToBase64(file) {
  return new Promise((ok, bad) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).split(",")[1] || "");
    r.onerror = () => bad(r.error);
    r.readAsDataURL(file);
  });
}

async function attach(files) {
  const t = tab();
  if (!t || t.kind !== "note" || !t.note) return;
  if (!t.note.editable) { toast(t.note.raw ? "唯讀模式，不能加附件。" : "知識庫的頁是 AI 寫的，附件請加在你自己的筆記。"); return; }
  const links = [];
  for (const f of files) {
    try {
      const r = await api("/api/attach", { name: f.name || "pasted.png", data: await fileToBase64(f) });
      TREE.images[r.name.toLowerCase()] = r.path; assetsData = null;
      links.push((r.image ? "![[" : "[[") + r.name + "]]");
    } catch (e) { toast("「" + f.name + "」沒存成：" + e.message); }
  }
  if (!links.length) return;
  const ins = links.join("\n");
  if (t.editing) {
    const ed = $("#editor");
    const a = ed.selectionStart, b = ed.selectionEnd;
    ed.value = ed.value.slice(0, a) + ins + ed.value.slice(b);
    ed.selectionStart = ed.selectionEnd = a + ins.length;
    ed.dispatchEvent(new Event("input"));
    toast("附件存進 " + S.tree.attach_to + "/，連結插在游標處。記得儲存。");
  } else {
    if (t.dirty) { toast("先儲存或放棄修改，再加附件。"); return; }
    t.editing = true; t.editText = t.note.text.replace(/\s*$/, "") + "\n\n" + ins + "\n"; t.dirty = true;
    renderTabbar(); renderView(); await save(); t.editing = false; renderView();
    toast("附件存進 " + S.tree.attach_to + "/，連結加在筆記最後。");
  }
}

const view = $("#view");
view.addEventListener("dragover", e => { if (e.dataTransfer && [...e.dataTransfer.types].includes("Files")) { e.preventDefault(); view.classList.add("drop"); } });
view.addEventListener("dragleave", e => { if (e.target === view) view.classList.remove("drop"); });
view.addEventListener("drop", e => {
  view.classList.remove("drop");
  if (!e.dataTransfer || !e.dataTransfer.files.length) return;
  e.preventDefault(); attach([...e.dataTransfer.files]);
});
view.addEventListener("paste", e => {
  const files = [...(e.clipboardData ? e.clipboardData.files : [])];
  if (files.length && e.target.id === "editor") { e.preventDefault(); attach(files); }
});

// ---------- highlight names in a note

let hlIndex = -1;
function highlight(names, root, scroll = true) {
  root = root || $("#note");
  if (!root) return 0;
  root.querySelectorAll("mark.hl").forEach(m => m.replaceWith(document.createTextNode(m.textContent)));
  root.normalize();
  const words = [...new Set(names.filter(w => w && w.length >= 2))].sort((a, b) => b.length - a.length);
  if (!words.length) return 0;
  const rx = new RegExp(words.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+")).join("|"), "gi");
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  let first = null, count = 0;
  for (const node of nodes) {
    const tx = node.nodeValue; rx.lastIndex = 0;
    if (!rx.test(tx)) continue;
    rx.lastIndex = 0;
    const frag = document.createDocumentFragment(); let last = 0, m;
    while ((m = rx.exec(tx))) {
      frag.append(tx.slice(last, m.index));
      const mark = document.createElement("mark"); mark.className = "hl"; mark.textContent = m[0];
      frag.append(mark); first = first || mark; count++; last = m.index + m[0].length;
    }
    frag.append(tx.slice(last)); node.replaceWith(frag);
  }
  hlIndex = 0;
  if (first && scroll) first.scrollIntoView({ behavior: "smooth", block: "center" });
  return count;
}
function nextHighlight() {
  const marks = [...document.querySelectorAll("#view mark.hl")];
  if (!marks.length) return;
  hlIndex = (hlIndex + 1) % marks.length;
  marks[hlIndex].scrollIntoView({ behavior: "smooth", block: "center" });
}

// ============================================================ right panel

const W_LABEL = { 2: "主題", 1: "有討論", 0: "順帶提到" };

function mentionRow(m) {
  const no = m.refers != null && m.refers <= 0.2;
  const unsure = m.refers != null && m.refers > 0.2 && m.refers < 0.8;
  const tag = m.refers == null ? "" : no ? "可能不是" : unsure ? "待確認 " + m.refers.toFixed(2) : (m.weight != null ? W_LABEL[m.weight] : "Jev " + m.refers.toFixed(2));
  return '<div class="mention' + (no ? " no" : "") + '" data-path="' + esc(m.path) + '" data-names="' + esc(JSON.stringify([m.title, ...(m.aliases || []), ...m.matched])) +
    '"><span class="w' + (m.weight != null ? " w" + m.weight : "") + '"></span><span><span class="t">' + esc(m.title) + '</span> <span class="muted">' + esc(TYPE_ZH[m.type] || "") +
    '</span><span class="s">' + esc(m.summary) + '</span></span><span class="x">×' + m.n + (tag ? "<br>" + esc(tag) : "") + "</span></div>";
}

function suggestionCard(s) {
  return '<div class="card contra" data-key="' + esc(s.key) + '"><div class="kind">可能矛盾 · Jev ' + s.p.toFixed(2) + '</div><div class="body">' +
    '<a data-path="' + esc(s.a.path) + '">' + esc(s.a.title) + '</a> 和 <a data-path="' + esc(s.b.path) + '">' + esc(s.b.title) + "</a> 對 " +
    '<a data-path="' + esc(s.topic.path) + '">' + esc(s.topic.title) + "</a> 的說法可能衝突。</div>" +
    '<div class="acts"><button data-compare="' + esc(s.key) + '">並排比較</button><button data-dismiss="' + esc(s.key) + '">看過，沒問題</button></div></div>';
}

function recordedCard(r) {
  const label = { contradiction: "已記錄的矛盾", positions: "不同看法（立場）", question: "待解的問題" }[r.kind] || r.kind;
  return '<div class="card ' + (r.kind === "contradiction" ? "contra" : "positions") + '"><div class="kind">' + label + '</div><details><summary>' + inline(r.title) + "</summary><div>" + md(r.text) + "</div></details></div>";
}

let panelData = null;
async function loadPanel(force) {
  const t = tab(), el = $("#panel");
  if (!t) return;
  if (t.kind === "compare") { renderComparePanel(t); return; }
  if (t.kind === "file") { renderFilePanel(t); return; }
  if (!t.note) { el.innerHTML = '<p class="muted"><span class="spin"></span></p>'; return; }
  const path = t.path;
  if (!force && S.panelFor === path && panelData) return renderPanel(panelData);
  el.innerHTML = '<p class="muted"><span class="spin"></span> 找連結…</p>';
  let p;
  try { p = await api("/api/panel?path=" + encodeURIComponent(path)); }
  catch (e) { el.innerHTML = '<p class="muted">' + esc(e.message) + "</p>"; return; }
  if (!tab() || tab().path !== path) return;
  S.panelFor = path; panelData = p;
  renderPanel(p);
  if (mine(path) && !p.checked && !p.private && jevUsable() && p.mentions.length && !S.checking.has(path)) runCheck(path);
}

async function renderFilePanel(t) {
  const el = $("#panel");
  el.innerHTML = '<p class="muted"><span class="spin"></span></p>';
  try { await loadAssets(true); } catch (e) { el.innerHTML = '<p class="muted">' + esc(e.message) + "</p>"; return; }
  if (tab() !== t) return;
  const f = assetsData.files.find(x => x.path === t.path);
  const used = f ? f.used_by : [];
  el.innerHTML = '<h3>用到這個檔案的筆記 <span class="n">' + used.length + "</span></h3>" +
    (used.length ? '<div class="linklist">' + used.map(p => '<a data-path="' + esc(p) + '">' + esc(baseName(p)) + "</a>").join("") + "</div>"
      : '<div class="note-line">沒有筆記連到它。把它拖進一篇筆記，或在筆記裡寫 <code>![[' + esc(t.title) + "]]</code>。</div>") +
    '<div class="note-line" style="margin-top:16px">附件不送 Jev，也不參加名稱比對。</div>';
  if (tab() === t && t.kind === "file") renderView();      // size now known
}

function renderComparePanel(t) {
  const s = t.s;
  $("#panel").innerHTML = "<h3>正在比較</h3>" + suggestionCard(s).replace('<button data-compare="' + esc(s.key) + '">並排比較</button>', "") +
    '<div class="note-line">看完兩邊：如果真的衝突，告訴 agent 在 <a data-path="' + esc(s.topic.path) + '">' + esc(s.topic.title) +
    "</a> 加一個矛盾或「不同看法」段落；如果只是談不同面向，按「看過，沒問題」，它就不會再出現。</div>";
}

function renderPanel(p) {
  const el = $("#panel"), isRaw = mine(p.path);
  let html = '<h3>建議 <span class="n">' + (p.suggestions.length || "") + "</span></h3>";
  html += p.suggestions.length ? p.suggestions.map(suggestionCard).join("") : '<div class="note-line">沒有需要你看的事。</div>';
  if (p.unsure) html += '<div class="note-line">另有 ' + p.unsure + " 對 Jev 不確定的說法差異沒列出：大約六成不是真矛盾，要 agent 讀過才會變成建議。</div>";
  if (p.stale) html += '<div class="note-line">' + p.stale + " 對的判斷做完之後，相關頁面又改過，判斷可能過時，先不列。下次 lint 會重判。</div>";
  if (p.suggestions.length || p.unsure) html += '<div class="note-line">這些判斷是 lint 時存下來的，Jev 關掉也看得到。</div>';
  if (p.recorded && p.recorded.length) html += "<h3>這頁記下的爭議</h3>" + p.recorded.map(recordedCard).join("");

  if (isRaw) {
    if (p.organized) {
      html += '<h3>已整理成</h3><div class="linklist"><a data-path="' + esc(p.organized.source.path) + '"><strong>' + esc(p.organized.source.title) + "</strong></a></div>";
      if (p.organized.pages.length) html += '<div class="note-line">累積到 ' + p.organized.pages.length + ' 個概念・人物頁：</div><div class="linklist">' +
        p.organized.pages.slice(0, 30).map(c => '<a data-path="' + esc(c.path) + '">' + esc(c.title) + "</a>").join("") + "</div>";
    } else if (!p.private) {
      html += '<h3>還沒整理</h3><div class="note-line">' + (p.triage ? "Jev 的判斷：" + esc(QUEUE_LABEL[p.triage.decision] || p.triage.decision) + "（優先度 " + esc(p.triage.priority) + "）。" : "還沒排進佇列。") +
        "</div>" + (S.tree.read_only ? "" : '<div class="ai-acts"><button data-ingest-note="' + esc(p.path) + '">✦ 請 AI 整理這篇</button></div>');
    }
  }

  const atts = noteAttachments(tab() && tab().note ? tab().note.text : "");
  if (atts.length) html += '<h3>這篇的附件 <span class="n">' + atts.length + '</span></h3><div class="linklist">' +
    atts.map(a => '<a data-path="' + esc(a) + '">' + fileKind(a)[1] + " " + esc(a.split("/").pop()) + "</a>").join("") + "</div>";

  const unlinked = p.mentions.filter(m => !m.linked), linked = p.mentions.filter(m => m.linked);
  html += '<h3>潛在連結 <span class="n">' + (unlinked.length || "") + "</span></h3>";
  if (isRaw) {
    if (p.private) html += '<div class="banner">日記不送 Jev，只用名稱比對。</div>';
    else if (S.checking.has(p.path)) html += '<div class="banner ok"><span class="spin"></span> Jev 正在判斷每個名稱是不是真的指那一頁…</div>';
    else if (!p.checked && unlinked.length) html += jevUsable() ? '<div class="note-line">目前只是名稱比對。<a id="check-now">用 Jev 判斷</a>（送出名稱前後的片段）' +
      (p.stale_check ? "：筆記改過，之前的判斷已過期。" : "") + "</div>" : '<div class="note-line">只用名稱比對' + (S.tree.jev ? "（Jev 已關閉）" : "（沒有 Jev key）") + "：同名的不同東西也會列進來。</div>";
  }
  if (!unlinked.length) html += '<div class="note-line">沒找到提到卻沒連的頁面。</div>';
  else if (isRaw && p.checked) {
    const groups = [["主題", m => m.refers >= 0.8 && m.weight === 2], ["有討論", m => m.refers >= 0.8 && m.weight === 1], ["順帶提到", m => m.refers >= 0.8 && !m.weight],
      ["待確認", m => m.refers > 0.2 && m.refers < 0.8], ["名稱沒被 Jev 看過", m => m.refers == null], ["可能不是這一頁", m => m.refers <= 0.2]];
    for (const [label, f] of groups) {
      const ms = unlinked.filter(f);
      if (ms.length) html += '<div class="sub">' + label + " · " + ms.length + "</div>" + ms.map(mentionRow).join("");
    }
  } else html += unlinked.slice(0, 60).map(mentionRow).join("");
  if (linked.length) html += '<h3>已連結 <span class="n">' + linked.length + "</span></h3>" + linked.slice(0, 40).map(mentionRow).join("");
  if (p.backlinks) html += '<h3>誰連到這頁 <span class="n">' + p.backlinks.length + '</span></h3><div class="linklist">' +
    p.backlinks.slice(0, 80).map(c => '<a data-path="' + esc(c.path) + '">' + esc(c.title) + "</a>").join("") + (p.backlinks.length > 80 ? '<div class="note-line">…還有 ' + (p.backlinks.length - 80) + " 頁</div>" : "") + "</div>";
  html += '<p class="note-line" style="margin-top:24px">點一個連結，會在筆記裡標出它出現的地方；點標題打開那一頁（⌘／Ctrl 開新分頁）。</p>';
  el.innerHTML = html;
  const c = $("#check-now");
  if (c) c.onclick = () => runCheck(p.path);
}

function noteAttachments(text) {
  const out = new Set();
  for (const m of text.matchAll(/\[\[([^\]|#^]+)/g)) {
    const rel = TREE.images[m[1].trim().split("/").pop().toLowerCase()];
    if (rel) out.add(rel);
  }
  return [...out];
}

async function runCheck(path) {
  S.checking.add(path);
  if (tab() && tab().path === path && panelData) renderPanel(panelData);
  let err = null;
  try { await api("/api/check", { path }); } catch (e) { err = e.message; }
  S.checking.delete(path);
  if (tab() && tab().path === path) {
    await loadPanel(true);
    if (err) $("#panel").insertAdjacentHTML("afterbegin", '<div class="banner">Jev 沒回應：' + esc(err) + "。先用名稱比對的結果。</div>");
  }
}

$("#panel").addEventListener("click", async e => {
  const ing = e.target.closest("[data-ingest-note]");
  if (ing) { startAgent("ingest", { path: ing.dataset.ingestNote }); return; }
  const cmp = e.target.closest("[data-compare]");
  if (cmp) { const s = panelData.suggestions.find(x => x.key === cmp.dataset.compare); if (s) openCompare(s); return; }
  const dis = e.target.closest("[data-dismiss]");
  if (dis) {
    await api("/api/dismiss", { key: dis.dataset.dismiss });
    const card = dis.closest(".card"); card.style.opacity = .45;
    card.querySelector(".acts").innerHTML = '<span class="muted" style="font-size:12px">已略過，不會再出現。</span> <button data-undo="' + esc(dis.dataset.dismiss) + '">復原</button>';
    return;
  }
  const undo = e.target.closest("[data-undo]");
  if (undo) { await api("/api/dismiss", { key: undo.dataset.undo, undo: true }); loadPanel(true); return; }
  const a = e.target.closest("a[data-path]");
  if (a) { openNote(a.dataset.path, { newTab: e.metaKey || e.ctrlKey || (tab() && tab().kind === "compare") }); return; }
  const m = e.target.closest(".mention");
  if (m) {
    if (e.target.closest(".t")) { openNote(m.dataset.path, { newTab: e.metaKey || e.ctrlKey }); return; }
    if (tab() && tab().editing) { toast("預覽模式才能標出位置。"); return; }
    if (!highlight(JSON.parse(m.dataset.names))) openNote(m.dataset.path, { newTab: e.metaKey || e.ctrlKey });
  }
});

// ============================================================ search

// While typing: titles, aliases (Chinese names included) and note names, matched in the browser with
// Traditional folded to Simplified, best matches first. Enter (or the last row) searches page contents.
const input = $("#search"), quick = $("#quick");
let quickSel = -1, T2S = {}, QINDEX = [];
api("/api/t2s").then(t => { T2S = t; buildQuickIndex(); }).catch(() => {});
const fold = s => { s = s.toLowerCase(); let o = ""; for (const c of s) o += T2S[c] || c; return o; };

function buildQuickIndex() {
  if (!S.tree) return;
  QINDEX = S.tree.pages.map(p => ({ path: p.path, title: p.title, type: p.type, kind: "wiki",
    keys: [p.title, ...(p.aliases || [])].map(k => [fold(k), k]) }));
  for (const f of S.tree.raw) {
    const n = baseName(f.path);
    QINDEX.push({ path: f.path, title: n, kind: inJournal(f.path) ? "journal" : "raw", done: f.done, d: f.d, keys: [[fold(n), n]] });
  }
}

function quickScore(e, q) {
  let best = 0, via = null;
  for (const [k, orig] of e.keys) {
    const i = k.indexOf(q);
    if (i < 0) continue;
    let sc = k === q ? 100 : i === 0 ? 80 : /[\s\-_(（,.:：、·'"]/.test(k[i - 1]) ? 65 : 40;
    sc -= Math.min(k.length, 60) / 10;                         // shorter names first
    if (sc > best) { best = sc; via = orig; }
  }
  if (!best) return null;
  if (e.kind === "wiki") best += e.type === "source" ? 2 : 6;     // concept / person pages before sources
  return { e, score: best, via: via !== e.title ? via : null };
}

// With Jev on, a pause in typing (0.45 s) asks Jev too; its answer replaces the list's top group.
const JEV_CACHE = new Map();
let jevTimer, jevSeq = 0;
const jevReady = raw => jevUsable() && raw.length >= (/[\u3400-\u9fff]/.test(raw) ? 2 : 3);
function jevQuick(raw) {
  clearTimeout(jevTimer);
  if (!jevReady(raw) || JEV_CACHE.has(raw)) return;
  jevTimer = setTimeout(async () => {
    const seq = ++jevSeq;
    let r;
    try { r = await api("/api/search?q=" + encodeURIComponent(raw)); } catch (e) { r = { error: e.message }; }
    JEV_CACHE.set(raw, r);
    if (JEV_CACHE.size > 50) JEV_CACHE.delete(JEV_CACHE.keys().next().value);
    if (seq === jevSeq && input.value.trim() === raw && document.activeElement === input) renderQuick(true);
  }, 450);
}

function renderQuick(keepSel) {
  const raw = input.value.trim(), q = fold(raw);
  const selPath = keepSel === true && quickSel >= 0 ? (quick.querySelectorAll(".qi")[quickSel] || {}).dataset : null;
  quickSel = -1;
  if (!q) { quick.hidden = true; return; }
  const hits = QINDEX.map(e => quickScore(e, q)).filter(Boolean).sort((a, b) => b.score - a.score);
  const useJev = jevReady(raw), jr = useJev ? JEV_CACHE.get(raw) : null;
  const wiki = hits.filter(h => h.e.kind === "wiki").slice(0, useJev ? 4 : 7), notes = hits.filter(h => h.e.kind !== "wiki").slice(0, useJev ? 3 : 5);
  const row = h => '<div class="qi" data-path="' + esc(h.e.path) + '"><span class="qt">' + esc(h.e.title) + "</span>" +
    (h.via ? '<span class="via">' + esc(h.via) + "</span>" : "") + '<span class="muted">' +
    (h.e.kind === "wiki" ? esc(TYPE_ZH[h.e.type] || "") : h.e.kind === "journal" ? "日記" : "筆記") + "</span></div>";
  let html = "";
  if (useJev) {
    html += '<div class="qg">Jev：和「' + esc(raw) + '」相關的頁</div>';
    if (!jr) html += '<div class="qg"><span class="spin"></span> Jev 判斷中…</div>';
    else if (jr.error || jr.mode !== "jev") html += '<div class="qg">Jev 沒回應' + (jr.error ? "：" + esc(jr.error) : "") + "，下面是名稱比對。</div>";
    else html += jr.results.slice(0, 7).map(x => '<div class="qi" data-path="' + esc(x.path) + '"><span class="qt">' + esc(x.title) + '</span><span class="muted">' +
      esc(TYPE_ZH[x.type] || "") + (x.bm25 ? " · 關鍵字" : x.score != null ? " · " + x.score.toFixed(2) : "") + "</span></div>").join("");
  }
  if (wiki.length) html += '<div class="qg">' + (useJev ? "名稱相符" : "知識庫") + "</div>" + wiki.map(row).join("");
  if (notes.length) html += '<div class="qg">筆記</div>' + notes.map(row).join("");
  if (!hits.length) html += '<div class="qg">標題和別名裡沒有「' + esc(raw) + "」</div>";
  const aiRow = '<div class="qi ai-row" data-ai="1"><span class="qt">✦ 問 AI：「' + esc(raw) + '」</span><span class="muted">⌘↵</span></div>';
  const asking = questionLike(raw);
  if (asking) html = aiRow + html; else html += aiRow;
  html += '<div class="qi" data-ask="1"><span>↵ ' + (useJev ? "在左欄列出 Jev 的完整結果（前 20 頁）" : jevUsable() ? "用 Jev 找和「" + esc(raw) + "」相關的頁" : "用關鍵字搜尋內容「" + esc(raw) + "」") + "</span></div>";
  quick.innerHTML = html;
  quick.hidden = false;
  const items = [...quick.querySelectorAll(".qi")];
  if (selPath) quickSel = items.findIndex(d => (d.dataset.path && d.dataset.path === selPath.path) || (d.dataset.ai && selPath.ai));
  else if (asking) quickSel = 0;                 // a question: Enter asks the AI
  if (quickSel >= 0) items[quickSel].classList.add("sel");
  jevQuick(raw);
}
input.addEventListener("input", () => renderQuick());
input.addEventListener("focus", () => { if (input.value.trim()) renderQuick(); });
input.addEventListener("keydown", e => {
  if (e.isComposing || e.keyCode === 229) return;              // Enter that confirms a Chinese IME candidate
  const items = [...quick.querySelectorAll(".qi")];
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault(); if (!items.length || quick.hidden) return;
    quickSel = (quickSel + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
    items.forEach((d, i) => d.classList.toggle("sel", i === quickSel));
    items[quickSel].scrollIntoView({ block: "nearest" });
  } else if (e.key === "Escape") { quick.hidden = true; input.blur(); }
  else if (e.key === "Enter") {
    e.preventDefault();
    const it = quickSel >= 0 && !quick.hidden ? items[quickSel] : null;
    quick.hidden = true;
    if (it && it.dataset.path) return openNote(it.dataset.path, { newTab: e.metaKey || e.ctrlKey });
    if ((it && it.dataset.ai) || e.metaKey || e.ctrlKey) return askAI(input.value);
    ask(input.value.trim());
  }
});
quick.addEventListener("mousedown", e => {
  const d = e.target.closest(".qi");
  if (!d) return;
  e.preventDefault(); quick.hidden = true;
  d.dataset.path ? openNote(d.dataset.path, { newTab: e.metaKey || e.ctrlKey }) : d.dataset.ai ? askAI(input.value) : ask(input.value.trim());
});
input.addEventListener("blur", () => setTimeout(() => (quick.hidden = true), 150));
document.addEventListener("keydown", e => {
  if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); input.focus(); input.select(); }
});

async function ask(q) {
  if (!q) return;
  const jev = jevUsable();
  S.results = { loading: true, jev };
  document.querySelector('.tabs button[data-tab="results"]').hidden = false;
  S.sideTab = "results"; renderTree();
  const cached = jev ? JEV_CACHE.get(q) : null;
  try { S.results = cached && !cached.error ? Object.assign({}, cached) : await api("/api/search?q=" + encodeURIComponent(q) + (jev ? "" : "&mode=bm25")); }
  catch (e) { S.results = { mode: "bm25", results: [], error: e.message }; }
  S.results.q = q;
  if (S.sideTab === "results") renderTree();
}

function renderJevState() {
  const el = $("#jev-state");
  if (!S.tree.jev) { el.className = "jev-state off"; el.textContent = "沒有 Jev key：只用名稱比對和關鍵字搜尋"; return; }
  el.className = "jev-state " + (S.jevOn ? "on" : "off");
  el.innerHTML = '<button id="jev-toggle" title="關掉後：搜尋改用關鍵字，筆記不送 Jev 判斷">Jev：' + (S.jevOn ? "開" : "關") + "</button>" +
    (S.tree.read_only ? ' <span class="chip">唯讀</span>' : "");
  $("#jev-toggle").onclick = () => {
    S.jevOn = !S.jevOn; store.set("jev-on", S.jevOn); renderJevState();
    toast(S.jevOn ? "Jev 開：搜尋用 Jev 判斷，打開筆記時自動判斷連結。" : "Jev 關：搜尋改用關鍵字，筆記內容不再送出。");
    if (panelData && tab() && tab().kind === "note") renderPanel(panelData);
  };
}

// ============================================================ live updates

async function refreshTree() {
  const t = await api("/api/tree");
  S.tree = t; window.TREE = t;
  S.rawRoot = buildRawTree(t.raw);
  queueData = null; assetsData = null;
  buildQuickIndex();
  renderTree();
}

async function poll() {
  try {
    const paths = S.tabs.filter(t => t.kind === "note").map(t => "path=" + encodeURIComponent(t.path)).join("&");
    const c = await api("/api/changes" + (paths ? "?" + paths : ""));
    if (S.sigs && (c.raw !== S.sigs.raw || c.wiki !== S.sigs.wiki)) {
      await refreshTree();
      if (c.wiki !== S.sigs.wiki && tab() && tab().kind === "note" && !tab().editing) loadPanel(true);
    }
    S.sigs = { raw: c.raw, wiki: c.wiki };
    for (const t of S.tabs) {
      if (t.kind !== "note" || !t.note || c.mtimes[t.path] == null) continue;
      if (Math.abs(c.mtimes[t.path] - t.note.mtime) < 0.001) continue;
      if (t.dirty || t.editing) { if (!t.external) { t.external = true; if (tab() === t) renderView(); } }
      else reloadTab(t);
    }
  } catch (e) {}
  setTimeout(poll, 4000);
}

// ============================================================ resizable columns
// Drag the line between two columns; double-click it to collapse or bring back that side. Remembered.

const L = { left: store.get("w-left", 280), right: store.get("w-right", 340), leftOff: store.get("off-left", false), rightOff: store.get("off-right", false),
  cmp: store.get("w-cmp", 0.5) };
function applyLayout() {
  const c = $("#cols");
  c.style.setProperty("--lw", (L.leftOff ? 0 : L.left) + "px");
  c.style.setProperty("--rw", (L.rightOff ? 0 : L.right) + "px");
  c.classList.toggle("left-off", L.leftOff); c.classList.toggle("right-off", L.rightOff);
  document.documentElement.style.setProperty("--cmp-a", (L.cmp * 100).toFixed(1) + "%");
  if (typeof syncToggles === "function") syncToggles();
}
function saveLayout() {
  store.set("w-left", L.left); store.set("w-right", L.right); store.set("off-left", L.leftOff); store.set("off-right", L.rightOff); store.set("w-cmp", L.cmp);
}
function dragGutter(g, e, onMove) {
  e.preventDefault(); g.setPointerCapture(e.pointerId); g.classList.add("on"); document.body.classList.add("resizing");
  const move = ev => onMove(ev);
  const up = () => { g.removeEventListener("pointermove", move); g.removeEventListener("pointerup", up); g.classList.remove("on"); document.body.classList.remove("resizing"); saveLayout(); };
  g.addEventListener("pointermove", move); g.addEventListener("pointerup", up);
}
document.querySelectorAll(".gutter[data-gutter]").forEach(g => {
  const side = g.dataset.gutter;
  g.addEventListener("pointerdown", e => {
    const x0 = e.clientX, w0 = L[side + "Off"] ? 0 : L[side];
    dragGutter(g, e, ev => {
      const w = side === "left" ? w0 + ev.clientX - x0 : w0 - (ev.clientX - x0);
      if (w < 120) L[side + "Off"] = true;                       // drag almost shut: collapse
      else { L[side + "Off"] = false; L[side] = Math.round(Math.min(Math.max(w, 180), window.innerWidth * 0.45)); }
      applyLayout();
    });
  });
  g.addEventListener("dblclick", () => { L[side + "Off"] = !L[side + "Off"]; applyLayout(); saveLayout(); });
});
$("#view").addEventListener("pointerdown", e => {
  const g = e.target.closest(".cmp-g");
  if (!g) return;
  const box = g.parentElement.getBoundingClientRect();
  dragGutter(g, e, ev => { L.cmp = Math.min(Math.max((ev.clientX - box.left) / box.width, 0.2), 0.8); applyLayout(); });
});
$("#view").addEventListener("dblclick", e => { if (e.target.closest(".cmp-g")) { L.cmp = 0.5; applyLayout(); saveLayout(); } });
function toggleSide(side) { L[side + "Off"] = !L[side + "Off"]; applyLayout(); saveLayout(); }
$("#toggle-left").onclick = () => toggleSide("left");
$("#toggle-right").onclick = () => toggleSide("right");
document.addEventListener("keydown", e => {
  if ((e.metaKey || e.ctrlKey) && (e.key === "\\" || e.code === "Backslash")) { e.preventDefault(); toggleSide(e.shiftKey ? "right" : "left"); }
});
function syncToggles() {
  $("#toggle-left").classList.toggle("on", !L.leftOff); $("#toggle-right").classList.toggle("on", !L.rightOff);
  $("#toggle-left").setAttribute("aria-pressed", String(!L.leftOff)); $("#toggle-right").setAttribute("aria-pressed", String(!L.rightOff));
};
applyLayout();

// ============================================================ start

(async function start() {
  try { await refreshTree(); } catch (e) { return; }       // no key or no vault: the start screen is showing
  $("#vault-name").textContent = S.tree.vault;
  const where = S.tree.vault_path.replace(/^\/Users\/[^/]+/, "~");
  $("#vault-where").textContent = S.tree.protected ? "受保護・唯讀" : S.tree.read_only ? "唯讀" : "在 " + where.split("/").slice(0, -1).join("/") + "/";
  $("#vault-where").classList.toggle("prot", !!S.tree.protected);
  $("#brand").title = "正在使用：" + S.tree.vault_path + (S.tree.protected ? "\n這個筆記庫在 protected.txt 裡：只能看，不能改。" : "") + "\n點一下切換筆記庫";
  document.title = S.tree.vault + " · 筆記";
  renderJevState();
  $("#journal-btn").hidden = $("#new-btn").hidden = !!S.tree.read_only;
  if (!["journal", "raw", "assets", "wiki"].includes(S.sideTab)) S.sideTab = "raw";
  renderTree();
  NAV.i = (history.state && history.state.i) || 0;
  if (history.state && history.state.tab != null) history.replaceState(Object.assign({}, history.state, { tab: null }), "");
  renderNav();
  const h = decodeURIComponent(location.hash.slice(1));
  if (h) openNote(h);
  poll();
})();

// ============================================================ new note, rename, version history

async function newNote(dir) {
  try {
    const r = await api("/api/new", { dir: dir ?? ROOT() });
    await refreshTree();
    if (dir && S.sideTab === "raw") { S.open.add(dir); store.set("open-folders", [...S.open]); renderTree(); }
    await openNote(r.path, { edit: true, newTab: true });
    const t = S.tabs.find(x => x.path === r.path);
    if (t) { t.renameNow = true; renderView(); }
  } catch (e) { toast("沒辦法新增：" + e.message); }
}
$("#new-btn").onclick = () => newNote();

// the title of a note whose title is its file name: click, type, Enter
function startTitleRename(t) {
  const h = $("#view h1.renamable");
  if (!h || !t.note) return;
  const old = h.textContent;
  const inp = document.createElement("input");
  inp.className = "title-input"; inp.value = old; inp.setAttribute("aria-label", "筆記名稱");
  h.replaceWith(inp); inp.focus(); inp.select();
  let done = false;
  const finish = async ok => {
    if (done) return; done = true;
    const v = inp.value.trim();
    if (ok && v && v !== old) await renameFile(t.path, v);
    else renderView();
    if (t.editing && $("#editor")) $("#editor").focus();
  };
  inp.addEventListener("keydown", e => {
    if (e.isComposing || e.keyCode === 229) return;
    if (e.key === "Enter") { e.preventDefault(); finish(true); }
    if (e.key === "Escape") { e.preventDefault(); finish(false); }
  });
  inp.addEventListener("blur", () => finish(true));
}

function renameFile(path, name) {
  const job = renameJob(path, name);
  const p = job.finally(() => { if (RENAMING === p) RENAMING = null; });
  RENAMING = p;
  return job;
}
async function renameJob(path, name) {
  const isNote = /\.md$/.test(path), file = path.split("/").pop();
  const oldName = isNote ? baseName(path) : file;
  if (name == null) {
    const ok = await dialog("改名", '<input id="rename-input" class="dialog-input" value="' + esc(oldName) + '">' +
      "<p>" + (isNote ? "筆記裡連到它的 <code>[[連結]]</code> 會一起更新。" : "筆記裡連到這個附件的地方會一起更新。") + "</p>", "改名");
    name = $("#rename-input").value.trim();
    if (!ok || !name || name === oldName) return;
  }
  const t0 = S.tabs.find(x => x.path === path);
  if (t0 && t0.dirty) {                          // unsaved edits are saved first, so nothing is lost
    if (t0 !== tab()) { toast("「" + t0.title + "」還有沒儲存的修改，先存再改名。"); return; }
    await saveTab(t0);
    if (t0.dirty) return;                        // the save failed; its message is on the note
  }
  try {
    const r = await api("/api/rename", { path, name });
    if (!r.renamed) return;
    for (const t of S.tabs) if (t.path === path) {
      t.path = r.path; t.title = t.kind === "note" ? baseName(r.path) : r.path.split("/").pop();
      if (t.note) { t.note = Object.assign({}, t.note, { path: r.path }); reloadTab(t); }   // its `title:` may have changed
    }
    if (tab() && tab().path === r.path) history.replaceState(Object.assign({}, history.state, { path: r.path }), "", "#" + encodeURIComponent(r.path));
    await refreshTree(); assetsData = null;
    renderTabbar(); renderView();
    const newName = isNote ? baseName(r.path) : r.path.split("/").pop();
    let msg = "改名為「" + newName + "」";
    if (r.relinked.length) msg += "，更新了 " + r.relinked.length + " 篇筆記裡的連結";
    if (r.warnings.includes("processed")) msg += "。這篇已整理過，知識庫的來源頁要等 agent 更新路徑";
    toast(msg + "。", { label: "復原", fn: () => renameFile(r.path, oldName) });
  } catch (e) { toast("沒改成：" + e.message); renderView(); }
}

// line diff for the version view: common head and tail, then LCS on what's left (bounded)
function lineDiff(a, b) {
  const A = a.split("\n"), B = b.split("\n");
  let s = 0; while (s < A.length && s < B.length && A[s] === B[s]) s++;
  let e = 0; while (e < A.length - s && e < B.length - s && A[A.length - 1 - e] === B[B.length - 1 - e]) e++;
  const a2 = A.slice(s, A.length - e), b2 = B.slice(s, B.length - e), out = [];
  for (let i = 0; i < s; i++) out.push([" ", A[i]]);
  if (a2.length * b2.length > 4e6) { a2.forEach(l => out.push(["-", l])); b2.forEach(l => out.push(["+", l])); }
  else {
    const n = a2.length, m = b2.length, L = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = a2[i] === b2[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
    let i = 0, j = 0;
    while (i < n || j < m) {
      if (i < n && j < m && a2[i] === b2[j]) { out.push([" ", a2[i]]); i++; j++; }
      else if (j < m && (i === n || L[i][j + 1] >= L[i + 1][j])) out.push(["+", b2[j++]]);
      else out.push(["-", a2[i++]]);
    }
  }
  for (let i = A.length - e; i < A.length; i++) out.push([" ", A[i]]);
  return out;
}
function diffHtml(cur, ver) {
  const d = lineDiff(cur, ver), keep = new Set();
  d.forEach((x, i) => { if (x[0] !== " ") for (let k = i - 2; k <= i + 2; k++) keep.add(k); });
  if (!keep.size) return '<p class="muted">和現在的內容一樣。</p>';
  let html = "", gap = false;
  d.forEach((x, i) => {
    if (!keep.has(i)) { if (!gap) { html += '<div class="d-gap">⋯</div>'; gap = true; } return; }
    gap = false;
    html += '<div class="d-' + (x[0] === "+" ? "add" : x[0] === "-" ? "del" : "same") + '">' + (esc(x[1]) || "&nbsp;") + "</div>";
  });
  return html;
}

async function showHistory(path) {
  let r;
  try { r = await api("/api/history?path=" + encodeURIComponent(path)); } catch (e) { toast(e.message); return; }
  const name = baseName(path);
  if (!r.versions.length) {
    await dialog("「" + name + "」的版本", "<p>還沒有較早的版本。從現在起，每次儲存改動前，app 會先留下前一版（連續寫作時每 10 分鐘最多留一版，每篇最多 100 版），存在筆記庫的隱藏資料夾 <code>.notesapp/history/</code>。</p>", "好");
    return;
  }
  let cur = "";
  try { cur = (await api("/api/note?path=" + encodeURIComponent(path))).text; } catch (e) {}
  const html = '<div class="hist"><div class="hist-list">' + r.versions.map(v => '<button data-v="' + esc(v.id) + '">' + esc(v.time) + "<span>" + fmtSize(v.size) + "</span></button>").join("") +
    '</div><div class="hist-view" id="hist-view"><p class="muted">選左邊一個版本，看它和現在差在哪。</p></div></div>' +
    '<p class="d-legend"><span class="d-del">現在有、還原後會拿掉</span> <span class="d-add">這個版本有、還原後會回來</span>　還原前，現在的內容會先留成一版，所以還原也能復原。</p>';
  $("#modal .modal").classList.add("wide");
  let sel = null;
  const p = dialog("「" + name + "」的版本", html, "還原這個版本");
  const okb = $("#modal-ok"); okb.disabled = true;
  $("#modal-body .hist-list").onclick = async e => {
    const b = e.target.closest("[data-v]"); if (!b) return;
    document.querySelectorAll(".hist-list button").forEach(x => x.classList.toggle("on", x === b));
    try {
      const v = await api("/api/history?path=" + encodeURIComponent(path) + "&id=" + encodeURIComponent(b.dataset.v));
      sel = b.dataset.v; okb.disabled = false;
      $("#hist-view").innerHTML = diffHtml(cur, v.text);
    } catch (err) { $("#hist-view").innerHTML = '<p class="muted">' + esc(err.message) + "</p>"; }
  };
  const ok = await p;
  $("#modal .modal").classList.remove("wide"); okb.disabled = false;
  if (!ok || !sel) return;
  const t = S.tabs.find(x => x.path === path);
  if (t && t.dirty && !(await dialog("放棄還沒儲存的修改？", "<p>這篇還有沒儲存的修改，還原會蓋掉它們。</p>", "還原", true))) return;
  try {
    await api("/api/history/restore", { path, id: sel });
    if (t) { t.editing = false; await reloadTab(t); }
    toast("還原了 " + r.versions.find(v => v.id === sel).time + " 的版本。", { label: "復原", fn: () => showHistory(path) });
  } catch (e) { toast("沒還原：" + e.message); }
}

async function showAgentDiff(id, path) {
  let r;
  try { r = await api("/api/agent/diff?id=" + encodeURIComponent(id) + "&path=" + encodeURIComponent(path)); } catch (e) { toast(e.message); return; }
  $("#modal .modal").classList.add("wide");
  await dialog("「" + baseName(path) + "」這次的修改", '<div class="hist-view">' + (r.old ? diffHtml(r.old, r.new) : '<div class="d-add">' + esc(r.new).replace(/\n/g, "<br>") + "</div>") + "</div>" +
    '<p class="d-legend"><span class="d-add">這次加的</span> <span class="d-del">這次拿掉的</span></p>', "好");
  $("#modal .modal").classList.remove("wide");
}

// ============================================================ vaults: start screen and switcher

const tilde = p => String(p || "").replace(/^\/Users\/[^/]+/, "~");
let startState = null;

async function showStart(mode) {
  const el = $("#start");
  if (mode === "nokey") {
    el.innerHTML = '<div class="start-card"><h1>筆記</h1><p>這個頁面要從 app 的<strong>啟動連結</strong>打開。</p>' +
      '<p class="muted">啟動 app 時，終端機會印出一個帶存取碼的網址（<code>http://127.0.0.1:…/?k=…</code>）。用那個網址打開一次，這個瀏覽器之後就記得了。存取碼讓別的網站沒辦法透過瀏覽器讀你的筆記。</p></div>';
    el.hidden = false; return;
  }
  let v;
  try { v = await api("/api/vaults"); } catch (e) { return; }
  startState = { v, mode: mode || null, path: null };
  el.hidden = false;
  renderStart();
  if (mode === "open" || mode === "create") browse(mode === "create" ? (v.home + "/Documents") : v.home);
}

function renderStart() {
  const { v, mode } = startState, el = $("#start");
  const rows = v.vaults.map(x => '<div class="vault-row' + (x.path === v.current ? " current" : "") + '">' +
    '<button class="vault-open" data-open-vault="' + esc(x.path) + '"' + (x.exists ? "" : " disabled") + '><strong>' + esc(x.name) + "</strong><span>" + esc(tilde(x.path)) + "</span></button>" +
    (x.path === v.current ? '<span class="chip">正在用</span>' : "") + (x.protected ? '<span class="chip warn">受保護・唯讀</span>' : "") + (x.exists ? "" : '<span class="chip warn">找不到資料夾</span>') +
    '<button class="ghost" data-forget="' + esc(x.path) + '" title="從清單拿掉（資料夾本身不動）">×</button></div>').join("");
  el.innerHTML = '<div class="start-card">' + (v.current ? '<button class="start-close" data-s="close" title="回到筆記">×</button>' : "") +
    "<h1>" + (v.current ? "切換筆記庫" : "歡迎") + "</h1>" +
    '<p class="muted">筆記庫就是一個資料夾。任何放 Markdown 筆記的資料夾都可以，包括 Obsidian 的 vault。你的筆記不會被 AI 改動；AI 整理出來的頁面放在資料夾裡的 <code>wiki/</code>。</p>' +
    (rows ? '<div class="group">最近用過</div><div class="vault-list">' + rows + "</div>" : "") +
    '<div class="start-acts"><button data-s="create" class="' + (mode === "create" ? "primary" : "") + '">＋ 建立新的筆記庫</button><button data-s="open" class="' + (mode === "open" ? "primary" : "") + '">打開一個資料夾…</button></div>' +
    '<div id="start-pane"></div></div>';
}

async function browse(path) {
  let b;
  try { b = await api("/api/browse?path=" + encodeURIComponent(path)); } catch (e) { toast(e.message); return; }
  startState.path = b.path;
  const create = startState.mode === "create";
  const pane = $("#start-pane");
  pane.innerHTML = '<div class="browser"><div class="places">' + b.places.map(p => '<button data-browse="' + esc(p.path) + '" class="' + (p.path === b.path ? "on" : "") + '">' + esc(p.name) + "</button>").join("") + "</div>" +
    '<div class="crumbs">' + (b.parent ? '<button data-browse="' + esc(b.parent) + '" title="上一層">↑</button>' : "") + '<span>' + esc(tilde(b.path)) + "</span>" + (b.vault ? '<span class="chip">筆記庫</span>' : "") + "</div>" +
    '<div class="folders">' + (b.folders.length ? b.folders.map(f => '<button data-browse="' + esc(f.path) + '"><span>📁 ' + esc(f.name) + "</span>" + (f.vault ? '<span class="chip">筆記庫</span>' : "") + "</button>").join("") : '<p class="muted">（沒有子資料夾）</p>') + "</div>" +
    '<div class="browse-acts">' + (create
      ? '<label>名字 <input id="new-vault-name" class="dialog-input" placeholder="例如：我的筆記"></label><button class="primary" data-s="do-create">在「' + esc(b.name) + '」裡建立</button>'
      : b.root ? '<span class="muted small">選一個放筆記的資料夾（不能是整個家目錄）</span>'
        : '<button class="primary" data-s="do-open">打開「' + esc(b.name) + "」</button>") + "</div></div>" +
    '<p class="muted small">' + (create ? "會建立一個新資料夾，裡面有 <code>journal/</code>（日記）、<code>assets/</code>（附件）、<code>wiki/</code>（AI 的頁面）和 Obsidian 的設定，用 Obsidian 也能打開。"
      : "打開既有的資料夾不會改動裡面的檔案。有 <code>raw/</code> 資料夾的話，筆記就是 <code>raw/</code>；沒有的話，除了 <code>wiki/</code> 以外都算你的筆記。") + "</p>";
  if (create) $("#new-vault-name").focus();
}

async function switchVault(action, body) {
  if (S.tabs.some(t => t.dirty) && !(await dialog("還有沒儲存的修改", "<p>切換筆記庫會關掉所有分頁，沒儲存的修改會不見。</p>", "切換", true))) return;
  try {
    await api(action, body);
    S.tabs.forEach(t => (t.dirty = false));
    try { sessionStorage.removeItem("nav-max"); } catch (e) {}
    location.href = "/";
  } catch (e) { toast(e.message); }
}

$("#start").addEventListener("click", async e => {
  const b = e.target.closest("button"); if (!b) return;
  if (b.dataset.openVault) return switchVault("/api/vault/open", { path: b.dataset.openVault });
  if (b.dataset.forget) { await api("/api/vault/forget", { path: b.dataset.forget }); startState.v = await api("/api/vaults"); renderStart(); return; }
  if (b.dataset.browse) return browse(b.dataset.browse);
  const s = b.dataset.s;
  if (s === "close") { $("#start").hidden = true; return; }
  if (s === "open" || s === "create") { startState.mode = s; renderStart(); return browse(s === "create" ? startState.v.home + "/Documents" : startState.v.home); }
  if (s === "do-open") return switchVault("/api/vault/open", { path: startState.path });
  if (s === "do-create") {
    const name = $("#new-vault-name").value.trim();
    if (!name) { $("#new-vault-name").focus(); return; }
    return switchVault("/api/vault/create", { parent: startState.path, name });
  }
});
$("#start").addEventListener("keydown", e => {
  if (e.key === "Enter" && e.target.id === "new-vault-name" && !e.isComposing) $("#start [data-s=do-create]").click();
  if (e.key === "Escape" && startState && startState.v.current) $("#start").hidden = true;
});

$("#brand").addEventListener("click", async e => {
  let v;
  try { v = await api("/api/vaults"); } catch (err) { return; }
  const r = $("#brand").getBoundingClientRect();
  const items = v.vaults.filter(x => x.exists).slice(0, 8).map(x => ({ label: (x.path === v.current ? "✓ " : "　 ") + x.name, fn: () => x.path !== v.current && switchVault("/api/vault/open", { path: x.path }) }));
  items.push(null, { label: "打開其他資料夾…", fn: () => showStart("open") }, { label: "建立新的筆記庫…", fn: () => showStart("create") },
    { label: "管理清單…", fn: () => showStart() }, null, { label: "✦ 連接 AI…", fn: () => showConnect() },
    { label: "✦ 請 AI 檢查知識庫…", fn: () => startAgent("lint", {}) },
    { label: "在 Finder 中顯示", fn: () => api("/api/reveal", {}).catch(err => toast(err.message)) });
  showMenu(r.left, r.bottom + 4, items);
});

// ============================================================ ask AI (Claude Code, answers only)
// One box for everything: typing finds pages; Enter searches; ⌘↵ (or the "問 AI" row, first when the text reads
// like a question) asks. The conversation lives in the right column's AI tab, next to the note's suggestions.
// The app finds the pages (Jev, or keywords with Jev off) and sends them with the open note (never the journal);
// Claude Code, with no tools, writes the answer with [[page]] citations.

const AI = { turns: [], ctx: undefined };       // ctx undefined: follow the open note; null: none
const CLAUDE_MODELS = [["auto", "Claude：自動（Jev 選）"], ["haiku", "Claude Haiku：快、省"], ["sonnet", "Claude Sonnet：一般"], ["opus", "Claude Opus：最強、最耗額度"]];
const GPT_TIER = { fast: "快、省", balanced: "一般", strong: "最強、最耗額度" };
let GPT_MODELS = [];          // the models the user's ChatGPT plan offers, from its catalogue (costs no usage)
const isGpt = m => String(m || "").startsWith("chatgpt");
function aiModels() {
  const gpt = [["chatgpt", "ChatGPT：自動（Jev 選）"]].concat(GPT_MODELS.map(m =>
    ["chatgpt:" + m.slug, "ChatGPT " + m.name + "：" + GPT_TIER[m.tier] + (m.legacy ? "（舊版）" : "")]));
  const all = CLAUDE_MODELS.concat(gpt);
  if (!all.some(([v]) => v === aiModel()) && isGpt(aiModel())) all.push([aiModel(), "ChatGPT " + aiModel().slice(8)]);
  return all;
}
async function loadGptModels() {
  try { GPT_MODELS = (await api("/api/connect/chatgpt/models")).list || []; } catch (e) { GPT_MODELS = []; }
  if ($("#ai-model")) renderAI();
}
const AI_EFFORTS = [["auto", "思考：自動"], ["low", "思考：少"], ["medium", "思考：一般"], ["high", "思考：仔細"]];
const EFFORT_NAME = { low: "想得少", medium: "一般", high: "想得仔細" };
function pref(k) { try { return localStorage.getItem("notesapp." + k) || "auto"; } catch (e) { return "auto"; } }
function setPref(k, v) { try { localStorage.setItem("notesapp." + k, v); } catch (e) {} }
const aiModel = () => pref("aiModel"), aiEffort = () => pref("aiEffort");
S.rtab = "note";

function questionLike(raw) {
  return /[?？]\s*$/.test(raw) || /(嗎|吗|呢)\s*$/.test(raw) || raw.length >= 18 ||
    /^(為什麼|为什么|怎麼|怎么|怎樣|如何|什麼|什么|哪|是否|有沒有|有没有|請|请|幫我|帮我|比較|比较|總結|总结|解釋|解释|整理|列出|找出|告訴|告诉)/.test(raw) ||
    /^(what|why|how|who|when|which|compare|summari[sz]e|explain|list)\b/i.test(raw);
}

function showRight(name) {
  if (L.rightOff) toggleSide("right");
  S.rtab = name;
  document.querySelectorAll(".rtabs button").forEach(b => b.classList.toggle("on", b.dataset.rtab === name));
  $("#panel").hidden = name !== "note"; $("#ai").hidden = name !== "ai";
  if (name === "ai") { if (!$("#ai").innerHTML) renderAI(); updateAICtx(); }
}
document.querySelector(".rtabs").addEventListener("click", e => { const b = e.target.closest("[data-rtab]"); if (b) showRight(b.dataset.rtab); });

function aiContext() {
  if (AI.ctx === null) return null;
  const t = tab();
  if (!t || t.kind !== "note" || !t.note) return null;
  return { path: t.path, title: t.title, private: !!t.note.private };
}

async function askAI(q) {
  q = String(q || "").trim();
  if (!q) return;
  input.value = ""; quick.hidden = true; input.blur();
  if ($("#ai-input")) $("#ai-input").value = "";
  showRight("ai");
  const turn = { q, ctx: aiContext(), status: "finding", sources: [], text: "" };
  AI.turns.push(turn); renderAI();
  const jev = jevUsable();
  let r = jev ? JEV_CACHE.get(q) : null;
  try { if (!r || r.error) r = await api("/api/search?q=" + encodeURIComponent(q) + (jev ? "" : "&mode=bm25")); }
  catch (e) { r = { mode: "bm25", results: [], error: e.message }; }
  turn.mode = r.mode; turn.searchError = r.error; turn.sources = (r.results || []).slice(0, 8);
  turn.status = "asking"; renderAI();
  const history = AI.turns.filter(t => t !== turn && t.status === "done").map(t => ({ q: t.q, a: t.text }));
  try {
    const gpt = isGpt(aiModel());
    const a = await api("/api/ai/ask", { q, context: turn.ctx && !turn.ctx.private ? turn.ctx.path : null,
      sources: turn.sources.map(x => x.path), history, provider: gpt ? "chatgpt" : "claude",
      model: aiModel(), effort: aiEffort(), jev: !!jevUsable() });
    Object.assign(turn, { id: a.id, used: a.used, ctxUsed: a.context, choice: a.choice, status: "writing" });
  } catch (e) {
    turn.status = "error"; turn.error = e.message; renderAI();
    if (e.data && e.data.connect) showConnect();
    return;
  }
  renderAI();
  while (turn.status === "writing") {
    await new Promise(res => setTimeout(res, 250));
    let p;
    try { p = await api("/api/ai/poll?id=" + turn.id); } catch (e) { turn.status = "error"; turn.error = e.message; break; }
    const changed = p.text !== turn.text || p.status !== "running";
    if (p.model !== turn.model || p.why !== turn.why || p.retried !== turn.retried) Object.assign(turn, { model: p.model, effort: p.effort, why: p.why, retried: p.retried }), renderAI();
    turn.text = p.text; turn.seconds = p.seconds;
    if (p.status !== "running") { turn.status = p.status; turn.error = p.error; }
    if (changed) renderAI();
  }
  renderAI();
}

// ------------------------------------------------------------ the wiki agent (plan → your OK → act → undo)
const AGENT_STEPS = 6;
async function startAgent(task, extra) {
  if (S.tree.read_only) return toast("這個筆記庫只能看，不能改。");
  showRight("ai");
  const m = aiModel(), e = aiEffort(), gpt = isGpt(m);
  const turn = { kind: "agent", task, status: "starting", steps: [] };
  AI.turns.push(turn); renderAI();
  const body = Object.assign({ task, provider: gpt ? "chatgpt" : "claude", model: gpt ? m : m === "auto" ? null : m,
    effort: e === "auto" ? null : e, jev: !!jevUsable(), ui_lang: navigator.language }, extra);
  try { const r = await api("/api/agent/start", body); turn.id = r.id; }
  catch (err) {
    turn.status = "error"; turn.error = err.message; renderAI();
    if (err.data && err.data.connect) showConnect();
    return;
  }
  pollAgent(turn);
}
async function pollAgent(turn) {
  let last = "";
  for (;;) {
    let p;
    try { p = await api("/api/agent/poll?id=" + turn.id); } catch (e) { turn.status = "error"; turn.error = e.message; break; }
    Object.assign(turn, p);
    const sig = p.status + p.steps.length + (p.live || "").length;
    if (sig !== last) { last = sig; renderAI(); }
    if (!["planning", "acting"].includes(p.status)) break;
    await new Promise(res => setTimeout(res, 1000));
  }
  renderAI();
  if (turn.status === "done") { await refreshTree(); }
}
const KIND = { created: "新", changed: "改", deleted: "刪" };
function stepsHtml(t, phase) {
  const st = t.steps.filter(x => x.phase === phase);
  if (!st.length) return "";
  const row = x => '<div class="ag-step' + (x.ok === false ? " bad" : "") + '">' + (x.ok === false ? "✗ " : x.ok ? "· " : "… ") + esc(x.what) + "</div>";
  const live = (phase === "plan" ? t.status === "planning" : t.status === "acting");
  if (live) return '<div class="ag-steps">' + st.slice(-AGENT_STEPS).map(row).join("") + "</div>";
  return '<details class="ag-steps"><summary>' + (phase === "plan" ? "讀了、查了 " : "做了 ") + st.length + " 步</summary>" + st.map(row).join("") + "</details>";
}
function planHtml(plan) {
  if (!plan) return '<div class="banner">AI 沒有給出計畫格式；看上面的說明決定要不要繼續。</div>';
  const li = xs => xs.map(x => "<li>" + x + "</li>").join("");
  let h = '<div class="ag-plan"><div class="ag-sum">' + esc(plan.summary || "") + "</div>";
  if ((plan.takeaways || []).length) h += "<h4>重點</h4><ul>" + li(plan.takeaways.map(esc)) + "</ul>";
  if ((plan.create || []).length) h += "<h4>新增 " + plan.create.length + " 頁</h4><ul>" + li(plan.create.map(x => md("[[" + x.page + "]]").replace(/^<p>|<\/p>$/g, "") + ' <span class="muted">' + esc(x.type || "") + "</span><div class=\"muted\">" + esc(x.why || "") + "</div>")) + "</ul>";
  if ((plan.update || []).length) h += "<h4>更新 " + plan.update.length + " 頁</h4><ul>" + li(plan.update.map(x => md("[[" + x.page + "]]").replace(/^<p>|<\/p>$/g, "") + '<div class="muted">' + esc(x.why || "") + "</div>")) + "</ul>";
  if (plan.notes) h += '<h4>其他</h4><p class="muted">' + esc(plan.notes) + "</p>";
  return h + "</div>";
}
function agentHtml(t) {
  const name = { ingest: "整理筆記", analysis: "存成分析頁", lint: "檢查知識庫" }[t.task] || "工作";
  let h = '<div class="ai-turn ag"><div class="ai-q">✦ ' + esc(t.label || name) + "</div>";
  if (t.model) h += '<div class="ai-ctxline">' + esc(cap(t.model)) + "，" + esc(EFFORT_NAME[t.effort] || t.effort) + (t.jev ? " · Jev 開" : " · Jev 關") + "</div>";
  h += '<div class="ai-a">';
  if (t.status === "starting") h += '<div class="muted"><span class="spin"></span> 準備…</div>';
  if (t.status === "planning") h += '<div class="muted"><span class="spin"></span> 讀筆記、找相關的頁，擬計畫（還不會改任何東西）…</div>';
  h += stepsHtml(t, "plan");
  if (t.message) h += md(t.message);
  if (t.plan !== undefined && t.status !== "planning" && t.status !== "starting" && t.task && (t.message || t.plan)) h += planHtml(t.plan);
  if (t.status === "waiting") h += '<textarea class="ag-note" rows="2" placeholder="想改計畫的話寫在這裡（可不填），例如：不要建立 X 頁"></textarea>' +
    '<div class="ai-acts"><button class="primary" data-ag-go="' + esc(t.id) + '">照這樣做</button><button data-ag-cancel="' + esc(t.id) + '">不要做</button></div>' +
    '<p class="muted small">只會改知識庫（wiki/）；你的筆記不會被改。做完會列出每一頁的修改，可以全部復原。</p>';
  if (t.status === "acting") h += '<div class="muted"><span class="spin"></span> 動手中：寫來源頁、更新相關的頁…</div>';
  h += stepsHtml(t, "act");
  if (t.status === "acting" && t.live) h += '<div class="muted small">' + esc(t.live.slice(-200)) + "</div>";
  if (t.status === "done" || ((t.status === "stopped" || t.status === "error") && (t.changes || []).length)) {
    if (t.report && t.status === "done") h += md(t.report);
    const ch = t.changes || [];
    h += '<div class="ag-changes"><h4>' + (ch.length ? "改了 " + ch.length + " 個檔案" : "沒有改任何檔案") + (t.undone ? "（已全部復原）" : "") + "</h4>" +
      ch.map(c => '<div class="ag-ch"><span class="ag-k ' + c.kind + '">' + KIND[c.kind] + "</span>" + '<a class="wl" data-path="' + esc(c.path) + '">' + esc(c.path.replace(/^wiki\//, "").replace(/\.md$/, "")) + "</a>" +
        '<button class="ghost" data-ag-diff="' + esc(c.path) + '" data-ag-id="' + esc(t.id) + '">差異</button></div>').join("") + "</div>";
    if ((t.outside || []).length) h += '<div class="banner">注意：這段時間知識庫以外也有檔案變了（可能是你自己改的）：' + t.outside.slice(0, 5).map(esc).join("、") + "</div>";
    if (ch.length && !t.undone) h += '<div class="ai-acts"><button data-ag-undo="' + esc(t.id) + '">全部復原</button></div>';
  }
  if (t.status === "error") h += '<div class="banner">沒有完成：' + esc(t.error || "") + (/log ?in|login|auth|登入/i.test(t.error || "") ? "。在終端機打 <code>claude</code> 登入後再試。" : "") + "</div>";
  if (t.status === "stopped") h += '<div class="ai-meta">已停止。' + ((t.changes || []).length ? "" : "") + "</div>";
  if (t.status === "cancelled") h += '<div class="ai-meta">沒有執行。</div>';
  if (["planning", "acting"].includes(t.status)) h += '<div class="ai-acts"><button data-ag-stop="' + esc(t.id) + '">停止</button></div>';
  if (t.cost && !["planning", "acting", "starting"].includes(t.status)) h += '<div class="ai-meta">約 $' + t.cost.toFixed(2) + "（以 API 價格換算，用的是你的 Claude 額度）" + (t.seconds ? " · " + Math.round(t.seconds) + " 秒" : "") + "</div>";
  return h + "</div></div>";
}

function turnHtml(t) {
  if (t.kind === "agent") return agentHtml(t);
  let h = '<div class="ai-turn"><div class="ai-q">' + esc(t.q) + "</div>";
  if (t.ctx) h += '<div class="ai-ctxline">背景：' + esc(t.ctx.title) + (t.ctx.private ? "（日記，不送出）" : "") + "</div>";
  if (t.status === "finding") return h + '<div class="ai-a muted"><span class="spin"></span> 找相關的頁…</div></div>';
  if (t.status === "asking") return h + '<div class="ai-a muted"><span class="spin"></span> 交給 Claude…</div></div>';
  if (t.status === "writing" && !t.text) h += '<div class="ai-a muted"><span class="spin"></span> ' + (!t.model ? (t.choice === "auto" ? "Jev 選模型…" : "準備…") :
    esc(cap(t.model)) + (t.retried ? " 重新回答（第 " + (t.retried + 1) + " 次）…" : " 想一下…")) + "</div>";
  h += '<div class="ai-a">' + (t.text ? md(t.text) : "") + (t.status === "writing" && t.text ? '<span class="ai-caret"></span>' : "");
  if (t.status === "error") h += '<div class="banner">沒有回答：' + esc(t.error || "") +
    (/log ?in|login|auth|登入/i.test(t.error || "") ? "。在終端機打 <code>claude</code> 登入後再試。" : "") + "</div>";
  if (t.status === "stopped") h += '<div class="ai-meta">已停止。</div>';
  const used = t.used || [];
  if (t.status !== "writing" && (used.length || t.ctxUsed)) {
    h += '<details class="ai-used"><summary>讀了' + (t.ctxUsed ? "背景筆記和 " : " ") + used.length + " 頁" +
      (t.mode === "jev" ? "（Jev 找的）" : "（關鍵字找的" + (t.searchError ? "，Jev 沒回應" : "") + "）") + (t.model ? " · " + esc(cap(t.model)) + "，" + esc(EFFORT_NAME[t.effort] || t.effort) + (t.why ? "（" + esc(t.why) + "）" : "") : "") + (t.seconds ? " · " + t.seconds + " 秒" : "") + "</summary>" +
      (t.ctxUsed ? '<a class="wl" data-path="' + esc(t.ctxUsed.path) + '">' + esc(t.ctxUsed.title) + "</a>（背景）" : "") +
      used.map(u => '<a class="wl" data-path="' + esc(u.path) + '">' + esc(u.title) + "</a>").join("") + "</details>";
  }
  if (t.status === "writing") h += '<div class="ai-acts"><button data-stop="' + esc(t.id) + '">停止</button></div>';
  else if (t.status === "done") h += '<div class="ai-acts"><button data-save="' + AI.turns.indexOf(t) + '">存成分析頁</button>' +
    (t.ctx && !t.ctx.private && mine(t.ctx.path) ? '<button data-ingest="' + esc(t.ctx.path) + '">整理「' + esc(t.ctx.title) + "」</button>" : "") + "</div>";
  return h + "</div></div>";
}

const cap = m => m ? m[0].toUpperCase() + m.slice(1) : "";
document.addEventListener("change", e => {
  if (e.target.id === "ai-model") setPref("aiModel", e.target.value);
  if (e.target.id === "ai-effort") setPref("aiEffort", e.target.value);
});

function renderAI() {
  const el = $("#ai");
  const old = $("#ai-input"), draft = old ? old.value : "", focused = old && document.activeElement === old;
  const conv0 = $("#ai-conv"), atBottom = !conv0 || conv0.scrollHeight - conv0.scrollTop - conv0.clientHeight < 40;
  let conv = "";
  if (!AI.turns.length) {
    const ctx = aiContext();
    const ex = (ctx && !ctx.private ? ["這篇的重點是什麼？", "這篇和我知識庫裡哪些概念有關？"] : []).concat(["我的筆記裡有哪些互相矛盾的說法？", "保險和信任有什麼關係？"]);
    conv = '<div class="ai-intro"><h3>✦ 問 AI</h3><p>在上面的搜尋框打問題按 ⌘↵，或在下面直接問。app 先找出相關的頁，連同目前打開的筆記交給 Claude，回答裡的頁面都能點。</p>' +
      '<p class="muted">Claude 只回答，不能開檔案、也不會改任何東西。日記永遠不送出。</p>' +
      '<div class="ai-examples">' + ex.map(x => '<button data-example="' + esc(x) + '">' + esc(x) + "</button>").join("") + "</div></div>";
  }
  conv += AI.turns.map(turnHtml).join("");
  el.innerHTML = '<div class="ai-head"><span>對話</span>' + (AI.turns.length ? '<button class="ghost" data-new>新對話</button>' : "") + "</div>" +
    '<div class="ai-conv" id="ai-conv">' + conv + "</div>" +
    '<div class="ai-composer"><div id="ai-ctx" class="ai-ctx"></div>' +
    '<textarea id="ai-input" rows="2" placeholder="接著問…（Enter 送出，Shift+Enter 換行）"></textarea>' +
    '<div class="ai-send-row"><select id="ai-model" title="回答用的模型">' + aiModels().map(([v, l]) => '<option value="' + v + '"' + (v === aiModel() ? " selected" : "") + ">" + l + "</option>").join("") +
    "</select>" +
    '<select id="ai-effort" title="想多深：自動＝照你在問題裡說的，或 Jev 判斷">' + AI_EFFORTS.map(([v, l]) => '<option value="' + v + '"' + (v === aiEffort() ? " selected" : "") + ">" + l + "</option>").join("") +
    '</select><button class="primary" id="ai-send">送出</button></div><div id="ai-sends" class="muted"></div></div>';
  const inp = $("#ai-input"); inp.value = draft; if (focused) inp.focus();
  const c = $("#ai-conv"); if (atBottom) c.scrollTop = c.scrollHeight; else if (conv0) c.scrollTop = conv0.scrollTop;
  updateAICtx();
}

function updateAICtx() {
  const box = $("#ai-ctx");
  if (!box) return;
  const ctx = aiContext();
  box.innerHTML = ctx ? '<span class="chip ctx">以「' + esc(ctx.title) + "」為背景" + (ctx.private ? "（日記，不送出）" : "") + ' <button data-ctx-off title="不要用這篇當背景">×</button></span>'
    : AI.ctx === null && tab() && tab().kind === "note" ? '<button class="link-btn" data-ctx-on>＋ 用目前的筆記當背景</button>' : '<span class="muted">沒有背景筆記</span>';
  $("#ai-sends").textContent = "會送給 " + (isGpt(aiModel()) ? "ChatGPT" : "Claude") + "：問題、相關的頁" + (ctx && !ctx.private ? "、背景筆記" : "") + "、這段對話。日記不送。";
}

$("#ai").addEventListener("click", e => {
  const a = e.target.closest("a.wl");
  if (a && a.dataset.path) { e.preventDefault(); openNote(a.dataset.path, { newTab: e.metaKey || e.ctrlKey }); return; }
  const att = e.target.closest("a.att");
  if (att) { e.preventDefault(); openNote(att.dataset.file); return; }
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.example) return askAI(b.dataset.example);
  if (b.dataset.stop) { api("/api/ai/stop", { id: b.dataset.stop }).catch(() => {}); return; }
  if (b.dataset.save !== undefined) {
    const t = AI.turns[+b.dataset.save];
    return startAgent("analysis", { q: t.q, answer: t.text, sources: (t.used || []).map(u => u.path) });
  }
  if (b.dataset.ingest) return startAgent("ingest", { path: b.dataset.ingest });
  if (b.dataset.agGo) {
    const note = (b.closest(".ai-a").querySelector(".ag-note") || {}).value || "";
    const t = AI.turns.find(x => x.id === b.dataset.agGo);
    api("/api/agent/approve", { id: b.dataset.agGo, note }).then(() => { t.status = "acting"; renderAI(); pollAgent(t); }).catch(err => toast(err.message));
    return;
  }
  if (b.dataset.agCancel) { const t = AI.turns.find(x => x.id === b.dataset.agCancel); api("/api/agent/stop", { id: t.id }).then(() => { t.status = "cancelled"; renderAI(); }); return; }
  if (b.dataset.agStop) { api("/api/agent/stop", { id: b.dataset.agStop }).catch(() => {}); return; }
  if (b.dataset.agDiff) return showAgentDiff(b.dataset.agId, b.dataset.agDiff);
  if (b.dataset.agUndo) {
    const t = AI.turns.find(x => x.id === b.dataset.agUndo);
    dialog("全部復原？", "<p>把這次改的 " + t.changes.length + " 個知識庫檔案放回改之前的樣子；新建的頁移到 <code>.trash/</code>。這次寫的內容會先留成一版。</p>", "全部復原", true).then(ok => {
      if (!ok) return;
      api("/api/agent/undo", { id: t.id }).then(async () => { t.undone = true; renderAI(); await refreshTree(); toast("復原了。"); }).catch(err => toast(err.message));
    });
    return;
  }
  if (b.hasAttribute("data-ctx-off")) { AI.ctx = null; updateAICtx(); return; }
  if (b.hasAttribute("data-ctx-on")) { AI.ctx = undefined; updateAICtx(); return; }
  if (b.hasAttribute("data-new")) { AI.turns = []; AI.ctx = undefined; renderAI(); return; }
  if (b.id === "ai-send") { askAI($("#ai-input").value); return; }
});
$("#ai").addEventListener("keydown", e => {
  if (e.target.id !== "ai-input" || e.key !== "Enter" || e.shiftKey || e.isComposing || e.keyCode === 229) return;
  e.preventDefault(); askAI(e.target.value);
});


// ============================================================ connect AI (Claude, ChatGPT, Jev) and the wiki's language
// Each person uses their own: their Claude subscription through Claude Code (Anthropic's own sign-in in the
// browser; the app never sees it), their ChatGPT plan through OpenAI's "Sign in with ChatGPT", their own Jev key.


const CN = { open: false, timer: null, models: null, jevMsg: "", codeMsg: "" };

function showConnect() {
  let el = $("#connect");
  if (!el) {
    el = document.createElement("div"); el.id = "connect"; el.className = "cn-back";
    el.innerHTML = '<div class="cn" role="dialog" aria-modal="true" aria-label="連接 AI"><div class="cn-head"><h2>連接 AI</h2>' +
      '<button class="ghost" data-cn-close title="關閉">✕</button></div><div id="cn-body"><p class="muted">檢查中…</p></div></div>';
    document.body.append(el);
    el.addEventListener("click", connectClick);
    el.addEventListener("keydown", e => {
      if (e.key === "Escape") closeConnect();
      if (e.key === "Enter" && e.target.id === "cn-jev-key") connectClick({ target: $("[data-cn=jev-save]") });
    });
  }
  el.hidden = false; CN.open = true;
  refreshConnect();
}
function closeConnect() {
  const el = $("#connect"); if (el) el.hidden = true;
  CN.open = false; clearTimeout(CN.timer);
}

async function refreshConnect() {
  clearTimeout(CN.timer);
  if (!CN.open) return;
  let st;
  try { st = await api("/api/connect/status"); } catch (e) { $("#cn-body").innerHTML = '<p class="cn-err">' + esc(e.message) + "</p>"; return; }
  if (!CN.open) return;
  const keep = { key: ($("#cn-jev-key") || {}).value || "", focus: document.activeElement && document.activeElement.id };
  const html = [claudeCard(st.claude), chatgptCard(st.chatgpt), jevCard(st.jev)];
  const body = $("#cn-body");
  if (!body.querySelector(".cn-slot")) {
    body.innerHTML = '<p class="muted cn-lead">用你自己的訂閱或金鑰。app 不經手你的帳號密碼，用量算在你自己的方案裡。至少連接 Claude 或 ChatGPT 其中一個。</p>' +
      '<div class="cn-slot"></div><div class="cn-slot"></div><div class="cn-slot"></div>';
  }
  // only the cards that changed are redrawn: a poll while Claude installs never swallows a click elsewhere
  body.querySelectorAll(".cn-slot").forEach((slot, i) => {
    if (slot.dataset.html !== html[i]) { slot.innerHTML = html[i]; slot.dataset.html = html[i]; }
  });
  if ($("#cn-jev-key") && !$("#cn-jev-key").value) $("#cn-jev-key").value = keep.key;
  if (keep.focus && $("#" + keep.focus) && document.activeElement.id !== keep.focus) $("#" + keep.focus).focus();
  if (st.chatgpt.welcome) gptWelcome();
  const cj = st.claude.job || {};
  if (cj.status === "running" || (cj.status === "waiting" && !st.claude.logged_in)) CN.timer = setTimeout(refreshConnect, 2000);
  // the answer box uses whichever AI is connected, without asking
  if (st.chatgpt.connected && !st.claude.connected && !isGpt(aiModel())) setPref("aiModel", "chatgpt");
  if (!st.chatgpt.connected && st.claude.connected && isGpt(aiModel())) setPref("aiModel", "auto");
  if (st.chatgpt.connected && !GPT_MODELS.length) loadGptModels();
  if (!st.chatgpt.connected) GPT_MODELS = [];
  if (CN.waitGpt && !st.chatgpt.connected) CN.timer = setTimeout(refreshConnect, 2000);
  if (st.chatgpt.connected) CN.waitGpt = false;
}

// Every card follows one rule: 未連接 → 「連接」; 連接中… → 「取消」; 已連接 → 「中斷連接」 (and 「管理用量」 where the
// service has a usage page). Each card: what it is for, what is in use now, the buttons, one line on what the app keeps.
const CN_STATE = { off: "未連接", wait: "連接中…", on: "已連接" };
function card(name, st, o) {
  return '<section class="cn-card"><div class="cn-row"><h3>' + name + '</h3><span class="cn-state ' + st + '">' + CN_STATE[st] + "</span></div>" +
    "<p>" + o.purpose + "</p>" + (o.detail ? '<div class="cn-detail">' + o.detail + "</div>" : "") +
    '<div class="cn-acts">' + o.acts + "</div>" + (o.err ? '<p class="cn-err">' + o.err + "</p>" : "") +
    (o.note ? '<p class="muted small">' + o.note + "</p>" : "") + "</section>";
}
const cnBtn = (cn, label, primary) => '<button class="' + (primary ? "primary" : "ghost") + '" data-cn="' + cn + '">' + label + "</button>";
const cnLink = (href, label) => '<a href="' + href + '" target="_blank" rel="noopener">' + label + "</a>";

function claudeCard(c) {
  const job = c.job || {};
  const installing = job.kind === "install" && job.status === "running";
  const waiting = job.kind === "login" && job.status === "waiting" && !c.logged_in;
  const o = { purpose: "用你的 Claude 訂閱（Pro、Max）回答問題、整理知識庫。" };
  let st;
  if (c.connected) {
    st = "on";
    const plan = c.subscription ? "Claude " + (c.plan ? cap(c.plan) + " " : "") + "訂閱" : "Claude API 金鑰（按用量計費）";
    o.detail = "目前使用：你的 " + esc(plan) + "。" + (c.subscription ? "" : '<span class="cn-err">這不是訂閱登入，用量會按 API 計費。</span>');
    o.acts = cnBtn("claude-disconnect", "中斷連接") + cnLink("https://claude.ai/settings/usage", "管理用量");
    o.note = "中斷連接只是 app 不再使用 Claude，你的 Claude Code 登入不受影響。";
  } else if (installing || waiting) {
    st = "wait";
    o.detail = installing ? installProgress(c.install || {})
      : job.terminal ? "已經打開終端機，照視窗裡的說明在瀏覽器登入，完成後這裡會自動變成已連接。"
      : "瀏覽器會出現 Claude 的登入頁，登入並按「Authorize」，這裡會自動變成已連接。";
    o.acts = cnBtn("claude-cancel", "取消") + (waiting && !job.terminal ? cnBtn("claude-terminal", "瀏覽器沒出現？改用終端機登入") : "");
    o.note = "登入完全在 Anthropic 的網頁完成，app 不經手你的帳號密碼。";
  } else {
    st = "off";
    o.acts = cnBtn("claude-connect", "連接 Claude", true);
    o.note = c.logged_in ? "你已經登入 Claude Code，按一下就會用它。"
      : (c.installed ? "" : "會先用 Anthropic 官方安裝程式裝好 Claude Code（不用管理員密碼），") + "接著在瀏覽器登入。app 不經手你的帳號密碼。";
  }
  if (job.status === "error" && job.error) o.err = esc(job.error) + (job.tail ? '<br><span class="small">' + esc(job.tail.slice(-200)) + "</span>" : "");
  return card("Claude", st, o);
}

// The official installer's progress: getting ready → downloading (bar, MB, time left) → installing → sign-in.
function installProgress(p) {
  const mins = s => s >= 90 ? "約 " + Math.round(s / 60) + " 分鐘" : "不到 2 分鐘";
  let pct = 0, line;
  if (p.phase === "setup") { pct = 100; line = "下載完成，正在安裝…"; }
  else if (p.phase === "download" && p.pct != null) {
    pct = p.pct;
    line = pct + "%・" + p.mb + " / " + p.total_mb + " MB" + (p.eta != null ? "・還要" + mins(p.eta) : "");
  } else if (p.phase === "download") line = "已下載 " + p.mb + " MB";
  else line = "選擇最快的下載路線…";
  const bar = '<div class="cn-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + pct +
    '"' + (p.phase === "download" && p.pct == null || !p.phase || p.phase === "start" ? ' data-busy="1"' : "") +
    '><span style="width:' + pct + '%"></span></div>';
  return "正在用 Anthropic 官方安裝程式安裝 Claude Code，裝好會直接帶你登入。" + bar +
    '<div class="muted small cn-progress-line">' + esc(line) + "</div>";
}

function chatgptCard(g) {
  const o = { purpose: "用你的 ChatGPT 付費方案（Go、Plus、Pro）回答問題。免費版 OpenAI 不開放給其他 app。" };
  let st;
  if (g.connected) {
    st = "on";
    o.detail = "目前使用：<b>Using ChatGPT plan</b>" + (g.email ? '<span class="muted">（' + esc(g.email) + "）</span>" : "") + "。" +
      (g.plan_use ? "" : '<span class="cn-err">你沒有同意讓 app 使用方案額度，請中斷後重新連接。</span>');
    o.acts = cnBtn("gpt-signout", "中斷連接") + cnLink("https://chatgpt.com/settings/usage", "Manage usage");
    o.note = "中斷連接會撤銷並刪除這個 app 的 ChatGPT 登入。";
  } else if (CN.waitGpt) {
    st = "wait";
    o.detail = "等你在瀏覽器同意…如果 OpenAI 的頁面說「無法取得必要權限」，表示這個帳號的方案不能用在其他 app。";
    o.acts = cnBtn("gpt-cancel", "取消");
    o.note = "登入完全在 OpenAI 的網頁完成，app 不經手你的帳號密碼。";
  } else {
    st = "off";
    o.acts = '<button class="primary cn-gpt" data-cn="gpt-start">Continue with ChatGPT</button>';
    o.note = "在 OpenAI 的網頁同意後就連上了。用量算在你的 ChatGPT 方案，和其他 app 共用同一份額度。";
  }
  return card("ChatGPT", st, o);
}

function jevCard(j) {
  const o = { purpose: "幫 app 找相關的頁、判斷問題難度、檢查整理結果。可以不連，app 會改用關鍵字搜尋。" };
  let st;
  if (j.connected) {
    st = "on";
    const where = { app: "存在這個 app", env: "環境變數 TYPESAFE_API_KEY", shared: "~/.config/typesafe" }[j.source];
    o.detail = "目前使用：你的 TypeSafe 金鑰（" + where + "）。";
    o.acts = cnBtn("jev-remove", "中斷連接");
    o.note = j.source === "app" ? "中斷連接會刪掉 app 存的金鑰。" : "中斷連接只是 app 不再使用 Jev，你的金鑰檔案不受影響。";
  } else if (CN.jevEditing) {
    st = "off";                                    // nothing is running yet: it waits for the key
    o.detail = '<input id="cn-jev-key" type="password" autocomplete="off" placeholder="貼上 TypeSafe API 金鑰">';
    o.acts = cnBtn("jev-save", "儲存", true) + cnBtn("jev-cancel", "取消");
    o.note = "貼上金鑰後按「儲存」。儲存前會先試一次，確定能用。金鑰只存在這台電腦（只有你的帳號能讀）。";
  } else {
    st = "off";
    o.acts = cnBtn("jev-connect", "連接 Jev", true);
    o.note = "用你自己的 TypeSafe 金鑰，費用很低。";
  }
  if (CN.jevMsg) o.err = esc(CN.jevMsg);
  return card("Jev", st, o);
}

async function gptWelcome() {
  await api("/api/connect/chatgpt/welcomed", {}).catch(() => {});
  dialog("You're using your ChatGPT plan", "<p>Eligible usage in this app uses your ChatGPT plan. Manage usage in your ChatGPT settings.</p>" +
    '<p class="muted">之後在 app 裡用 ChatGPT 回答，用量算在你的 ChatGPT 方案。可以在 <a href="https://chatgpt.com/settings/usage" target="_blank" rel="noopener">ChatGPT 設定 → Usage</a> 查看。</p>', "Got it");
}

async function connectClick(e) {
  const t = e.target.closest ? e.target.closest("[data-cn], [data-cn-close]") : e.target;
  if (!t) { if (e.target && e.target.id === "connect") closeConnect(); return; }
  if (t.hasAttribute("data-cn-close")) return closeConnect();
  const what = t.dataset.cn;
  const run = async (path, body = {}) => { try { return await api(path, body); } catch (err) { toast(err.message); return null; } };
  const sure = (name, more) => dialog("中斷 " + name + " 連接？", "<p>" + more + "之後隨時可以再連接。</p>", "中斷連接", true);
  if (what === "claude-connect") await run("/api/connect/claude/connect");
  else if (what === "claude-terminal") await run("/api/connect/claude/terminal");
  else if (what === "claude-cancel") await run("/api/connect/claude/cancel");
  else if (what === "claude-disconnect") { if (await sure("Claude", "app 不再使用 Claude；你的 Claude Code 登入不受影響。")) await run("/api/connect/claude/disconnect"); }
  else if (what === "gpt-start") { if (await run("/api/connect/chatgpt/start")) CN.waitGpt = true; }
  else if (what === "gpt-cancel") CN.waitGpt = false;
  else if (what === "gpt-signout") { if (await sure("ChatGPT", "app 會撤銷並刪除這台電腦上的 ChatGPT 登入。")) await run("/api/connect/chatgpt/signout"); }
  else if (what === "jev-connect") { const r = await run("/api/connect/jev/connect"); CN.jevMsg = ""; if (r && r.need_key) CN.jevEditing = true; else await refreshTree(); }
  else if (what === "jev-cancel") { CN.jevEditing = false; CN.jevMsg = ""; }
  else if (what === "jev-save") {
    const k = ($("#cn-jev-key") || {}).value.trim(); if (!k) return;
    t.disabled = true; t.textContent = "測試中…";
    try { await api("/api/connect/jev/save", { key: k }); CN.jevMsg = ""; CN.jevEditing = false; await refreshTree(); }
    catch (err) { CN.jevMsg = err.message; }
  }
  else if (what === "jev-remove") {
    const own = ((await api("/api/connect/status").catch(() => ({}))).jev || {}).source === "app";
    if (await sure("Jev", own ? "app 會刪掉它存的金鑰。" : "app 不再使用 Jev；你的金鑰檔案不受影響。")) { await run("/api/connect/jev/remove"); await refreshTree(); }
    CN.jevMsg = "";
  }
  refreshConnect();
}

// at start: the ChatGPT plan's models for the model menu; on the first run, nothing connected → the page once
(async () => {
  try {
    const st = await api("/api/connect/status");
    if (st.chatgpt.connected) loadGptModels();
    if (store.get("connect-seen", false)) return;
    if (!(st.claude.connected || st.chatgpt.connected)) showConnect();
    store.set("connect-seen", true);
  } catch (e) {}
})();
