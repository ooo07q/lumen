#!/usr/bin/env python3
"""The app's tools for the wiki agent, as a small MCP server (stdio, JSON-RPC, stdlib only).

The agent gets no shell: a shell can read anything (`grep -r` walks straight into the journal). Instead it gets
these tools, each a fixed command of the app's own tools/wiki.py and tools/jev.py, run on the open vault:
- a file argument must be one of the user's notes (never the journal, never outside the vault);
- output lines naming a page drawn from the journal, or the journal folder, are dropped;
- in the plan phase only the tools that read are offered; cite and lint (which write wiki/) come in the act phase;
- Jev's tools are offered only when Jev is on (NOTES_AGENT_JEV=1).

Environment: NOTES_VAULT, NOTES_DATA (as for the tools), NOTES_AGENT_PHASE (plan | act), NOTES_AGENT_JEV (0 | 1).
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
    return run(wiki.cmd_outline, file=os.path.join(wiki.VAULT, note_file(a["file"])), hits=bool(a.get("hits")),
               skim=bool(a.get("skim")), lines=a.get("lines"))


def t_prep(a):
    return run(jev.cmd_prep, file=os.path.join(wiki.VAULT, note_file(a["file"])), max=40)


def t_skim(a):
    return run(jev.cmd_skim, file=os.path.join(wiki.VAULT, note_file(a["file"])), lines=a.get("lines"))


def t_query(a):
    return run(jev.cmd_query, question=a["question"], n=int(a.get("n") or 20), bm25=5)


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
    ("log", "plan act", False, t_log, "The last n entries of wiki/log.md.", S({"n": INT})),
    ("check_source", "act", True, t_check_source,
     "After writing a source page: the raw note's parts whose main point the page leaves out, and the page's "
     "bullets the note doesn't back (names, numbers). A filter: read the passages it names, then fix the page.",
     S({"title": STR}, ["title"])),
    ("cite", "act", False, t_cite,
     "Add text to existing wiki pages, citing a source page. `blocks`: blocks each headed '=== Page Title | Section' "
     "(section optional); each goes at the end of that section (or a new section), and the page gets the source in "
     "sources:, ## Sources and today's updated:. dry_run=true shows the change without writing.",
     S({"blocks": STR, "source": STR, "dry_run": BOOL}, ["blocks", "source"])),
    ("lint", "act", False, t_lint,
     "Rebuild wiki/index.md and check the wiki mechanically (broken frontmatter, links, names). Only in the "
     "'check the wiki' task, full=true (Jev on) also runs Jev's checks over the whole wiki: aliases, missing links "
     "(applied), contradictions, not_aliases phrases; slow the first time on a vault.",
     S({"full": BOOL})),
]
AVAILABLE = {t[0]: t for t in TOOLS if PHASE in t[1].split() and (JEV_ON or not t[2])}


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
