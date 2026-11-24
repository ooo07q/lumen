#!/usr/bin/env python3
"""Jev (TypeSafe) judgments for ingest, lint and query.

Jev answers fixed questions about one item at a time (a raw note, a mention, a new term, a phrase,
an image, an alias, an essay); the rules in this file turn the answers into a decision. A clear
answer (probability >= 0.8, or <= 0.2) decides; the band between is printed as "check", for Claude
to read the text and decide. Jev is paid per input token (~$0.04 per million), so calls are cheap.

  python3 tools/jev.py triage [--limit N] [--redo]  convert new PDFs, rank unprocessed raw notes and books
                                           -> tools/triage.json
  python3 tools/jev.py prep FILE           ingest step 2 in one run: map, images, hits, terms, phrases, skim
  python3 tools/jev.py check-source TITLE  a source page against its raw note (missing main points, unbacked
                                           bullets), then which essays in raw/essays/ draw on it
  python3 tools/jev.py lint [--all]        lint's Jev checks in one run: aliases, links (applied), contradictions,
                                           not_aliases phrases across raw/
  python3 tools/jev.py hits FILE           check outline --hits matches against their context
  python3 tools/jev.py terms FILE          outline's new terms: conversion typo / same as a page / worth a page
  python3 tools/jev.py phrases [FILE]      glued names: does the phrase mean something else (not_aliases)? (no FILE: all raw/)
  python3 tools/jev.py images FILE         undecided web images: download or keep the URL (-> --skip list)
  python3 tools/jev.py aliases [PAGE ...] [--all]  aliases against CLAUDE.md §2 (default: every entity and
                                           concept); asks only new or changed ones (tools/aliases.json)
  python3 tools/jev.py essays SOURCE       which essays in raw/essays/ draw on, or are confirmed by, a source page
  python3 tools/jev.py skim FILE [--lines A-B]  outline --skim with Jev picking the central paragraphs and sentences
  python3 tools/jev.py contradictions     source pages that link the same topic and conflict about it (new or
                                           changed pairs; answers kept in tools/contradictions.json)
  python3 tools/jev.py links [--apply]     wiki pages that name another page without linking it: Jev-sure ones
                                           linked (first mention), unsure ones listed; answers kept in tools/links.json
  python3 tools/jev.py query "QUESTION"    pages that help answer a question (/query): Jev over every page card,
                                           plus BM25 for the question's rare keywords; stops if any request fails

Key: TYPESAFE_API_KEY or ~/.config/typesafe/api_key. Stdlib only, run from the vault root.
"""
import argparse
import itertools
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wiki  # noqa: E402

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
KEY_FILE = os.path.expanduser("~/.config/typesafe/api_key")
TRIAGE = os.path.join(wiki.DATA, "triage.json")
ESSAYS = os.path.join(wiki.RAW, "essays")
ALIASES = os.path.join(wiki.DATA, "aliases.json")
ALIASES_USE = os.path.join(wiki.DATA, "aliases_use.json")
YES, NO = 0.8, 0.2          # clear yes / clear no; between = "check" (conservative: more items go to "check")
COVER = 0.7                 # a Score reads as the lowest level covering 70% of its probability
WORKERS = 6
SNIPPET = 300               # characters of context on each side of a mention


# ------------------------------------------------------------------ Jev

def _ssl():
    ctx = ssl.create_default_context()
    if ctx.get_ca_certs() or ssl.get_default_verify_paths().cafile:
        return ctx
    for path in ("/etc/ssl/cert.pem", "/private/etc/ssl/cert.pem"):
        if os.path.exists(path):
            return ssl.create_default_context(cafile=path)
    return ctx


def _key():
    k = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not k and os.path.exists(KEY_FILE):
        k = open(KEY_FILE).read().strip()
    if not k:
        sys.exit("jev: no API key (TYPESAFE_API_KEY or %s)" % KEY_FILE)
    return k


def ask(state, questions):
    """One state, several questions, one request. Retries 429/5xx/network with backoff; raises on
    failure, so a failed call is never read as an answer."""
    body = json.dumps({"model": MODEL, "state": state, "questions": questions}).encode()
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "Authorization": "Bearer " + _key(), "Content-Type": "application/json"})
    err = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60, context=_ssl()) as r:
                return json.loads(r.read().decode())["answers"]
        except urllib.error.HTTPError as e:
            err = "HTTP %d %s" % (e.code, e.read().decode(errors="ignore")[:200])
            if e.code != 429 and e.code < 500:
                break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            err = type(e).__name__
        time.sleep(1.5 * 2 ** attempt)
    raise RuntimeError("Jev: %s" % err)


FAILED = [0]                # items Jev gave no answer for this run (ask_all); main() reports them


def ask_all(items, questions_of):
    """[(item, answers or None)] for items asked in parallel; questions_of(item) -> (state, questions)."""
    def one(it):
        try:
            return it, ask(*questions_of(it))
        except RuntimeError as e:
            FAILED[0] += 1
            if FAILED[0] <= 3:
                print("  ! %s" % e, file=sys.stderr)
            return it, None
    with ThreadPoolExecutor(WORKERS) as ex:
        return list(ex.map(one, items))


def noul(a, name):
    return float(a[name]["noul"])


def score(a, name):
    """Lowest level covering COVER of the probability: an unsure answer reads higher."""
    probs = {int(k): float(v) for k, v in a[name]["probabilities"].items()}
    total = 0.0
    for lv in sorted(probs):
        total += probs[lv]
        if total >= COVER:
            return lv
    return max(probs)


def choice(a, name):
    """(option, p); option is None unless p >= YES."""
    c = a[name]["choice"]
    p = float(a[name]["probabilities"].get(c, 0))
    return (c if p >= YES else None), p


def band(p):
    return "yes" if p >= YES else "no" if p <= NO else "check"


def N(instructions, true, false):
    return {"type": "noul", "instructions": instructions, "criteria": {"true": true, "false": false}}


def S(instructions, levels):
    return {"type": "score", "instructions": instructions, "criteria": levels}


def C(instructions, options):
    return {"type": "choice", "instructions": instructions, "criteria": options}


# --------------------------------------------------------------- text

def flat(text):
    """Body text for a state: no frontmatter, embeds, HTML or page markers; whitespace collapsed."""
    _, body, _ = wiki.parse_frontmatter(text)
    body = re.sub(r"!\[\[[^\]]*\]\]|!\[[^\]]*\]\([^)]*\)", " ", body)
    body = re.sub(r"<!-- p\.(\d+) -->", r"[p.\1]", body)
    body = re.sub(r"<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", body).strip()


def read(rel):
    return open(os.path.join(wiki.VAULT, rel), encoding="utf-8", errors="ignore").read()


def contexts(text, rx, n=3):
    """Up to n passages around matches of rx, spread over the text (first, middle, last…)."""
    ms = list(rx.finditer(text))
    if not ms:
        return []
    pick = sorted({round(i * (len(ms) - 1) / max(n - 1, 1)) for i in range(n)}) if len(ms) > n else range(len(ms))
    return [text[max(ms[i].start() - SNIPPET, 0):ms[i].end() + SNIPPET] for i in pick]


def name_rx(t, case_sensitive=False):
    """A wiki name in folded text: Chinese as is, Latin as a whole word across line breaks."""
    core = re.escape(t) if wiki.CJK_RUN.search(t) else \
        r"(?<![\w])" + re.escape(t).replace(r"\ ", r"[\s+]+") + r"(?![\w])"
    return re.compile(core if case_sensitive else "(?i:" + core + ")")


def page_card(p):
    return {"title": p.name, "type": p.type, "summary": str(p.fm.get("summary", ""))}


JOURNAL = wiki.JOURNAL


def private(path):
    """The human's journal never goes to Jev (CLAUDE.md §6)."""
    return os.path.abspath(os.path.join(wiki.VAULT, path)).startswith(JOURNAL + os.sep)


def note_path(arg):
    path = arg if os.path.isabs(arg) else os.path.join(wiki.VAULT, arg)
    if not os.path.exists(path):
        sys.exit("jev: no such file: %s" % arg)
    if private(path):
        sys.exit("jev: raw/journal/ is not sent to Jev")
    return path


# ------------------------------------------------------------- triage

TRIAGE_Q = {
    "relevance": S("How closely is the subject of `excerpt` tied to the wiki topics in `related_pages`?", [
        "Its subject matches none of `related_pages`: ingesting it would start a topic the wiki doesn't have.",
        "It touches one or two of `related_pages` in passing (it names a person or idea the wiki has a page "
        "on), but its subject is elsewhere.",
        "Its subject is the same as one or more of `related_pages`, and it adds an argument, case, data or "
        "viewpoint on it.",
        "It is a primary text or central study on a subject several of `related_pages` are about: the original "
        "work a concept page discusses, or the work those pages keep citing.",
    ]),
    "substance": S("How much is there to learn from the whole text `excerpt` samples? `excerpt` joins its opening "
                   "and slices from inside it with \" … \"; `tokens` is the whole text's length.", [
        "Little: the whole text is only a cover, table of contents, index, front matter, notes, a page of links "
        "or ads, or a few lines.",
        "A short or light piece: a news brief, a summary, a short post, a list of tips or quotes.",
        "A full argument, study, chapter, interview or long discussion.",
    ]),
    "broken": N("Is the text in `excerpt` too damaged by PDF conversion or OCR for a careful reader to follow?",
                "Most sentences can't be followed: characters are garbled or mojibake, words are broken into "
                "letters, or it is only a cover or permissions page where an article or chapter should follow.",
                "The sentences can be followed, even with OCR typos, words clipped at line edges, running headers, "
                "page numbers, or footnotes and table fragments mixed into the text."),
    "overlap": C("How does `excerpt` relate to the source pages (type source) in `related_pages`?", {
        "none": "It is a different work from every listed source page, even if on the same subject or by the "
                "same author; or no source page is listed.",
        "same_text": "It is the same text a listed source page already covers: the same title and author, in "
                     "another copy, version, edition or translation, or an excerpt of it.",
        "other_part": "It is another part of a work a listed source page covers in part: a chapter, part, "
                      "volume or the rest of a book of which only some is ingested.",
    }),
}


