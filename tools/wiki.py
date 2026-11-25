#!/usr/bin/env python3
"""Helper CLI for the LLM wiki. Stdlib only. Run from anywhere; paths resolve to the vault.

    python3 tools/wiki.py status            convert new PDFs, then unprocessed raw files, counts, recent log
    python3 tools/wiki.py search "terms"    BM25 search over wiki pages
    python3 tools/wiki.py lint              rebuild index.md, then mechanical health check (exit 1 on errors)
    python3 tools/wiki.py log [-n 5]        last log entries
    python3 tools/wiki.py stats             counts by type, hub pages
    python3 tools/wiki.py index             regenerate wiki/index.md and tools/zh_keywords.json (lint and query do it on their own)
    python3 tools/wiki.py images FILE       list a raw note's web images and which to download (--apply to do it)
    python3 tools/wiki.py outline FILE      reading mode + map of a PDF-converted note (--hits: wiki topics, new terms; --skim)
    python3 tools/wiki.py phrases [FILE]    page names mostly used inside one phrase (candidates for not_aliases)
    python3 tools/wiki.py cite FILE --source "Title"   add a source's facts to existing pages (blocks headed '=== Page | Section')
    python3 tools/wiki.py essay-source ESSAY --source "Title"   an essay draws on a source: its source: list and wiki page
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from collections import Counter, defaultdict

# The vault: $NOTES_VAULT (the app sets it), else the folder this tools/ folder sits in.
VAULT = os.path.abspath(os.path.expanduser(os.environ.get("NOTES_VAULT")
                                           or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
WIKI = os.path.join(VAULT, "wiki")
# The human's notes: raw/ in a vault laid out that way, else the whole vault except the AI's wiki/ and
# the folders below (hidden folders never count).
RAW = os.path.join(VAULT, "raw") if os.path.isdir(os.path.join(VAULT, "raw")) else VAULT
RAW_REL = os.path.relpath(RAW, VAULT) if RAW != VAULT else ""
NOT_NOTES = {"wiki", "tools", "templates"}       # top-level folders that aren't notes when RAW is the vault
NOT_NOTE_FILES = {"CLAUDE.md", "AGENTS.md"}       # top-level instructions for an agent, not notes
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))    # these scripts and their fixed data (t2s_chars.json)
# Caches and per-vault data (triage.json, links.json, …): $NOTES_DATA, else the vault's tools/ if it has
# one, else the vault's hidden .notesapp/.
DATA = os.path.abspath(os.environ.get("NOTES_DATA") or (os.path.join(VAULT, "tools") if os.path.isdir(os.path.join(VAULT, "tools"))
                                                        else os.path.join(VAULT, ".notesapp")))


def _journal():
    """The daily-notes folder (Obsidian's setting, else <notes>/journal/). Never sent to Jev."""
    try:
        folder = json.load(open(os.path.join(VAULT, ".obsidian", "daily-notes.json"), encoding="utf-8")).get("folder")
    except (OSError, ValueError, AttributeError):
        folder = None
    if folder and folder.strip("/ "):
        return os.path.normpath(os.path.join(VAULT, folder.strip("/ ")))
    return os.path.join(RAW, "journal")


JOURNAL = _journal()
JOURNAL_REL = os.path.relpath(JOURNAL, VAULT)


def skip_dir(root, d):
    """Folders a walk over the notes skips: hidden ones, attachments, and (when the notes are the whole
    vault) the AI's wiki/ and the tools/templates folders."""
    return d.startswith(".") or d == "assets" or (RAW == VAULT and os.path.abspath(root) == VAULT and d in NOT_NOTES)


def in_notes(rel):
    """Is this vault-relative path the human's (a note or an attachment), not the AI's or the app's?"""
    full = os.path.abspath(os.path.join(VAULT, rel))
    if not full.startswith(RAW + os.sep):
        return False
    parts = os.path.relpath(full, RAW).split(os.sep)
    if any(x.startswith(".") for x in parts):
        return False
    return not (RAW == VAULT and (parts[0] in NOT_NOTES or (len(parts) == 1 and parts[0] in NOT_NOTE_FILES)))


def unit_of(rel):
    """triage's unit for a note: the note itself at the top of the notes, else its top-level folder (a book)."""
    p = os.path.relpath(os.path.join(VAULT, rel), RAW).split(os.sep)
    return rel if len(p) == 1 else os.path.join(RAW_REL, p[0])
SPECIAL = {"index", "log"}
TYPES = {"source", "entity", "concept", "analysis", "overview"}
TYPE_DIRS = {"sources": "source", "entities": "entity", "concepts": "concept", "analyses": "analysis"}
REQUIRED = ["type", "title", "created", "updated", "summary"]
LINK_RE = re.compile(r"(!?)\[\[([^\]\|#\^]+)(?:[#\^][^\]\|]*)?(?:\|[^\]]*)?\]\]")
IGNORED_RAW = {".DS_Store"}
# True: lint warns on concepts with no Traditional Chinese alias (tag a page no-zh-name to exempt it).
# Set it to match the "Every concept has a ... name" rule in CLAUDE.md §2.
REQUIRE_ZH_NAME = False


# ---------- parsing ----------

def parse_frontmatter(text):
    """Minimal YAML frontmatter parser: scalars, inline lists, and '- item' lists."""
    if not text.startswith("---"):
        return {}, text, False
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text, False
    block = text[3:end].strip("\n")
    body = text[end + 4:].lstrip("\n")
    data, key = {}, None
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val.startswith("[") and val.endswith("]"):
                inner = val[1:-1].strip()
                data[key] = [unquote(v) for v in split_list(inner)] if inner else []
            elif val == "":
                data[key] = []
            else:
                data[key] = unquote(val)
        elif key and line.lstrip().startswith("- "):
            if not isinstance(data.get(key), list):
                data[key] = []
            data[key].append(unquote(line.lstrip()[2:].strip()))
    return data, body, True


def split_list(s):
    out, cur, depth, q = [], "", 0, None
    for ch in s:
        if q:
            cur += ch
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
            cur += ch
        elif ch == "[":
            depth += 1
            cur += ch
        elif ch == "]":
            depth -= 1
            cur += ch
        elif ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


class Page:
    def __init__(self, path):
        self.path = path
        self.rel = os.path.relpath(path, VAULT)
        self.name = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as f:
            self.text = f.read()
        self.fm, self.body, self.has_fm = parse_frontmatter(self.text)
        aliases = self.fm.get("aliases", [])
        self.aliases = aliases if isinstance(aliases, list) else [aliases]
        self.links = [m.group(2).strip() for m in LINK_RE.finditer(self.text) if not m.group(1)]
        self.embeds = [m.group(2).strip() for m in LINK_RE.finditer(self.text) if m.group(1)]

    @property
    def type(self):
        return self.fm.get("type", "")


def load_pages():
    pages = []
    for root, dirs, files in os.walk(WIKI):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in sorted(files):
            if fn.endswith(".md"):
                pages.append(Page(os.path.join(root, fn)))
    return pages


def raw_files():
    out = []
    if not os.path.isdir(RAW):
        return out
    for root, dirs, files in os.walk(RAW):
        dirs[:] = [d for d in dirs if not skip_dir(root, d)]
        for fn in sorted(files):
            if fn in IGNORED_RAW or fn.startswith(".") or fn == "README.md":
                continue
            if RAW == VAULT and os.path.abspath(root) == VAULT and (fn in NOT_NOTE_FILES or not fn.endswith(".md")):
                continue
            out.append(os.path.relpath(os.path.join(root, fn), VAULT))
    return out


def all_vault_names():
    """Every file in the vault by basename-without-.md and by relative path (for link resolution)."""
    names = set()
    for root, dirs, files in os.walk(VAULT):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), VAULT)
            names.add(rel.lower())
            names.add(fn.lower())
            if fn.endswith(".md"):
                names.add(fn[:-3].lower())
                names.add(rel[:-3].lower())
    return names


def resolver(pages):
    m = {}
    for p in pages:
        m[p.name.lower()] = p
        for a in p.aliases:
            if a:
                m.setdefault(str(a).lower(), p)
    return m


# ---------- commands ----------

def processed_paths(pages):
    done = set()
    for p in pages:
        if p.type == "source":
            sp = p.fm.get("source_path")
            for v in (sp if isinstance(sp, list) else [sp]):
                if v:
                    v = os.path.normpath(str(v).strip().strip("[]"))
                    done.add(v)
                    if os.path.isdir(os.path.join(VAULT, v)):   # a book folder: every note in it
                        for root, _, files in os.walk(os.path.join(VAULT, v)):
                            done.update(os.path.relpath(os.path.join(root, f), VAULT) for f in files)
    return done


PDF_DIR = os.path.join(RAW, "assets")          # PDFs anywhere under raw/assets/, in any subfolder
PDF2RAW_SKIPPED = os.path.join(DATA, ".pdf2raw_skipped.json")


