# 001 — Respect Reduce Motion when scrolling to a highlighted name

- **Status**: TODO
- **Commit**: 3aee96d
- **Severity**: MEDIUM
- **Category**: Accessibility
- **Estimated scope**: 1 file (`static/app.js`), about 3 lines

## Problem

Clicking a row in the right panel's 「這篇」 tab marks where that name appears in the open note and scrolls to the first mark; the 「下一處」 button (`data-act="next-hl"`) scrolls to the next one. Both use a smooth scroll that ignores the system's Reduce Motion setting. Every other motion in Lumen honours it (see `static/style.css`, the `@media (prefers-reduced-motion: reduce)` block at the end of the "step 3: motion" section). A long smooth scroll is the kind of large on-screen movement Reduce Motion exists to stop.

```js
/* static/app.js:1033 — current, end of highlight() */
  if (first && scroll) first.scrollIntoView({ behavior: "smooth", block: "center" });
```

```js
/* static/app.js:1040 — current, nextHighlight() */
  marks[hlIndex].scrollIntoView({ behavior: "smooth", block: "center" });
```

The smooth scroll itself stays for everyone else: it shows which way the note moved, which a jump does not. Its duration and curve are the browser's own; leave them.

## Target

- Reduce Motion off: unchanged (`behavior: "smooth"`).
- Reduce Motion on: the note jumps (`behavior: "auto"`) and the mark lands centred, as now.
- The setting is read at each scroll, so changing it in System Settings takes effect without a reload.

```js
/* target, static/app.js, next to the other small helpers above highlight() */
const scrollMotion = () => (matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth");   // Reduce Motion: jump, don't glide
```

```js
/* target, static/app.js:1033 */
  if (first && scroll) first.scrollIntoView({ behavior: scrollMotion(), block: "center" });
/* target, static/app.js:1040 */
  marks[hlIndex].scrollIntoView({ behavior: scrollMotion(), block: "center" });
```

## Repo conventions to follow

- Plain JS, no build step, no libraries; short helpers are `const name = () => …` one-liners with a trailing `//` comment saying why (exemplar: `const isNarrow = () => innerWidth < NARROW;` near `applyLayout()` in `static/app.js`).
- Reduced motion is otherwise handled in CSS; this is the only place JS chooses a motion, so the helper lives in JS.

## Steps

1. In `static/app.js`, directly above `function highlight(names, root, scroll = true) {` (currently line 1008), add the `scrollMotion` line from Target.
2. In `highlight()`, replace `behavior: "smooth"` with `behavior: scrollMotion()`.
3. In `nextHighlight()`, replace `behavior: "smooth"` with `behavior: scrollMotion()`.

## Boundaries

- Do NOT touch `static/style.css`, `static/wys.js` or any other `scrollIntoView` call.
- Do NOT change `block: "center"`, the marking logic, or `hlIndex`.
- Do NOT add a setting or UI text.
- If the two lines don't match the excerpts above (drift since 3aee96d), STOP and report.

## Verification

- **Mechanical**: `node -e "new Function(require('fs').readFileSync('static/app.js','utf8'))"` prints nothing; `python3 tools/i18n_check.py` still reports 0 missing.
- **Feel check** (test vault only, `~/LumenTest/習以為常 the usual`):
  - Open a long concept page, click a row in 「這篇」 whose name appears far down: the note glides there and the mark ends up centred.
  - Click 「下一處」 several times quickly: each click retargets from where the scroll is, never stalls.
  - Turn on System Settings › Accessibility › Display › Reduce motion (or Chrome DevTools › Rendering › Emulate `prefers-reduced-motion: reduce`) without reloading: the same clicks jump instantly, mark centred.
- **Done when**: both calls use `scrollMotion()`, and the two feel checks pass in Safari and Chrome.
