"""Check that every interface string has an English entry: the T("…") literals in static/app.js, wys.js, props.js and the Chinese
text in static/index.html must be keys of static/i18n-en.js. Run after changing interface text."""
import json, os, re, sys
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static")
src = open(os.path.join(HERE, "i18n-en.js"), encoding="utf-8").read()
EN = json.loads(src[src.index("{"):src.rindex("}") + 1])
app = "".join(open(os.path.join(HERE, f), encoding="utf-8").read() for f in ("app.js", "wys.js", "props.js"))
want = set()
for m in re.finditer(r'T\(("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')\)', app):
    lit = m.group(1)
    want.add(json.loads(lit) if lit[0] == '"' else json.loads('"' + lit[1:-1].replace("\\'", "'").replace('"', '\\"') + '"'))
html = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
want |= set(re.findall(r'(?:title|placeholder|aria-label)="([^"]*[一-鿿][^"]*)"', html))
want |= {t.strip() for t in re.findall(r">([^<>]*[一-鿿][^<>]*)<", html)}
missing = sorted(w for w in want if w not in EN)
for w in missing:
    print("no English:", json.dumps(w, ensure_ascii=False))
print("%d strings, %d without English" % (len(want), len(missing)))
sys.exit(1 if missing else 0)