def waiting_pdfs():
    """PDFs under raw/assets/ that no raw note points to (frontmatter `pdf:`), split into
    (to convert, could not convert)."""
    done = set()
    for root, dirs, files in os.walk(RAW):
        dirs[:] = [d for d in dirs if not skip_dir(root, d)]
        for fn in files:
            if fn.endswith(".md"):
                try:
                    head = open(os.path.join(root, fn), encoding="utf-8", errors="ignore").read(4000)
                except OSError:
                    continue
                m = re.search(r'^pdf:\s*"?\[\[([^\]|]+)', head, re.M)
                if m:
                    done.add(os.path.normpath(m.group(1).strip()))
    try:
        skipped = json.load(open(PDF2RAW_SKIPPED, encoding="utf-8"))
    except (OSError, ValueError):
        skipped = {}
    todo, failed = [], []
    for root, dirs, files in os.walk(PDF_DIR):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for fn in sorted(files):
            if not fn.lower().endswith(".pdf"):
                continue
            rel = os.path.relpath(os.path.join(root, fn), VAULT)
            if os.path.normpath(rel) in done:
                continue
            s = skipped.get(rel)
            if s and s.get("mtime") == os.path.getmtime(os.path.join(VAULT, rel)):
                failed.append((rel, s.get("reason", "")))
            else:
                todo.append(rel)
    return todo, failed


def convert_pdfs():
    """Convert new PDFs under raw/assets/ into raw notes (tools/pdf2raw.py, run through uv)."""
    todo, _ = waiting_pdfs()
    if not todo:
        return
    uv = shutil.which("uv") or os.path.expanduser("~/.local/bin/uv")
    if not os.path.exists(uv):
        print("%d new PDF(s) in raw/assets/ not converted: uv is not installed "
              "(https://docs.astral.sh/uv/)\n" % len(todo))
        return
    print("Converting %d new PDF(s) from raw/assets/:" % len(todo))
    sys.stdout.flush()
    r = subprocess.run([uv, "run", "--quiet", "--no-project", "--with", "pymupdf4llm>=2.1,<3"] +
                       (["--with", "pyobjc-framework-Vision", "--with", "numpy", "--with", "pillow"] if sys.platform == "darwin" else []) + ["python",
                        os.path.join(TOOLS_DIR, "pdf2raw.py")], capture_output=True, text=True,
                       env=dict(os.environ, NOTES_VAULT=VAULT, NOTES_DATA=DATA))
    for line in (r.stdout.strip() or r.stderr.strip()[-500:] or "(no output)").splitlines():
        print("  " + line)
    print()


READ_BUDGET = 35000   # most tokens read in one go: a long note's skim and key parts
READ_WHOLE = int(os.environ.get("NOTES_READ_WHOLE") or 0)   # notes up to this are read whole; 0: none, every note is read
# by its key passages (Jev, ~80% of its key points) unless the user asks for it whole (the user's rule, 2026-11-25)



def est_tokens(text):
    """Rough token count: ~1 token per CJK character, ~4 characters per token otherwise."""
    cjk = len(re.findall(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]", text))
    return int(cjk + (len(text) - cjk) / 4)


SKIP_BLOCK = re.compile(r"^(#|<!--|!\[\[|\||```|>|\$\$)")   # not body text: notes, quotes, tables, code
HEAD = re.compile(r"#{1,6} +\S")
PAGE = re.compile(r"<!-- p\.(\d+) -->")


def segments(lines, ranges, lo=1000, hi=4000):
    """The note in parts of ~1-4k tokens: past `lo` a heading starts a new part, past `hi` the next line does.
    One rule for papers, books and transcripts; the map, new terms and skim all use these parts.
    Each part: {start, end (0-based, end exclusive), label (last heading, page), n (tokens)}."""
    segs, head, page = [], "start", None
    for a, b in ranges:
        cur = None
        for i in range(a, b):
            ln = lines[i]
            pm = PAGE.match(ln)
            if pm:
                page = int(pm.group(1))
            is_head = bool(HEAD.match(ln))
            if is_head:
                head = re.sub(r"[#*_`]", "", ln).strip()[:45]
            if cur is None or (is_head and cur["n"] >= lo) or cur["n"] >= hi:
                cur = {"start": i, "end": i, "label": head + (" p.%d" % page if page else ""), "n": 0}
                segs.append(cur)
            cur["n"] += est_tokens(ln)
            cur["end"] = i + 1
    if len(segs) > 1 and segs[-1]["n"] < lo:
        segs[-2]["end"], segs[-2]["n"] = segs[-1]["end"], segs[-2]["n"] + segs[-1]["n"]
        segs.pop()
    return segs


SENTENCE = re.compile(r"(?<=[。！？!?])|(?<=[.;])\s+(?=[A-Z\"“(])")
SKIM_RATIO = 0.15


def content_units(text):
    """Words and CJK bigrams, without stop words: what a sentence is about."""
    t = CJK_GAP.sub("", text).lower()
    out = [w for w in re.findall(r"[a-zà-ɏ][a-zà-ɏ0-9'-]+", t) if not is_stop(w)]
    for r in CJK_RUN.findall(t):
        out += [r[i:i + 2] for i in range(len(r) - 1) if not set(r[i:i + 2]) & ZH_STOP]
    return out


def skim(lines, segs, library):
    """Per part: headings, plus from each paragraph its sentence most about the note's main subjects,
    best paragraphs first, until ~SKIM_RATIO of the part; printed in reading order with line numbers.
    A sentence's score: its content words, each weighted by how much the note uses it (very common
    words in raw/ muted), over the square root of their number."""
    df = Counter()
    for text in library:
        df.update(set(content_units(text)))
    n_docs = len(library) + 1
    tf = Counter()
    for sg in segs:
        tf.update(content_units("\n".join(lines[sg["start"]:sg["end"]])))
    weight = lambda u: math.log(1 + tf[u]) * min(1.0, math.log(1 + (n_docs - df[u] + 0.5) / (df[u] + 0.5)) / 2)
    out = []
    for sg in segs:
        heads, best = [], {}
        for i in range(sg["start"], sg["end"]):
            ln = lines[i].strip()
            if HEAD.match(ln):
                heads.append((i, "%d %s" % (i + 1, re.sub(r"[*_`]", "", ln)[:120])))
                continue
            if not ln or SKIP_BLOCK.match(ln):
                continue
            for x in SENTENCE.split(ln):
                x = x.strip()
                us = set(content_units(x))
                if len(us) >= 3:
                    score = sum(weight(u) for u in us) / math.sqrt(len(us))
                    if i not in best or score > best[i][0]:
                        best[i] = (score, x)
        budget, keep = SKIM_RATIO * sg["n"], []
        for i, (score, x) in sorted(best.items(), key=lambda kv: -kv[1][0]):
            if est_tokens(x) <= budget:
                keep.append((i, "  %d  %s" % (i + 1, x)))
                budget -= est_tokens(x)
        out += [t for _, t in sorted(heads + keep)]
    return out


T2S_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "t2s_chars.json")
_T2S = None


def zh(s):
    """Fold Traditional Chinese characters to Simplified, so 工作記憶 and 工作记忆 match.
    Only for matching (search, outline --hits, lint); pages stay as written. Traditional → Simplified
    is many-to-one (發, 髮 → 发), so a per-character table is exact; the other way would need guessing.
    tools/t2s_chars.json was made once with OpenCC."""
    global _T2S, _SIMP
    if _T2S is None:
        try:
            with open(T2S_PATH, encoding="utf-8") as f:
                data = json.load(f)
            _T2S, _SIMP = str.maketrans(data["t2s"]), set(data["simplified_only"])
        except (OSError, ValueError, KeyError):
            _T2S, _SIMP = {}, set()
    return s.translate(_T2S)


_SIMP = set()


def traditional_name(s):
    """True if s is Chinese with no Simplified-only character (馬斯克, 特斯拉 are; 马斯克 isn't)."""
    zh("")
    return bool(CJK_RUN.search(s)) and not any(c in _SIMP for c in s)


def wiki_terms(exclude=()):
    """{term: (page name, case-sensitive)} from entity and concept titles and aliases, Chinese folded by zh().
    Entity names must match case-sensitively, so the company "Apple" doesn't match "apple"."""
    terms = {}
    exclude = {e.lower() for e in exclude}
    for pg in load_pages():
        if pg.type not in ("entity", "concept") or pg.name.lower() in exclude:
            continue
        for t in [pg.name] + [a for a in pg.aliases if isinstance(a, str)]:
            t = zh(re.sub(r"\s*\(.*?\)\s*", " ", t).strip())   # "Kang Youwei (康有為)" → "Kang Youwei"
            cjk = re.search(r"[㐀-鿿]", t)
            if (cjk and len(t) >= 2) or (not cjk and len(t) >= 4):
                key = t if pg.type == "entity" else t.lower()
                terms.setdefault(key, (pg.name, pg.type == "entity"))
    # not_aliases: longer phrases that contain a page's name but mean something else ("sales tax" on
    # Sales). They join the match as page None; the longest match wins, so "sales tax" isn't "sales".
    for pg in load_pages():
        for t in not_aliases(pg):
            terms.setdefault(zh(t).lower(), (None, False))
    return terms


def not_aliases(pg):
    v = pg.fm.get("not_aliases") or []
    return [str(x) for x in (v if isinstance(v, list) else [v]) if str(x).strip()]


GLUE = 0.6   # a name "glued" to one neighbour in ≥60% of its uses is likely part of another term