def triage_units(pages):
    """Unprocessed raw notes grouped as ingest units: a top-level note, or a book folder."""
    done = wiki.processed_paths(pages)
    units = defaultdict(list)
    for r in wiki.raw_files():
        if r.endswith(".md") and os.path.normpath(r) not in done:
            unit = wiki.unit_of(r)
            full = os.path.abspath(os.path.join(wiki.VAULT, r))
            if private(r) or full.startswith(ESSAYS + os.sep):   # essays aren't sources to ingest; the journal never goes to Jev
                continue
            units[unit].append(r)
    return units


def essay_sources():
    """{raw note or book folder: [essays whose `source:` lists it]}, from raw/essays/ (subfolders too)."""
    cited = defaultdict(list)
    for r, ds, fs in os.walk(ESSAYS):
        for f in fs:
            if not f.endswith(".md") or f.startswith("."):
                continue
            fm, _, _ = wiki.parse_frontmatter(open(os.path.join(r, f), encoding="utf-8").read())
            for v in fm.get("source") or []:
                m = re.match(r"\[\[(raw/[^\]|#]+)", str(v).strip())
                if not m:
                    continue                    # a URL: no raw note to point at
                rel = os.path.normpath(m.group(1))
                if not rel.endswith(".md") and os.path.isfile(os.path.join(wiki.VAULT, rel + ".md")):
                    rel += ".md"
                cited[rel].append(f[:-3])
    return cited


