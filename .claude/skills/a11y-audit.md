---
description: >-
  AI-assisted accessibility audit methodology beyond axe-core: keyboard navigation,
  viewport/media matrix, semantic structure, and Jira bug filing. Use for a11y audits,
  WCAG reviews, or when the user asks to check keyboard/focus/landmarks/reading order.
user-invocable: true
---

# Accessibility audit (AI-assisted)

Codifies manual and AI-assisted checks that **axe-core alone cannot catch**. axe-core finds roughly 30% of real WCAG issues; this skill covers the rest using trusted tools already in the repo and agent session.

**Do not** use third-party accessibility MCP servers (for example `mcp-accessibility-scanner`). Heuristics from those tools are reflected here, but execution uses only the tools listed below.

## Trusted tools

| Tool | Role in this skill |
| --- | --- |
| **Browser MCP** (`cursor-ide-browser`: `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_press_key`, `browser_cdp`) | Live keyboard traversal, accessibility tree inspection, focus/activeElement checks, emulated media features |
| **Playwright** (E2E specs, `@axe-core/playwright`) | Repeatable axe scans, keyboard simulation, viewport sizing, `toMatchAriaSnapshot` |
| **axe-core** (`vitest-axe` in unit tests, `@axe-core/playwright` in E2E) | Automated WCAG rule sweep (floor, not ceiling) |
| **Lighthouse** (Chrome DevTools → Lighthouse panel, or `npx lighthouse --only-categories=accessibility`) | Secondary automated pass; useful for contrast and document-level checks |

Prefer **`browser_snapshot`** (accessibility tree) over screenshots when deciding whether a finding is real.

## When to run this skill

- Auditing a page, flow, modal, or nav region before filing bugs
- Reviewing a PR that touches interactive UI, focus, landmarks, or routing
- User asks for keyboard audit, skip link check, heading hierarchy, or "beyond axe" review
- Completing an accessibility audit story (file one Jira bug per violation)

Load `.claude/skills/frontend-testing-guidelines/SKILL.md` for unit-test axe patterns and `.claude/skills/frontend-playwright-e2e/SKILL.md` for E2E axe setup.

---

## Phase 0 — Scope and baseline

1. **Identify surfaces** — route(s), modals, menus, wizards, and states (empty, error, loading, success).
2. **Start the app** — `make dev` or `npm run start:ui` (mock API is fine for most UI audits).
3. **Automated baseline** — run axe on the surface:
   - E2E: `@axe-core/playwright` with `wcag2a`, `wcag2aa`, `wcag21aa` tags (see `frontend-playwright-e2e` skill).
   - Component: `vitest-axe` `toHaveNoViolations()` for isolated widgets.
4. **Record baseline violations** separately from manual findings; do not treat a clean axe run as "pass."

Document: URL, viewport, theme (light/dark), and whether mock or real backend.

---

## Phase 1 — Keyboard audit

Exercise the surface **without a mouse**. Use Browser MCP or Playwright `page.keyboard`.

### 1.1 Tab order and focus visibility

- From the address bar, press **Tab** through the full page. Note every stop; none should be silent (focus must be visible).
- After SPA navigation, confirm focus lands in a sensible place (typically `main`), not on `<body>` with no announcement.
- Use CDP / `Runtime.evaluate` when needed:

```javascript
({
  tag: document.activeElement?.tagName,
  role: document.activeElement?.getAttribute?.('role'),
  name: document.activeElement?.getAttribute?.('aria-label') || document.activeElement?.textContent?.trim()?.slice(0, 80),
  tabIndex: document.activeElement?.tabIndex,
})
```

**Flag:**

- Focus disappears (no visible indicator)
- Focus order does not match visual/reading order
- Focus drops to `<body>` between regions
- Inert content or off-screen elements receive focus

### 1.2 Skip links and bypass blocks (SC 2.4.1)

- First Tab stop should expose **Skip to main content** (or equivalent) on full chrome pages.
- Activating the skip link moves focus into `main` (target needs `tabindex="-1"` or focusable content).
- axe `bypass` passing **does not** excuse missing skip links for keyboard-only users who do not use landmark shortcuts.

### 1.3 Menus, dropdowns, and dialogs

For each overlay (menu, popover, modal, drawer):

| Check | Pass criteria |
| --- | --- |
| Open | **Enter** and **Space** open; **Escape** closes |
| Focus trap | Tab cycles inside modal; cannot Tab into background |
| Focus return | On close, focus returns to the trigger (or logical successor) |
| Menu button pattern | **Enter** / **ArrowDown** moves focus to first item when appropriate |
| Roving tabindex | Arrow keys move within composite widgets (tabs, toolbars, menus) per ARIA spec |

**Flag focus traps** that strand users (can open but not close with keyboard, or Tab escapes incorrectly).

### 1.4 Focus jumps and unexpected moves

- Opening/closing panels must not teleport focus to unrelated regions.
- After delete/submit, focus should move to a logical successor (next row, confirmation, or list heading), not vanish.
- Route changes: verify `main` receives programmatic focus without extra phantom Tab stops.

---

## Phase 2 — Viewport and media matrix

Run the same keyboard and visual checks under each condition. Use Browser MCP CDP `Emulation.setEmulatedMedia` / viewport commands or Playwright `page.emulateMedia` / `setViewportSize`.