def glued_names(text, terms, names_of):
    """Single-word page names that, in this text, mostly sit next to one word ("marketing costs",
    "sales tax", "artificial intelligence"): candidates for a page's not_aliases. A phrase that is
    already a wiki name, or part of one of the page's own names ("Ray Dalio"), is left out.
    Returns [(page, phrase, times glued, mentions)]."""
    cs = {t: v[0] for t, v in terms.items() if v[1] and v[0] and re.fullmatch(r"[A-Za-z][A-Za-z-]+", t)}
    ci = {t: v[0] for t, v in terms.items() if not v[1] and v[0] and re.fullmatch(r"[a-z][a-z-]+", t)}
    words = re.findall(r"[A-Za-z][A-Za-z'-]*[A-Za-z]|[A-Za-z]", zh(text))
    low = [w.lower() for w in words]
    at = defaultdict(list)
    for i, w in enumerate(words):
        page = cs.get(w) or ci.get(low[i])
        if page:
            at[(page, low[i])].append(i)
    out = []
    for (page, name), idx in at.items():
        if len(idx) < 2:
            continue
        for d in (-1, 1):
            nb = Counter(low[i + d] for i in idx if 0 <= i + d < len(low))
            nb = Counter({w: n for w, n in nb.items() if w not in TERM_STOP and len(w) >= 3
                          and w not in ("https", "http", "www", "com", "raw")})
            if not nb:
                continue
            w, n = nb.most_common(1)[0]
            phrase = "%s %s" % ((w, name) if d < 0 else (name, w))
            if n >= GLUE * len(idx) and phrase not in terms and not any(phrase in o for o in names_of[page]):
                out.append((page, phrase, n, len(idx)))
                break
    return out


def names_by_page(pages):
    """{page: [its title and aliases, lowercased]}."""
    return {p.name: [zh(re.sub(r"\s*\(.*?\)\s*", " ", str(t)).strip()).lower() for t in [p.name] + p.aliases]
            for p in pages}


def raw_texts(skip=None):
    """Text of every raw note except `skip` (the library new terms and BM25 rarity are measured against)."""
    out = []
    for rel in raw_files():
        p = os.path.join(VAULT, rel)
        if rel.endswith(".md") and os.path.normpath(p) != os.path.normpath(skip or ""):
            out.append(open(p, encoding="utf-8", errors="ignore").read())
    return out


def bm25(tf, df, n_docs, length, avg_length, k1=1.2, b=0.75):
    """Rarer across the library → higher; more mentions → higher but saturating; long parts discounted."""
    idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
    return idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * length / max(avg_length, 1)))


def wiki_hits(lines, ranges, marks, exclude=(), library=()):
    """Which wiki entities/concepts each page (or section) mentions, ranked by BM25 so concepts that are
    everywhere (in this note and across raw/) don't drown out the ones a page is specifically about.
    `exclude` = the source's own authors, who would otherwise show up on every page."""
    terms = wiki_terms(exclude)
    if not terms:
        return []

    def pat(t, case_sensitive):
        # words may be split by a line break or, in URLs, "+" ("artificial+intelligence")
        core = re.escape(t) if re.search(r"[㐀-鿿]", t) else \
            r"(?<![\w])" + re.escape(t).replace(r"\ ", r"[\s+]+") + r"(?![\w])"
        return core if case_sensitive else "(?i:" + core + ")"

    alts = sorted(terms, key=len, reverse=True)
    rx = re.compile("|".join(pat(t, terms[t][1]) for t in alts))

    def lookup(m):
        m = re.sub(r"[\s+]+", " ", m)
        return (terms.get(m) or terms.get(m.lower()) or terms.get(m.casefold()))[0]   # casefold: long s, Happineſs
    # library document frequency: cheap tests first (words present, then substring), the exact pattern last
    single = {t: re.compile(pat(t, cs)) for t, (_, cs) in terms.items()}
    df = Counter()
    word = re.compile(r"[0-9A-Za-zÀ-ɏ]+")
    parts = {t: (set(word.findall(t.lower())), bool(CJK_RUN.search(t))) for t in terms}
    for text in library:
        text = zh(text)
        low = text.lower()
        words, has_cjk = set(word.findall(low)), bool(CJK_RUN.search(text))
        df.update({terms[t][0] for t, (ws, zh) in parts.items() if terms[t][0] and ws <= words and (has_cjk or not zh)
                   and (t in text if terms[t][1] else t.lower() in low) and single[t].search(text)})
    groups = []
    for a, b, ln, label in parts_of(lines, ranges, marks):
        text = "\n".join(lines[a:b])
        c = Counter(lookup(m.group(0)) for m in rx.finditer(zh(text)))
        c.pop(None, None)   # not_aliases matched: not a mention of any page
        if sum(c.values()) >= 2:
            groups.append([ln, label, c, est_tokens(text)])
    avg = sum(g[3] for g in groups) / max(len(groups), 1)
    for g in groups:
        g[3] = {t: bm25(n, df[t], len(library) + 1, g[3], avg) for t, n in g[2].items()}
    return groups


def parts_of(lines, ranges, marks):
    """Split `ranges` at `marks` [(line, label)]: yields (start, end, line, label), 0-based [start, end)."""
    for a, b in ranges:
        inside = [(ln, lb) for ln, lb in marks if a < ln <= b]
        if not inside or inside[0][0] > a + 1:
            inside.insert(0, (a + 1, inside[0][1] if inside else "start"))
        for k, (ln, label) in enumerate(inside):
            end = inside[k + 1][0] - 1 if k + 1 < len(inside) else b
            if end > ln - 1:
                yield ln - 1, end, ln, label


# --- new terms: words and phrases a note uses often that the wiki doesn't know and raw/ rarely has ---
TERM_STOP = set("""the of and a an to in is are was were be been being for on with as by that this it its at
from or which we our us they their them these those can could not but has have had do does did done et al also
than such so if then there here when where while whereas who whom whose what why how all any each both few more
most other some no nor only own same too very just may might must shall should will would about above after again
against before below between during into through under until up down out off over once further because however
therefore thus although though since yet even still also either neither one two three first second new used use
using based well many much often less least can't don't doesn't isn't i'm it's that's you're we're they're i you
he she his her him my me your yours its itself themselves ourselves need needs suggest suggests suggested show
shows shown found find finds make makes made way ways like get got go going gonna yeah yes um uh oh okay laughs
know think thing things really actually kind sort lot right something someone people time year years see said say
says given within without across among per via vs e.g i.e etc fig figure table section""".split())
CJK_RUN = re.compile(r"[㐀-鿿]+")
stop = lambda w: w in TERM_STOP or w.endswith(("n't", "'ll", "'ve", "'re", "'d", "'m"))   # + won't, we'll
LATIN_WORD = re.compile(r"[A-Za-zÀ-ɏ][A-Za-zÀ-ɏ0-9'’-]*[A-Za-zÀ-ɏ0-9]")
CITE = re.compile(r"[(（][^()（）\n]*\b(?:1[5-9]|20)\d\d[a-z]?\b[^()（）\n]*[)）]")   # (Nourani et al., 2021)
CJK_GAP = re.compile(r"(?<=[㐀-鿿])[ \t\r\n`]+(?=[㐀-鿿])")   # PDF line breaks inside Chinese words
ZH_STOP = set("的了着著过過们們个個之其这這那也都就被把将將于於与與及或而等是和在如")   # function chars
UNIT = re.compile(r"[㐀-鿿]|[A-Za-zÀ-ɏ][A-Za-zÀ-ɏ0-9'-]*[A-Za-zÀ-ɏ0-9]|[A-Za-zÀ-ɏ]")
is_stop = lambda u: u in ZH_STOP or stop(u)


def units(text):
    """The note as a stream of CJK characters and lowercase words; None marks a break (punctuation, line end).
    Citations in parentheses, links and markup are removed first."""
    t = CJK_GAP.sub("", text).replace("’", "'").replace("ſ", "s")
    t = re.sub(r"<!--.*?-->|!?\[\[[^\]]*\]\]|\]\([^)]*\)|<[^>]+>|https?://\S+", " ", t)
    out = []
    for piece in re.split(r"[^\w \t'㐀-鿿-]+|_", CITE.sub(" ", t)):
        out += [u.lower() for u in UNIT.findall(piece)] + [None]
    return out


def library_df(want, library):
    """Document frequency in raw/ of the candidate terms `want` (and of CJK bigrams, for the piece test),
    looking only for those terms instead of listing every gram of every file."""
    cjk_want = [g for g in want if CJK_RUN.fullmatch(g)]
    words1 = {g for g in want if " " not in g} - set(cjk_want)
    phrases = {g for g in want if " " in g}
    firsts = {g.split(" ")[0] for g in phrases}
    df, bigram = Counter(), Counter()
    for text in library:
        t = CJK_GAP.sub("", text).replace("’", "'").replace("ſ", "s")
        runs = CJK_RUN.findall(t)
        if runs:
            cjk = "\n".join(runs)
            df.update(g for g in cjk_want if g in cjk)
            bigram.update({r[i:i + 2] for r in runs for i in range(len(r) - 1)})
        w = [x.lower() for x in LATIN_WORD.findall(t)]
        found = words1 & set(w)
        for i, x in enumerate(w):
            if x in firsts:
                found |= phrases & {" ".join(w[i:i + 2]), " ".join(w[i:i + 3])}
        df.update(found)
    return df, bigram


RARE = 0.05   # "rare in raw/": in at most 5% of raw files