def triage_state(unit, files, pages):
    files = sorted(files)
    if len(files) == 1 and unit == files[0]:
        text = read(unit)
        fm, _, _ = wiki.parse_frontmatter(text)
        title, chapters, body = str(fm.get("title") or os.path.basename(unit)[:-3]), [], flat(text)
    else:   # a book: the chapter list, and text from its chapters
        title, chapters = os.path.basename(unit), [os.path.basename(f)[:-3] for f in files]
        body = " … ".join(flat(read(f)) for f in files)
    tokens = sum(wiki.est_tokens(read(f)) for f in files)
    # the opening (title, often a cover or contents) plus slices from inside, where the real text is
    cuts = [0] if len(body) < 6000 else [0, len(body) // 4, len(body) // 2, 3 * len(body) // 4]
    excerpt = " … ".join(body[c:c + (600 if len(cuts) > 1 else 1500)] for c in cuts)
    related = [page_card(p) for _, p in wiki.search_pages(title + " " + body[:400], pages)[:6]]
    state = {"title": title, "folder": os.path.dirname(unit), "tokens": tokens, "excerpt": excerpt,
             "related_pages": related}
    if chapters:
        state["chapters"] = chapters[:40]
    return state, TRIAGE_Q


def pdf_pages(path):
    """Page count of a PDF: Spotlight's, else the largest /Count in the file; 0 if unknown."""
    try:
        out = subprocess.run(["mdls", "-raw", "-name", "kMDItemNumberOfPages", path],
                             capture_output=True, text=True).stdout.strip()
        if out.isdigit():
            return int(out)
        return max(map(int, re.findall(rb"/Count\s+(\d+)", open(path, "rb").read())), default=0)
    except OSError:
        return 0


def half_converted(unit):
    """Notes holding far fewer pages than their PDF (only a JSTOR cover, or a book whose chapters are
    missing): reconvert, no Jev. A book counts all its notes, ingested ones too."""
    folder = os.path.join(wiki.VAULT, unit)
    files = [os.path.join(r, f) for r, _, fs in os.walk(folder) for f in fs if f.endswith(".md")] \
        if os.path.isdir(folder) else [unit]
    texts = [read(f) for f in files]
    m = next((m for m in (re.search(r'^pdf: "\[\[(.+?)\]\]"', t, re.M) for t in texts) if m), None)
    if not m or not os.path.exists(os.path.join(wiki.VAULT, m.group(1))):
        return False
    pages = pdf_pages(os.path.join(wiki.VAULT, m.group(1)))
    return pages >= 3 and 2 * sum(len(wiki.PAGE.findall(t)) for t in texts) < pages


def triage_decide(a):
    """(decision, priority). Priority = relevance * 3 + substance, +2 for the rest of a work begun."""
    if noul(a, "broken") >= YES:
        return "reconvert", 0
    sub, rel = score(a, "substance"), score(a, "relevance")
    if sub == 0:
        return "skip (no content)", 0
    overlap, _ = choice(a, "overlap")
    if overlap == "same_text":
        return "duplicate?", 0
    prio = rel * 3 + sub + (2 if overlap == "other_part" else 0)
    unsure = NO < noul(a, "broken") < YES or overlap is None
    return ("check" if unsure else "continue a work" if overlap == "other_part" else "ingest"), prio


def cmd_triage(args):
    if not args.no_convert:
        wiki.convert_pdfs()                    # new PDFs become raw notes first, so they are ranked too
    pages = wiki.load_pages()
    units = triage_units(pages)
    old = json.load(open(TRIAGE)) if os.path.exists(TRIAGE) else {}
    todo = [u for u in sorted(units) if args.redo or u not in old]
    if args.limit:
        step = max(len(todo) // args.limit, 1)      # spread a trial run over the whole list
        todo = todo[::step][:args.limit]
    half = {u for u in todo if half_converted(u)}
    for u in half:
        old[u] = {"files": len(units[u]), "relevance": 0, "substance": 0, "broken": 1.0, "overlap": "?",
                  "decision": "reconvert", "priority": 0, "judged": time.strftime("%Y-%m-%d"),
                  "why": "the PDF has far more pages than the note"}
    todo = [u for u in todo if u not in half]
    print("triage: %d units (%d already judged), %d half-converted, asking Jev about %d"
          % (len(units), len(old) - len(half), len(half), len(todo)))
    for u, a in ask_all(todo, lambda u: triage_state(u, units[u], pages)):
        if a is None:
            continue
        decision, prio = triage_decide(a)
        old[u] = {"files": len(units[u]), "relevance": score(a, "relevance"),
                  "substance": score(a, "substance"), "broken": round(noul(a, "broken"), 2),
                  "overlap": a["overlap"]["choice"], "decision": decision, "priority": prio,
                  "judged": time.strftime("%Y-%m-%d")}
    for u in list(old):           # drop units ingested since
        if u not in units:
            del old[u]
    with open(TRIAGE, "w", encoding="utf-8") as f:
        json.dump(old, f, ensure_ascii=False, indent=1, sort_keys=True)
    # a note one of the human's essays draws on ranks higher (+3): until it is ingested, the essay's
    # wiki pages can cite only the essay, not the speakers or authors themselves
    by_unit = defaultdict(set)
    for rel, essays in essay_sources().items():
        for u, fs in units.items():
            if rel == u or rel in fs:
                by_unit[u].update(essays)
    for u, v in old.items():                   # saved, so `wiki.py status` ranks the same way
        if u in by_unit:
            v["essays"] = sorted(by_unit[u])
        else:
            v.pop("essays", None)
    with open(TRIAGE, "w", encoding="utf-8") as f:
        json.dump(old, f, ensure_ascii=False, indent=1, sort_keys=True)
    prio = lambda u, v: v["priority"] + (3 if v.get("essays") and v["priority"] else 0)
    rows = sorted(old.items(), key=lambda x: (x[1]["decision"] not in ("ingest", "continue a work"), -prio(*x), x[0]))
    print("\n%-18s %4s %3s %3s  %s" % ("decision", "prio", "rel", "sub", "unit"))
    for u, v in rows:
        print("%-18s %4d %3d %3d  %s%s%s" % (v["decision"], prio(u, v), v["relevance"],
              v["substance"], u, "  (%d notes)" % v["files"] if v["files"] > 1 else "",
              "  ← essay " + "、".join("〈%s〉" % e for e in sorted(by_unit[u])) if u in by_unit else ""))
    print("\n" + ", ".join("%s %d" % kv for kv in Counter(v["decision"] for v in old.values()).most_common()))


# --------------------------------------------------------------- hits

HITS_Q = {
    "refers": N("Do the passages in `snippets` use `matched` to mean the subject of `page`, as its summary says?",
                "In most passages the words name this page's subject: the same person, organisation, work or idea.",
                "In most passages the words mean something else: another person or thing with the same name, an "
                "everyday sense of the word, part of a longer term (\"sales tax\" for a page on sales), or only a "
                "reference-list entry."),
    "weight": S("How much does the note discuss the subject of `page`, judging from `snippets` and `mentions`?", [
        "In passing: a name in a list, a citation, an aside.",
        "Some discussion: a paragraph or a few remarks that say something about it.",
        "A main subject: discussed at length, argued about, or the note's topic.",
    ]),
}


def matcher(exclude=()):
    """(terms, regex) for every entity/concept name: build once, reuse over many texts."""
    terms = wiki.wiki_terms(exclude)
    alts = sorted(terms, key=len, reverse=True)
    return terms, re.compile("|".join(name_rx(t, terms[t][1]).pattern for t in alts))


def mentions(text, exclude=(), match=None):
    """{page: (matched names Counter, [match objects])} for every entity/concept named in text."""
    terms, rx = match or matcher(exclude)
    out = defaultdict(lambda: (Counter(), []))
    for m in rx.finditer(text):
        key = re.sub(r"[\s+]+", " ", m.group(0))
        hit = terms.get(key) or terms.get(key.lower()) or terms.get(key.casefold())
        if hit and hit[0]:
            out[hit[0]][0][key] += 1
            out[hit[0]][1].append(m)
    return out


def cmd_hits(args):
    path = note_path(args.file)
    raw = read(path)
    fm, _, _ = wiki.parse_frontmatter(raw)
    authors = [re.sub(r"[\[\]\"]", "", str(a)) for a in (fm.get("author") or [])] if isinstance(fm.get("author"), list) else []
    text = wiki.zh(flat(raw))
    found = mentions(text, exclude=authors)
    byname = {p.name: p for p in wiki.load_pages()}
    top = sorted(found, key=lambda p: -len(found[p][1]))[:args.max]

    def q(page):
        names, ms = found[page]
        n = len(ms)
        pick = [ms[round(i * (n - 1) / 2)] for i in range(3)] if n > 3 else ms
        return {"note": os.path.basename(path)[:-3], "page": page_card(byname[page]),
                "matched": sorted(names), "mentions": n,
                "snippets": [text[max(m.start() - SNIPPET, 0):m.end() + SNIPPET] for m in pick]}, HITS_Q
    rows = ask_all(top, q)
    print("%s: %d pages mentioned, %d checked\n" % (os.path.relpath(path, wiki.VAULT), len(found), len(top)))
    for label, keep in (("about the page (weight 2 = main subject)", "yes"), ("check", "check"),
                        ("false matches (consider not_aliases)", "no")):
        sel = [(p, a) for p, a in rows if a and band(noul(a, "refers")) == keep]
        if sel:
            print(label + ":")
            for p, a in sorted(sel, key=lambda x: -score(x[1], "weight")):
                print("  %.2f  w%d  %-40s ×%d  %s" % (noul(a, "refers"), score(a, "weight"), p[:40],
                      len(found[p][1]), ", ".join(sorted(found[p][0]))[:60]))


# -------------------------------------------------------------- terms

TERMS_Q_BASE = {
    "garbled": N("Is `term` an artefact of PDF conversion or OCR rather than a word the author wrote? See `snippets`.",
                 "It is a misreading (letters doubled, dropped or swapped, words joined or cut in two), a running "
                 "page header, or a fragment of a URL, citation or reference list.",
                 "It is a real word, name or phrase as the author wrote it."),
    "worth": S("Does `term` deserve a wiki page of its own, judging from `snippets`? A wiki page is about a "
               "named person, work, organisation, event, or a concept that has a name of its own.", [
        "No: an ordinary word or phrase, however often it appears: an adjective, a verb, a common noun, a "
        "generic phrase (\"first step\", \"imaginative\", \"accommodation\", \"natural forces\"), or a "
        "publisher, place of publication or other bibliographic detail.",
        "A real name or term the note mentions in passing.",
        "A named person, work, organisation or event the note discusses, or a term of art it uses, worth a page "
        "if other sources mention it too.",
        "A concept the author names and defines or argues for (\"the religious\" as opposed to \"a religion\" in "
        "Dewey, \"disciplinary power\" in Foucault), or the person or work the note is about: it deserves its "
        "own page now.",
    ]),
}


def cmd_terms(args):
    path = note_path(args.file)
    lines = read(path).split("\n")
    body_start = next((i + 1 for i in range(1, len(lines)) if lines[i] == "---"), 0) if lines[0] == "---" else 0
    segs = wiki.segments(lines, [(body_start, len(lines))])
    library = wiki.raw_texts(skip=path)
    core, rows = wiki.new_terms(lines, segs, library)
    terms = list(dict.fromkeys(core + [t for _, ts in rows for t in ts]))[:args.max]
    text = wiki.zh(flat("\n".join(lines)))
    pages = [p for p in wiki.load_pages() if p.type in ("entity", "concept")]

    def q(term):
        cands = [p for _, p in wiki.search_pages(term, pages)[:3]]
        qs = dict(TERMS_Q_BASE)
        opts = {"c%d" % i: "`term` is another name for %s: %s" % (p.name, p.fm.get("summary", ""))
                for i, p in enumerate(cands)}
        opts["none"] = "`term` names something none of the listed pages is about."
        qs["same_as"] = C("Is `term` another name for the subject of one of `candidates`?", opts)
        return {"term": term, "snippets": contexts(text, name_rx(wiki.zh(term))),
                "candidates": [page_card(p) for p in cands]}, qs
    res = ask_all(terms, q)
    print("%s: %d new terms checked\n" % (os.path.relpath(path, wiki.VAULT), len(terms)))
    out = defaultdict(list)
    for term, a in res:
        if a is None:
            continue
        same, p = choice(a, "same_as")
        if noul(a, "garbled") >= YES:
            out["conversion artefact (fix silently, no page)"].append(term)
        elif same and same != "none":
            cand = q(term)[0]["candidates"][int(same[1:])]["title"]
            out["same as an existing page (link it; alias only if §2 allows)"].append("%s → [[%s]]" % (term, cand))
        else:
            w = score(a, "worth")
            key = {3: "create a page now", 2: "worth a page if other sources mention it"}.get(w, "ignore")
            if NO < noul(a, "garbled") < YES:
                key = "check (maybe an artefact)"
            out[key].append(term)
    for k in ("create a page now", "worth a page if other sources mention it",
              "same as an existing page (link it; alias only if §2 allows)", "check (maybe an artefact)",
              "conversion artefact (fix silently, no page)", "ignore"):
        if out[k]:
            print("%s:\n  %s" % (k, "、".join(out[k])))


# ------------------------------------------------------------ phrases

PHRASE_Q = {
    "other": N("Does `phrase` mean something other than the subject of `page`? See `snippets`.",
               "The phrase names a different thing that only contains the page's name: \"sales tax\" for a page on "
               "sales, \"artificial intelligence\" for one on intelligence, \"marketing costs\" (transaction costs) "
               "for one on marketing.",
               "The phrase is the page's subject, or a kind or instance of it: \"Scotch whisky\" for a page on "
               "whisky, \"working memory capacity\" for one on working memory."),
}


PHRASES = os.path.join(wiki.DATA, "phrases.json")


def phrases_all(args):
    """Every raw note's glued names (wiki.py phrases), judged by Jev; answers kept in tools/phrases.json and
    only new (page, phrase) pairs asked; lists those unless --all."""
    import hashlib
    pages = wiki.load_pages()
    byname = {p.name: p for p in pages}
    terms, names = wiki.wiki_terms(), wiki.names_by_page(pages)
    rows = defaultdict(list)
    for rel in wiki.raw_files():
        if not rel.endswith(".md") or private(rel):
            continue
        text = read(rel)
        for page, phrase, n, total in wiki.glued_names(text, terms, names):
            rows[(page, phrase)].append((rel, n, total))
    cache = json.load(open(PHRASES, encoding="utf-8")) if os.path.exists(PHRASES) else {}
    key = lambda pp: "%s\t%s" % pp
    card = lambda pp: hashlib.sha1(json.dumps(page_card(byname[pp[0]]), ensure_ascii=False).encode()).hexdigest()[:12]
    todo = [pp for pp in rows if pp[0] in byname and (getattr(args, "redo", False) or cache.get(key(pp), {}).get("h") != card(pp))]

    def q(pp):
        snips = []
        for rel, _, _ in rows[pp][:3]:
            if os.path.exists(os.path.join(wiki.VAULT, rel)):        # a note renamed while this runs
                snips += contexts(wiki.zh(flat(read(rel))), name_rx(pp[1]), 1)
        return {"page": page_card(byname[pp[0]]), "phrase": pp[1], "snippets": snips[:3]}, PHRASE_Q
    for pp, a in ask_all(todo, q):
        if a:
            cache[key(pp)] = {"p": round(noul(a, "other"), 3), "h": card(pp)}
    live = {key(pp) for pp in rows}
    tmp = PHRASES + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in cache.items() if k in live}, f, ensure_ascii=False, indent=0, sort_keys=True)
    os.replace(tmp, PHRASES)
    asked = {key(pp) for pp in todo}
    show = [pp for pp in rows if key(pp) in cache and (args.all or key(pp) in asked)]
    print("%d glued names across raw/; asked Jev about %d new ones (%s)" % (
        len(rows), len(todo), "listing all" if args.all else "listing those; --all for every one"))
    for label, keep in (("add to not_aliases (the phrase means something else)", "yes"), ("check", "check")):
        sel = [pp for pp in show if band(cache[key(pp)]["p"]) == keep]
        if sel:
            print(label + ":")
            for pp in sorted(sel, key=lambda pp: -cache[key(pp)]["p"]):
                hits = rows[pp]
                print("  %.2f  %-26s \"%s\"  %d/%d uses in %d note(s)" % (
                    cache[key(pp)]["p"], pp[0][:26], pp[1], sum(h[1] for h in hits), sum(h[2] for h in hits), len(hits)))


