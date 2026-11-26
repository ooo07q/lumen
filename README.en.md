# Lumen

[中文](README.md)

You write notes, clip web pages and add PDFs as usual; press one button in Lumen and an AI reads a note. It writes a source page for
each note, gives the people and ideas in them pages of their own, linked to each other, and flags where your sources
disagree; ask a question and it answers from those pages, with citations. Its pages go in the same folder's `wiki/`;
your own text stays as it is.

A vault is an ordinary folder. An Obsidian vault opens as it is.

Editing works like Apple Notes: you see headings, bold, lists, checklists and tables as they look, with no `#` or `**`
marks. The file is still saved as Markdown, and lines you didn't touch stay exactly as they were.

## Install and run

You need macOS and Python 3 (the one that comes with the system is fine).

```
git clone https://github.com/ooo07q/lumen.git ~/Lumen
python3 ~/Lumen/server.py --open
```

Lumen opens in your browser. The first time, it asks whether to create a new vault or open a folder you already have.

The address printed in the terminal carries an access code (`http://127.0.0.1:8765/?k=…`). Open it once and the
browser remembers it, so other websites can't reach your notes through your browser.

| Option | What it does |
|---|---|
| `--vault PATH` | open this folder |
| `--read-only` | look only; nothing is written |
| `--port 8765` | another port; a busy one is replaced by a free one |

A PDF has to become a note before it can be organised. The first time you add one, Lumen asks; press Convert to
notes and it downloads the converter ([uv](https://docs.astral.sh/uv/), into Lumen's own folder; a minute or two, once).
After that, PDFs are converted automatically.

The interface comes in English, 繁體中文 and 简体中文, following the system language; switch it from the menu under the
vault's name at the top left.

## Connecting an AI

Click the vault's name at the top left → Connect AI. Lumen uses your own subscription: it never handles your
password, and usage counts against your plan.

| Service | For | Needs |
|---|---|---|
| Claude Code | answering questions, organising the wiki | a Claude subscription (Pro, Max). If Claude Code isn't installed, Lumen installs it with Anthropic's official installer, then sends you to the browser to sign in |
| ChatGPT | answering questions, organising the wiki | a paid ChatGPT plan (Go, Plus, Pro) |
| Jev (TypeSafe) | finding related pages, picking a note's key passages, deciding where a long note splits, checking the result | a TypeSafe API key; it costs very little. Without it, search falls back to keywords |

Connect at least one of Claude Code and ChatGPT.

## Organising a note

Open a note and press Organise this note in the right column. It runs in two steps:

1. The AI reads the note and the related wiki pages, and lists the note's key points and the pages it will create or
   update. Nothing is written yet.
2. You read the plan, add changes if you like, and press Go ahead. The AI writes the source page and
   updates the related pages, then lists every file it changed, with the differences.

Undo all puts the whole run back.

The AI reads key passages. Jev rates every paragraph and hands the AI the ones that carry about 80% of the note's key
points; each paragraph left out leaves its main sentence behind, so the AI can go back for it. For a book chapter,
about half the text goes out. To have the AI read all of it, write "read the whole note" under the plan: the AI asks
Lumen for the full text (for a long note, still only this part).

A long note whose key points won't fit one source page is organised a part at a time, split by its content: Jev judges
where a new topic or chapter begins, and each part holds about a chapter's worth. Each part gets its own source page.
The list shows "3/16 done" until every part is, and editing the note midway keeps the progress. On three chapters of
the same book, three runs caught more of the key points than one run over all of it.

## Also

- Ask the AI: type a question in the search box and press ⌘↵. Lumen finds the related pages and hands them to the AI
  with the open note; every claim in the answer links to where it came from.
- To-do list: notes not organised yet, in the order Jev suggests. PDFs put in the attachments folder (`Attachments/` in
  a new vault, or the one set in Obsidian) become notes and join the list.
- Unlinked mentions and contradictions: the right column lists pages a note mentions but doesn't link, and sets two
  sources side by side when they disagree.
- Version history: each save keeps the previous version, to compare or restore.
- Journal: ＋ Today. The journal stays on this computer and goes neither to the AI nor to Jev.

## Where things are

| What | Where |
|---|---|
| Your notes | everything in the vault folder outside `wiki/` |
| The AI's pages | the vault's `wiki/` |
| Version history | the vault's `.lumen/history/` |
| Deleted files | the vault's `.trash/` (shared with Obsidian; restorable) |
| Settings, sign-ins, caches | `~/Library/Application Support/Lumen/` |

The server listens on this computer only (127.0.0.1), and every read or write needs the access code.

## What the AI can and can't do

- It writes only under `wiki/`. Your notes, attachments and PDFs can't be changed, moved or deleted; afterwards Lumen
  checks that nothing outside `wiki/` changed.
- It can't read the journal, or pages drawn from it.
- It has no shell and no web, only Lumen's fixed tools.
- It reads no CLAUDE.md in the vault and loads none of your own Claude Code settings.

The interface is in Traditional Chinese for now.