def new_terms(lines, segs, library):
    """(core, [(segment, terms)]): words and phrases this note uses often that the wiki has no page for.
    1. Candidates: 2-6 CJK characters or 1-3 words, not starting or ending with a stop word.
    2. Distinctive: frequent here, in at most RARE of raw/, not a wiki page or alias; ranked by BM25.
    3. Free on both sides: no single neighbour takes 60% of one side, else it is a piece of a longer
       word ("丙子" of 丙子胡乱, "ai background" of ai background knowledge).
    The core line holds terms spread over the note (8); each part gets its own top 5."""
    if not segs:
        return [], []
    known = set()
    for pg in load_pages():
        known |= {zh(pg.name.lower())} | {zh(str(a).lower()) for a in pg.aliases}
    is_cjk = lambda u: "㐀" <= u[0] <= "鿿"
    sides, per_seg = {}, []
    for sg in segs:
        us, c = units("\n".join(lines[sg["start"]:sg["end"]])), Counter()
        for i, u in enumerate(us):
            if u is None:
                continue
            cj = is_cjk(u)
            for n in (range(2, 7) if cj else range(1, 4)):
                g = us[i:i + n]
                if len(g) < n or None in g or any(is_cjk(x) != cj for x in g):
                    break
                if is_stop(g[0]) or is_stop(g[-1]) or (not cj and (len(set(g)) < n or max(map(len, g)) < 3)):
                    continue
                key = ("" if cj else " ").join(g)
                c[key] += 1
                left, right = sides.setdefault(key, (Counter(), Counter()))
                left[us[i - 1] if i else None] += 1
                right[us[i + n] if i + n < len(us) else None] += 1
        per_seg.append(c)
    here, spread = Counter(), Counter()
    for c in per_seg:
        here.update(c)
        spread.update(set(c))
    free = lambda g: all(max((v for u, v in side.items() if u is not None), default=0) < 0.6 * here[g]
                         for side in sides[g])
    want = {g for c in per_seg for g, n in c.items() if n >= 2} | {g for g, n in here.items() if n >= 4}
    want = {g for g in want if zh(g) not in known and free(g)}
    df, _ = library_df(want, library)
    want = {g for g in want if df[g] <= RARE * len(library)}
    n_docs = len(library) + 1
    idf = lambda g: math.log(1 + (n_docs - df[g] + 0.5) / (df[g] + 0.5))

    def pick(scores, k, skip=()):
        """Top k; of two overlapping terms ("明朝", "对明朝") only the higher-scoring one."""
        out = []
        for g in sorted(scores, key=scores.get, reverse=True):
            if g not in skip and not any(g in o or o in g for o in out):
                out.append(g)
                if len(out) == k:
                    break
        return out
    core = pick({g: idf(g) * here[g] / (here[g] + 5) for g in want
                 if here[g] >= 4 and spread[g] >= max(2, 0.2 * len(segs))}, 8)
    avg = sum(sum(c.values()) for c in per_seg) / len(per_seg)
    rows = []
    for sg, c in zip(segs, per_seg):
        size = sum(c.values())
        terms = pick({g: bm25(n, df[g], n_docs, size, avg) for g, n in c.items() if n >= 2 and g in want}, 5, core)
        if terms:
            rows.append((sg, terms))
    return core, rows


APPENDIX = re.compile(r"(appendix|appendices|supplementary|supplemental|附錄|附录)", re.I)
REFS = re.compile(r"(references|bibliography|works cited|參考文獻|參考資料|参考文献)\b", re.I)


def reading_ranges(lines, lines_arg=None):
    """A note's map: (body_start, headings, page markers, references line, appendix line, ranges), where
    ranges are the 0-based spans worth reading: body up to the references, plus any appendix after them,
    narrowed to lines_arg ("A-B") if given."""
    body_start = 0
    if lines and lines[0] == "---":
        body_start = next((i for i in range(1, len(lines)) if lines[i] == "---"), 0) + 1
    heads, pages, refs, appendix = [], [], None, None
    in_code = False
    for i in range(body_start, len(lines)):
        ln = lines[i]
        if ln.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = re.match(r"(#{1,6}) +(.+)", ln)
        if m:
            heads.append((i + 1, len(m.group(1)), re.sub(r"[*_`]", "", m.group(2)).strip()[:90]))
            if REFS.match(heads[-1][2]):
                refs, appendix = i + 1, None
            elif refs and not appendix and APPENDIX.match(heads[-1][2]):
                appendix = i + 1
        pm = re.match(r"<!-- p\.(\d+) -->", ln)
        if pm:
            pages.append((i + 1, int(pm.group(1))))
    # the text worth reading: body up to the references, plus any appendix after them (0-based ranges)
    ranges = [(body_start, refs - 1 if refs else len(lines))]
    if appendix:
        ranges.append((appendix - 1, len(lines)))
    if lines_arg:
        x, _, y = lines_arg.partition("-")
        lo, hi = max(int(x) - 1, 0), min(int(y or len(lines)), len(lines))
        ranges = [(max(a, lo), min(b, hi)) for a, b in ranges if min(b, hi) > max(a, lo)] or [(lo, hi)]

    return body_start, heads, pages, refs, appendix, ranges


