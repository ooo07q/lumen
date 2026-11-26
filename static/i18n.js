// Lumen's interface languages. The text in app.js and index.html is Traditional Chinese; T() gives it in the
// chosen language: Simplified Chinese by character table; English, Japanese and Korean from LUMEN_EN, LUMEN_JA and
// LUMEN_KO (i18n-en.js, i18n-ja.js, i18n-ko.js; a string missing in Japanese or Korean shows in English). The default
// is the system's language; a choice made in the menu is remembered in this browser.
const LANGS = { "zh-Hant": "繁體中文", "zh-Hans": "简体中文", en: "English", ja: "日本語", ko: "한국어" };

function systemLang() {
  for (const l of navigator.languages || [navigator.language || ""]) {
    const s = l.toLowerCase();
    if (/^zh-(tw|hk|mo)|^zh-hant/.test(s)) return "zh-Hant";
    if (s.startsWith("zh")) return "zh-Hans";
    if (s.startsWith("en")) return "en";
    if (s.startsWith("ja")) return "ja";
    if (s.startsWith("ko")) return "ko";
  }
  return "en";
}
function chosenLang() {
  try { const v = localStorage.getItem("lumen.lang"); if (v && LANGS[v]) return v; } catch (e) {}
  return "";
}
const LANG = chosenLang() || systemLang();
function setLang(v) {
  try { v ? localStorage.setItem("lumen.lang", v) : localStorage.removeItem("lumen.lang"); } catch (e) {}
  location.reload();
}
document.documentElement.lang = LANG;

// Simplified: the same character table the search uses (fetched once, before the page is drawn).
let T2S_UI = null;
if (LANG === "zh-Hans") {
  try {
    const x = new XMLHttpRequest(); x.open("GET", "/api/t2s", false); x.send();
    if (x.status === 200) T2S_UI = JSON.parse(x.responseText);
  } catch (e) {}
}
const toHans = s => { if (!T2S_UI) return s; let o = ""; for (const c of s) o += T2S_UI[c] || c; return o; };

// The dictionary for the chosen language; Japanese and Korean fall back to English for a string they lack.
const DICT_OWN = LANG === "en" ? LUMEN_EN : LANG === "ja" && typeof LUMEN_JA !== "undefined" ? LUMEN_JA
  : LANG === "ko" && typeof LUMEN_KO !== "undefined" ? LUMEN_KO : null;
const USE_DICT = !!DICT_OWN || LANG === "ja" || LANG === "ko";
const look = s => DICT_OWN && DICT_OWN[s] !== undefined ? DICT_OWN[s] : LUMEN_EN[s];

// Messages with %s / %d holes (from the server) as patterns, longest first.
const KEYS = typeof LUMEN_EN === "undefined" ? [] : Object.keys(LUMEN_EN);
const EN_PATTERNS = KEYS.filter(k => /%[sd]/.test(k)).map(k => {
  const re = new RegExp("^" + k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/%[sd]/g, "([\\s\\S]*?)") + "$");
  return [re, k];
});
const EN_PIECES = KEYS.filter(k => k.length >= 2 && !/%[sd]|[<>"=]/.test(k)).sort((a, b) => b.length - a.length);
// Chinese punctuation left between translated pieces: Western forms for English and Korean, Japanese keeps its own.
const PUNCT = LANG === "ja" ? { "；": "；", "：": "：", "、": "、", "「": "「", "」": "」", "（": "（", "）": "）", "，": "、", "。": "。" }
  : { "；": "; ", "：": ": ", "、": ", ", "「": "“", "」": "”", "（": " (", "）": ")", "，": ", ", "。": ". " };

function T(s) {
  if (LANG === "zh-Hant" || typeof s !== "string" || !s) return s;
  if (LANG === "zh-Hans") return toHans(s);
  const v = look(s);
  return v === undefined ? s : v;
}
// A message from the server (an error, a step, a reason): whole message, then a pattern, then known pieces.
function TS(s) {
  if (!USE_DICT || typeof s !== "string" || !s || !/[\u3000-\u9fff\uff00-\uffef]/.test(s)) return LANG === "zh-Hans" ? toHans(s || "") : s;
  if (look(s) !== undefined) return look(s);
  for (const [re, k] of EN_PATTERNS) {
    const m = s.match(re);
    if (m) { let i = 1; return look(k).replace(/%[sd]/g, () => TS(m[i++] || "")); }
  }
  let o = s;
  for (const k of EN_PIECES) if (o.includes(k)) o = o.split(k).join(look(k));
  return o.replace(/[；：、「」（），。]/g, c => PUNCT[c]).replace(/ +\)/g, ")").replace(/\s+$/, "");
}

// Journal headings: "2026 年 11 月", "26 日　星期四" in Chinese; the locale's own form otherwise.
function monthLabel(y, m) {
  if (!USE_DICT) return y + T(" 年 ") + m + T(" 月");
  return new Date(y, m - 1, 1).toLocaleDateString(LANG, { year: "numeric", month: "long" });
}
function dayLabel(y, m, d, week) {
  if (!USE_DICT) return d + T(" 日　星期") + week;
  return new Date(y, m - 1, d).toLocaleDateString(LANG, { weekday: "short", day: "numeric" });
}

// The page's own text (index.html), before app.js draws anything.
function translatePage(root) {
  if (LANG === "zh-Hant") return;
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = []; while (w.nextNode()) nodes.push(w.currentNode);
  for (const n of nodes) {
    const t = n.nodeValue.trim();
    if (t && /[\u3000-\u9fff\uff00-\uffef]/.test(t)) n.nodeValue = n.nodeValue.replace(t, T(t));
  }
  root.querySelectorAll("[title],[placeholder],[aria-label]").forEach(el => {
    for (const a of ["title", "placeholder", "aria-label"]) {
      const v = el.getAttribute(a);
      if (v && /[\u3000-\u9fff\uff00-\uffef]/.test(v)) el.setAttribute(a, T(v));
    }
  });
}
translatePage(document.body);