def cmd_phrases(args):
    if not args.file:
        return phrases_all(args)
    path = note_path(args.file)
    raw = read(path)
    pages = wiki.load_pages()
    byname = {p.name: p for p in pages}
    found = wiki.glued_names(raw, wiki.wiki_terms(), wiki.names_by_page(pages))
    text = wiki.zh(flat(raw))
    res = ask_all(found, lambda f: ({"page": page_card(byname[f[0]]), "phrase": f[1],
                                     "snippets": contexts(text, name_rx(f[1]))}, PHRASE_Q))
    if not res:
        print("No glued names.")
    for (page, phrase, n, total), a in res:
        if a:
            p = noul(a, "other")
            act = {"yes": "add to not_aliases", "no": "leave (same thing)", "check": "check"}[band(p)]
            print("  %.2f  %-20s %-26s \"%s\"  (%d/%d uses)" % (p, act, page[:26], phrase, n, total))


# ------------------------------------------------------------- images

IMG_KINDS = {
    "figure": "A figure or table from a paper or book, with a numbered caption.",
    "chart": "A chart or graph of data.",
    "map": "A map.",
    "diagram": "A diagram, flowchart, timeline or illustration that explains how something works.",
    "scan": "A scan or photo of a document, manuscript, inscription, page or artwork being discussed.",
    "artifact": "A photo of an archaeological find, object, building or site being discussed.",
    "screenshot": "A screenshot of software, a website, a post or data the text talks about.",
    "subject": "A photo of the thing, product, place or event the article is about.",
    "portrait": "A portrait of a person the article discusses.",
    "author": "A photo of the author, host or contributor.",
    "decoration": "A header banner, stock photo, mood picture or divider that adds nothing to the text.",
    "promo": "An ad, sponsor image, subscribe or call-to-action button, or a thumbnail linking to another article.",
}
IMG_Q = {
    "kind": C("What is the image, judging from `alt`, `caption`, `file` and the text around it?", IMG_KINDS),
    "referenced": N("Does the text in `before` or `after` point to or describe this image?",
                    "It says \"see the figure\", \"as shown\", \"如下圖\", gives a figure number, or describes what "
                    "the image shows.",
                    "The text goes on without mentioning or describing the image."),
    "carries_info": N("Would a reader lose information if the image were gone?",
                      "The image holds something the text doesn't state: numbers, positions, structure, wording of a "
                      "document, or what an object or place looks like where that matters to the argument.",
                      "The text says everything the image shows, or the image only sets a mood."),
    "gallery": N("Is the image one of a run of the same kind (`run` counts images in a row) whose captions only "
                 "name them?",
                 "It sits in a row of five or more similar images (photos of tours, products, people) with captions "
                 "that only name or date them.",
                 "It stands alone or with a few images, or the captions explain something."),
    "site": N("Does the image belong to the website rather than to this article?",
              "It is site furniture: a logo, newsletter or app promo, sponsor, related-article thumbnail, social "
              "button, or author box.",
              "It belongs to the article's content."),
}
IMG_KEEP = {"author", "decoration", "promo"}


def caption(text, end):
    """The line right under an image; none if a blank line follows (that is the next paragraph)."""
    rest = text[end:end + 400].lstrip(" )")
    rest = rest[1:] if rest.startswith("\n") else rest
    return "" if rest.startswith("\n") else rest.split("\n")[0].strip()[:200]


