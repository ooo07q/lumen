#!/usr/bin/env python3
"""The app's tools for the wiki agent, as a small MCP server (stdio, JSON-RPC, stdlib only).

The agent gets no shell: a shell can read anything (`grep -r` walks straight into the journal). Instead it gets
these tools, each a fixed command of the app's own tools/wiki.py and tools/jev.py, run on the open vault:
- a file argument must be one of the user's notes (never the journal, never outside the vault);
- output lines naming a page drawn from the journal, or the journal folder, are dropped;
- in the plan phase only the tools that read are offered; cite and lint (which write wiki/) come in the act phase;
- Jev's tools are offered only when Jev is on (NOTES_AGENT_JEV=1);
- with NOTES_AGENT_FILES=1 (the AI has no file tools of its own) also `read`, and in the act phase `write` and
  `edit`, which touch only wiki/ (never index.md or a page drawn from the journal);
- the "lean" phase: the AI was handed everything it reads, so it gets only the tools that write and check.

Environment: NOTES_VAULT, NOTES_DATA (as for the tools), NOTES_AGENT_PHASE (plan | act | lean), NOTES_AGENT_JEV
(0 | 1), NOTES_AGENT_FILES (0 | 1).
"""
import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
OUT = sys.stdout                       # the protocol channel; tool output is captured, never printed here
sys.stdout = sys.stderr                # anything a tool prints outside a capture goes to the log, not the protocol
import wiki  # noqa: E402
import jev   # noqa: E402

PHASE = os.environ.get("NOTES_AGENT_PHASE", "plan")
JEV_ON = os.environ.get("NOTES_AGENT_JEV") == "1"
TASK = os.environ.get("NOTES_AGENT_TASK", "")
FILES = os.environ.get("NOTES_AGENT_FILES") == "1" or PHASE == "lean"
RUN = os.environ.get("NOTES_AGENT_RUN", "")
WHOLE = os.environ.get("NOTES_AGENT_WHOLE") == "1"          # the user asked for the note to be read whole
# a long note organised a part at a time: this run covers lines PART ("A-B") of the note NOTE only
NOTE = os.environ.get("NOTES_AGENT_NOTE", "")
PART = os.environ.get("NOTES_AGENT_PART", "")


def part_of(rel):
    """This run's part ("A-B") when `rel` is the note being organised a part at a time, else None."""
    return PART if PART and NOTE and os.path.normpath(rel) == os.path.normpath(NOTE) else None
MAX_OUT = 60000


def private_pages():
    """Wiki pages drawn from the journal: (titles, rels)."""
    pages = [p for p in wiki.load_pages() if p.name not in wiki.SPECIAL]     # index, log: not drawn from anything
    ok = {p.name for p in jev.query_pages()}
    priv = [p for p in pages if p.name not in ok]
    return {p.name for p in priv}, {p.rel for p in priv}


def scrub(text):
    names, rels = private_pages()
    j = wiki.JOURNAL_REL.rstrip("/") + "/"
    keep = []
    for line in text.split("\n"):
        if j in line or any(r in line for r in rels) or any(n and n in line for n in names):
            continue
        keep.append(line)
    text = "\n".join(keep)
    return text if len(text) <= MAX_OUT else text[:MAX_OUT] + "\n… (cut at %d characters)" % MAX_OUT


def note_file(arg):
    """A vault-relative path of one of the user's notes, or ValueError."""
    full = os.path.realpath(arg if os.path.isabs(arg) else os.path.join(wiki.VAULT, arg))
    vault = os.path.realpath(wiki.VAULT)
    if not full.startswith(vault + os.sep):
        raise ValueError("not a file in this vault: %s" % arg)
    rel = os.path.relpath(full, vault)
    if rel == wiki.JOURNAL_REL or rel.startswith(wiki.JOURNAL_REL.rstrip("/") + "/"):
        raise ValueError("the journal is off limits")
    if not rel.endswith(".md") or not os.path.isfile(full):
        raise ValueError("no such note: %s" % arg)
    if not wiki.in_notes(rel):
        raise ValueError("not one of the user's notes (wiki pages are read with Read): %s" % arg)
    return rel


