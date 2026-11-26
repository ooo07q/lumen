#!/usr/bin/env python3
"""Convert PDFs anywhere under raw/assets/ into Web Clipper–style notes in raw/.

Run through uv (wiki.py status does this automatically when PDFs are waiting):
  uv run --no-project --with "pymupdf4llm>=2.1,<3" --with pyobjc-framework-Vision --with numpy --with pillow python tools/pdf2raw.py [--dry-run] [--out-dir DIR] [--ocr] [PDF ...]

For each PDF that no raw note points to yet (frontmatter `pdf:`):
1. Metadata: DOI or arXiv id from the first pages → Crossref / arXiv API (title, authors, date,
   abstract). Falls back to the PDF's own metadata, then the file name.
2. Convert with pymupdf4llm, page by page, without running headers/footers.
   - `<!-- p.N -->` marks the start of every page (invisible in Obsidian's reading view).
   - Figures go to raw/assets/<title>/<Author><Year>-p<page>-<n>.png and are linked as ![[name]].
     Tiny images (logos, icons) are dropped.
   - Hyphenated line breaks are joined. References are kept.
3. Papers → raw/<title>.md. Books (no DOI/arXiv, 80+ pages, a table of contents) → raw/<title>/ with
   an index note plus one note per chapter. A book with no chapters to split (e.g. one chapter or an
   excerpt carrying the book's DOI) stays a single note.
   A book whose PDF has no outline can get a hand-written chapter list, tools/chapters/<pdf name>.txt:
   `Chapter title | PDF page` per line (the page as in <!-- p.N -->), optional `title:`, `author:`
   (repeatable) and `published:` lines to fix the metadata, `#` for comments. It is used instead of
   the outline and follows the PDF when the PDF is renamed.
4. A wiki source page whose source_path is missing but whose url has the same DOI/arXiv id is
   pointed at the new note (re-imported PDFs keep their wiki pages).
5. Never overwrites a file. Scanned PDFs (almost no text, an unreadable text layer, or text on under
   half the pages; --ocr forces it) are OCR'd with Apple Vision (macOS, via
   pyobjc-framework-Vision): the language is picked from sample pages (Traditional Chinese or English),
   the note gets `ocr:` in its frontmatter. Pages that read as almost nothing are retried as vertical
   Chinese (直排): each column is cut into glyphs and re-laid as a horizontal line (needs numpy, Pillow).
   A landscape page with a text-free gutter in its middle is a scanned two-page spread: its two
   halves are OCR'd separately, left then right. If OCR is unavailable or finds too little text, the PDF is reported, not written.
6. The PDF is renamed to match its note (papers: the note's file name; books: the book's title),
   so raw/assets/ reads like the notes (it stays in its folder). `pdf:` in the frontmatter is the only link back to it.

Prints one line per PDF.
"""
import argparse, contextlib, datetime, glob, html, io, json, os, re, subprocess, sys, unicodedata
import xml.etree.ElementTree as ET

import pymupdf
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    import pymupdf4llm   # prints an optional-OCR notice on import

VAULT = os.path.abspath(os.path.expanduser(os.environ.get("LUMEN_VAULT")
                                           or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
RAW = os.path.join(VAULT, "raw") if os.path.isdir(os.path.join(VAULT, "raw")) else VAULT    # as wiki.py
DATA = os.path.abspath(os.environ.get("LUMEN_DATA") or (os.path.join(VAULT, "tools") if os.path.isdir(os.path.join(VAULT, "tools"))
                                                        else os.path.join(VAULT, ".lumen")))
def attachment_folder():
    """Where attachments go: Obsidian's "attachment folder" setting when it names a folder inside the notes, else
    <notes>/Attachments/ (<notes>/assets/ in the raw/ layout or where a vault already has one). PDFs are looked
    for in every attachment folder."""
    try:
        f = json.load(open(os.path.join(VAULT, ".obsidian", "app.json"), encoding="utf-8")).get("attachmentFolderPath")
    except (OSError, ValueError, AttributeError):
        f = None
    if isinstance(f, str) and f and not f.startswith(".") and f.strip("/ "):
        full = os.path.normpath(os.path.join(VAULT, f.strip("/ ")))
        if full == RAW or full.startswith(RAW + os.sep):
            return full
    if RAW != VAULT or os.path.isdir(os.path.join(RAW, "assets")):   # the raw/ layout, or a vault already using assets/
        return os.path.join(RAW, "assets")
    return os.path.join(RAW, "Attachments")


ATTACH = attachment_folder()
ATTACH_DIRS = sorted({ATTACH} | ({os.path.join(RAW, "assets")} if os.path.isdir(os.path.join(RAW, "assets")) else set()))
PDF_DIRS = [d for d in ATTACH_DIRS if not any(d.startswith(o + os.sep) for o in ATTACH_DIRS)]   # PDFs anywhere under these
IMG_DIR = ATTACH                                # figures: <attachments>/<note title>/
TODAY = datetime.date.today().isoformat()
SKIPPED = os.path.join(DATA, ".pdf2raw_skipped.json")   # PDFs that could not be converted
CHAPTERS_DIR = os.path.join(DATA, "chapters")            # hand-written chapter lists (books without an outline)

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>\])]+)", re.I)
ARXIV_RE = re.compile(r"arXiv:\s*(\d{4}\.\d{4,5})(v\d+)?", re.I)
BOOK_TYPES = {"book", "monograph", "edited-book", "reference-book"}


