---
name: frontend-a11y-audit
description: >-
  AI-assisted accessibility audit methodology: axe-core baseline plus keyboard navigation,
  viewport/media matrix, semantic structure, and issue-tracker draft templates. Use for a11y audits,
  WCAG reviews, or when the user asks to check keyboard/focus/landmarks/reading order.
user-invocable: true
---

# Accessibility audit (AI-assisted)

Codifies a phased accessibility audit. **Phase 0** establishes an axe-core automated baseline (registry sweep or targeted scan). **Phases 1–3** cover keyboard, viewport/media, and semantic checks that automated rules miss. axe-core finds roughly 30% of real WCAG issues; Phases 1–3 address the rest using trusted tools already in the repo and agent session.

**Do not** use third-party accessibility MCP servers (for example `mcp-accessibility-scanner`). Heuristics from those tools are reflected here, but execution uses only the tools listed below.

## Trusted tools

| Tool | Role in this skill |
| --- | --- |
| **Playwright MCP** (server `playwright` in `.mcp.json`: `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_press_key`, and related browser tools) | Live keyboard traversal, accessibility tree inspection, focus/activeElement checks |
| **Chrome DevTools MCP** (server `chrome-devtools` in `.mcp.json`) | CDP emulation (viewport, `prefers-reduced-motion`, forced colors) and deeper DOM/console inspection when Playwright MCP is insufficient |
| **Playwright** (E2E specs, `@axe-core/playwright`) | Repeatable axe scans, keyboard simulation, viewport sizing, `toMatchAriaSnapshot` |
| **axe-core** (`vitest-axe` in unit tests, `@axe-core/playwright` in E2E) | Automated WCAG rule sweep (floor, not ceiling) |
| **Lighthouse** (Chrome DevTools → Lighthouse panel, or `npx lighthouse --only-categories=accessibility`) | Secondary automated pass; useful for contrast and document-level checks |

Prefer **`browser_snapshot`** (accessibility tree) over screenshots when deciding whether a finding is real.

## WCAG reference data