def run(fn, **kw):
    """Call a tool command with an argparse namespace; return what it printed."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            fn(argparse.Namespace(**kw))
        except SystemExit as e:
            if e.code not in (None, 0, 1):
                print(e.code)
    return scrub(buf.getvalue()) or "(no output)"


def t_search(a):
    _, rels = private_pages()
    pages = [p for p in wiki.load_pages() if p.rel not in rels]
    scored = wiki.search_pages(a["query"], pages)
    if not scored:
        return "No results."
    lines = []
    for s, p in scored[: int(a.get("n") or 10)]:
        lines.append("%6.2f  %-10s %s" % (s, p.type or "?", p.rel))
        if p.fm.get("summary"):
            lines.append("        " + str(p.fm["summary"]))
    return scrub("\n".join(lines))


def t_outline(a):
    rel = note_file(a["file"])
    return run(wiki.cmd_outline, file=os.path.join(wiki.VAULT, rel), hits=bool(a.get("hits")),
               skim=bool(a.get("skim")), lines=a.get("lines") or part_of(rel))


def t_prep(a):
    rel = note_file(a["file"])
    return run(jev.cmd_prep, file=os.path.join(wiki.VAULT, rel), max=40, lines=part_of(rel))


def t_skim(a):
    rel = note_file(a["file"])
    return run(jev.cmd_skim, file=os.path.join(wiki.VAULT, rel), lines=a.get("lines") or part_of(rel))


def t_query(a):
    return run(jev.cmd_query, question=a["question"], n=int(a.get("n") or 20), bm25=5)


def t_read(a):
    """One of the user's notes, or a wiki page (never the journal or a page drawn from it), with line numbers."""
    arg = str(a.get("path") or "")
    full = os.path.realpath(arg if os.path.isabs(arg) else os.path.join(wiki.VAULT, arg))
    vault = os.path.realpath(wiki.VAULT)
    rel = os.path.relpath(full, vault)
    if rel.startswith("wiki" + os.sep) and rel.endswith(".md") and os.path.isfile(full):
        _, rels = private_pages()
        if rel in rels:
            raise ValueError("this page is drawn from the journal: off limits")
    else:
        rel = note_file(arg)
        full = os.path.join(vault, rel)
    lines = open(full, encoding="utf-8", errors="replace").read().split("\n")
    a0, _, b0 = str(a.get("lines") or "").partition("-")
    start = max(int(a0), 1) if a0.strip().isdigit() else 1
    end = min(int(b0), len(lines)) if b0.strip().isdigit() else min(len(lines), start + 1999)
    part = part_of(rel)
    if part:                                         # this run covers one part of the note: only its lines
        pa, _, pb = part.partition("-")
        pa, pb = int(pa), min(int(pb), len(lines))
        if end < pa or start > pb:
            raise ValueError("this run covers lines %s of the note only (one part of a long note)" % part)
        start = max(start, pa)
        end = min(end if b0.strip().isdigit() else pb, pb)
    keep, note = None, ""
    if not rel.startswith("wiki" + os.sep) and not WHOLE and wiki.est_tokens("\n".join(lines)) > wiki.READ_WHOLE:
        # a long note: its key passages, the paragraphs Jev rates as carrying ~80% of its key points, and headings
        try:
            keep, st = jev.key_lines(full, part=part)
            note = ("(you get the note's key passages — the paragraphs Jev rates as carrying %d%% of its key "
                    "points, %d of %d paragraphs — and its headings; the rest is left out)\n"
                    % (round(st["coverage"] * 100), st["kept"], st["paragraphs"]))
        except Exception as e:                       # Jev off or failing: the note as it is
            note = "(Jev couldn't pick the key passages (%s): the lines as they are)\n" % str(e)[:120]
    if keep is None:
        out = "\n".join("%6d\t%s" % (i, lines[i - 1]) for i in range(start, end + 1))
    else:
        rows, gap = [], []

        def flush():
            if any(len(lines[j - 1].strip()) >= 40 for j in gap):     # a real passage, not page furniture
                rows.append("     …\t(lines %d–%d left out)" % (gap[0], gap[-1]) if len(gap) > 1
                            else "     …\t(line %d left out)" % gap[0])
            gap.clear()
        for i in range(start, end + 1):
            if (i - 1) in keep:
                flush()
                rows.append("%6d\t%s" % (i, lines[i - 1]))
            else:
                gap.append(i)
        flush()
        out = note + "\n".join(rows)
    if rel.startswith("wiki" + os.sep):              # index.md and others list journal-drawn pages: drop those lines
        out = scrub(out)
    if end < len(lines):
        out += "\n… (%d lines in all; ask for lines='%d-…' to read on)" % (len(lines), end + 1)
    return out if len(out) <= MAX_OUT else out[:MAX_OUT] + "\n… (cut)"