def cmd_outline(args):
    """Print a compact map of a raw file so a long source can be read in parts (Read with offset/limit)."""
    path = args.file if os.path.isabs(args.file) else os.path.join(VAULT, args.file)
    lines = open(path, encoding="utf-8", errors="ignore").read().split("\n")
    total = est_tokens("\n".join(lines))
    body_start, heads, pages, refs, appendix, ranges = reading_ranges(lines, args.lines)
    segs = segments(lines, ranges)
    library = raw_texts(skip=path) if (total > READ_WHOLE or args.skim or args.hits) else []
    sk = skim(lines, segs, library) if (total > READ_WHOLE or args.skim) else []
    # how to read it: whole up to READ_WHOLE; else skim it whole if the skim fits; else skim chosen sections
    if total > READ_WHOLE:
        sk_all = est_tokens("\n".join(sk))
        mode = ("LONG: skim it whole (~%d tokens), then read the key parts in full" % sk_all
                if sk_all <= READ_BUDGET else
                "VERY LONG: its skim is ~%d tokens; pick sections (headings, --hits) to skim, up to ~%d"
                % (sk_all, READ_BUDGET))
    else:
        mode = "short: read it whole"
    print("%s: ~%d tokens, %d lines -> %s" % (os.path.relpath(path, VAULT), total, len(lines), mode))
    if body_start:
        print("frontmatter: lines 1-%d" % body_start)
    # section tokens: text between one heading and the next
    if heads:
        print("sections (line, ~tokens):")
        bounds = [h[0] for h in heads] + [len(lines) + 1]
        shown = heads if len(heads) <= 60 else [h for h in heads if h[1] <= 2][:60]
        for (ln, lvl, title) in shown:
            j = bounds.index(ln)
            t = est_tokens("\n".join(lines[ln - 1:bounds[j + 1] - 1]))
            print("  %s%d  %s  (~%d)" % ("  " * (lvl - 1), ln, title, t))
        if len(shown) < len(heads):
            print("  … %d deeper headings not shown" % (len(heads) - len(shown)))
    if refs:
        end = (appendix - 1) if appendix else len(lines)
        print("references: lines %d-%d (~%d tokens; skip unless needed)%s" %
              (refs, end, est_tokens("\n".join(lines[refs - 1:end])),
               "; appendix from line %d" % appendix if appendix else ""))
    if pages:
        step = max(1, len(pages) // 12)
        print("page markers: " + ", ".join("p.%d@%d" % (p, ln) for ln, p in pages[::step]))
    span = "lines " + ", ".join("%d-%d" % (a + 1, b) for a, b in ranges)
    if args.skim:
        print("\nskim, %s (headings + each paragraph's most central sentence, ~%d%% per part; ~%d tokens):"
              % (span, SKIM_RATIO * 100, est_tokens("\n".join(sk))))
        print("\n".join(sk))
    if args.hits:
        authors = re.findall(r'^\s+- "\[\[([^\]|]+)', "\n".join(lines[:body_start]), re.M)
        marks = [(sg["start"] + 1, sg["label"][:40]) for sg in segs]
        groups = wiki_hits(lines, ranges, marks, exclude=authors, library=library)
        overall, counts = Counter(), Counter()
        for _, _, c, sc in groups:
            overall.update(sc)
            counts.update(c)
        print("\nwiki topics, %s (entity/concept pages mentioned, by part; BM25 order):" % span)
        if not groups:
            print("  (none mentioned twice or more)")
        for ln, label, c, sc in groups[:60]:
            top = sorted(sc, key=sc.get, reverse=True)[:5]
            print("  %s@%d: %s" % (label, ln, ", ".join("%s ×%d" % (t, c[t]) for t in top)))
        if overall:
            print("  overall: " + ", ".join("%s ×%d" % (t, counts[t]) for t, _ in overall.most_common(8)))
        core, rows = new_terms(lines, segs, library)
        print("\nnew terms (no wiki page yet, rare in raw/, frequent here):")
        print("  whole note: " + ("、".join(core) if core else "(none)"))
        for sg, terms in rows[:120]:
            print("  %d %s: %s" % (sg["start"] + 1, sg["label"][:40], "、".join(terms)))


def cmd_status(args):
    """Page counts, what's waiting in raw/ (by unit: a top-level note or a folder, the top 10 in
    jev.py triage's order), unconvertible PDFs, recent log. `jev.py triage` lists every unit."""
    if not getattr(args, "no_convert", False):
        convert_pdfs()
    pages = load_pages()
    done = processed_paths(pages)
    pending = [r for r in raw_files() if os.path.normpath(r) not in done]
    counts = Counter(p.type or "?" for p in pages if p.name not in SPECIAL)
    print("Wiki pages: " + (", ".join("%s %d" % (k, v) for k, v in sorted(counts.items())) or "none yet"))
    units = defaultdict(list)
    for r in pending:
        units[unit_of(r)].append(r)
    tri_path = os.path.join(DATA, "triage.json")
    tri = json.load(open(tri_path, encoding="utf-8")) if os.path.exists(tri_path) else {}
    prio = lambda t: t.get("priority", 0) + (3 if t.get("essays") and t.get("priority") else 0)
    rank = lambda u: (tri.get(u, {}).get("decision") not in ("ingest", "continue a work"), -prio(tri.get(u, {})), u)
    print("\nUnprocessed raw: %d files in %d units (a note, or a folder such as a book)" % (len(pending), len(units)))
    for u in sorted(units, key=rank)[:args.n]:
        t = tri.get(u, {})
        print("  %-16s %s%s%s" % (t.get("decision", "(not triaged)"), u,
                                  "  (%d notes)" % len(units[u]) if len(units[u]) > 1 else "",
                                  "  ← essay " + "、".join("〈%s〉" % e for e in t["essays"]) if t.get("essays") else ""))
    if len(units) > args.n:
        print("  … %d more: `python3 tools/jev.py triage` ranks them all" % (len(units) - args.n))
    if not pending:
        print("  (none)")
    _, failed = waiting_pdfs()
    if failed:
        print("\nPDFs that could not be converted (%d):" % len(failed))
        for rel, why in failed:
            print("  %s  (%s)" % (rel, why))
    print("\nRecent log:")
    print_log(3, indent="  ")


def tokenize(s):
    s = zh(s.lower())   # query and pages alike, so Traditional and Simplified match
    words = re.findall(r"[a-z0-9]+", s)
    # CJK: index single characters and bigrams so Chinese/Japanese text is searchable
    cjk = re.findall(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]+", s)
    for run in cjk:
        words.extend(run)
        words.extend(run[i:i + 2] for i in range(len(run) - 1))
    return words


def cmd_search(args):
    scored = search_pages(args.query)
    if not scored:
        print("No results.")
        return
    for s, p in scored[: args.n]:
        print("%6.2f  %-10s %s" % (s, p.type or "?", p.rel))
        if p.fm.get("summary"):
            print("        " + str(p.fm["summary"]))


def search_pages(query, pages=None):
    """[(score, page)] best first, BM25 over wiki pages with title/aliases/summary weighted."""
    pages = [p for p in (pages or load_pages()) if p.name not in SPECIAL]
    q = tokenize(query)
    if not q or not pages:
        return []
    docs = []
    for p in pages:
        head = " ".join([p.name] + [str(a) for a in p.aliases] + [str(p.fm.get("summary", ""))])
        toks = tokenize(head) * 3 + tokenize(p.body)  # weight title/aliases/summary
        docs.append(Counter(toks))
    N = len(docs)
    avgdl = sum(sum(d.values()) for d in docs) / float(N)
    df = Counter()
    for d in docs:
        df.update(set(d))
    k1, b = 1.5, 0.75
    scored = []
    for p, d in zip(pages, docs):
        dl = sum(d.values())
        s = 0.0
        for t in set(q):
            if t not in d:
                continue
            idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * d[t] * (k1 + 1) / (d[t] + k1 * (1 - b + b * dl / avgdl))
        if s > 0:
            scored.append((s, p))
    scored.sort(key=lambda x: -x[0])
    return scored


def cmd_phrases(args):
    """Candidates for not_aliases: where a single-word page name is mostly part of one phrase."""
    pages = load_pages()
    terms, names = wiki_terms(), names_by_page(pages)
    if args.file:
        path = args.file if os.path.isabs(args.file) else os.path.join(VAULT, args.file)
        files = [os.path.relpath(path, VAULT)]
    else:
        files = [r for r in raw_files() if r.endswith(".md")]
    rows = defaultdict(list)
    for rel in files:
        text = open(os.path.join(VAULT, rel), encoding="utf-8", errors="ignore").read()
        for page, phrase, n, total in glued_names(text, terms, names):
            rows[(page, phrase)].append((rel, n, total))
    if not rows:
        print("No glued names.")
        return
    print("Single-word names mostly used inside one phrase. If the phrase means something else,")
    print("add it to that page's not_aliases (CLAUDE.md §2 Aliases); if it is the same thing, leave it.\n")
    for (page, phrase), hits in sorted(rows.items(), key=lambda x: (-len(x[1]), x[0])):
        n, total = sum(h[1] for h in hits), sum(h[2] for h in hits)
        where = ", ".join(os.path.basename(h[0])[:40] for h in hits[:3]) + (" …" if len(hits) > 3 else "")
        print("  %-24s \"%s\"  %d/%d uses, %d note(s): %s" % (page[:24], phrase, n, total, len(hits), where))


def cmd_lint(args):
    import datetime
    pages = load_pages()
    changed, _ = write_index(pages)
    if changed:
        print("index.md rebuilt (a page was added, renamed or re-summarised)\n")
        pages = load_pages()
    by_name = resolver(pages)
    vault_names = all_vault_names()
    errors, warnings = [], []

    # duplicate titles
    seen = defaultdict(list)
    for p in pages:
        seen[p.name.lower()].append(p.rel)
    for n, rels in seen.items():
        if len(rels) > 1:
            errors.append("duplicate page name '%s': %s" % (n, ", ".join(rels)))

    # frontmatter
    for p in pages:
        if p.name in SPECIAL:
            continue
        if not p.has_fm:
            errors.append("%s: missing frontmatter" % p.rel)
            continue
        fm_block = p.text[3:p.text.find("\n---", 3)]
        for ln in fm_block.splitlines():
            m = re.match(r"^([A-Za-z_][\w-]*): (.+)$", ln)
            if m and m.group(2)[0] not in "\"'[" and (": " in m.group(2) or " #" in m.group(2)):
                errors.append("%s: frontmatter '%s' needs quotes (contains ': ' or ' #')" % (p.rel, m.group(1)))
        for k in REQUIRED:
            if not p.fm.get(k):
                errors.append("%s: frontmatter missing '%s'" % (p.rel, k))
        if p.type and p.type not in TYPES:
            errors.append("%s: unknown type '%s'" % (p.rel, p.type))
        folder = os.path.basename(os.path.dirname(p.path))
        if folder in TYPE_DIRS and p.type and p.type != TYPE_DIRS[folder]:
            warnings.append("%s: type '%s' but lives in %s/" % (p.rel, p.type, folder))
        if p.type == "source":
            sp = p.fm.get("source_path")
            if not sp:
                errors.append("%s: source page without source_path" % p.rel)
            else:
                for v in (sp if isinstance(sp, list) else [sp]):
                    if not os.path.exists(os.path.join(VAULT, str(v))):
                        errors.append("%s: source_path not found: %s" % (p.rel, v))
        if p.type in ("entity", "concept", "analysis") and not p.fm.get("sources"):
            warnings.append("%s: no sources listed" % p.rel)

    # names: an alias names one page only; with REQUIRE_ZH_NAME, each concept has a Chinese name
    # (compared with Chinese folded and case ignored, as search and outline --hits compare them)
    key = lambda s: zh(str(s)).casefold().strip()
    titles = {key(p.name): p for p in pages if p.name not in SPECIAL}
    owners = defaultdict(dict)
    for p in pages:
        if p.name in SPECIAL:
            continue
        for a in p.aliases:
            if not str(a).strip():
                continue
            t = titles.get(key(a))
            if t is not None and t is not p:
                errors.append("%s: alias '%s' is the title of %s" % (p.rel, a, t.rel))
            owners[key(a)].setdefault(p.name, str(a))
        tags = p.fm.get("tags") or []
        if REQUIRE_ZH_NAME and p.type == "concept" and "no-zh-name" not in (tags if isinstance(tags, list) else [tags]) \
                and not any(traditional_name(str(n)) for n in [p.name] + p.aliases):
            warnings.append("%s: no Traditional Chinese name in aliases" % p.rel)
    names = names_by_page(pages)
    for p in pages:
        for t in not_aliases(p):
            if not any(re.search(r"(?<![\w])" + re.escape(o) + r"(?![\w])", zh(t).lower()) for o in names[p.name] if o):
                warnings.append("%s: not_aliases '%s' doesn't contain the page's title or an alias, so it does nothing"
                                % (p.rel, t))
    for k, by_page in sorted(owners.items()):
        if len(by_page) > 1:
            warnings.append("alias '%s' is shared by %s" % (next(iter(by_page.values())), ", ".join(sorted(by_page))))

    # links
    inbound = Counter()
    wanted = defaultdict(set)
    for p in pages:
        if p.name == "log":                  # history: it names pages since renamed or removed
            continue
        for target in p.links + p.embeds:
            t = target.strip().lower()
            if t in by_name:
                if by_name[t] is not p:
                    inbound[by_name[t].rel] += 1
            elif t in vault_names or t.rstrip("/") in vault_names:
                pass
            else:
                wanted[target.strip()].add(p.name)
    for target, srcs in sorted(wanted.items(), key=lambda x: (-len(x[1]), x[0].lower())):
        warnings.append("wanted page [[%s]] (linked from %d: %s)" % (target, len(srcs), ", ".join(sorted(srcs)[:5])))

    # orphans (no inbound links from other wiki pages, index excluded)
    for p in pages:
        if p.name in SPECIAL:
            continue
        # inbound links excluding index.md
        real_inbound = 0
        for q in pages:
            if q is p or q.name == "index":
                continue
            if any(by_name.get(l.lower()) is p for l in q.links):
                real_inbound += 1
        if real_inbound == 0 and p.type != "overview":
            warnings.append("%s: orphan (no inbound links besides index)" % p.rel)

    # unprocessed raw
    done = processed_paths(pages)
    pending = [r for r in raw_files() if os.path.normpath(r) not in done]
    if pending:
        warnings.append("%d unprocessed raw files (listed by `wiki.py status`, ranked by `jev.py triage`)" % len(pending))
    todo, failed = waiting_pdfs()
    for r in todo:
        warnings.append("PDF not converted yet (run status): %s" % r)
    for r, why in failed:
        warnings.append("PDF could not be converted (%s): %s" % (why, r))

    # warnings about pages created or changed today come first: those are the ones an ingest just made
    today = datetime.date.today().isoformat()
    fresh = [p for p in pages if p.name not in SPECIAL and
             today in (str(p.fm.get("updated", "")), str(p.fm.get("created", "")))]
    pat = re.compile("|".join(r"(?<![\w\[])%s(?![\w\]])" % re.escape(x) for p in fresh
                              for x in sorted({p.rel, p.name}, key=len, reverse=True))) if fresh else None
    mine = [w for w in warnings if pat and pat.search(w)]
    rest = [w for w in warnings if w not in set(mine)]
    for e in errors:
        print("ERROR   " + e)
    if mine:
        print("-- about the %d page(s) created or changed today --" % len(fresh))
        for w in mine:
            print("WARN    " + w)
        print("-- the rest --")
    for w in rest:
        print("WARN    " + w)
    print("\n%d error(s), %d warning(s) across %d pages; %d about today's pages." % (
        len(errors), len(warnings), len(pages), len(mine)))
    sys.exit(1 if errors else 0)


def print_log(n, indent=""):
    path = os.path.join(WIKI, "log.md")
    if not os.path.exists(path):
        print(indent + "(no log)")
        return
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    starts = [i for i, l in enumerate(lines) if l.startswith("## [")]
    for i in starts[-n:]:
        j = next((s for s in starts if s > i), len(lines))
        block = [l for l in lines[i:j] if l.strip()]
        for l in block:
            print(indent + l)
    if not starts:
        print(indent + "(empty)")


def cmd_log(args):
    print_log(args.n)


def cmd_stats(args):
    pages = load_pages()
    by_name = resolver(pages)
    counts = Counter(p.type or "?" for p in pages if p.name not in SPECIAL)
    for k, v in sorted(counts.items()):
        print("%-10s %d" % (k, v))
    inbound = Counter()
    for p in pages:
        if p.name in SPECIAL:
            continue
        for l in set(p.links):
            q = by_name.get(l.lower())
            if q and q is not p:
                inbound[q.rel] += 1
    print("\nHubs (most inbound links):")
    for rel, c in inbound.most_common(args.n):
        print("  %3d  %s" % (c, rel))


SECTIONS = [("overview", "Overview"), ("source", "Sources"), ("entity", "Entities"),
            ("concept", "Concepts"), ("analysis", "Analyses")]


def cmd_index(args):
    """Rebuild index.md and tools/zh_keywords.json. lint and jev.py query also do this on their own."""
    pages = load_pages()
    changed, stamp = write_index(pages)
    print("index.md %s: %s" % ("rebuilt" if changed else "unchanged", stamp))
    print("zh_keywords.json rebuilt: %d strings" % len(build_zh_keywords(pages)))


def write_index(pages=None):
    """Rebuild index.md from frontmatter (title + summary). Keeps the header text above '## Overview'.
    Writes only when a line other than the date stamp changed. Returns (changed, stamp)."""
    import datetime
    pages = [p for p in (pages or load_pages()) if p.name not in SPECIAL]
    old = None
    path = os.path.join(WIKI, "index.md")
    head = "# Index\n"
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = f.read()
        cut = old.find("\n## ")
        head = old[:cut + 1] if cut != -1 else old
    by_type = defaultdict(list)
    for p in pages:
        by_type[p.type or "?"].append(p)
    counts = {t: len(by_type.get(t, [])) for t, _ in SECTIONS}
    stamp = "updated: %s · %d sources · %d entities · %d concepts · %d analyses" % (
        datetime.date.today().isoformat(), counts["source"], counts["entity"], counts["concept"], counts["analysis"])
    head = re.sub(r"(?m)^updated:.*$", stamp, head) if re.search(r"(?m)^updated:", head) else head + "\n" + stamp + "\n"
    out = [head.rstrip("\n"), ""]
    for t, label in SECTIONS:
        out.append("## " + label)
        group = by_type.get(t, [])
        if t == "source":
            group.sort(key=lambda p: (str(p.fm.get("ingested", "")), p.name.lower()))
        else:
            group.sort(key=lambda p: p.name.lower())
        for p in group:
            line = "- [[%s]] — %s" % (p.name, p.fm.get("summary", ""))
            if t == "source":
                meta = " · ".join(x for x in [str(p.fm.get("source_type", "")), str(p.fm.get("published", ""))] if x)
                if meta:
                    line += " · " + meta
            out.append(line)
        out.append("")
    new = "\n".join(out)
    unstamp = lambda t: re.sub(r"(?m)^updated:.*$", "", t or "")
    if unstamp(new) == unstamp(old):
        return False, stamp
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    return True, stamp


# ---------- Chinese keywords for jev.py query ----------

ZH_KEYWORDS = os.path.join(DATA, "zh_keywords.json")
ZH_RARE_PAGES = 5      # a keyword appears in at most this many wiki pages…
ZH_RARE_RAW = 0.05     # …and in under this share of the Chinese raw notes


def build_zh_keywords(pages=None):
    """Chinese 2–4-character strings found in 1..ZH_RARE_PAGES wiki pages, with the share of Chinese raw
    notes that contain them -> tools/zh_keywords.json. jev.py query sends a question's rare strings to BM25.
    Rarity in the wiki alone isn't enough: the wiki is in English, so 什麼 or 這件事 are rare there too,
    but common in Chinese raw notes. Built locally; nothing leaves the vault."""
    pages = [p for p in (pages or load_pages()) if p.name not in SPECIAL]
    df = Counter()
    for p in pages:
        grams = set()
        for run in CJK_RUN.findall(zh(p.body)):
            for n in (2, 3, 4):
                grams.update(run[i:i + n] for i in range(len(run) - n + 1))
        df.update(grams)
    rare = {g for g, c in df.items() if c <= ZH_RARE_PAGES}
    seen, n_zh = Counter(), 0
    for text in raw_texts():
        runs = CJK_RUN.findall(zh(text))
        if sum(map(len, runs)) <= 500:      # not a Chinese note
            continue
        n_zh += 1
        found = set()
        for run in runs:
            for n in (2, 3, 4):
                found.update(g for g in (run[i:i + n] for i in range(len(run) - n + 1)) if g in rare)
        seen.update(found)
    share = {g: round(seen[g] / max(n_zh, 1), 4) for g in sorted(rare)}
    with open(ZH_KEYWORDS, "w", encoding="utf-8") as f:
        json.dump({"rare_pages": ZH_RARE_PAGES, "chinese_raw_notes": n_zh, "raw_share": share},
                  f, ensure_ascii=False, indent=0)
    return share


def zh_keywords():
    """{string: share of Chinese raw notes} from tools/zh_keywords.json, rebuilt (~15s) when missing or
    older than a wiki page, so a new page's Chinese terms reach query without a manual `index`."""
    built = os.path.getmtime(ZH_KEYWORDS) if os.path.exists(ZH_KEYWORDS) else 0
    if any(os.path.getmtime(p.path) > built for p in load_pages() if p.name not in SPECIAL):
        print("(wiki pages changed: rebuilding tools/zh_keywords.json, ~15s)", file=sys.stderr)
        return build_zh_keywords()
    with open(ZH_KEYWORDS, encoding="utf-8") as f:
        return json.load(f)["raw_share"]


# ---------- images: download a raw note's web images ----------

IMG_DIR = os.path.join(RAW, "assets")          # a note's downloaded images go to raw/assets/<note title>/
_URL = r"(?:https?://|data:image/)(?:[^()\s>]|\([^()\s]*\))+"
IMG_RE = re.compile(r'!\[([^\]]*)\]\(\s*<?(' + _URL + r')>?(?:\s+"[^"]*")?\s*\)'
                    r'|<img\b[^>]*?\bsrc="((?:https?://|data:image/)[^"]+)"[^>]*>')
VIDEO_RE = re.compile(r"youtube\.com|youtu\.be|vimeo\.com", re.I)
JUNK_RE = re.compile(r"avatar|profile_images|gravatar|logo|icon|badge|placeholder|/authors?/|call-to-action"
                     r"|altmetric|sprite|spinner|emoji|button|advert|tracking|pixel\.gif", re.I)
IMG_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp",
           "image/svg+xml": ".svg", "image/avif": ".avif", "image/tiff": ".tif"}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