When citing success criteria, use the machine-readable catalog at [WCAG 2.2 JSON](https://www.w3.org/WAI/WCAG22/wcag.json). Each entry includes `num`, `title`, `level`, `versions`, and `url` for the normative guidance.

## When to run this skill

- Auditing a page, flow, modal, or nav region before drafting bugs
- Reviewing a PR that touches interactive UI, focus, landmarks, or routing
- User asks for keyboard audit, skip link check, heading hierarchy, or "beyond axe" review
- Completing an accessibility audit story (draft one bug per violation for user review)

Load `.claude/skills/frontend-testing-guidelines/SKILL.md` for unit-test axe patterns and `.claude/skills/frontend-playwright-e2e/SKILL.md` for targeted E2E axe setup.

---

## Phase 0 — Scope and baseline

### 0.1 Full-app axe baseline (page registry)

When auditing broadly (or before a manual pass on many surfaces), run the **report-only registry sweep** first:

```bash
# from frontend/ or packages/syntara-ui/
npm run e2e:a11y-audit
```

This runs `e2e/a11y-audit.spec.ts`, which scans every entry in `e2e/visual-regression/page-registry.ts` with axe-core (WCAG 2.x A/AA). Details live in `frontend/packages/syntara-ui/TESTING.md` (**Accessibility audit (report-only)**).

| Property | Value |
| --- | --- |
| **Output** | `packages/syntara-ui/test-results/a11y-audit-report.json` plus per-page JSON in the Playwright report |
| **Stdout** | `A11y audit summary` with page/violation counts |
| **Mode** | Report-only — tests always pass; CI is not gated on the backlog yet |
| **Opt-in** | Excluded from default `npm run e2e`; run via `e2e:a11y-audit` only |
| **Environment** | Mock API seed data required (`@local-only`; skipped in real-backend E2E) |

Each violation in the JSON includes `ruleId`, `impact`, `description`, `helpUrl`, `wcagTags`, and DOM `targets` — use these when drafting bugs (Phase 4).

**Registry sweep limits:** static page loads only. It does not open modals, exercise wizards, or traverse keyboard flows. Treat it as the automated floor; Phases 1–3 still apply per surface (especially overlays and multi-step flows not captured at load time).

### 0.2 Targeted axe baseline

For a single route, modal, or component under review:

1. **Identify surfaces** — route(s), modals, menus, wizards, and states (empty, error, loading, success).
2. **Start the app** — `make dev` or `npm run start:ui` (mock API is fine for most UI audits).
3. **Run axe** on the surface:
   - **E2E / Playwright MCP:** `@axe-core/playwright` with `wcag2a`, `wcag2aa`, `wcag21aa` tags (see `frontend-playwright-e2e` skill). Scope with `.include()` after opening dialogs/menus.
   - **Unit:** `vitest-axe` `toHaveNoViolations()` for isolated widgets.
4. **Record baseline violations** separately from manual findings; do not treat a clean axe run as "pass."

Document: URL, viewport, theme (light/dark), and whether mock or real backend.

---

## Phase 1 — Keyboard audit

Exercise the surface **without a mouse**. Use Playwright MCP or Playwright `page.keyboard`.

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

> **Known gap (Syntara today):** the app does not yet expose a skip-to-main link on full chrome pages. Record this as a finding when auditing, but do not treat it as an automatic audit failure unless the user asked for strict SC 2.4.1 compliance.

When skip links are expected or present:

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

Run the same keyboard and visual checks under each condition. Use Chrome DevTools MCP (CDP `Emulation.setEmulatedMedia`, viewport) or Playwright `page.emulateMedia` / `setViewportSize`.

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
- Prefer top-level **`contentinfo`** landmarks (sibling of **`main`**, not nested). Per [ARIA in HTML](https://www.w3.org/TR/html-aria/), a `<footer>` inside `main` is `role=generic`, not `contentinfo`; flag explicit `role="contentinfo"` nested in another landmark as a best-practice issue (axe `landmark-contentinfo-is-top-level`), not a WCAG failure.
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

## Phase 4 — Report and draft bugs

**Do not create tracker issues without explicit user approval.** Draft findings using the templates below and present them to the user for review first. Only file issues when the user confirms (or explicitly asks you to file).

Draft **one issue per distinct violation** (not one umbrella ticket per page). Link related issues in description if helpful.

### Triage registry report (`a11y-audit-report.json`)

After `npm run e2e:a11y-audit`:

1. Open `packages/syntara-ui/test-results/a11y-audit-report.json`.
2. For each page with `violationCount > 0`, draft **one bug per violation** (not one bug per page).
3. Copy from the report into the bug template:
   - **Summary:** `a11y: [ruleId] on [section/name] — [short description]`
   - **WCAG Reference:** join `wcagTags` (e.g. `wcag2aa`, `wcag21aa`) to the SC cited in `helpUrl` / axe docs; cross-check [WCAG 2.2 JSON](https://www.w3.org/WAI/WCAG22/wcag.json)
   - **Steps to Reproduce:** `Navigate to [path]` from the page entry
   - **Actual Behavior:** `description`, `targets`, and `failureSummary` from the matching node
   - **Impact / Priority:** map axe `impact` using the table below (axe `critical`/`serious`/`moderate`/`minor` align with common impact labels)
4. Skip or note `loadError` pages separately — fix load/navigation before treating axe results as authoritative.

Manual findings from Phases 1–3 use the same template when axe did not report the issue.

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
[Impact level] → [tracker priority] (per audit priority mapping below)
```

### Impact → priority mapping

Map axe impact levels when applicable (adapt priority names to your tracker):

| Impact | Suggested priority | Notes |
| --- | --- | --- |
| **Critical** | **P1** (Urgent) | Blocks task completion for assistive technology or keyboard users |
| **Serious** | **P2** (Major) | Major barrier; workaround painful or unknown |
| **Moderate** | **P3** (Normal) | Degraded experience; workaround exists |
| **Minor** | **P4** (Minor) / backlog | Nuisance; low user impact |

Examples:

- Keyboard focus lost to `<body>` after route change → **Serious → P2**
- Missing `aria-haspopup="menu"` on menu button → **Moderate → P3**
- Missing skip link (landmarks present but no skip control) → **Minor → P4** when landmarks exist; **Serious → P2** when keyboard users must tab through entire nav on every page

Apply team tracker conventions (components, labels, priority field names) from local agent config when available (for example `CLAUDE.local.md`). Prefix summary with **`a11y:`** for discoverability.

---

## Phase 5 — Deliverables checklist

Before marking an audit complete:

- [ ] Registry axe baseline run (`npm run e2e:a11y-audit`) or targeted axe recorded for the scope
- [ ] `a11y-audit-report.json` triaged (or equivalent per-page axe notes for a narrow audit)
- [ ] Keyboard path exercised for primary flow and all overlays
- [ ] Viewport/media matrix spot-checked (mobile, 200% zoom, reduced motion, forced colors)
- [ ] Headings, landmarks, and names/roles reviewed via snapshot or tree dump
- [ ] Each finding (report + manual) drafted as its own bug with impact → priority; user approved before filing
- [ ] No findings dismissed solely because axe did not report them

---

## Anti-patterns

| Do not | Do instead |
| --- | --- |
| Rely on axe alone | Run registry sweep **and** this skill's manual phases |
| Run registry sweep for modals/wizards only | Open overlays and re-scan (Phase 0.2) or use Playwright MCP |
| Use unvetted accessibility MCP scanners | Playwright MCP + axe-core + Lighthouse |
| File one mega-bug per page | One bug per violation with WCAG SC |
| File tracker issues without user approval | Draft bugs and wait for explicit confirmation |
| Disable axe rules to "pass" | Fix the component; document upstream PF issues separately |
| Guess locators or roles | `browser_snapshot` first, then interact |