def wiki_file(arg):
    """(vault-relative, absolute) path of a page the AI may write: a .md file under wiki/, not index.md, not a
    page drawn from the journal."""
    arg = str(arg or "").strip()
    vault = os.path.realpath(wiki.VAULT)
    full = os.path.realpath(arg if os.path.isabs(arg) else os.path.join(vault, arg))
    root = os.path.join(vault, "wiki")
    if not full.startswith(root + os.sep) or not full.endswith(".md"):
        raise ValueError("only .md pages under wiki/ can be written: %s" % arg)
    rel = os.path.relpath(full, vault)
    bad = set(os.path.basename(full)[:-3]) & set(':*?"<>|#^[]\\')
    if bad:
        raise ValueError("a page title can't contain %s (links break): choose another title, e.g. ' — ' for '|'"
                         % " ".join(sorted(bad)))
    if rel == os.path.join("wiki", "index.md"):
        raise ValueError("wiki/index.md is rebuilt by lint: don't write it")
    if os.path.exists(full):
        _, rels = private_pages()
        if rel in rels:
            raise ValueError("this page is drawn from the journal: off limits")
    return rel, full


def save(full, text):
    os.makedirs(os.path.dirname(full), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(full), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, full)


CREATED = set()                        # pages this run created: the only ones `remove` may take back


def t_write(a):
    rel, full = wiki_file(a.get("path"))
    text = str(a.get("content") or "")
    if not text.strip():
        raise ValueError("empty content")
    existed = os.path.exists(full)
    save(full, text if text.endswith("\n") else text + "\n")
    if not existed:
        CREATED.add(rel)
    return "%s %s (%d lines)" % ("replaced" if existed else "created", rel, text.count("\n") + 1)


def t_edit(a):
    rel, full = wiki_file(a.get("path"))
    if not os.path.isfile(full):
        raise ValueError("no such page: %s (create it with write)" % rel)
    old, new = str(a.get("old") or ""), str(a.get("new") or "")
    text = open(full, encoding="utf-8").read()
    n = text.count(old) if old else 0
    if n == 0:
        raise ValueError("`old` is not in %s: copy it exactly from the page (read it first)" % rel)
    if n > 1 and not a.get("all"):
        raise ValueError("`old` occurs %d times in %s: give more context, or all=true" % (n, rel))
    save(full, text.replace(old, new) if a.get("all") else text.replace(old, new, 1))
    return "edited %s (%d place%s)" % (rel, n if a.get("all") else 1, "s" if a.get("all") and n > 1 else "")


def t_remove(a):
    rel, full = wiki_file(a.get("path"))
    if rel not in CREATED:
        raise ValueError("only a page you created in this run can be removed: %s" % rel)
    os.remove(full)
    CREATED.discard(rel)
    return "removed %s" % rel


def t_log_append(a):
    entry = str(a.get("entry") or "").strip()
    if not entry.startswith("## ["):
        raise ValueError("an entry starts with its header line: ## [YYYY-MM-DD] operation | Title")
    full = os.path.join(wiki.VAULT, "wiki", "log.md")
    text = open(full, encoding="utf-8").read() if os.path.exists(full) else "# Log\n"
    save(full, text.rstrip("\n") + "\n\n" + entry + "\n")
    return "appended to wiki/log.md"


def t_log(a):
    return run(wiki.cmd_log, n=int(a.get("n") or 5))


def t_check_source(a):
    return run(jev.cmd_check_source, source=a["title"])


def t_cite(a):
    fd, path = tempfile.mkstemp(suffix=".md", dir=wiki.DATA)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(a["blocks"])
        return run(wiki.cmd_cite, file=path, source=a["source"], dry_run=bool(a.get("dry_run")))
    finally:
        os.remove(path)


def t_lint(a):
    if a.get("full") and JEV_ON and TASK == "lint":   # Jev over the whole wiki: only when checking the wiki
        return run(jev.cmd_lint, all=False)
    return run(wiki.cmd_lint)


S = lambda props, req=(): {"type": "object", "properties": props, "required": list(req)}  # noqa: E731
STR, INT, BOOL = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}