| Condition | What to verify |
| --- | --- |
| **Mobile** (~375×667) | Masthead/menu patterns, touch targets, no horizontal scroll for primary content, modals fit viewport |
| **200% zoom** (browser zoom or `deviceScaleFactor`) | No clipped text/controls; no loss of functionality; reflow without two-dimensional scrolling for body text |
| **`prefers-reduced-motion: reduce`** | No essential information conveyed only via motion; respect `motion-safe` / CSS transitions that hide content |
| **`forced-colors: active`** (Windows High Contrast) | Focus rings, buttons, links, and states remain visible and distinguishable |

Also spot-check **dark theme** if the app exposes a theme toggle.

**Flag:** content unreachable at mobile width, controls overlapping at 200% zoom, motion-only status without text equivalent.

---

## Phase 3 — Semantic and structural audit

Use **`browser_snapshot`** and DOM inspection (CDP / DevTools) — not guessed markup.

### 3.1 Heading hierarchy (SC 1.3.1)

- One **h1** per view (page title).
- Levels do not skip (`h1` → `h3` with no `h2`).
- Headings describe sections; not used for styling alone.

### 3.2 Landmarks (SC 1.3.6, 2.4.1)

- **`banner`**, **`navigation`**, **`main`**, **`search`** (if present) are top-level and unique where required.
- **`contentinfo`** is not nested inside **`main`** (common PatternFly wizard footer issue).
- Page has exactly one primary **`main`**.

### 3.3 Names, roles, values (SC 4.1.2)

- Interactive elements have accessible names (`aria-label`, visible text, or `aria-labelledby`).
- Custom controls expose correct **`role`**; state via **`aria-expanded`**, **`aria-checked`**, **`aria-selected`**, etc.
- Icon-only buttons have discernible names.
- **`aria-haspopup="menu"`** on menu buttons (consistent with other nav triggers).
- Form fields: **`label`** association or `aria-labelledby`; errors linked via **`aria-describedby`** / **`aria-invalid`**.

### 3.4 Reading order and structure

- DOM order matches visual order for primary content (no positive `tabindex` reordering hacks).
- Lists use **`ul`/`ol`/`li`** or equivalent roles.
- Data tables use **`table`**, **`th`**, scope/headers as appropriate.
- Dynamic updates use **`aria-live`** where status changes must be announced (filters, save confirmations, async errors).

### 3.5 ARIA correctness

- Prefer native HTML over redundant ARIA.
- No **`role="presentation"`** on meaningful content.
- **`aria-hidden="true"`** must not hide focusable or essential content.

---

## Phase 4 — Report and file bugs

File **one Jira bug per distinct violation** (not one umbrella ticket per page). Link related bugs in description if helpful.

### Bug description template

```markdown
## Summary
[One sentence: what is wrong and where]

## WCAG Reference
SC x.x.x — [Name] (WCAG 2.1 Level A/AA)

## Steps to Reproduce
1. Navigate to [route]
2. [Keyboard or interaction steps]

## Expected Behavior
[Correct pattern or ARIA authoring practice]

## Actual Behavior
[What happens; include activeElement or snapshot excerpt if relevant]

## Impact
[Critical | Serious | Moderate | Minor] — [one sentence on who is blocked and how]

## Priority Rationale
[Impact level] → [Jira priority] (per audit priority mapping below)
```

### Impact → priority mapping

From the Nexus accessibility audit epic (axe impact levels when applicable):

| Impact | Jira priority | Notes |
| --- | --- | --- |
| **Critical** | **P1** (Urgent) | Blocks task completion for assistive technology or keyboard users |
| **Serious** | **P2** (Major) | Major barrier; workaround painful or unknown |
| **Moderate** | **P3** (Normal) | Degraded experience; workaround exists |
| **Minor** | **P4** (Minor) / backlog | Nuisance; low user impact |

Examples aligned with filed audit bugs:

- Keyboard focus lost to `<body>` after route change → **Serious → P2**
- Missing `aria-haspopup="menu"` on menu button → **Moderate → P3**
- Missing skip link (landmarks present but no skip control) → **Minor → P4** when landmarks exist; **Serious → P2** when keyboard users must tab through entire nav on every page

Set **components** to Automation Orchestrator, labels **`nexus-a11y`**, **`automation-orchestrator-ui`** when filing in AAP.

Prefix summary with **`a11y:`** for discoverability.

---

## Phase 5 — Deliverables checklist

Before marking an audit complete:

- [ ] axe baseline recorded (violations listed or confirmed none)
- [ ] Keyboard path exercised for primary flow and all overlays
- [ ] Viewport/media matrix spot-checked (mobile, 200% zoom, reduced motion, forced colors)
- [ ] Headings, landmarks, and names/roles reviewed via snapshot or tree dump
- [ ] Each manual finding filed as its own Jira bug with impact → priority
- [ ] No findings dismissed solely because axe did not report them

---

## Anti-patterns

| Do not | Do instead |
| --- | --- |
| Rely on axe alone | Run this skill's manual phases |
| Use unvetted accessibility MCP scanners | Browser MCP + axe-core + Lighthouse |
| File one mega-bug per page | One bug per violation with WCAG SC |
| Disable axe rules to "pass" | Fix the component; document upstream PF issues separately |
| Guess locators or roles | `browser_snapshot` first, then interact |