def safe_name(s):
    return re.sub(r"\s+", " ", re.sub(r'[\\/:*?"<>|#^\[\]]', "", s)).strip()[:150].rstrip(". ")


def image_size(b):
    """(width, height) from PNG/GIF/JPEG/WEBP header bytes, or None."""
    import struct
    try:
        if b[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", b[16:24])
        if b[:6] in (b"GIF87a", b"GIF89a"):
            return struct.unpack("<HH", b[6:10])
        if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
            k = b[12:16]
            if k == b"VP8X":
                return 1 + int.from_bytes(b[24:27], "little"), 1 + int.from_bytes(b[27:30], "little")
            if k == b"VP8 ":
                w, h = struct.unpack("<HH", b[26:30])
                return w & 0x3FFF, h & 0x3FFF
            if k == b"VP8L":
                v = int.from_bytes(b[21:25], "little")
                return 1 + (v & 0x3FFF), 1 + ((v >> 14) & 0x3FFF)
        if b[:2] == b"\xff\xd8":
            i = 2
            while i < len(b) - 9:
                if b[i] != 0xFF:
                    i += 1
                    continue
                m = b[i + 1]
                if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h, w = struct.unpack(">HH", b[i + 5:i + 9])
                    return w, h
                if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
                    i += 2
                    continue
                i += 2 + struct.unpack(">H", b[i + 2:i + 4])[0]
    except Exception:
        pass
    return None


def too_small(wh):
    return bool(wh) and (max(wh) < 200 or (min(wh) < 100 and wh[0] * wh[1] < 30000))


def curl(url):
    r = subprocess.run(["curl", "-sSL", "--fail", "--retry", "3", "--retry-delay", "3", "--max-time", "90",
                        "-A", UA, "-o", "-", "-w", "\\n%{content_type}", url], capture_output=True)
    if r.returncode:
        raise RuntimeError(r.stderr.decode(errors="replace").strip().splitlines()[-1][:120])
    data, _, ct = r.stdout.rpartition(b"\n")
    return data, ct.decode().split(";")[0].strip().lower()


def fetch_image(url):
    """Image bytes and content type for an image URL (Wikipedia File: pages resolved to the image)."""
    import base64
    if url.startswith("data:"):
        head, _, body = url.partition(",")
        ct = head[5:].split(";")[0].lower()
        data = base64.b64decode(urllib.parse.unquote(body)) if ";base64" in head else urllib.parse.unquote(body).encode()
        return data, ct
    m = re.match(r"https?://([a-z\-]+)\.(?:m\.)?wikipedia\.org/wiki/File:(.+)", url)
    if m:
        api = (f"https://{m.group(1)}.wikipedia.org/w/api.php?action=query&prop=imageinfo&iiprop=url"
               f"&iiurlwidth=1280&format=json&titles=File:" + urllib.parse.quote(urllib.parse.unquote(m.group(2))))
        j = json.loads(curl(api)[0])
        ii = [i for p in j["query"]["pages"].values() for i in p.get("imageinfo", [])]
        if not ii:
            raise RuntimeError("Wikipedia file not found")
        url = ii[0].get("thumburl") or ii[0]["url"]
    return curl(url)


def scan_images(text):
    """Every image link in a note: number, match, url, alt, caption, auto decision and reason."""
    found = [m for m in IMG_RE.finditer(text)]
    counts = Counter(m.group(2) or m.group(3) for m in found)
    items = []
    for m in found:
        url, alt = m.group(2) or m.group(3), (m.group(1) or "").strip()
        after = text[m.end():m.end() + 300].lstrip(" )\n").split("\n")[0].strip()
        cap = re.sub(r"\s+", " ", alt or after)[:70]
        if VIDEO_RE.search(url):
            why = "video"
        elif url.startswith("data:image/svg"):
            why = "inline svg (site icon)"
        elif JUNK_RE.search(url.split("?")[0]) or JUNK_RE.search(alt) or re.search(r"/authors?/", after):
            why = "avatar/logo/icon/ad"
        elif counts[url] >= 3:
            why = f"repeated x{counts[url]}"
        else:
            why = ""
        items.append({"m": m, "url": url, "cap": cap, "why": why})
    # galleries: 5+ images in a row whose captions start with a year (e.g. "1911 touring")
    run = []
    for it in items + [None]:
        if it and not it["why"] and re.match(r"^(c\. )?\d{4}\b", it["cap"]):
            run.append(it)
            continue
        if len(run) >= 5:
            for r in run:
                r["why"] = "gallery"
        run = []
    return items


def parse_nums(s):
    out = set()
    for part in (s or "").split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.update(range(int(a), int(b) + 1))
        elif part:
            out.add(int(part))
    return out


def cmd_images(args):
    import hashlib
    path = os.path.abspath(args.file if os.path.exists(args.file) else os.path.join(VAULT, args.file))
    rel = os.path.relpath(path, VAULT)
    in_vault = not rel.startswith("..")
    if not path.endswith(".md") or (in_vault and not in_notes(rel)):
        sys.exit("images: give a raw/ note")
    text = open(path, encoding="utf-8").read()
    items = scan_images(text)
    skip, take = parse_nums(args.skip), parse_nums(args.take)
    for i, it in enumerate(items, 1):
        it["get"] = (not it["why"] or i in take) and i not in skip and not VIDEO_RE.search(it["url"])
    if not args.apply:
        if not items:
            print("no web images")
            return
        quiet = Counter(it["why"] for it in items if it["why"] in ("video", "inline svg (site icon)"))
        for i, it in enumerate(items, 1):
            if it["why"] in quiet:
                continue
            mark = "get " if it["get"] else "keep"
            note = it["why"]
            host = "data" if it["url"].startswith("data:") else it["url"].split("/")[2]
            print(f"{i:3} {mark} {note:22.22} {host:22.22} {it['cap']}")
        for why, c in quiet.items():
            print(f"    keep {why}: {c}")
        n = sum(it["get"] for it in items)
        print(f"\n{n} to download, {len(items) - n} keep their URL. "
              "Check the 'get' ones for decorative images, then: images FILE --apply [--skip 3,5-9] [--take 4]")
        return
    title = os.path.splitext(os.path.basename(path))[0]
    folder = os.path.join(IMG_DIR, safe_name(title))
    prefix = safe_name(title)[:40].rstrip(" .-,")
    taken = set()
    for root, dirs, files in os.walk(VAULT):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        taken.update(files)
    by_hash = {}
    if os.path.isdir(folder):
        for fn in os.listdir(folder):
            with open(os.path.join(folder, fn), "rb") as f:
                by_hash[hashlib.sha1(f.read()).hexdigest()] = fn
    by_url, done, failed, small = {}, 0, [], []
    n = 0
    for i, it in enumerate(items, 1):
        if not it["get"] or it["url"] in by_url:
            continue
        try:
            data, ct = fetch_image(it["url"])
            if not ct.startswith("image/"):
                raise RuntimeError("not an image: " + ct)
        except Exception as e:
            failed.append((i, str(e)))
            continue
        if i not in take and too_small(image_size(data)):
            small.append(i)
            by_url[it["url"]] = None
            continue
        h = hashlib.sha1(data).hexdigest()
        if h not in by_hash:
            os.makedirs(folder, exist_ok=True)
            ext = IMG_EXT.get(ct) or os.path.splitext(urllib.parse.urlparse(it["url"]).path)[1].lower() or ".img"
            while True:
                n += 1
                name = f"{prefix}-{n:02d}{ext}"
                if name not in taken:
                    break
            with open(os.path.join(folder, name), "wb") as f:
                f.write(data)
            taken.add(name)
            by_hash[h] = name
            done += 1
        by_url[it["url"]] = by_hash[h]
    out, last = [], 0
    for it in items:
        name = by_url.get(it["url"]) if it["get"] else None
        out += [text[last:it["m"].start()], f"![[{name}]]" if name else it["m"].group(0)]
        last = it["m"].end()
    out.append(text[last:])
    new = "".join(out)
    if new != text:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)
    print(f"{done} downloaded to {os.path.relpath(folder, VAULT)}/, "
          f"{sum(1 for it in items if it['get'] and by_url.get(it['url']))} links now local")
    if small:
        print("too small, kept URL: " + ", ".join(map(str, small)))
    for i, e in failed:
        print(f"failed #{i}: {e}")


