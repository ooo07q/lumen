# 002 — Let the "Organise with AI" plan and result blocks enter once

- **Status**: DONE (2026-11-28)
- **Commit**: 6ca4973
- **Severity**: LOW
- **Category**: Missed opportunities (from `find-animation-opportunities`, 2026-11-28)
- **Estimated scope**: 2 files (`static/app.js`, `static/style.css`), about 15 lines

## Problem

In the right column's AI panel, an "organise" run (`agentHtml`) moves through stages that take minutes each. When the plan is ready (`status === "waiting"`) or the run finishes (`status === "done"`), the new block (plan + approval buttons, or report + list of changed pages) appears all at once, replacing a spinner line. A block that teleports in after a long wait is easy to miss, and the finish is the one moment in this flow that deserves a small beat. Frequency: a few times a day, so a standard entrance fits.

The panel is rebuilt with `innerHTML` on every update (`renderAI`, `static/app.js:2050`, called from 22 places, including on every streamed text update of other turns). A plain CSS `@starting-style` entrance would therefore replay on every re-render. The entrance must be tied to the stage change, rendered once.

Current code:

```js
/* static/app.js:1970 — current (start of agentHtml) */
function agentHtml(t) {
  const name = { ingest: T("整理筆記"), analysis: T("存進知識庫"), lint: T("檢查知識庫") }[t.task] || T("工作");
  let h = '<div class="ai-turn ag"><div class="ai-q">✦ ' + esc(TS(t.label) || name) + "</div>";
  ...
  h += stepsHtml(t, "plan");
  if (t.message) h += md(t.message);
  if (t.plan !== undefined && t.status !== "planning" && t.status !== "starting" && t.task && (t.message || t.plan)) h += planHtml(t.plan);
  if (t.status === "waiting") h += T('<p class="note-line">上面是 AI 打算怎麼做…') + ... ;
  if (t.status === "acting") h += ...;
  h += stepsHtml(t, "act");
  if (t.status === "acting" && t.live) h += ...;
  if (t.status === "done" || ((t.status === "stopped" || t.status === "error") && (t.changes || []).length)) {
    if (t.report && t.status === "done") h += md(t.report);
    ...  /* .ag-changes with one .ag-ch row per changed page */
  }
  if (t.status === "done" && t.part && t.part.next && !t.undone) h += ...;   /* "organise next part" */
  else if (t.status === "done" && t.part && !t.part.next) h += ...;
  if (t.status === "error") ...
```

```css
/* static/style.css:492 — current */
.ag-ch { display: flex; align-items: center; gap: 6px; padding: 2px 0; }
```

## Target

- The **plan-ready block** (everything from `if (t.message)` through the waiting-stage buttons) and the **done block** (report, changed-pages list, next-part line) are each wrapped in `<div class="ag-stage">`.
- On the **first render after the status changed to `waiting` or `done`** (status seen before in this session, and different), that wrapper also gets `ag-enter`. Never on a turn's first-ever render (chat history reopened, page reload), never on later re-renders.
- Motion:

```css
/* target, in the step-3 motion block */
.ag-enter { transition: opacity 200ms var(--ease-out), transform 200ms var(--ease-out); }
@starting-style { .ag-enter { opacity: 0; transform: translateY(4px); } }
.ag-enter .ag-ch { transition: opacity 200ms var(--ease-out), transform 200ms var(--ease-out); }
@starting-style { .ag-enter .ag-ch { opacity: 0; transform: translateY(4px); } }
.ag-enter .ag-ch:nth-child(1 of .ag-ch) { transition-delay: 30ms; }
.ag-enter .ag-ch:nth-child(2 of .ag-ch) { transition-delay: 60ms; }
.ag-enter .ag-ch:nth-child(3 of .ag-ch) { transition-delay: 90ms; }
.ag-enter .ag-ch:nth-child(4 of .ag-ch) { transition-delay: 120ms; }
.ag-enter .ag-ch:nth-child(5 of .ag-ch) { transition-delay: 150ms; }
.ag-enter .ag-ch:nth-child(6 of .ag-ch) { transition-delay: 180ms; }
.ag-enter .ag-ch:nth-child(7 of .ag-ch) { transition-delay: 210ms; }
.ag-enter .ag-ch:nth-child(n+8 of .ag-ch) { transition-delay: 240ms; }   /* cap: 8 steps, 240ms */
```