def cmd_images(args):
    path = note_path(args.file)
    text = read(path)
    items = wiki.scan_images(text)
    todo = []
    for i, it in enumerate(items, 1):
        if it["why"]:
            continue
        m = it["m"]
        run, j = 1, i
        while j < len(items) and len(text[items[j - 1]["m"].end():items[j]["m"].start()].strip()) < 120:
            run, j = run + 1, j + 1
        todo.append((i, {"alt": (m.group(1) or "").strip(), "file": it["url"].split("?")[0].split("/")[-1][:80],
                         "caption": caption(text, m.end()),
                         "before": re.sub(r"\s+", " ", text[max(m.start() - SNIPPET, 0):m.start()]),
                         "after": re.sub(r"\s+", " ", text[m.end():m.end() + SNIPPET]),
                         "position": "%d%% into the note" % (100 * m.start() // max(len(text), 1)), "run": run}))
    res = ask_all(todo, lambda t: (t[1], IMG_Q))
    skip = []
    print("%s: %d images, %d auto-decided, %d asked\n" % (os.path.relpath(path, wiki.VAULT), len(items),
          len(items) - len(todo), len(todo)))
    for (i, st), a in res:
        if a is None:
            print("  %3d get   (no answer; download when unsure)" % i)
            continue
        kind, _ = choice(a, "kind")
        keep = noul(a, "site") >= YES or noul(a, "gallery") >= YES or \
            (kind in IMG_KEEP and noul(a, "referenced") < YES and noul(a, "carries_info") < YES)
        if keep:
            skip.append(i)
        print("  %3d %-5s %-10s ref %.2f info %.2f gallery %.2f site %.2f  %s" % (
            i, "keep" if keep else "get", kind or "?(%s)" % a["kind"]["choice"], noul(a, "referenced"),
            noul(a, "carries_info"), noul(a, "gallery"), noul(a, "site"), (st["alt"] or st["caption"])[:50]))
    print("\nthen: python3 tools/wiki.py images \"%s\" --apply%s" % (
        os.path.relpath(path, wiki.VAULT), " --skip " + ",".join(map(str, skip)) if skip else ""))


# ------------------------------------------------------------ aliases

ALIAS_Q = {
    "specific": N("When a text uses `alias`, does it almost always refer to the subject of `page`, even in a "
                  "passing mention? `snippets` show how notes in the library use it (`notes_using` counts them).",
                  "`alias` is another name for this exact subject: wherever it appears it means this person, "
                  "thing or idea, as in the snippets. A surname counts when the library almost always means this "
                  "person by it (\"Hume\" for David Hume). A subtopic wholly inside the subject counts too "
                  "(\"jailbreak\" for LLM security, \"bourbon\" for whisky).",
                  "`alias` names something else, or more than this subject: a broader field or kind it belongs to, "
                  "a neighbouring idea, an opposing view, an everyday word, or a name other people or "
                  "things share (\"touch\" for robot tactile sensing, \"設計\" for product design, "
                  "\"relationalism\" for substantivalism)."),
}


def cmd_aliases(args):
    pages = [p for p in wiki.load_pages() if p.type in ("entity", "concept")]
    if args.pages:
        want = {n.lower() for n in args.pages}
        pages = [p for p in pages if p.name.lower() in want]
    # Where each alias is used in raw/ is kept in ALIASES_USE with each raw note's size and mtime, so a run
    # scans only notes that are new or changed since the last one (a full scan is ~3 min).
    use = json.load(open(ALIASES_USE, encoding="utf-8")) if os.path.exists(ALIASES_USE) else {}
    old_files, old_using = use.get("files", {}), use.get("using", {})
    files = {}
    for rel in wiki.raw_files():
        if rel.endswith(".md") and not private(rel):
            st_ = os.stat(os.path.join(wiki.VAULT, rel))
            files[rel] = "%d:%d" % (st_.st_size, int(st_.st_mtime))
    changed = sorted(r for r in files if old_files.get(r) != files[r])
    gone = set(old_files) - set(files)
    texts = {}

    def text(rel):
        if rel not in texts:
            t = wiki.zh(flat(read(rel)))
            texts[rel] = (t, t.lower())
        return texts[rel]

    items, unsourced, new_using = [], [], {}
    for p in pages:
        for al in p.aliases:
            al = str(al).strip()
            if not al or al.lower() == p.name.lower():
                continue
            key = wiki.zh(al)
            rx = name_rx(key, p.type == "entity")
            ukey = "%s\t%s\t%d" % (p.name, al, p.type == "entity")
            hits = lambda rels: [r for r in rels if key.lower() in text(r)[1] and rx.search(text(r)[0])]
            if ukey in old_using and not getattr(args, "redo", False):
                keep = [r for r in old_using[ukey] if r in files and r not in gone and r not in changed]
                using = sorted(set(keep) | set(hits(changed)))
            else:
                using = hits(sorted(files))
            new_using[ukey] = using
            if p.type == "entity" and wiki.CJK_RUN.search(al) and not using:
                unsourced.append((p.name, al))      # §2: an entity's Chinese name must come from raw/
            snips = [contexts(text(r)[0], rx, 1)[0] for r in using[:3]]
            items.append((p, al, len(using), snips))
    if not args.pages:
        tmp = ALIASES_USE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"files": files, "using": new_using}, f, ensure_ascii=False)
        os.replace(tmp, ALIASES_USE)
    print("raw/: %d notes, %d new or changed since the last run (%d read)" % (len(files), len(changed), len(texts)),
          file=sys.stderr)
    import hashlib
    state = lambda it: {"page": page_card(it[0]), "alias": it[1], "notes_using": it[2], "snippets": it[3]}
    digest = lambda it: hashlib.sha1(json.dumps(state(it), ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    key = lambda it: "%s\t%s" % (it[0].name, it[1])
    cache = json.load(open(ALIASES, encoding="utf-8")) if os.path.exists(ALIASES) else {}
    todo = [it for it in items if args.redo or cache.get(key(it), {}).get("h") != digest(it)]
    res = ask_all(todo, lambda it: (state(it), ALIAS_Q))
    for it, a in res:
        if a:
            cache[key(it)] = {"p": round(noul(a, "specific"), 3), "h": digest(it)}
    live = {key(it) for it in items}
    if not args.pages:                                   # a partial run keeps the other pages' answers
        cache = {k: v for k, v in cache.items() if k in live}
    tmp = ALIASES + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=0, sort_keys=True)
    os.replace(tmp, ALIASES)
    asked = {key(it) for it in todo}
    print("%d aliases on %d pages; asked Jev about %d new or changed (%s)\n" % (
        len(items), len(pages), len(todo), "listing all" if args.all else "listing those; --all for every alias"))
    for label, keep in (("too broad: remove, or move the phrase to not_aliases", "no"), ("check", "check")):
        sel = [(it, cache[key(it)]["p"]) for it in items if key(it) in cache and band(cache[key(it)]["p"]) == keep
               and (args.all or key(it) in asked)]
        if sel:
            print(label + ":")
            for (p, al, n, _), pr in sorted(sel, key=lambda x: x[1]):
                print("  %.2f  %-34s %-22s in %d notes" % (pr, p.name[:34], al[:22], n))
    if unsourced:
        print("\nentity Chinese names found in no raw note (§2: remove unless it is the subject's own name):")
        for name, al in unsourced:
            print("  %-34s %s" % (name[:34], al))


# ------------------------------------------------------------- essays

ESSAY_Q = {
    "draws_on": N("Does the essay in `essay` use the work described in `source`: quote it, retell its argument, "
                  "facts or stories, or build on its author's ideas from this work?",
                  "The essay uses this work, named or not: its examples, figures, quotations or line of argument "
                  "appear in the essay.",
                  "The essay doesn't use this work; at most it shares a topic or names the author for something else."),
    "confirms": N("Does `source` back a specific claim the essay makes, even if the essay doesn't cite it?",
                  "A particular fact, figure, event or argument stated in `essay` is reported or argued for in "
                  "`source`.",
                  "Nothing specific in the essay is backed by the source; they share a topic at most."),
}


def cmd_essays(args):
    src = next((p for p in wiki.load_pages() if p.type == "source" and p.name.lower() == args.source.lower()), None)
    if not src:
        sys.exit("jev: no source page titled %r" % args.source)
    sp = str(src.fm.get("source_path", "")).strip()
    brief = re.split(r"\n## (?:Notable|Connections)", src.body)[0]
    source = {"title": src.name, "author": str(src.fm.get("author", "")), "summary": str(src.fm.get("summary", "")),
              "notes": re.sub(r"\s+", " ", brief)[:6000]}
    essays = []
    found = sorted(os.path.relpath(os.path.join(r, f), ESSAYS) for r, ds, fs in os.walk(ESSAYS)
                   for f in fs if f.endswith(".md") and not f.startswith("."))   # subfolders too (raw/essays/<subfolder>/)
    for fn in found:
        if fn.endswith(".md"):
            text = read(os.path.join(ESSAYS, fn))
            fm, _, _ = wiki.parse_frontmatter(text)
            listed = " ".join(map(str, fm.get("source") or []))
            if sp and os.path.splitext(sp)[0] in listed and not args.all:
                continue                    # already linked
            essays.append((os.path.basename(fn)[:-3], flat(text)[:20000]))
    res = ask_all(essays, lambda e: ({"source": source, "essay": {"title": e[0], "text": e[1]}}, ESSAY_Q))
    print("%s: %d essays checked%s\n" % (src.name, len(essays), "" if args.all else " (already linked ones skipped)"))
    for (title, _), a in sorted(res, key=lambda x: -(max(noul(x[1], "draws_on"), noul(x[1], "confirms")) if x[1] else 0)):
        if not a:
            continue
        d, c = noul(a, "draws_on"), noul(a, "confirms")
        # draws_on separates cleanly (~0.95 vs ~0.1); confirms runs high on shared topics, so it only flags
        verdict = "add to source:" if d >= YES else "check" if max(d, c) > NO else None
        if verdict:
            print("  %-15s draws_on %.2f  confirms %.2f  %s" % (verdict, d, c, title))
    print("\n(\"check\": add only if you find the essay's sentence the source backs; \"add\": confirm the part it draws on)")


# -------------------------------------------------------------- links

LINKS = os.path.join(wiki.DATA, "links.json")
LINK_TYPES = ("source", "entity", "concept", "analysis", "overview")
# Masked before matching, so names inside them are never linked: frontmatter, code, wikilinks and
# embeds, markdown links, URLs, HTML, headings, and the ## Sources list.
MASK_RE = re.compile(r"^## Sources\b.*?(?=^## |\Z)|```.*?```|`[^`\n]*`|!?\[\[[^\]]*\]\]|!?\[[^\]\n]*\]\([^)\n]*\)"
                     r"|https?://\S+|<[^>\n]+>|^#{1,6} [^\n]*", re.S | re.M)


def masked(text):
    """text with everything that mustn't be linked blanked to spaces (same length, so offsets hold)."""
    _, _, has_fm = wiki.parse_frontmatter(text)
    start = text.index("\n---", 3) + 4 if has_fm else 0
    out = " " * start + MASK_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text[start:])
    return out


def link_candidates(pages):
    """Every page that names an entity/concept page without linking it: one candidate per (page, target),
    with the first unlinked occurrence's offsets and a few snippets."""
    match = matcher()
    resolve = {}
    for p in pages:
        for a in [p.name] + [str(a) for a in p.aliases]:
            resolve.setdefault(a.lower(), p.name)
    names = {p.name for p in pages}
    out = []
    for p in pages:
        if p.type not in LINK_TYPES:
            continue
        linked = {resolve.get(l.lower(), l) for l in p.links}
        plain = masked(p.text)
        for target, (count, ms) in mentions(wiki.zh(plain), match=match).items():
            if target == p.name or target in linked or target not in names:
                continue
            first = ms[0]
            snips = [re.sub(r"\s+", " ", plain[max(m.start() - SNIPPET, 0):m.end() + SNIPPET]).strip() for m in ms[:3]]
            out.append({"page": p.name, "target": target, "n": sum(count.values()), "matched": "/".join(count),
                        "start": first.start(), "end": first.end(), "text": p.text[first.start():first.end()],
                        "snippets": snips})
    return out


def link_markup(c, line, title_or_alias):
    """[[Target|as written]], or [[as written]] when that already names the page; \\| inside a table row."""
    word = c["text"]
    if word in title_or_alias:
        return "[[%s]]" % word
    return "[[%s%s%s]]" % (c["target"], "\\|" if line.lstrip().startswith("|") else "|", word)


def cmd_links(args):
    pages = [p for p in query_pages()]          # journal-drawn pages are never sent, nor edited here
    by = {p.name: p for p in pages}
    t0 = time.time()
    cands = link_candidates(pages)
    cache = json.load(open(LINKS, encoding="utf-8")) if os.path.exists(LINKS) else {}
    key = lambda c: "%s\t%s\t%s" % (c["page"], c["target"], c["matched"])
    todo = [c for c in cands if args.redo or key(c) not in cache]
    print("%d unlinked mentions on %d pages (%.0fs); asking Jev about %d new ones" % (
        len(cands), len({c["page"] for c in cands}), time.time() - t0, len(todo)))

    def ask_one(c):
        st = {"page": page_card(by[c["target"]]), "matched": c["matched"], "snippets": c["snippets"]}
        return noul(ask(st, {"refers": HITS_Q["refers"]}), "refers")

    failed = 0
    with ThreadPoolExecutor(12) as ex:
        futs = [(c, ex.submit(ask_one, c)) for c in todo]
        for c, f in futs:
            try:
                cache[key(c)] = round(f.result(), 3)
            except Exception as e:
                failed += 1
                print("  Jev failed for %s → %s: %s" % (c["page"], c["target"], e), file=sys.stderr)
    tmp = LINKS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in cache.items()}, f, ensure_ascii=False, indent=0, sort_keys=True)
    os.replace(tmp, LINKS)

    groups = defaultdict(list)
    for c in cands:
        if key(c) in cache:
            groups[band(cache[key(c)])].append(c)
    print("Jev: link %d · check %d · no %d%s" % (len(groups["yes"]), len(groups["check"]), len(groups["no"]),
                                                 " · %d FAILED (no answer; say so in the report)" % failed if failed else ""))
    asked = {key(c) for c in todo}
    shown = [c for c in groups["check"] if args.all_checks or key(c) in asked]
    if shown:
        print("\ncheck (read and decide; link by hand if it names the page)%s:" % (
            "" if args.all_checks else ", new this run; --all-checks for the %d in all" % len(groups["check"])))
        for c in sorted(shown, key=lambda c: (c["target"], -cache[key(c)])):
            s = c["snippets"][0]
            k = wiki.zh(s).lower().find(wiki.zh(c["text"]).lower())
            print("  %.2f  %s → [[%s]]  (%s ×%d)\n        …%s…" % (cache[key(c)], c["page"], c["target"], c["matched"],
                                                            c["n"], s[max(k - 120, 0):k + 120]))
    if not args.apply:
        print("\n%d links to add (first unlinked mention on each page). Run with --apply to write them." % len(groups["yes"]))
        for c in groups["yes"][:args.show]:
            print("  %s: %s → [[%s]]" % (c["page"], c["text"], c["target"]))
        return
    edits = defaultdict(list)
    for c in groups["yes"]:
        edits[c["page"]].append(c)
    applied = 0
    for name, cs in edits.items():
        p = by[name]
        text = open(p.path, encoding="utf-8").read()
        if text != p.text:
            print("  skipped %s: changed while running" % name, file=sys.stderr)
            continue
        for c in sorted(cs, key=lambda c: -c["start"]):          # back to front, so offsets hold
            if text[c["start"]:c["end"]] != c["text"] or "\n" in c["text"]:
                continue
            line = text[text.rfind("\n", 0, c["start"]) + 1:c["start"]]
            t = by[c["target"]]
            text = text[:c["start"]] + link_markup(c, line, {t.name, *map(str, t.aliases)}) + text[c["end"]:]
            applied += 1
        with open(p.path, "w", encoding="utf-8") as f:
            f.write(text)
    print("\nadded %d links on %d pages%s" % (applied, len(edits), "; %d left (the mention spans a line break or the page changed): link by hand" % (len(groups["yes"]) - applied) if applied < len(groups["yes"]) else ""))