# ---------- cite: add a source's facts to existing pages ----------

TAIL_HEADS = ("timeline", "tensions & open questions", "related", "sources")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


def add_to_fm_list(text, key, value):
    """Append a quoted value to a frontmatter list (inline or '- item' form) unless it's already there."""
    end = text.find("\n---", 3)
    fm, rest = text[:end], text[end:]
    m = re.search(r"^%s:[ \t]*\[(.*)\][ \t]*$" % re.escape(key), fm, re.M)
    if m:
        inner = m.group(1).strip()
        if value in inner:
            return text
        new = '%s: [%s"%s"]' % (key, inner + ", " if inner else "", value)
        return fm[:m.start()] + new + fm[m.end():] + rest
    m = re.search(r"^%s:[ \t]*\n((?:[ \t]*- .*\n?)*)" % re.escape(key), fm + "\n", re.M)
    if m:
        items = m.group(1)
        if value in items:
            return text
        pos = m.end(1) if items else m.end()
        fm2 = (fm + "\n")[:pos] + '  - "%s"\n' % value + (fm + "\n")[pos:]
        return fm2.rstrip("\n") + rest
    return fm + '\n%s: ["%s"]' % (key, value) + rest


def cite_into(text, section, block, link):
    """Put block into the page body: at the end of an existing section, or as a new `## section`
    before Timeline / Tensions / Related / Sources (or before those with no section given).
    Then make sure `## Sources` lists the link. Returns the new text."""
    lines = text.split("\n")
    body_start = text[:text.find("\n---", 3) + 4].count("\n") + 1 if text.startswith("---") else 0
    heads = [(i, len(m.group(1)), m.group(2)) for i, l in enumerate(lines) if i >= body_start
             for m in [HEAD_RE.match(l)] if m]
    tail = next((i for i, lv, h in heads if lv == 2 and h.lower().rstrip(":") in TAIL_HEADS), len(lines))
    target = None
    if section:
        want = section.lstrip("#").strip().lower()
        hit = next(((i, lv) for i, lv, h in heads if h.lower() == want), None)
        if hit:
            i, lv = hit
            nxt = next((j for j, l2, _ in heads if j > i and l2 <= lv), len(lines))
            target = nxt
            while target > i + 1 and not lines[target - 1].strip():
                target -= 1
            new = block.strip("\n").split("\n")
        else:
            target = tail
            new = ["## " + section.lstrip("#").strip(), ""] + block.strip("\n").split("\n")
    else:
        target = tail
        new = block.strip("\n").split("\n")
    if target == tail:                       # a new block: blank lines around it
        while target > 0 and not lines[target - 1].strip():
            target -= 1
        new = [""] + new + [""]
        lines[target:tail] = new
    else:
        if lines[target - 1].lstrip().startswith(">"):     # don't run on into a callout
            new = [""] + new
        lines[target:target] = new
    text = "\n".join(lines)
    # ## Sources
    m = re.search(r"^## Sources[ \t]*\n", text, re.M)
    if not m:
        return text.rstrip("\n") + "\n\n## Sources\n- %s\n" % link
    nxt = re.search(r"^#{1,2} ", text[m.end():], re.M)
    end = m.end() + nxt.start() if nxt else len(text)
    if link.lower() in text[m.end():end].lower():
        return text
    sec = text[m.end():end].rstrip("\n")
    return text[:m.end()] + (sec + "\n" if sec else "") + "- %s\n" % link + ("\n" + text[end:] if nxt else "")