TOOLS = [
    # name, phases, needs Jev, function, description, schema
    ("search", "plan act", False, t_search,
     "BM25 search over the wiki's pages (titles, aliases and summaries weigh most). Returns score, type, path, summary.",
     S({"query": STR, "n": INT}, ["query"])),
    ("outline", "plan act", False, t_outline,
     "Map of one of the user's notes: size, reading mode, sections with line numbers. hits=true adds the wiki pages "
     "it mentions and new terms per part; skim=true each paragraph's central sentence; lines='A-B' limits both.",
     S({"file": STR, "hits": BOOL, "skim": BOOL, "lines": STR}, ["file"])),
    ("prep", "plan act", True, t_prep,
     "Jev's report on a note before reading it: map, pages it mentions (and which matches are false), new terms, "
     "not_aliases phrases, and for long notes a skim. Ignore its web-images section (notes are never changed).",
     S({"file": STR}, ["file"])),
    ("skim", "plan act", True, t_skim,
     "Jev's skim of part of a long note: each paragraph's main sentence for the most central paragraphs.",
     S({"file": STR, "lines": STR}, ["file"])),
    ("jev_query", "plan act", True, t_query,
     "Jev's ranking of the wiki pages most likely to help with a question (plus keyword matches).",
     S({"question": STR, "n": INT}, ["question"])),
    ("read", "plan act files", False, t_read,
     "Read one of the user's notes or a wiki page (vault-relative path), with line numbers; lines='A-B' for a part. "
     "The journal and pages drawn from it are refused.",
     S({"path": STR, "lines": STR}, ["path"])),
    ("log", "plan act", False, t_log, "The last n entries of wiki/log.md.", S({"n": INT})),
    ("write", "act lean files", False, t_write,
     "Create a wiki page, or replace one whole (path like 'wiki/concepts/Title.md'; content: the full page with "
     "frontmatter). Only under wiki/.",
     S({"path": STR, "content": STR}, ["path", "content"])),
    ("edit", "act lean files", False, t_edit,
     "Change part of a wiki page: replace the exact text `old` (copied from the page; it must occur once unless "
     "all=true) with `new`. For fixes, summary changes and callouts; additions go through cite.",
     S({"path": STR, "old": STR, "new": STR, "all": BOOL}, ["path", "old", "new"])),
    ("remove", "act lean files", False, t_remove,
     "Take back a page you created in this run (e.g. one written under a wrong title). Nothing else can be removed.",
     S({"path": STR}, ["path"])),
    ("log_append", "act lean", False, t_log_append,
     "Append an entry to wiki/log.md: its header line '## [YYYY-MM-DD] ingest | Title', then '- created: …', "
     "'- updated: …', '- notes: …' lines.",
     S({"entry": STR}, ["entry"])),
    ("check_source", "act lean", True, t_check_source,
     "After writing a source page: the raw note's parts whose main point the page leaves out, and the page's "
     "bullets the note doesn't back (names, numbers). A filter: read the passages it names, then fix the page.",
     S({"title": STR}, ["title"])),
    ("cite", "act lean", False, t_cite,
     "Add text to existing wiki pages, citing a source page. `blocks`: blocks each headed '=== Page Title | Section' "
     "(section optional); each goes at the end of that section (or a new section), and the page gets the source in "
     "sources:, ## Sources and today's updated:. dry_run=true shows the change without writing.",
     S({"blocks": STR, "source": STR, "dry_run": BOOL}, ["blocks", "source"])),
    ("lint", "act lean", False, t_lint,
     "Rebuild wiki/index.md and check the wiki mechanically (broken frontmatter, links, names). Only in the "
     "'check the wiki' task, full=true (Jev on) also runs Jev's checks over the whole wiki: aliases, missing links "
     "(applied), contradictions, not_aliases phrases; slow the first time on a vault.",
     S({"full": BOOL})),
]
def offered(phases):
    p = phases.split()
    if "files" in p and not FILES:
        return False
    return PHASE in p


AVAILABLE = {t[0]: t for t in TOOLS if offered(t[1]) and (JEV_ON or not t[2])}


def reply(id_, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": id_}
    if error:
        msg["error"] = {"code": -32601, "message": error}
    else:
        msg["result"] = result
    OUT.write(json.dumps(msg, ensure_ascii=False) + "\n")
    OUT.flush()


def main():
    for line in sys.stdin:
        try:
            req = json.loads(line)
        except ValueError:
            continue
        method, id_, params = req.get("method"), req.get("id"), req.get("params") or {}
        if id_ is None:                           # a notification
            continue
        if method == "initialize":
            reply(id_, {"protocolVersion": params.get("protocolVersion", "2024-11-05"),
                        "capabilities": {"tools": {}}, "serverInfo": {"name": "notes", "version": "1"}})
        elif method == "tools/list":
            reply(id_, {"tools": [{"name": n, "description": t[4], "inputSchema": t[5]} for n, t in AVAILABLE.items()]})
        elif method == "tools/call":
            t = AVAILABLE.get(params.get("name"))
            if not t:
                reply(id_, {"content": [{"type": "text", "text": "no such tool now"}], "isError": True})
                continue
            try:
                text = t[3](params.get("arguments") or {})
                reply(id_, {"content": [{"type": "text", "text": text}]})
            except ValueError as e:
                reply(id_, {"content": [{"type": "text", "text": str(e)}], "isError": True})
            except Exception:
                traceback.print_exc(file=sys.stderr)
                reply(id_, {"content": [{"type": "text", "text": "the tool failed: %s" % traceback.format_exc(limit=1)[-300:]}],
                      "isError": True})
        elif method == "ping":
            reply(id_, {})
        else:
            reply(id_, error="unknown method %s" % method)


if __name__ == "__main__":
    main()
