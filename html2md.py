"""A saved web page (.html) → a raw note in Web Clipper's shape: frontmatter (title, source, author,
published, created, description, html) and the page's main text as Markdown. Stdlib only.

The main text is the page's <article>, else <main>, else <body>, without scripts, styles, menus,
sidebars, footers and forms. Links and web images keep their URLs (made absolute when the page says
where it came from); images saved next to the page are left out (they are not in the vault).
"""
import datetime
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
        "track", "wbr"}
DROP = {"script", "style", "noscript", "template", "svg", "canvas", "iframe", "form", "button", "nav",
        "footer", "aside", "select", "textarea", "head", "dialog", "object"}
BLOCK = {"p", "div", "section", "article", "main", "header", "figure", "figcaption", "address", "details",
         "summary", "dl", "dd", "dt", "center", "body", "html"}


class Node:
    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.parent, self.kids = tag, dict(attrs or {}), parent, []


class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.cur = self.root
        self.meta = {}
        self.comments = []

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs, self.cur)
        self.cur.kids.append(n)
        if tag == "meta":
            a = n.attrs
            k = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if k and a.get("content"):
                self.meta.setdefault(k, a["content"].strip())
        if tag == "link" and "canonical" in (n.attrs.get("rel") or "").lower() and n.attrs.get("href"):
            self.meta.setdefault("canonical", n.attrs["href"])
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.cur.tag == tag:
            self.cur = self.cur.parent

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:            # close it (and anything left open inside it)
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.kids.append(data)

    def handle_comment(self, data):
        self.comments.append(data)


def find(node, tag):
    for k in node.kids:
        if isinstance(k, Node):
            if k.tag == tag:
                return k
            r = find(k, tag)
            if r:
                return r
    return None


def text_of(node):
    if isinstance(node, str):
        return node
    if node.tag in DROP:
        return ""
    return "".join(text_of(k) for k in node.kids)


class Md:
    def __init__(self, base):
        self.base = base

    def url(self, u):
        u = (u or "").strip()
        if not u or u.startswith(("javascript:", "data:", "#", "mailto:")):
            return u if u.startswith("mailto:") else ""
        if re.match(r"https?://", u):
            return u
        return urljoin(self.base, u) if self.base else ""

    def inline(self, node):
        if isinstance(node, str):
            return re.sub(r"\s+", " ", node)
        t = node.tag
        if t in DROP:
            return ""
        if t == "br":
            return "\n"
        if t == "img":
            src = self.url(node.attrs.get("src") or node.attrs.get("data-src"))
            return "![%s](%s)" % ((node.attrs.get("alt") or "").replace("]", ""), src) if src else ""
        inner = "".join(self.inline(k) for k in node.kids)
        if t == "a":
            href = self.url(node.attrs.get("href"))
            s = inner.strip()
            return "[%s](%s)" % (s, href) if href and s else inner
        if t in ("strong", "b") and inner.strip():
            return "**%s**" % inner.strip()
        if t in ("em", "i", "cite") and inner.strip():
            return "*%s*" % inner.strip()
        if t in ("code", "kbd", "samp") and inner.strip():
            return "`%s`" % inner.strip()
        if t in ("del", "s", "strike") and inner.strip():
            return "~~%s~~" % inner.strip()
        if t == "mark" and inner.strip():
            return "==%s==" % inner.strip()
        if t in ("sup", "sub"):
            return "<%s>%s</%s>" % (t, inner.strip(), t)
        if t in BLOCK or t in ("li", "ul", "ol", "table", "blockquote", "pre") or re.fullmatch(r"h[1-6]", t):
            return " " + inner + " "      # a block inside inline content: keep its text
        return inner

    def blocks(self, node, depth=0):
        """Markdown blocks (a list of strings) for a node's children."""
        out, run = [], []

        def flush():
            s = "".join(run)
            s = "\n".join(l.strip() for l in s.split("\n"))
            s = re.sub(r"[ \t]+", " ", s).strip()
            if s:
                out.append(s)
            run.clear()

        for k in node.kids:
            if isinstance(k, str) or not self.is_block(k):
                run.append(self.inline(k))
                continue
            flush()
            out.extend(self.block(k, depth))
        flush()
        return out

    def is_block(self, n):
        return (n.tag in BLOCK or n.tag in DROP or n.tag in ("ul", "ol", "li", "table", "blockquote", "pre", "hr")
                or re.fullmatch(r"h[1-6]", n.tag) is not None)

    def block(self, n, depth):
        t = n.tag
        if t in DROP:
            return []
        if re.fullmatch(r"h[1-6]", t):
            s = re.sub(r"\s+", " ", "".join(self.inline(k) for k in n.kids)).strip()
            return ["#" * int(t[1]) + " " + s] if s else []
        if t == "hr":
            return ["---"]
        if t == "pre":
            code = text_of(n).strip("\n")
            return ["```\n" + code + "\n```"] if code.strip() else []
        if t == "blockquote":
            inner = "\n\n".join(self.blocks(n, depth))
            return ["\n".join("> " + l if l else ">" for l in inner.split("\n"))] if inner else []
        if t in ("ul", "ol"):
            lines, i = [], 0
            for li in n.kids:
                if not isinstance(li, Node) or li.tag != "li":
                    continue
                i += 1
                mark = "%d. " % i if t == "ol" else "- "
                parts = self.blocks(li, depth + 1)
                if not parts:
                    continue
                pad = "    " * depth
                first, rest = parts[0], parts[1:]
                lines.append(pad + mark + first.replace("\n", "\n" + pad + "  "))
                for r in rest:
                    lines.append(r if r.lstrip().startswith(("- ", "1. ")) or re.match(r"\s*\d+\. ", r)
                                 else pad + "  " + r)
            return ["\n".join(lines)] if lines else []
        if t == "li":
            return ["- " + " ".join(self.blocks(n, depth))]
        if t == "table":
            rows = []
            for tr in self.rows(n):
                cells = [re.sub(r"\s+", " ", "".join(self.inline(k) for k in c.kids)).strip().replace("|", "\\|")
                         for c in tr.kids if isinstance(c, Node) and c.tag in ("td", "th")]
                if cells:
                    rows.append(cells)
            if not rows:
                return []
            w = max(len(r) for r in rows)
            rows = [r + [""] * (w - len(r)) for r in rows]
            md = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * w]
            md += ["| " + " | ".join(r) + " |" for r in rows[1:]]
            return ["\n".join(md)]
        return self.blocks(n, depth)

    def rows(self, n):
        for k in n.kids:
            if isinstance(k, Node):
                if k.tag == "tr":
                    yield k
                elif k.tag in ("thead", "tbody", "tfoot"):
                    yield from self.rows(k)