def cmd_cite(args):
    """Blocks from FILE, each headed `=== Page Title | Section` (section optional), go into those pages,
    citing --source: the block goes in, `sources:` and `## Sources` get the source, `updated:` today."""
    import datetime
    pages = load_pages()
    by_name = resolver(pages)
    src = by_name.get(args.source.lower())
    if not src or src.type != "source":
        sys.exit("wiki: no source page titled %r" % args.source)
    link = "[[%s]]" % src.name
    text = open(args.file, encoding="utf-8").read() if args.file != "-" else sys.stdin.read()
    blocks = re.split(r"^===[ \t]*(.+?)[ \t]*$", text, flags=re.M)[1:]
    if not blocks:
        sys.exit("wiki: no '=== Page Title | Section' headers in %s" % args.file)
    today = datetime.date.today().isoformat()
    changed, problems = [], []
    for head, block in zip(blocks[::2], blocks[1::2]):
        title, _, section = head.partition("|")
        pg = by_name.get(title.strip().lower())
        if not pg or pg.type in ("source", "") or pg.name in SPECIAL:
            problems.append("no entity/concept/analysis page titled %r" % title.strip())
            continue
        if link.lower()[:-2] not in block.lower():
            problems.append("%s: the block never cites %s" % (pg.name, link))
        new = cite_into(pg.text, section.strip(), block, link)
        new = add_to_fm_list(new, "sources", link)
        new = re.sub(r"^updated:.*$", "updated: " + today, new, count=1, flags=re.M)
        if args.dry_run:
            print("=== %s%s\n%s" % (pg.rel, "  (§ %s)" % section.strip() if section.strip() else "",
                                     "\n".join(l for l in new.split("\n") if l not in pg.text.split("\n"))))
        else:
            with open(pg.path, "w", encoding="utf-8") as f:
                f.write(new)
        pg.text = new
        changed.append(pg.name)
    print("%s %d page(s): %s" % ("would update" if args.dry_run else "updated", len(changed),
                                 ", ".join("[[%s]]" % n for n in changed)))
    for pr in problems:
        print("!! " + pr)
    if problems and not args.dry_run:
        sys.exit(1)


ESSAYS_DIR = os.path.join(RAW, "essays")


def cmd_essay_source(args):
    """Record that an essay in raw/essays/ draws on a source: the raw note goes into the essay's `source:`
    list and the source page into the essay's wiki page `sources:` (with today's `updated:`)."""
    import datetime
    pages = load_pages()
    by_name = resolver(pages)
    src = by_name.get(args.source.lower())
    if not src or src.type != "source":
        sys.exit("wiki: no source page titled %r" % args.source)
    want = args.essay.strip().lower()
    found = []
    for r, ds, fs in os.walk(ESSAYS_DIR):
        for f in fs:
            if f.endswith(".md") and not f.startswith("."):
                path = os.path.join(r, f)
                fm, _, _ = parse_frontmatter(open(path, encoding="utf-8").read())
                if want in (f[:-3].lower(), str(fm.get("title", "")).lower()):
                    found.append(path)
    if len(found) != 1:
        sys.exit("wiki: %s essay in raw/essays/ named %r" % ("no" if not found else "more than one", args.essay))
    essay = found[0]
    raws = args.raw or [os.path.splitext(str(src.fm.get("source_path", "")).strip())[0]]
    out = []
    text = open(essay, encoding="utf-8").read()
    for r in raws:
        r = r.strip().strip("[]")
        r = r[:-3] if r.endswith(".md") else r
        if not r.startswith("raw/") or not (os.path.exists(os.path.join(VAULT, r + ".md"))
                                            or os.path.isdir(os.path.join(VAULT, r))):
            sys.exit("wiki: %r is not a raw note or folder" % r)
        new = add_to_fm_list(text, "source", "[[%s]]" % r)
        out.append(("added" if new != text else "already listed") + ": [[%s]]" % r)
        text = new
    rel_essay = os.path.relpath(essay, VAULT)
    page = next((p for p in pages if p.type == "source" and
                 os.path.normpath(str(p.fm.get("source_path", ""))) == os.path.normpath(rel_essay)), None)
    if not args.dry_run:
        with open(essay, "w", encoding="utf-8") as f:
            f.write(text)
    print("%s → source: %s" % (rel_essay, "; ".join(out)))
    if not page:
        print("!! the essay has no wiki page yet (ingest it); only its source: list was changed")
        return
    link = "[[%s]]" % src.name
    new = add_to_fm_list(page.text, "sources", link)
    if new != page.text:
        new = re.sub(r"^updated:.*$", "updated: " + datetime.date.today().isoformat(), new, count=1, flags=re.M)
        if not args.dry_run:
            with open(page.path, "w", encoding="utf-8") as f:
                f.write(new)
    print("%s → sources: %s" % (page.rel, "added " + link if new != page.text else "already lists " + link))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    st = sub.add_parser("status")
    st.add_argument("--no-convert", action="store_true", help="don't convert new PDFs first")
    st.add_argument("-n", type=int, default=10, help="units of raw/ to list (default 10)")
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("-n", type=int, default=10)
    sub.add_parser("lint")
    l = sub.add_parser("log")
    l.add_argument("-n", type=int, default=5)
    st = sub.add_parser("stats")
    st.add_argument("-n", type=int, default=15)
    sub.add_parser("index")
    o = sub.add_parser("outline")
    o.add_argument("file")
    o.add_argument("--skim", action="store_true", help="first sentence of every paragraph")
    o.add_argument("--hits", action="store_true", help="wiki entities/concepts mentioned, by page")
    o.add_argument("--lines", help="limit --skim/--hits to a line range, e.g. 120-480")
    ph = sub.add_parser("phrases")
    ph.add_argument("file", nargs="?", help="one raw note (default: all of raw/)")
    ci = sub.add_parser("cite")
    ci.add_argument("file", help="blocks headed '=== Page Title | Section' ('-' for stdin)")
    ci.add_argument("--source", required=True, help="the source page the blocks cite")
    ci.add_argument("--dry-run", action="store_true", help="show the new lines, write nothing")
    es = sub.add_parser("essay-source")
    es.add_argument("essay", help="the essay's file name or title in raw/essays/")
    es.add_argument("--source", required=True, help="the source page the essay draws on")
    es.add_argument("--raw", action="append", help="raw note(s) to list instead of the source's source_path "
                    "(e.g. a book's chapters); repeatable")
    es.add_argument("--dry-run", action="store_true")
    im = sub.add_parser("images")
    im.add_argument("file")
    im.add_argument("--apply", action="store_true", help="download and replace links")
    im.add_argument("--skip", help="image numbers to leave as URLs, e.g. 3,5-9")
    im.add_argument("--take", help="image numbers to download even if auto-skipped or small")
    args = ap.parse_args()
    cmds = {"status": cmd_status, "search": cmd_search, "lint": cmd_lint, "log": cmd_log, "stats": cmd_stats, "index": cmd_index, "outline": cmd_outline, "images": cmd_images, "phrases": cmd_phrases, "cite": cmd_cite, "essay-source": cmd_essay_source}
    if args.cmd not in cmds:
        ap.print_help()
        sys.exit(2)
    cmds[args.cmd](args)


if __name__ == "__main__":
    main()