# --------------------------------------------------------------- skim

SKIM_Q = S("How much does this paragraph (`paragraph`, from the note `note`, section `section`) carry the note's "
           "own argument or findings? A reader skimming the note will see only the top paragraphs.", [
               "Filler: figure/table residue, citations, examples repeated elsewhere, transitions, page furniture.",
               "Background or support: context, a minor example, a step on the way.",
               "A substantive claim, result, definition or argument step.",
               "Central: a thesis, main finding, key definition or conclusion of the note."])
SKIM_PICK = "Which sentence of the paragraph best states its main point?"


def cmd_skim(args):
    """outline --skim with Jev choosing: each paragraph rated for how much it carries the note's argument, its
    main sentence picked; per part, the best paragraphs' sentences up to ~SKIM_RATIO of the part.
    Tested 2026-11-22 on three notes read whole: 52 of 100 key points covered vs 37 for outline --skim."""
    path = note_path(args.file)
    rel = os.path.relpath(path, wiki.VAULT)
    lines = read(path).split("\n")
    fm, _, _ = wiki.parse_frontmatter("\n".join(lines))
    title = str(fm.get("title") or os.path.splitext(os.path.basename(path))[0])
    _, _, _, _, _, ranges = wiki.reading_ranges(lines, args.lines)
    segs = wiki.segments(lines, ranges)
    paras, heads = [], []
    for k, sg in enumerate(segs):
        section = sg["label"]
        for i in range(sg["start"], sg["end"]):
            ln = lines[i].strip()
            if wiki.HEAD.match(ln):
                section = re.sub(r"[#*_`]", "", ln).strip()[:100]
                heads.append((i, "%d %s" % (i + 1, section[:120])))
                continue
            if not ln or wiki.SKIP_BLOCK.match(ln):
                continue
            sents = [x.strip() for x in wiki.SENTENCE.split(ln) if len(set(wiki.content_units(x))) >= 3][:12]
            if sents:
                paras.append({"seg": k, "line": i, "section": section, "text": ln, "sents": sents})
    print("%s: %d paragraphs in %d parts; asking Jev…" % (rel, len(paras), len(segs)), file=sys.stderr)

    def ask_one(pr):
        q = {"importance": SKIM_Q}
        if len(pr["sents"]) > 1:
            q["pick"] = C(SKIM_PICK, {str(j): x[:400] for j, x in enumerate(pr["sents"])})
        a = ask({"note": title, "section": pr["section"], "paragraph": pr["text"][:3000]}, q)
        probs = {int(k): float(v) for k, v in a["importance"]["probabilities"].items()}
        best = pr["sents"][int(a["pick"]["choice"])] if len(pr["sents"]) > 1 else pr["sents"][0]
        return sum(k * v for k, v in probs.items()), best

    t0 = time.time()
    try:
        with ThreadPoolExecutor(12) as ex:
            res = list(ex.map(ask_one, paras))
    except Exception as e:
        sys.exit("jev skim FAILED: %s\nUse `python3 tools/wiki.py outline %s --skim` instead and say so in the report."
                 % (e, rel))
    keep = []
    for k, sg in enumerate(segs):
        budget = wiki.SKIM_RATIO * sg["n"]
        mine = sorted(((ev, pr, s) for pr, (ev, s) in zip(paras, res) if pr["seg"] == k), key=lambda x: -x[0])
        for ev, pr, s in mine:
            if wiki.est_tokens(s) <= budget:
                keep.append((pr["line"], "  %d  %s" % (pr["line"] + 1, s)))
                budget -= wiki.est_tokens(s)
    out = [t for _, t in sorted(heads + keep)]
    span = ", ".join("%d-%d" % (a + 1, b) for a, b in ranges)
    print("Jev skim of %s, lines %s (%d paragraphs judged in %.0fs; each part's most central sentences, ~%d%%; "
          "~%d tokens):" % (rel, span, len(paras), time.time() - t0, wiki.SKIM_RATIO * 100, wiki.est_tokens("\n".join(out))))
    print("\n".join(out))


# ------------------------------------------------------ contradictions

CONTRA = os.path.join(wiki.DATA, "contradictions.json")
CONTRA_CHARS = 30000        # of each source page's body (two pages stay under Jev's ~30k-token limit)
CONTRA_Q = N(
    "`a` and `b` are two different sources; both discuss `topic`. Do they make claims about the topic that conflict?",
    "They conflict on at least one point about the topic: one asserts what the other denies, or they give "
    "incompatible answers, facts, dates or figures to the same question (even if each could be right about a "
    "different case).",
    "No conflict: they agree, complement each other, or discuss different aspects of the topic.")
CALLOUT_RE = re.compile(r"> \[!warning\][^\n]*\n((?:>[^\n]*\n?)+)")


def contra_text(p):
    """A source page's body as Jev reads it: link brackets dropped, display text kept."""
    _, body, _ = wiki.parse_frontmatter(p.text)
    body = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", body).replace("[[", "").replace("]]", "")
    return body[:CONTRA_CHARS]


def contra_pairs(pages):
    """(topic, a, b) for every two source pages that link the same entity/concept page."""
    resolve = {}
    for p in pages:
        for a in [p.name] + [str(a) for a in p.aliases]:
            resolve.setdefault(a.lower(), p.name)
    by = {p.name: p for p in pages}
    linkers = defaultdict(set)
    for p in pages:
        if p.type == "source":
            for l in p.links:
                t = resolve.get(l.lower(), l)
                if t in by and by[t].type in ("concept", "entity"):
                    linkers[t].add(p.name)
    return [(t, a, b) for t, ss in sorted(linkers.items()) for a, b in itertools.combinations(sorted(ss), 2)]


POSITIONS_RE = re.compile(r"^##+ Positions\b[^\n]*\n(.*?)(?=^##? |\Z)", re.M | re.S)


def noted(topic_page, a, b):
    """Both sources already cited in one warning callout, or in one Positions section, on the topic page."""
    blocks = [m.group(1) for m in CALLOUT_RE.finditer(topic_page.text)]
    blocks += [m.group(1) for m in POSITIONS_RE.finditer(topic_page.text)]
    for block in blocks:
        cited = {l.group(2).strip() for l in wiki.LINK_RE.finditer(block)}
        if a in cited and b in cited:
            return True
    return False


def cmd_contradictions(args):
    import hashlib
    pages = query_pages()                       # nothing drawn from raw/journal/ goes to Jev
    by = {p.name: p for p in pages}
    texts = {p.name: contra_text(p) for p in pages if p.type == "source"}
    digest = {n: hashlib.sha1(t.encode()).hexdigest()[:12] for n, t in texts.items()}
    pairs = contra_pairs(pages)
    cache = json.load(open(CONTRA, encoding="utf-8")) if os.path.exists(CONTRA) else {}
    key = lambda t, a, b: "%s\t%s\t%s" % (t, a, b)
    fresh = lambda t, a, b: (lambda c: c and c["ha"] == digest[a] and c["hb"] == digest[b])(cache.get(key(t, a, b)))
    todo = [x for x in pairs if args.redo or not fresh(*x)]
    print("%d source pairs on %d topics; asking Jev about %d new or changed" % (
        len(pairs), len({t for t, _, _ in pairs}), len(todo)))

    def ask_one(x):
        t, a, b = x
        st = {"topic": page_card(by[t]), "a": {"source": a, "text": texts[a]}, "b": {"source": b, "text": texts[b]}}
        return noul(ask(st, {"x": CONTRA_Q}), "x")

    failed, t0 = 0, time.time()
    with ThreadPoolExecutor(12) as ex:
        futs = [(x, ex.submit(ask_one, x)) for x in todo]
        for i, (x, f) in enumerate(futs):
            try:
                cache[key(*x)] = {"p": round(f.result(), 3), "ha": digest[x[1]], "hb": digest[x[2]]}
            except Exception as e:
                failed += 1
                if failed <= 3:
                    print("  Jev failed for %s: %s" % (" / ".join(x), e), file=sys.stderr)
            if (i + 1) % 2000 == 0:
                print("  … %d/%d (%.0fs)" % (i + 1, len(todo), time.time() - t0), file=sys.stderr)
    live = {key(*x) for x in pairs}
    tmp = CONTRA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in cache.items() if k in live}, f, ensure_ascii=False, indent=0, sort_keys=True)
    os.replace(tmp, CONTRA)

    asked = {key(*x) for x in todo}
    rows = [(x, cache[key(*x)]["p"]) for x in pairs if key(*x) in cache and (args.all or key(*x) in asked)]
    rows = [(x, p) for x, p in rows if p > NO and not noted(by[x[0]], x[1], x[2])]
    sure = [r for r in rows if r[1] >= YES]
    unsure = [r for r in rows if r[1] < YES]
    print("Jev: %d conflict · %d check%s (%s; pairs already in a callout or Positions section left out)" % (
        len(sure), len(unsure), " · %d FAILED (no answer; say so in the report)" % failed if failed else "",
        "all pairs" if args.all else "new or changed this run; --all for every pair"))
    for label, rs in (("conflict (Jev sure)", sure), ("check (read both pages and decide)", unsure)):
        if not rs:
            continue
        print("\n%s:" % label)
        topic = None
        for (t, a, b), p in sorted(rs, key=lambda r: (r[0][0], -r[1])):
            if t != topic:
                print("  [[%s]]" % t)
                topic = t
            print("    %.2f  %s  ×  %s" % (p, a, b))