Inside the existing `@media (prefers-reduced-motion: reduce)` block:

```css
  .ag-enter, .ag-enter .ag-ch { transition: opacity 150ms ease; transition-delay: 0ms; }
  @starting-style { .ag-enter, .ag-enter .ag-ch { transform: none; } }
```

`--ease-out` is `cubic-bezier(0.23, 1, 0.32, 1)` (`static/style.css:19`); use the token, don't inline the curve.

## Repo conventions to follow

- Entrances use `@starting-style` + `transition` on `transform`/`opacity`, and live in the step-3 motion block, `static/style.css:636–652`. Exemplar: `.toast` at `static/style.css:645–646`; its reduced-motion version at 649 and 652.
- Closing/removal is always instant (documented decision, `docs/ai-ui-skills/lumen-uiux-plan.md:139`): no exit animation.
- JS state lives in module-level `const` maps next to the function that uses them, with a short `//` comment.

## Steps

1. In `static/app.js`, directly above `function agentHtml(t) {` (line 1970), add:
   ```js
   const AG_SEEN = new Map();   // turn id → status last rendered; a new stage (plan ready, done) enters once
   ```
2. In `agentHtml`, right after the `let h = …` line, add:
   ```js
   const prev = AG_SEEN.get(t.id); AG_SEEN.set(t.id, t.status);
   const enter = prev !== undefined && prev !== t.status && (t.status === "waiting" || t.status === "done");
   const open = () => '<div class="ag-stage' + (enter ? " ag-enter" : "") + '">';
   ```
3. Wrap the plan-ready part: immediately before `if (t.message) h += md(t.message);` add `let s1 = h.length;`. Immediately after the `if (t.status === "waiting") h += …;` statement, add:
   ```js
   if (t.status === "waiting") h = h.slice(0, s1) + open() + h.slice(s1) + "</div>";
   ```
4. Wrap the done part: immediately before `if (t.status === "done" || ((t.status === "stopped" …` add `let s2 = h.length;`. Immediately after the `else if (t.status === "done" && t.part && !t.part.next) h += …;` statement, add:
   ```js
   if (t.status === "done") h = h.slice(0, s2) + open() + h.slice(s2) + "</div>";
   ```
5. In `static/style.css`, add the target rules after line 646 (the `.toast` `@starting-style` line), and the two reduced-motion lines inside the `@media (prefers-reduced-motion: reduce)` block that follows.
6. Add `.ag-stage { display: contents; }` next to `.ag-ch` (line 492) only if the wrapper changes spacing (check against the screenshot from before the change); `ag-enter` needs a box to transform, so if you add `display: contents`, put it on `.ag-stage:not(.ag-enter)` only.

## Boundaries

- Do NOT touch `renderAI`, `turnHtml`, the chat (non-agent) turns, or any other animation.
- Do NOT animate `planning`, `acting`, `stopped`, `error` or `cancelled`, and do NOT add an exit animation.
- Do NOT add dependencies or a build step.
- If the lines quoted above don't match (drift since 6ca4973), STOP and report instead of improvising.

## Verification

- **Mechanical**: `node --check static/app.js` passes; `python3 tools/i18n_check.py` still reports 0 missing (no new UI text).
- **Feel check** (test vault in `~/LumenTest` only; never the iCloud vault): open a note, press "請 AI 整理這篇":
  - When the plan arrives, the plan block rises 4px and fades in once; the buttons are clickable immediately.
  - Typing in the plan's note box, scrolling the chat, or another turn streaming text does NOT replay it.
  - When the run finishes, the report fades in and the changed pages follow one after another, the last starting by 240ms.
  - Press "全部復原" (undo all): the list updates instantly, no replay.
  - Reload the page or reopen the conversation from the history: everything appears instantly.
  - In DevTools → Animations, slow to 10%: the movement is upward and never starts from below 4px.
  - Turn on Reduce Motion (macOS System Settings → Accessibility → Display, or DevTools Rendering): opacity-only fade, no movement, no stagger.
- **Done when**: both stage blocks enter exactly once per stage change, nothing else in the AI panel moves, and both checks above pass in Safari's engine and Chrome.