# ---------- helpers ----------

def q(s):
    return json.dumps(s, ensure_ascii=False)


def safe_name(s):
    s = re.sub(r"€{2,}", " ", s)   # some outlines use "€€€" as a tab ("1€€€The Challenge of the Future")
    s = re.sub(r"[\x00-\x1f\x7f]", "", s)   # control characters (some outlines pad titles with NULs)
    return re.sub(r"\s+", " ", re.sub(r'[\\/:*?"<>|#^\[\]]', "", s)).strip()[:150].rstrip(". ")


def curl_json(url):
    r = subprocess.run(["curl", "-sL", "--max-time", "25", "-A", "llm-wiki/1.0", url],
                       capture_output=True)
    try:
        return json.loads(r.stdout.decode("utf-8", "ignore")) if r.returncode == 0 else None
    except ValueError:
        return None


def frontmatter(path, n=4000):
    try:
        t = open(path, encoding="utf-8", errors="ignore").read(n)
    except OSError:
        return ""
    m = re.match(r"---\n(.*?)\n---", t, re.S)
    return m.group(1) if m else ""


def skipped():
    try:
        return json.load(open(SKIPPED, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def remember_skip(rel_pdf, reason):
    d = skipped()
    d[rel_pdf] = {"reason": reason, "mtime": os.path.getmtime(os.path.join(VAULT, rel_pdf))}
    with open(SKIPPED, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def converted_pdfs():
    """PDF paths (relative to the vault) that some raw note already points to via `pdf:`."""
    done = set()
    for p in glob.glob(os.path.join(RAW, "**", "*.md"), recursive=True):
        if any(p.startswith(d + os.sep) for d in ATTACH_DIRS):
            continue
        m = re.search(r'^pdf:\s*"?\[\[([^\]|]+)', frontmatter(p), re.M)
        if m:
            done.add(m.group(1).strip())
    return done


# ---------- metadata ----------

def ids_from(doc):
    text = "".join(doc[i].get_text() for i in range(min(2, doc.page_count)))
    text += " " + " ".join(v for v in doc.metadata.values() if isinstance(v, str))
    doi = DOI_RE.search(text)
    arx = ARXIV_RE.search(text) or re.match(r"(\d{4}\.\d{4,5})(v\d+)?$", os.path.splitext(os.path.basename(doc.name))[0])
    return (doi.group(1).rstrip(".,;") if doi else None), (arx.group(1) if arx else None)


def crossref(doi):
    d = curl_json("https://api.crossref.org/works/" + doi)
    m = (d or {}).get("message")
    if not m:
        return None
    parts = (m.get("published") or m.get("issued") or {}).get("date-parts", [[None]])[0]
    date = "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate(parts) if x) if parts and parts[0] else None
    abstract = re.sub(r"<[^>]+>", " ", m.get("abstract") or "")
    return {"title": (m.get("title") or [None])[0],
            "authors": [" ".join(x for x in (a.get("given"), a.get("family")) if x) or a.get("name", "")
                        for a in m.get("author", [])],
            "published": date, "abstract": re.sub(r"\s+", " ", html.unescape(abstract)).strip(),
            "url": "https://doi.org/" + doi, "type": m.get("type", "")}


def arxiv(aid):
    r = subprocess.run(["curl", "-sL", "--max-time", "25", f"https://export.arxiv.org/api/query?id_list={aid}"],
                       capture_output=True)
    try:
        e = ET.fromstring(r.stdout).find("{http://www.w3.org/2005/Atom}entry")
    except ET.ParseError:
        return None
    if e is None:
        return None
    ns = "{http://www.w3.org/2005/Atom}"
    g = lambda k: re.sub(r"\s+", " ", (e.findtext(ns + k) or "")).strip()
    if not g("title"):
        return None
    return {"title": g("title"), "authors": [g2.findtext(ns + "name") for g2 in e.findall(ns + "author")],
            "published": g("published")[:10], "abstract": g("summary"),
            "url": f"https://arxiv.org/abs/{aid}", "type": "preprint"}


def pdf_date(s):
    m = re.match(r"D:(\d{4})(\d{2})(\d{2})", s or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def metadata(doc, first_text):
    doi, aid = ids_from(doc)
    meta = (crossref(doi) if doi else None) or (arxiv(aid) if aid else None)
    if meta:
        meta["id"] = doi or aid
        return meta
    pm = doc.metadata
    h1 = re.search(r"^#\s+(.+)$", first_text, re.M)
    title = (pm.get("title") or "").strip() or (re.sub(r"[*_]", "", h1.group(1)).strip() if h1 else "") \
        or os.path.splitext(os.path.basename(doc.name))[0]
    authors = []
    for part in (a.strip() for a in re.split(r";| and | & ", pm.get("author") or "")):
        bits = [b.strip() for b in part.split(",") if b.strip()]
        if ";" in (pm.get("author") or "") and len(bits) == 2 and " " not in bits[0]:   # "Vogel, Ezra F.;" → "Ezra F. Vogel"
            authors.append(f"{bits[1]} {bits[0]}")
        else:
            authors += bits
    return {"title": title, "authors": authors, "published": None, "abstract": "", "url": "",
            "type": "", "id": doi or aid}


# ---------- conversion ----------

def short_id(meta):
    fam = (meta["authors"][0].split()[-1] if meta["authors"] else meta["title"].split()[0])
    fam = re.sub(r"[^\w]", "", fam)[:20] or "pdf"
    return fam + (meta.get("published") or "")[:4]


def convert(doc):
    tmp = os.path.join(IMG_DIR, ".pdf2raw_tmp")
    os.makedirs(tmp, exist_ok=True)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        chunks = pymupdf4llm.to_markdown(doc, page_chunks=True, write_images=True, image_path=tmp,
                                         header=False, footer=False, show_progress=False)
    return chunks, tmp


def vision_lines(png, langs):
    """Apple Vision OCR on one PNG: [(text, x, y_top, height)] in page coordinates (0–1, top = 0)."""
    import objc, Vision
    from Foundation import NSData
    with objc.autorelease_pool():
        req = Vision.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        req.setRecognitionLanguages_(langs)
        req.setUsesLanguageCorrection_(True)
        data = NSData.dataWithBytes_length_(png, len(png))
        Vision.VNImageRequestHandler.alloc().initWithData_options_(data, None).performRequests_error_([req], None)
        out = []
        for o in req.results() or []:
            c = o.topCandidates_(1)
            if c:
                b = o.boundingBox()
                out.append((c[0].string(), b.origin.x, 1 - b.origin.y - b.size.height, b.size.height))
        return out


CJK = re.compile(r"[㐀-鿿豈-﫿]")


def lines_to_text(lines):
    """Reading order (top to bottom), lines joined into paragraphs at larger vertical gaps."""
    if not lines:
        return ""
    h = sorted(l[3] for l in lines)[len(lines) // 2]
    # Group lines into rows (tops within half a line height), then left to right within a row.
    lines.sort(key=lambda l: l[2])
    rows, row = [], [lines[0]]
    for l in lines[1:]:
        if l[2] - row[0][2] < 0.5 * h:
            row.append(l)
        else:
            rows.append(row)
            row = [l]
    rows.append(row)
    lines = [l for r in rows for l in sorted(r, key=lambda l: l[1])]
    left = sorted(l[1] for l in lines)[len(lines) // 10]   # left margin, ignoring a few stray lines
    paras, cur, prev, px = [], "", None, left
    for t, x, y, hh in lines:
        t = t.strip()
        indent = x - left > 0.025 and x - px > 0.025       # first-line indent (block quotes stay whole)
        if prev is not None and (y - prev > 1.9 * h or indent):   # gap or indent
            paras.append(cur)
            cur = ""
        if not cur:
            cur = t
        elif cur.endswith("-") and t[:1].islower():
            cur = cur[:-1] + t                             # hyphenated line break
        elif CJK.search(cur[-1:]) or CJK.search(t[:1]):
            cur += t
        else:
            cur += " " + t
        prev, px = y, x
    paras.append(cur)
    return "\n\n".join(p for p in paras if p)


def _runs(mask, min_gap):
    """[(start, end)] of True runs in a 1-D mask, joining runs separated by gaps under min_gap."""
    out, start, last = [], None, None
    for i, v in enumerate(mask):
        if v:
            if start is None:
                start = i
            elif i - last > min_gap:
                out.append((start, last + 1))
                start = i
            last = i
    if start is not None:
        out.append((start, last + 1))
    return out


def vertical_png(pix):
    """Re-lay a page of vertical CJK text (columns read top to bottom, right to left) as horizontal
    lines, one per column, since Apple Vision only reads horizontal text. CJK glyphs are about as tall
    as a column is wide, which is how a column is cut into glyphs. None without numpy/Pillow or columns."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return None
    gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    ink = gray < 140
    w = ink.shape[1]
    cols = [c for c in _runs(ink.sum(axis=0) > 2, max(3, w // 200)) if c[1] - c[0] > w // 80][::-1]
    lines = []
    for x0, x1 in cols:
        cw = x1 - x0
        glyphs = []
        for a, b in _runs(ink[:, x0:x1].sum(axis=1) > 0, 1):
            if glyphs and b - glyphs[-1][0] <= 1.15 * cw:      # fragments of one glyph (三, 只)
                glyphs[-1] = (glyphs[-1][0], b)
            else:
                glyphs.append((a, b))
        cells = []
        for a, b in glyphs:                                     # touching glyphs: split evenly
            n = max(1, round((b - a) / (1.08 * cw)))
            cells += [(int(a + (b - a) * k / n), int(a + (b - a) * (k + 1) / n)) for k in range(n)]
        if not cells:
            continue
        pad = cw // 4
        line = Image.new("L", (sum(b - a for a, b in cells) + pad * (len(cells) + 1), int(1.3 * cw) + 2 * pad), 255)
        x = pad
        for a, b in cells:
            line.paste(Image.fromarray(gray[a:b, x0:x1]), (x, pad + max(0, (cw - (b - a)) // 2)))
            x += (b - a) + pad
        lines.append(line)
    if not lines:
        return None
    page = Image.new("L", (min(max(l.width for l in lines), 8000), sum(l.height + 10 for l in lines)), 255)
    y = 0
    for l in lines:
        page.paste(l, (0, y))
        y += l.height + 10
    buf = io.BytesIO()
    page.save(buf, "PNG")
    return buf.getvalue()


def ocr_page(doc, i, langs, clip=None):
    """[(text, x, y, h)] for one page (or the clip of it); a page that reads as almost nothing is
    tried as vertical text."""
    pix = doc[i].get_pixmap(dpi=200, colorspace=pymupdf.csGRAY, clip=clip)
    lines = vision_lines(pix.tobytes("png"), langs)
    if len(re.sub(r"\s", "", "".join(l[0] for l in lines))) < 60 and "zh-Hant" in langs:
        vpng = vertical_png(pix)
        vlines = vision_lines(vpng, langs) if vpng else []
        if len("".join(l[0] for l in vlines)) > 2 * len("".join(l[0] for l in lines)):
            lines = vlines
    return lines


def ocr_pages(doc):
    """OCR a scanned PDF with Apple Vision (macOS). Returns ([(page, text)], languages) or None."""
    try:
        import Vision  # noqa: F401  (pyobjc-framework-Vision)
    except ImportError:
        return None
    # Pick languages from a few sample pages: Chinese model if the text is mostly CJK.
    probe = "".join(t for i in sorted({doc.page_count // 4, doc.page_count // 2, 3 * doc.page_count // 4})
                    for t, *_ in ocr_page(doc, i, ["zh-Hant", "en-US"]))
    cjk = len(CJK.findall(probe))
    langs = ["zh-Hant", "zh-Hans", "en-US"] if cjk > 0.3 * max(1, len(re.sub(r"\s", "", probe))) else ["en-US"]
    return [(i + 1, ocr_text(doc, i, langs)) for i in range(doc.page_count)], langs


def gutter(page):
    """x (in points) between the two pages of a scanned spread: the middle of the widest run of
    columns without dark (text) pixels in the middle 40% of the page. None without numpy or a gap."""
    try:
        import numpy as np
    except ImportError:
        return None
    pix = page.get_pixmap(dpi=50, colorspace=pymupdf.csGRAY)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, :pix.width]
    ink = (a < max(110, int(np.median(a)) - 70)).sum(axis=0)   # light-grey text on a pale scan
    ink = ink - np.percentile(ink, 5)                 # dark scan borders darken every column alike
    lo, hi = int(0.3 * pix.width), int(0.7 * pix.width)
    empty = ink[lo:hi] <= 0.015 * pix.height         # a ruled line or specks may cross it
    runs = _runs(empty, 3)                            # the fold may leave a thin dark line
    if not runs:
        return None
    s, e = max(runs, key=lambda r: r[1] - r[0])
    if e - s < 0.02 * pix.width:
        return None
    return page.rect.x0 + (lo + (s + e) / 2) / pix.width * page.rect.width


def ocr_text(doc, i, langs):
    """A landscape page is taken for a scan of a two-page spread and read as two pages, left then
    right; read whole, Vision merges lines that line up across the gutter."""
    r = doc[i].rect
    mid = gutter(doc[i]) if r.width >= 1.25 * r.height else None
    if mid is None:
        return lines_to_text(ocr_page(doc, i, langs))
    halves = (pymupdf.Rect(r.x0, r.y0, mid, r.y1), pymupdf.Rect(mid, r.y0, r.x1, r.y1))
    return "\n\n".join(t for t in (lines_to_text(ocr_page(doc, i, langs, h)) for h in halves) if t)


def read_chapter_list(pdf):
    """tools/chapters/<pdf name>.txt: a hand-written chapter list for a book whose PDF has no outline.
    Header lines `title: …`, `author: …` (repeatable), `published: …` override the metadata;
    other lines are `Chapter title | page` (the PDF page, as in <!-- p.N -->); `#` starts a comment.
    Returns (overrides, [(title, page), ...]) or None when there is no list."""
    path = os.path.join(CHAPTERS_DIR, os.path.splitext(os.path.basename(pdf))[0] + ".txt")
    if not os.path.exists(path):
        return None
    over, chapters = {"authors": []}, []
    for line in open(path, encoding="utf-8"):
        line = line.split("#", 1)[0].strip() if line.lstrip().startswith("#") else line.strip()
        if not line:
            continue
        m = re.match(r"(title|author|published):\s*(.+)$", line)
        if m and "|" not in line:
            k, v = m.groups()
            if k == "author":
                over["authors"].append(v.strip())
            else:
                over[k] = v.strip()
            continue
        t, _, p = line.rpartition("|")
        if t.strip() and p.strip().isdigit():
            chapters.append((t.strip(), int(p)))
    if not over["authors"]:
        del over["authors"]
    return over, sorted(chapters, key=lambda x: x[1])


def chapters_from_outline(toc, npages):
    """Level-1 outline entries, sorted by page. An entry that spans over a quarter of the book and
    has level-2 children is replaced by them (books that nest every chapter under one part)."""
    top = sorted((p, i) for i, (lvl, t, p) in enumerate(toc) if lvl == 1 and p > 0)
    out = []
    for k, (p, i) in enumerate(top):
        end = top[k + 1][0] if k + 1 < len(top) else npages + 1
        kids = [(t, cp) for lvl, t, cp in toc[i + 1:] if lvl == 2 and p <= cp < end]
        stop = next((j for j, (lvl, *_ ) in enumerate(toc[i + 1:]) if lvl == 1), None)
        if stop is not None:
            kids = [(t, cp) for lvl, t, cp in toc[i + 1:i + 1 + stop] if lvl == 2 and p <= cp < end]
        if end - p > npages / 4 and len(kids) >= 2:
            if kids[0][1] > p:
                out.append((toc[i][1], p))
            out += sorted(kids, key=lambda x: x[1])
        else:
            out.append((toc[i][1], p))
    return out


def place_images(pages, tmp, folder, sid, dry):
    """Rename extracted images, drop tiny ones, rewrite links to ![[name]]."""
    taken = {os.path.basename(p) for p in glob.glob(os.path.join(IMG_DIR, "**", "*"), recursive=True)}
    kept = 0
    out = []
    for pno, text in pages:
        n = 0

        def sub(m):
            nonlocal n, kept
            src = m.group(1)
            src = src if os.path.isabs(src) else os.path.join(tmp, os.path.basename(src))
            try:
                pix = pymupdf.Pixmap(src)
                small = pix.width < 120 or pix.height < 80 or pix.width * pix.height < 30000
            except Exception:
                small = True
            if small:
                return ""
            n += 1
            name = f"{sid}-p{pno}-{n}.png"
            while name in taken:
                name = name[:-4] + "b.png"
            taken.add(name)
            kept += 1
            if not dry:
                os.makedirs(folder, exist_ok=True)
                os.replace(src, os.path.join(folder, name))
            return f"![[{name}]]"

        out.append((pno, re.sub(r"!\[[^\]]*\]\(([^)]+)\)", sub, text)))
    for f in glob.glob(os.path.join(tmp, "*")):
        os.remove(f)
    os.rmdir(tmp)
    return out, kept


def clean(text):
    # Kangxi / CJK radical lookalikes (⾃ U+2F83) → the ordinary characters (自), or search misses them
    text = re.sub(r"[⺀-⻿⼀-⿟]", lambda m: unicodedata.normalize("NFKC", m.group()), text)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)             # hyphenated line breaks
    text = re.sub(r"^(#{1,6}) \*\*(.+?)\*\*\s*$", r"\1 \2", text, flags=re.M)   # ## **Title** → ## Title
    text = re.sub(r"^#(?=[^#\s])", r"\\#", text, flags=re.M)  # a line starting "#word" is text, not a tag
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def body_of(pages):
    return "\n\n".join(f"<!-- p.{p} -->\n{clean(t)}" for p, t in pages if t.strip())


def fm(meta, pdf_rel, extra=None):
    lines = ["---", f"title: {q(meta['title'])}", f"source: {q(meta['url'])}" if meta["url"] else "source:", "author:"]
    lines += [f"  - {q('[[' + a + ']]')}" for a in meta["authors"] if a]
    lines.append(f"published: {meta['published']}" if meta.get("published") else "published:")
    lines.append(f"created: {TODAY}")
    desc = re.sub(r"\s+", " ", meta.get("abstract") or "")[:200].strip()
    lines.append(f"description: {q(desc)}" if desc else "description:")
    for k, v in (extra or {}).items():
        lines.append(f"{k}: {v}")
    lines.append(f"pdf: {q('[[' + pdf_rel + ']]')}")
    return "\n".join(lines + ["---"])


def write(path, text, dry):
    if os.path.exists(path):
        return False
    if not dry:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    return True


def unique_path(base_dir, name, ext=".md"):
    p = os.path.join(base_dir, name + ext)
    i = 2
    while os.path.exists(p):
        p = os.path.join(base_dir, f"{name} ({i}){ext}")
        i += 1
    return p


def relink_wiki(meta, new_rel, dry):
    """Point wiki source pages with a missing source_path and the same DOI/arXiv id at the new note."""
    if not meta.get("id"):
        return []
    done = []
    for p in glob.glob(os.path.join(VAULT, "wiki", "sources", "*.md")):
        t = open(p, encoding="utf-8").read()
        m = re.search(r'^source_path:\s*"?([^"\n]+)"?\s*$', t, re.M)
        if not m or os.path.exists(os.path.join(VAULT, m.group(1))):
            continue
        if meta["id"].lower() not in frontmatter(p).lower():
            continue
        if not dry:
            t = t.replace(m.group(0), f'source_path: "{new_rel}"', 1)
            t = re.sub(r"^updated: .*$", f"updated: {TODAY}", t, count=1, flags=re.M)
            open(p, "w", encoding="utf-8").write(t)
        done.append(os.path.splitext(os.path.basename(p))[0])
    return done


def rename_pdf(pdf, name, dry, out_dir):
    """Rename a PDF under raw/assets/ to `name`.pdf (never overwriting); return its new path."""
    if dry or out_dir or not any(os.path.abspath(pdf).startswith(d + os.sep) for d in PDF_DIRS):
        return pdf
    if os.path.splitext(os.path.basename(pdf))[0] == name:
        return pdf
    new = unique_path(os.path.dirname(pdf), name, ".pdf")
    os.rename(pdf, new)
    return new


# ---------- main ----------

BOPOMOFO = re.compile(r"[ㄅ-ㄩˇˋˊ˙]")


def unreadable(text):
    """Why a text layer can't be used, or None: U+FFFD from fonts without a Unicode map, or Big5
    bytes read as another encoding (Bopomofo and kana scattered through hanzi)."""
    body = re.sub(r"\s", "", text)
    if not body:
        return None
    if body.count("\ufffd") > 0.05 * len(body):
        return "text layer is replacement characters"
    if len(BOPOMOFO.findall(body)) > 0.02 * len(body):
        return "text layer is mis-encoded (Big5?)"
    return None


def process(pdf, dry, out_dir, force_ocr=False):
    rel_pdf = os.path.relpath(pdf, VAULT)
    doc = pymupdf.open(pdf)
    chunks, tmp = convert(doc)
    pages = [(c["metadata"].get("page_number") or i + 1, c["text"]) for i, c in enumerate(chunks)]
    plain = [re.sub(r"!\[[^\]]*\]\([^)]*\)|\s", "", t) for _, t in pages]
    chars = sum(map(len, plain))
    ocr = None
    # OCR when the text layer is missing (scans), unreadable, or covers under half the pages
    # (a JSTOR cover page in front of scanned pages, a book with only its front matter as text).
    why_ocr = ("asked" if force_ocr else
               "almost no text" if chars < 150 * max(1, doc.page_count) * 0.3 else
               unreadable("".join(plain)) or
               ("text on under half the pages" if doc.page_count >= 3 and
                sum(len(t) >= 100 for t in plain) < 0.5 * doc.page_count else None))
    if why_ocr:
        # Scanned PDF: the "images" are whole pages, so drop them and OCR the pages instead.
        for f in glob.glob(os.path.join(tmp, "*")):
            os.remove(f)
        os.rmdir(tmp)
        ocr = ocr_pages(doc)
        ok = ocr and sum(len(re.sub(r"\s", "", t)) for _, t in ocr[0]) >= 150 * max(1, doc.page_count) * 0.3
        if not ok:
            why = "almost no text (scanned PDF?)" + ("; OCR found too little text" if ocr else "; OCR unavailable")
            if not dry and not out_dir and os.path.abspath(os.path.join(VAULT, rel_pdf)).startswith(RAW + os.sep):
                remember_skip(rel_pdf, why)
            return f"skip  {os.path.basename(pdf)}: {why}; not converted"
        pages, langs = ocr

    meta = metadata(doc, pages[0][1] if pages else "")
    manual = read_chapter_list(pdf)
    if manual:
        meta.update(manual[0])
    title = safe_name(meta["title"]) or safe_name(os.path.splitext(os.path.basename(pdf))[0])
    sid = short_id(meta)
    if ocr:
        nimg = 0
        warns_ocr = [f"OCR ({'+'.join(langs)})"]
        ocr_fm = {"ocr": q("apple-vision " + "+".join(langs))}
    else:
        pages, nimg = place_images(pages, tmp, os.path.join(IMG_DIR, title), sid, dry)
        warns_ocr, ocr_fm = [], {}
    base = out_dir or RAW
    toc1 = manual[1] if manual and manual[1] else chapters_from_outline([(l, re.sub(r"[\x00-\x1f\x7f]", "", tt).strip(), pg) for l, tt, pg in doc.get_toc()], doc.page_count)
    is_book = bool(manual and manual[1]) or meta.get("type") in BOOK_TYPES \
        or (not meta.get("id") and doc.page_count >= 80 and len(toc1) >= 3)
    if not toc1:
        is_book = False     # a book's DOI but no chapters (an excerpt, one chapter): a single note
    warns = [w for w, bad in (("no author", not meta["authors"]), ("no date", not meta.get("published")),
                              ("no DOI/arXiv id, metadata from the PDF itself", not meta.get("id"))) if bad] + warns_ocr

    if not is_book:
        path = unique_path(base, title)
        rel_pdf = os.path.relpath(rename_pdf(pdf, os.path.splitext(os.path.basename(path))[0], dry, out_dir), VAULT)
        text = fm(meta, rel_pdf, ocr_fm) + "\n\n" + body_of(pages) + "\n"
        write(path, text, dry)
        new_rel = os.path.relpath(path, VAULT)
        relinked = relink_wiki(meta, new_rel, dry or bool(out_dir))
        msg = f"add   {os.path.basename(path)}  ({doc.page_count} pages, {nimg} images"
    else:
        folder = os.path.join(base, title)
        new_pdf = rename_pdf(pdf, title, dry, out_dir)
        if manual and new_pdf != pdf:   # the chapter list follows the PDF's new name
            old_list = os.path.join(CHAPTERS_DIR, os.path.splitext(os.path.basename(pdf))[0] + ".txt")
            new_list = os.path.join(CHAPTERS_DIR, os.path.splitext(os.path.basename(new_pdf))[0] + ".txt")
            if not os.path.exists(new_list):
                os.rename(old_list, new_list)
        rel_pdf = os.path.relpath(new_pdf, VAULT)
        bounds = [p for _, p in toc1] + [doc.page_count + 1]
        chapters = []
        if toc1 and toc1[0][1] > 1:
            chapters.append(("Front matter", 1, toc1[0][1] - 1))
        chapters += [(t, bounds[i], bounds[i + 1] - 1) for i, (t, _) in enumerate(toc1)]
        links = []
        for ct, a, b in chapters:
            body = body_of([x for x in pages if a <= x[0] <= b])
            if not re.sub(r"<!-- p\.\d+ -->|!\[\[[^\]]*\]\]|\s", "", body):
                continue                              # no text (e.g. a cover page): no note
            cname = f"{len(links):02d} {safe_name(ct)[:80]}"
            cmeta = dict(meta, title=f"{meta['title']} — {ct}", abstract="")
            index_rel = os.path.relpath(os.path.join(folder, title), VAULT)
            extra = {"book": q(f"[[{index_rel}|{title}]]"), "pages": q(f"{a}–{b}"), **ocr_fm}
            ctext = fm(cmeta, rel_pdf, extra) + "\n\n" + body + "\n"
            write(os.path.join(folder, cname + ".md"), ctext, dry)
            links.append(f"- [[{os.path.relpath(os.path.join(folder, cname), VAULT)}|{cname}]] (pp. {a}–{b})")
        index = fm(meta, rel_pdf, {"chapters": len(links), **ocr_fm}) + "\n\n## Chapters\n\n" + "\n".join(links) + "\n"
        write(os.path.join(folder, title + ".md"), index, dry)
        relinked = relink_wiki(meta, os.path.relpath(os.path.join(folder, title + ".md"), VAULT), dry or bool(out_dir))
        msg = f"add   {title}/ (book: {len(chapters)} chapters, {doc.page_count} pages, {nimg} images"
    if relinked:
        msg += "; wiki page relinked: " + ", ".join(relinked)
    if warns:
        msg += "; " + "; ".join(warns)
    return msg + ")" + ("  [dry run]" if dry else "")


def main():
    # The PDF libraries print notices straight to the terminal (some only at exit).
    # Send all of that to /dev/null and keep a private handle for this script's own lines.
    out = os.fdopen(os.dup(1), "w", buffering=1)
    null = os.open(os.devnull, os.O_WRONLY)
    os.dup2(null, 1)
    os.dup2(null, 2)
    try:
        run(out)
    except Exception as e:
        print(f"warn  pdf2raw failed ({type(e).__name__}: {e})", file=out)


def run(out):
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="*", help="specific PDFs (default: every unconverted PDF under raw/assets/)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out-dir", help="write notes here instead of raw/ (for testing)")
    ap.add_argument("--ocr", action="store_true", help="OCR every page, ignoring the PDF's text layer")
    a = ap.parse_args()
    global IMG_DIR
    if a.out_dir:   # test mode: images go next to the notes, wiki pages are not touched
        IMG_DIR = os.path.join(os.path.abspath(a.out_dir), "images")
    done = converted_pdfs()
    todo = [os.path.abspath(p) for p in a.pdfs] or sorted(
        p for d in PDF_DIRS for p in glob.glob(os.path.join(d, "**", "*.pdf"), recursive=True)
        if os.path.relpath(p, VAULT) not in done
        and skipped().get(os.path.relpath(p, VAULT), {}).get("mtime") != os.path.getmtime(p))
    if not todo:
        print("no new PDFs", file=out)
        return
    for pdf in todo:
        try:
            print(process(pdf, a.dry_run, a.out_dir, a.ocr), file=out)
        except Exception as e:  # one bad PDF must not stop the rest
            print(f"warn  {os.path.basename(pdf)}: conversion failed ({type(e).__name__}: {e})", file=out)


if __name__ == "__main__":
    main()