# -------------------------------------------------------- check-source

GAP_Q = S("`part` is one part of a source; `summary` is the wiki's summary page of the whole source. What is the "
          "most important thing in `part` that `summary` leaves out?", [
              "Nothing substantive: the summary covers the part's points, at least in gist, or the part is filler.",
              "A minor detail: an example, a figure, a side remark the summary can do without.",
              "A substantive point: a claim, finding or argument step a reader of the summary would want.",
              "A main point of the source: a thesis, central finding or key argument missing from the summary."])
SUPPORT_Q = {
    "supported": N("Does `source` (the text the claim summarises) support `claim`?",
                   "Yes: the source says this, in gist; who-said-what matches.",
                   "No: the source says otherwise, attributes it differently, or doesn't say it."),
    "figures": N("Do the names, numbers, dates and figures in `claim` match what `source` says?",
                 "Yes: every name, number, date and figure in the claim is the one the source gives (or the claim "
                 "has none).",
                 "No: at least one name, number, date or figure differs from the source or isn't in it."),
}
EVIDENCE_TOKENS = 24000     # the whole raw note goes with each claim when it fits; else its best-matching parts


def source_bullets(page):
    """Key points and Notable details bullets, as written (link brackets dropped)."""
    _, body, _ = wiki.parse_frontmatter(page.text)
    out = []
    for sec in ("Key points", "Notable details"):
        m = re.search(r"\n## %s[^\n]*\n(.*?)(?=\n## |\Z)" % sec, body, re.S)
        if not m:
            continue
        parent = ""
        for l in m.group(1).split("\n"):
            if not re.match(r"\s*([-*]|\d+\.) ", l):
                continue
            text = re.sub(r"^\s*([-*]|\d+\.)\s+", "", l).strip()
            if l[:1] in " \t":                   # a sub-item reads with its parent ("Three stages: 1. …")
                text = parent[:300] + " — " + text
            else:
                parent = text
            if len(text) > 40:
                out.append(text)
    clean = lambda t: re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", t).replace("[[", "").replace("]]", "")
    return [clean(b) for b in out]