def yaml_str(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip() + '"'


def decode(data):
    """Bytes of a saved page → text, by its BOM or <meta charset>, else UTF-8 (Big5 and GBK pages exist)."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", "replace")
    m = re.search(rb'charset=["\']?([\w-]+)', data[:4096], re.I)
    enc = m.group(1).decode() if m else "utf-8"
    try:
        return data.decode(enc, "replace")
    except LookupError:
        return data.decode("utf-8", "replace")


def convert(html, attachment_name):
    """(title, note text) for a saved page; the note's `html:` links back to the attachment."""
    tr = Tree()
    tr.feed(html)
    tr.close()
    m = tr.meta
    title_node = find(tr.root, "title")
    title = m.get("og:title") or (text_of(title_node).strip() if title_node else "")
    url = m.get("og:url") or m.get("canonical") or ""
    if not url:                                   # "Save Page As" leaves <!-- saved from url=(0040)https://… -->
        for c in tr.comments:
            mm = re.search(r"saved from url=\(\d+\)(\S+)", c)
            if mm:
                url = mm.group(1)
                break
    if not re.match(r"https?://", url):
        url = ""
    main = find(tr.root, "article") or find(tr.root, "main") or find(tr.root, "body") or tr.root
    body = "\n\n".join(Md(url).blocks(main)).strip()
    body = re.sub(r"\n{3,}", "\n\n", body)
    h1 = re.search(r"^# (.+)$", body, re.M)
    if h1 and title and title.startswith(h1.group(1).strip()) and title != h1.group(1).strip():
        title = h1.group(1).strip()               # "Why We Specialize | Example Blog" → the page's own heading
    if not title:
        title = h1.group(1) if h1 else re.sub(r"\.html?$", "", attachment_name, flags=re.I)
    author = m.get("author") or m.get("article:author") or ""
    published = (m.get("article:published_time") or m.get("datepublished") or m.get("date") or "")[:10]
    desc = m.get("description") or m.get("og:description") or ""
    fm = ["---", "title: " + yaml_str(title)]
    if url:
        fm.append("source: " + yaml_str(url))
    if author and not re.match(r"https?://", author):
        fm += ["author:", '  - "[[%s]]"' % author.replace('"', "").strip()]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", published):
        fm.append("published: " + published)
    fm.append("created: " + datetime.date.today().isoformat())
    if desc:
        fm.append("description: " + yaml_str(desc[:300]))
    fm.append('html: "[[%s]]"' % attachment_name)
    fm.append("---")
    return title, "\n".join(fm) + "\n" + body + "\n"