def cmd_check_source(args):
    """A source page against its raw note: parts whose main point the page leaves out, and Key points or
    details the raw note doesn't back. Tested 2026-11-22 (8 notes, planted errors): 10/16 removed points
    found as 'main point missing' (5/53 parts of intact pages); every foreign claim and 17/30 changed numbers
    flagged; 1 of 98 true bullets flagged."""
    import math
    pages = {p.name: p for p in wiki.load_pages()}
    p = pages.get(args.source)
    if not p or p.type != "source":
        sys.exit("jev: no source page titled %r" % args.source)
    sp = str(p.fm.get("source_path", ""))
    full = os.path.join(wiki.VAULT, sp)
    if private(full):
        sys.exit("jev: raw/journal/ is not sent to Jev")
    files = sorted(os.path.join(sp, f) for f in os.listdir(full) if f.endswith(".md")) if os.path.isdir(full) else [sp]
    if not os.path.isfile(os.path.join(wiki.VAULT, files[0])):
        sys.exit("jev: source_path %r is not a raw note" % sp)
    _, body, _ = wiki.parse_frontmatter(p.text)
    summary = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", body).replace("[[", "").replace("]]", "")[:30000]
    parts = []                                  # (file, first line, last line, text)
    for f in files:
        lines = read(f).split("\n")
        _, _, _, _, _, ranges = wiki.reading_ranges(lines)
        for sg in wiki.segments(lines, ranges, lo=800, hi=2500):
            parts.append((f, sg["start"] + 1, sg["end"], flat("\n".join(lines[sg["start"]:sg["end"]]))[:12000]))
    whole = " ".join(t for *_, t in parts)
    fits = wiki.est_tokens(whole) <= EVIDENCE_TOKENS
    units = lambda t: Counter(wiki.content_units(wiki.zh(t)))
    pu = [units(t) for *_, t in parts]

    def evidence(claim):
        if fits:
            return whole
        u = units(claim)
        sim = lambda k: sum(min(u[w], pu[k][w]) for w in u) / math.sqrt(sum(u.values()) * sum(pu[k].values()) + 1)
        out, n = [], 0
        for k in sorted(range(len(parts)), key=lambda k: -sim(k)):
            if n + wiki.est_tokens(parts[k][3]) > EVIDENCE_TOKENS:
                break
            out.append(k)
            n += wiki.est_tokens(parts[k][3])
        return " … ".join(parts[k][3] for k in sorted(out))

    bl = source_bullets(p)
    print("%s: %d parts of %s, %d bullets; evidence per claim: %s" % (
        p.name, len(parts), sp, len(bl), "the whole note" if fits else
        "best-matching parts up to ~%dk tokens (a claim in another language than the note may miss its part)"
        % (EVIDENCE_TOKENS // 1000)), file=sys.stderr)
    gaps = ask_all(list(range(len(parts))), lambda k: ({"summary": summary, "part": parts[k][3]}, {"gap": GAP_Q}))
    sups = ask_all(bl, lambda b: ({"claim": b, "source": evidence(b)}, SUPPORT_Q))

    main = [(k, a) for k, a in gaps if a and score(a, "gap") >= 3]
    print("\nparts whose main point the page leaves out (%d of %d; read them and add what's missing):" % (
        len(main), len(parts)))
    for k, a in main:
        f, lo, hi, t = parts[k]
        print("  %s lines %d-%d: %s…" % (os.path.basename(f) if len(files) > 1 else "", lo, hi, t[:110]))
    if not main:
        print("  none")
    some = sum(1 for _, a in gaps if a and score(a, "gap") == 2)
    if some:
        print("  (%d more parts have a substantive point the page leaves out; fine for a summary)" % some)
    bad = [(b, a) for b, a in sups if a and (noul(a, "supported") <= NO or noul(a, "figures") <= NO)]
    unsure = [(b, a) for b, a in sups if a and (b, a) not in bad and noul(a, "supported") < YES]
    print("\nbullets the raw note doesn't back (check against the note and fix):")
    for b, a in bad:
        why = "names/numbers differ" if noul(a, "figures") <= NO else "not in the source"
        print("  %.2f/%.2f  %s — %s" % (noul(a, "supported"), noul(a, "figures"), why, b[:160]))
    if not bad:
        print("  none")
    if unsure:
        print("\nbullets Jev is unsure the note supports (read the passage if the claim matters):")
        for b, a in unsure:
            print("  %.2f  %s" % (noul(a, "supported"), b[:160]))
    if not os.path.abspath(full).startswith(ESSAYS + os.sep):     # an essay is not a source of other essays
        section("essays that draw on this source (Ingest step 5)", cmd_essays, argparse.Namespace(source=p.name, all=False))
        return
    todo = essay_pending(sp, list(pages.values()))
    print("\nthis essay's sources not ingested yet (ingest them next, so pages can cite them directly):")
    print("\n".join("  " + t for t in todo) if todo else "  none")


def essay_pending(rel, pages=None):
    """The raw notes an essay's `source:` lists that no source page covers yet."""
    done = wiki.processed_paths(pages or wiki.load_pages())
    fm, _, _ = wiki.parse_frontmatter(read(rel))
    todo = []
    for v in fm.get("source") or []:
        m = re.match(r"\[\[(raw/[^\]|#]+)", str(v).strip())
        if m:
            r = os.path.normpath(m.group(1))
            r = r + ".md" if os.path.isfile(os.path.join(wiki.VAULT, r + ".md")) else r
            if r not in done:
                todo.append(r)
    return todo


# ---------------------------------------------------------- prep, lint

def section(title, fn, ns):
    """Run one command inside prep/lint; a failure ends that section only."""
    print("\n" + "=" * 8 + " " + title + " " + "=" * max(4, 60 - len(title)))
    sys.stdout.flush()
    try:
        fn(ns)
    except SystemExit as e:
        if e.code not in (None, 0):
            FAILED[0] += 1
            print("FAILED: %s" % e.code)
    except Exception as e:                      # one broken section shouldn't hide the others
        FAILED[0] += 1
        print("FAILED: %s: %s" % (type(e).__name__, e))
    sys.stdout.flush()


def cmd_prep(args):
    """Ingest step 2 in one run: the note's map, images, page mentions, new terms, not_aliases phrases, skim."""
    path = note_path(args.file)
    rel = os.path.relpath(path, wiki.VAULT)
    total = wiki.est_tokens(read(path))
    ns = argparse.Namespace
    if os.path.abspath(path).startswith(ESSAYS + os.sep):
        todo = essay_pending(rel)
        if todo:                                # Ingest step 1: these first, then the essay
            print("!! an essay whose sources aren't ingested yet: ingest these first, then the essay,\n"
                  "   so its pages can cite the sources themselves, not only the essay:")
            print("\n".join("   " + t for t in todo))
    section("map (wiki.py outline)", wiki.cmd_outline, ns(file=rel, hits=False, skim=False, lines=None))
    if wiki.scan_images(read(path)):
        section("web images", cmd_images, ns(file=rel))
    section("pages the note mentions", cmd_hits, ns(file=rel, max=args.max))
    section("new terms", cmd_terms, ns(file=rel, max=args.max))
    section("not_aliases phrases", cmd_phrases, ns(file=rel))
    if total > wiki.READ_BUDGET:
        sk = wiki.est_tokens(read(path)) * wiki.SKIM_RATIO
        if sk <= wiki.READ_BUDGET:
            section("skim (Jev)", cmd_skim, ns(file=rel, lines=None))
        else:
            print("\n(skim: VERY LONG note; pick sections from the map and run `jev.py skim %s --lines A-B`)" % rel)


def cmd_lint(args):
    """All of lint in one run: wiki.py lint and stats (mechanical), then Jev's checks: aliases, missing
    links (applied), contradictions, not_aliases phrases."""
    ns = argparse.Namespace

    def mechanical(_):
        try:
            wiki.cmd_lint(ns())
        except SystemExit:                       # exit 1 = lint errors, listed above; not a Jev failure
            pass
        print()
        wiki.cmd_stats(ns(n=10))
    section("wiki.py lint and stats", mechanical, None)
    section("aliases", cmd_aliases, ns(pages=[], all=args.all, redo=False))
    section("missing links", cmd_links, ns(apply=True, redo=False, all_checks=args.all, show=0))
    section("contradictions", cmd_contradictions, ns(all=args.all, redo=False))
    section("not_aliases phrases across raw/", cmd_phrases, ns(file=None, all=args.all, redo=False))


# -------------------------------------------------------------- query

QUERY_BATCH = 30            # page cards per request (60+ is faster but ranks less stably)
QUERY_WORKERS = 12
LATIN_RARE = 0.10           # a Latin keyword appears in at most this share of pages
QUERY_Q = ("Would wiki page {k} (its card is in state.pages) help answer the user's question?",
           "the page's subject bears directly on the question; reading it would help answer",
           "the page is unrelated or only tangential to the question")


def query_pages():
    """Pages a query may send to Jev: not index/log, and nothing drawn from raw/journal/ (CLAUDE.md §6):
    journal source pages and pages citing one are left out."""
    pages = [p for p in wiki.load_pages() if p.name not in wiki.SPECIAL]
    journal = {p.name for p in pages if p.type == "source" and
               (str(p.fm.get("source_path", "")).replace("\\", "/").strip("[]\" ") + "/").startswith(
                   wiki.JOURNAL_REL.replace(os.sep, "/") + "/")}
    cites = lambda p: any(m.group(2).strip() in journal for m in wiki.LINK_RE.finditer(" ".join(map(str, p.fm.get("sources") or []))))
    return [p for p in pages if p.name not in journal and not cites(p)]


def query_keywords(q, pages):
    """The question's keywords for BM25: Latin words or numbers in at most LATIN_RARE of pages (Vygotsky,
    1494; not AI) and Chinese strings rare in the wiki and in Chinese raw notes (康有為; not 什麼)."""
    s = wiki.zh(q)
    keys = []
    bodies = None
    for w in dict.fromkeys(re.findall(r"[A-Za-z0-9][A-Za-z0-9.\-]*[A-Za-z0-9]|[0-9]", s)):
        if len(w) < 2 and not w.isdigit():
            continue
        if bodies is None:
            bodies = [p.text.lower() for p in pages]
        rx = re.compile(r"(?<![a-z0-9])" + re.escape(w.lower()) + r"(?![a-z0-9])")
        if sum(1 for b in bodies if rx.search(b)) <= LATIN_RARE * len(pages):
            keys.append(w)
    rare = {g for g, share in wiki.zh_keywords().items() if share < wiki.ZH_RARE_RAW}
    for run in wiki.CJK_RUN.findall(s):
        i = 0
        while i < len(run):
            for n in (4, 3, 2):
                if run[i:i + n] in rare and len(run[i:i + n]) == n:
                    keys.append(run[i:i + n])
                    i += n
                    break
            else:
                i += 1
    return keys


def cmd_query(args):
    """Jev reads every page card (title, type, summary) and says how likely the page helps answer the
    question; the top N are listed. Keywords in the question also get a BM25 search, since a card
    can't show what only the page body says. Any failed Jev request stops the command: no partial list."""
    t0 = time.time()
    pages = query_pages()
    chunks = [pages[i:i + QUERY_BATCH] for i in range(0, len(pages), QUERY_BATCH)]

    def one(chunk):
        qs = {"p%d" % i: N(QUERY_Q[0].format(k="p%d" % i), *QUERY_Q[1:]) for i in range(len(chunk))}
        a = ask({"question": args.question, "pages": {"p%d" % i: page_card(p) for i, p in enumerate(chunk)}}, qs)
        return [(noul(a, "p%d" % i), p) for i, p in enumerate(chunk)]
    try:
        with ThreadPoolExecutor(QUERY_WORKERS) as ex:
            scored = sorted((x for r in ex.map(one, chunks) for x in r), key=lambda x: -x[0])
    except Exception as e:      # RuntimeError after retries, or a malformed answer
        sys.exit("jev query FAILED: %s\nNo results: a scan with missing pages can't be trusted. "
                 "Tell the human (CLAUDE.md §3 Query); don't fall back to wiki.py search on your own." % e)
    top = scored[:args.n]
    print("Jev: %d pages in %d requests, %.1fs. Top %d (probability the page helps):\n"
          % (len(pages), len(chunks), time.time() - t0, len(top)))
    for i, (s, p) in enumerate(top, 1):
        print("%3d  %.2f  %s\n           %s" % (i, s, p.rel, str(p.fm.get("summary", ""))))
    keys = query_keywords(args.question, pages) if args.bm25 else []
    if not keys:
        print("\n[bm25] no rare keywords in the question; BM25 skipped.")
        return
    listed = {p.name for _, p in top}
    # search_pages splits 康有为 into 康, 有, 为…: keep only pages that contain a keyword as written
    rxs = [name_rx(wiki.zh(k)) for k in keys]
    hits = [p for _, p in wiki.search_pages(" ".join(keys), pages)
            if any(rx.search(wiki.zh(p.text)) for rx in rxs)][:args.bm25]
    new = [p for p in hits if p.name not in listed]
    print("\n[bm25] keywords: %s — top %d, %d already listed above%s" % (
        ", ".join(keys), len(hits), len(hits) - len(new), "" if new else "."))
    rank = {p.name: i for i, (_, p) in enumerate(scored, 1)}
    for p in new:
        print("[bm25]   (Jev #%d)  %s\n           %s" % (rank.get(p.name, 0), p.rel, str(p.fm.get("summary", ""))))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    t = sub.add_parser("triage")
    t.add_argument("--limit", type=int, help="ask about at most N units, spread over the list (a trial run)")
    t.add_argument("--redo", action="store_true", help="ask again about units already in triage.json")
    t.add_argument("--no-convert", action="store_true", help="don't convert new PDFs first")
    for name, mx in (("hits", 40), ("terms", 40)):
        s = sub.add_parser(name)
        s.add_argument("file")
        s.add_argument("--max", type=int, default=mx)
    ph = sub.add_parser("phrases")
    ph.add_argument("file", nargs="?", help="one raw note (default: all of raw/, answers cached)")
    ph.add_argument("--all", action="store_true", help="all of raw/: list every judged phrase, not only new ones")
    ph.add_argument("--redo", action="store_true")
    sub.add_parser("images").add_argument("file")
    al = sub.add_parser("aliases")
    al.add_argument("pages", nargs="*")
    al.add_argument("--all", action="store_true", help="list every flagged alias, not only new or changed ones")
    al.add_argument("--redo", action="store_true", help="ask again about every alias")
    e = sub.add_parser("essays")
    e.add_argument("source", help="title of a source page")
    e.add_argument("--all", action="store_true", help="also essays that already link it (to test the questions)")
    sk = sub.add_parser("skim")
    sk.add_argument("file")
    sk.add_argument("--lines", help="A-B: only these lines")
    cs = sub.add_parser("check-source")
    cs.add_argument("source", help="title of a source page")
    pr = sub.add_parser("prep")
    pr.add_argument("file")
    pr.add_argument("--max", type=int, default=40)
    lt = sub.add_parser("lint")
    lt.add_argument("--all", action="store_true", help="list everything unresolved, not only what is new")
    co = sub.add_parser("contradictions")
    co.add_argument("--all", action="store_true", help="list every unresolved pair, not only new or changed ones")
    co.add_argument("--redo", action="store_true", help="ask again about every pair")
    li = sub.add_parser("links")
    li.add_argument("--apply", action="store_true", help="write the links Jev is sure of")
    li.add_argument("--redo", action="store_true", help="ask again about mentions already in links.json")
    li.add_argument("--all-checks", action="store_true", help="list every unsure mention, not only new ones")
    li.add_argument("--show", type=int, default=30, help="without --apply: links to preview (default 30)")
    qu = sub.add_parser("query")
    qu.add_argument("question")
    qu.add_argument("-n", type=int, default=20, help="pages to list from the Jev scan (default 20)")
    qu.add_argument("--bm25", type=int, default=5, help="BM25 results for the question's keywords (0: none)")
    args = ap.parse_args()
    cmds = {"triage": cmd_triage, "hits": cmd_hits, "terms": cmd_terms, "phrases": cmd_phrases,
            "images": cmd_images, "aliases": cmd_aliases, "essays": cmd_essays, "query": cmd_query,
            "links": cmd_links, "contradictions": cmd_contradictions, "skim": cmd_skim,
            "check-source": cmd_check_source, "prep": cmd_prep, "lint": cmd_lint}
    if args.cmd not in cmds:
        ap.print_help()
        sys.exit(2)
    cmds[args.cmd](args)
    if FAILED[0]:
        print("\n!! %d item(s) got no answer from Jev and are missing above; say so in the report." % FAILED[0])


if __name__ == "__main__":
    main()
