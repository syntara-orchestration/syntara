---
description: "PatternFly 6 UX design system guide — component selection, layout patterns, accessibility, project conventions."
user-invocable: false
---

<!--
  SYNC NOTE: A condensed version of this file exists at .cursor/rules/patternfly-ux-design-system.mdc
  (the Cursor rule). Both files must stay in sync — when updating one, update the other.
  This file is the comprehensive source of truth. The Cursor rule is the lightweight version.
-->

# Claude Skill: PatternFly UX Design System — Opinionated Implementation

> **Before writing React, Zod, Zustand, or other library code**, fetch current docs from [`.claude/skills/frontend-library-references/SKILL.md`](../frontend-library-references/SKILL.md).

Your goal is to build frontend UI that adheres to PatternFly standards **and** the UX team's opinionated component usage. This skill codifies specific "PatternFly-first" patterns to ensure consistency across all feature teams and reduce cognitive load for users.

---

## Overview

### Purpose of this Framework

This document serves as the definitive technical and design North Star for **this product's user experience**. It is designed specifically for engineers and designers to ensure we build a scalable, maintainable, and cohesive experience.

### Why This Exists

- **Accelerated Velocity:** By establishing a clear UX framework and component library upfront, we eliminate "decision fatigue." Engineers can focus on implementation logic rather than debating UI patterns or custom CSS. PatternFly is that design framework for all products across the PatternFly portfolio.
- **The Power of PatternFly:** Our commitment to a **PatternFly-first** architecture is strategic. Utilizing the core library ensures that our UI is accessible (WCAG 2.1 AA compliant), themeable, and — most importantly — **upgrade-compatible**. Staying aligned with PF reduces long-term maintenance overhead and prevents "technical debt" through custom, one-off components.
- **A Shared Language:** This skill codifies the UI/UX team's guidelines for this specific product. It bridges the gap between UX design and React implementation, ensuring that "Opinionated" choices are applied consistently across every feature branch.
- **Contribution over Customization:** When you encounter a UI gap, this framework provides the process for feeding requirements back into the core PatternFly system, ensuring fixes land in the shared library rather than as "snowflake" code in the local repo.

**In short:** We use this framework to build faster, stay aligned with the broader PatternFly ecosystem, and ensure that this product remains premium and stable.

### UI/UX Team

For engagement questions, reach out to the UX team in the project's contributor channels.

### Tech Stack

| Category            | Tools                                     |
| ------------------- | ----------------------------------------- |
| IDE and Agent Tools | Cursor, Claude Code, Gemini               |
| Design Library      | [PatternFly](https://www.patternfly.org/) |
| Design Tooling      | Figma, Miro                               |

---

## Design System

How this UI is anchored, and how it relates to other design tooling:

- **Foundation** — Built on top of [PatternFly](https://www.patternfly.org/) for [components](https://www.patternfly.org/components/all-components), [patterns](https://www.patternfly.org/patterns/about-patterns), and [accessibility](https://www.patternfly.org/accessibility/patternflys-accessibility) baselines.
- **Layout** — Page and shell structure follow PatternFly's **Compass** layout architecture.
- **Theming** — Visual treatment uses PatternFly's **Unified Theme**, accounting for layout and color palettes.
- **Icons** — Use icons with the `RhUi` prefix (e.g., `RhUiAddIcon`, `RhUiEditIcon`).
- **Automation builder** — Based on [React Flow](https://reactflow.dev/) as the underlying graph/canvas foundation while PatternFly acts as a visual wrapper. The layout reads from left to right.
- **Accessibility** — While PatternFly provides a strong foundation with accessibility built into its individual components, achieving full [WCAG 2.1 AA](https://www.w3.org/WAI/WCAG2AA-Conformance) and [Section 508](https://www.section508.gov/) compliance requires careful implementation within this codebase.
- **PatternFly gaps** — Before implementing a custom component or styling override:
  1. **Check first.** Search PatternFly docs to confirm the need is not already covered by a component, variant, or token.
  2. **Raise it with UX.** Discuss with the UX team. Describe the gap with a clear before/after versus what PatternFly provides today. UX will confirm whether the gap is valid or an existing pattern applies.
  3. **Engage PatternFly.** If UX confirms the gap, UX coordinates with PatternFly on resolution — new component, variant, token, or an accepted override — often via a PatternFly GitHub issue or direct conversation.
  4. **Document and track.** If a temporary override is approved, create an issue with the label `patternfly-override` to track technical debt. Link the PatternFly issue if one exists.
  5. **Resolve upstream.** The aim is to remove the override by contributing back to PatternFly. Overrides without a resolution path should be periodically reviewed.
- **`Nx` prefix convention** — opinionated global components use the `Nx` prefix (e.g., `SynPage`, `SynPanel`, `NxConfirmationDialog`, `NxDetailList`) and live in `frontend/packages/syntara-ui/src/components/` organized by subdirectory: `layout/`, `dialogs/`, `details/`, `tabs/`, `states/`. These wrap raw PatternFly primitives with project-specific defaults and behavior — use the `Nx*` wrapper, not the raw PF component, for these patterns.
- **What this is not** — The experience is **not** built on custom libraries. This product deliberately uses a PatternFly-first stack.

---

## Research Process

This project is committed to evidence-based development, utilizing user research to steer both product capabilities and the overall user experience.

### Competitive Analysis

Early in the project, the UX Research team conducted a competitive analysis of key players in the agentic and workflow automation space. This research was instrumental in defining the "PatternFly-first" strategy.

### Key Insights & Established Patterns

The study identified several "table stakes" features that users expect as standard in a modern builder:

- **The Three-Panel Layout:** Industry-standard layout consisting of an **Explorer** (left), **Canvas** (center), and **In-Context Configuration** (right) to progressively disclose complexity without overwhelming the user.
- **Standardized Terminology:** Familiar terms such as "Workflow," "Trigger," "Action," and "Logs" to reduce cognitive load.
- **Visual Data Mapping:** "Data pills" and visual mapping for low-code users, with advanced expression editors as an "escape hatch" for power users.

### Strategic Differentiators

Research revealed critical friction points in competitor products — specifically around fragmented AI integration and poor observability:

- **Hybrid Workflow Debugging:** Unlike competitors who struggle to differentiate between probabilistic (AI) and deterministic (code) failures, this platform provides superior debugging and observability for hybrid workflows.
- **Safety as a First-Class Object:** "Gating" steps and Human-In-The-Loop (HITL) checkpoints build trust, ensuring users can safely manage non-deterministic AI outputs before they execute against critical infrastructure.
- **In-Context Documentation:** Context-aware help and documentation integrated directly into configuration panels to save users from switching tabs.

### Accessibility & Compliance

A major finding was that basic usability and accessibility are often an "afterthought" in technical automation tools. By building on PatternFly, this product meets high accessibility standards (WCAG 2.1 AA) from the start, providing a more inclusive experience than the current market leaders.

---

## Philosophy

### The Opinionated Implementation

While PatternFly provides flexible building blocks, this project follows an **opinionated implementation**. We pick the components that best serve the "supervisor" mental model — an operator who must understand, trust, and intervene in complex automation across scale.

**Key principles:**

- **Standardized compositions** — Atomic PatternFly components are combined into larger, opinionated compositions (e.g., a "complete table view" with prescribed pagination, filtering, and bulk action patterns). These compositions are the unit of consistency, not individual components.
- **Data-driven adjustments** — Side-out panels instead of modals for step configuration, preserving workflow canvas context.
- **No custom one-offs** — When PatternFly does not meet a requirement, collaborate via the PatternFly liaison path rather than building a custom component. This keeps the product upgrade-compatible.

### Framework & Source of Truth

| Source                                       | Description                                                                           |
| -------------------------------------------- | ------------------------------------------------------------------------------------- |
| **Compass Layout**                           | Layout architecture providing systematic page structure and spacing                   |
| **UI Repository**                         | The opinionated PatternFly implementation — the reference for tables, filters, modals |
| **PatternFly (https://www.patternfly.org/)** | The upstream design system; always check here first for component docs                |

### Key Experience Principles

The automation platform market has matured, but the user experience across it has not. Most competitors were architected as engineering tools first and operator interfaces second. Their UX accrued over years of feature addition without a unifying experience philosophy. The result is a category where power and usability are treated as trade-offs rather than compounding forces.

Our UX is designed around a single mental model: the **supervisor** — an operator who must understand, trust, and intervene in complex automation across scale.

When an automation platform spans inventories, credentials, templates, schedules, and RBAC, the cognitive tax of learning different interaction patterns per domain is enormous. Users shouldn't have to re-learn how filtering, pagination, or bulk actions work in each section. We define opinionated, reusable compositions from PatternFly's atomic components — a "complete table view" that prescribes pagination, toolbar filtering, bulk action placement, and empty-state behavior. These compositions are the unit of consistency, not individual components.

### Addressing Gaps

Opinionated does not mean custom. When PatternFly does not meet a specific design requirement, follow the 5-step PatternFly gaps liaison process defined in the Design System section above (Check first → Raise with UX → Engage PatternFly → Document and track → Resolve upstream). Never create custom, one-off components.

---

## 1. Side Navigation Structure

Use a docked icon navigation (left sidebar) with PatternFly's [flyout panels component](https://www.patternfly.org/components/navigation/#flyout) for items with sub-navigation.

### Behavior Rules

| Interaction                      | Behavior                                      |
| -------------------------------- | --------------------------------------------- |
| Hover on nav item (no children)  | Show tooltip with label                       |
| Hover on nav item (has children) | Show flyout panel with sub-items              |
| Click on nav item (no children)  | Navigate to route                             |
| Click on nav item (has children) | Navigate to first enabled child route         |
| Click on flyout sub-item         | Navigate to that route, **close flyout immediately** |
| Mouse leaves flyout              | Close flyout after 150ms delay (grace period) |
| Mouse moves from icon to flyout  | Flyout stays open (no gap flicker)            |

---

## 2. Page Layout

Every page **must** follow this structural hierarchy:

| Layer              | Component                   | Purpose                                  |
| ------------------ | --------------------------- | ---------------------------------------- |
| App Shell          | `Compass`                   | Overall application frame                |
| Navigation         | `AppDockedNav`              | Left sidebar with icons                  |
| Page Content       | `CompassContent` + `SynPage` | Main content area wrapper                |
| Page Header        | `SynPageHeader`              | Page title and actions                   |
| Content Frame      | `SynPanel`                   | `Panel` → `PanelMain` → `PanelMainBody`  |
| Content Stack      | `SynPanelContentStack`       | Full-height flex column inside `SynPanel` |
| Main Content       | Table / Canvas / Form       | Primary page content                     |
| Footer (on tables) | `PaginationFooter`          | Navigation between table pages           |

For **floating panels on the workflow canvas** under the glass theme, prefer `SynPanel` with `variant="raised"` for compact controls (opaque + shadow) or `opaqueFloatingFill` for large flat shells without raised chrome; see JSDoc on `frontend/packages/syntara-ui/src/components/layout/SynPanel.tsx`.

### Centered Layout for Loading / Empty States

Use `SynPageBody` with `isCentered` for page-level centered layouts (loading spinners, empty states). For nested slots (e.g. `StackItem` + `isFilled`), use `flexCenteredBothAxes` from `src/app/flexCenteredBothAxes.ts`.

### Panel Content Stack

Use `SynPanelContentStack` (from `frontend/packages/syntara-ui/src/components/layout/SynPanelContentStack.tsx`) as the main content column inside `SynPanel isFullHeight`. It provides the correct flex behavior (`flex: 1`, `minHeight: 0`) so nested scroll areas resolve height correctly.

| Variant   | Use case                                                            |
| --------- | ------------------------------------------------------------------- |
| `default` | Standard full-height panel content                                  |
| `inset`   | List pages with horizontal inset (workflows, executions, approvals) |

### Page Layout Archetypes

The following four compositions are the canonical page structures. Storybook documents each as a composed story under `SynPage`.

| Archetype          | Structure                                                                                                                        |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| **List page**      | `SynPageHeader` (Create CTA) → `SynPageBody` → `SynPanel isFullHeight` → `SynPanelContentStack variant="inset"` → filter bar + table |
| **Detail page**    | `SynPageBreadcrumbs` → `SynPageHeader` → `SynPanel isFullHeight` → `SynPanelContentStack` (default) → tabs + content                 |
| **Form page**      | `SynPageBreadcrumbs` → `SynPageHeader` → `SynPanel isFullHeight footer={<ActionGroup>…</ActionGroup>}` → form body (max-width 600px) |
| **Error in panel** | Same shell as list page → `SynPageBody isCentered` + `NxErrorState` **inside** `SynPanel` (page header and shell remain visible)   |

### Sticky Form Footer

Form submit and cancel buttons live in a **pinned footer at the bottom of the content panel**, not in the page header toolbar. Use the `SynPanel` `footer` prop:

```tsx
<SynPanel isFullHeight footer={<ActionGroup>{/* Save + Cancel buttons */}</ActionGroup>}>
  {/* form body */}
</SynPanel>
```

- When `SynPanel` is `isScrollable`, `PanelMain` scrolls while the footer stays pinned — no custom sticky CSS needed
- Cancel button uses `variant="link"` (per UX design system)
- `SynPanel.module.css` normalizes footer padding (`--spacer--md`), widens button spacing, and adds a visible divider border
- **Applies to:** Create/Edit User, Configure Integration, Edit Group Mapping, Settings tabs, Integration Tools, Approval Detail
- **Does NOT apply to:** Builder forms (use node editor panel footer), modals/dialogs (buttons inside modal footer)
- **Does NOT apply to:** Check Access / Who Can forms — these are inline query forms inside a tab panel with no header buttons to move

**`NxListPanel` — canonical list page implementation:**

List pages should use the `NxListPanel` compound component API instead of manually assembling `SynPanelContentStack` + `useQueryState` + three-state branching:

- **`NxListPanelView`** — handles loading/error/empty/filter states declaratively via props: `tabKey`, `isPending`, `isFetching`, `isEmpty`, `hasActiveFilters`, `noDataState`, `toolbar`, `children`
- **`NxListPanelToolbar`** — wraps `FilterBar` + action buttons; automatically wraps content in `<fieldset disabled={isFetching}>` with a screen-reader legend during refetch
- **`NxListPanelTable`** — standardized table slot inside the list panel

### Page Header Structure

The page header appears at the top of every page and contains the title and primary actions.

There are different kinds of page headers:

- **Main page header**
  - Left-aligned page title
  - Right-aligned page actions

- **Details page header**
  - Left-aligned breadcrumbs (via `SynPageBreadcrumbs`) + page title
  - Optional: resource type label badge alongside the resource name
  - Right-aligned toolbar actions ordered left to right: `Switch` toggle (if applicable) → Edit button (primary) → kebab menu with remaining actions

- **Form page header**
  - Left-aligned breadcrumbs (via `SynPageBreadcrumbs`) + page title
  - No action buttons in the header — Save and Cancel live in the `SynPanel` sticky footer (see Sticky Form Footer above)

### Breadcrumbs

Use `SynPageBreadcrumbs` for detail and form page navigation.

- Renders **nothing** when fewer than 2 items (single-level pages have no breadcrumb)
- Last item is the current page (rendered as non-link text)
- Middle segments collapse to a dropdown at ≤768px viewport width
- Use PF6 default breadcrumb styling (dashed underline) — no CSS overrides

For live examples:

```
list-all-documentation → find "SynPageBreadcrumbs" → get-documentation("SynPageBreadcrumbs")
```

### Tabs

When a page uses tabs, the tabs must live inside `SynPanel`, not outside it.

- Tab labels should be clear, professional, and action-oriented
- Use sentence case for tab labels (e.g. "Activity log", not "Activity Log")
- Avoid colloquial language, slang, or informal phrasing
- Avoid punctuation in tab labels (no question marks, exclamation points)
- **Tab intro paragraphs:** For complex admin sections (e.g., Access Management — Groups, Projects, Users, Assignments, Policies, Roles), add a descriptive `<Content component={ContentVariants.p}>` block above the tab content (before filters/toolbars) explaining what the section does and how it relates to RBAC. Use `marginBottom: var(--pf-t--global--spacer--md)` below the intro text. This is not a page header description — it lives inside the tab panel content.

**`NxUrlTabs` API:**

- `basePath` — the URL path prefix for the tabs
- `defaultTab` — tab to show when no tab segment is in the URL (defaults to `"details"`)
- `validTabs` — optional array for dynamic tab lists; invalid tab segments redirect to `defaultTab`
- URL is the single source of truth for the active tab — no local active-tab state
- Tab panel content owns its own inner padding (typically `--pf-t--global--spacer--lg`)

For live examples and story-driven documentation, use the Storybook MCP:

```
list-all-documentation → find "NxUrlTabs" / "SynPage" / "SynPageHeader" / "SynPanel" /
"SynPageBreadcrumbs" / "NxConfirmationDialog" / "NxDetailList" / "NxCodeBlock" → get-documentation(...)
```

---

## 3. Page Content Frame

### Filter Bar Components

Use PatternFly's [Attribute Search component](https://www.patternfly.org/patterns/filters/#attribute-search).

By default every filter type should be a "Keyword" search which is a `contains` filter on all content.

Filter bar is visible when data exists or when filters are active; hidden only when the resource type has never had data created.

- **Filter dropdown search threshold** — Filter select dropdowns hide the `SearchInput` when there are fewer than 10 static options (e.g., Enabled/Disabled toggles), reducing visual clutter for small option lists. Async (server-side) filters always show the search bar since it drives the server query. The threshold is defined as `SEARCH_THRESHOLD = 10` in `textFilterSelectControls.tsx`.
- **Multi-select (IN) filters** — For bounded, enumerable fields (status, type, role), use `MultiSelectFilter` (`components/filters/MultiSelectFilter.tsx`) instead of a single-value filter: a checkbox `Select` that emits one filter with operator `in` and a string-array value, a count badge on the toggle showing how many are selected, and `Select All` / `Clear All` actions above the option list. Reserve the plain single-value filter dropdown for fields where only one value can reasonably apply at a time.

| Component           | Purpose                            |
| ------------------- | ---------------------------------- |
| Filter dropdown     | Select filter category             |
| Search input        | Text search                        |
| Active filter chips | Show applied filters (when active) |
| Clear all           | Remove all filters                 |

### Table Component

- Always use `NxScrollableTableContainer` wrapper — this applies the standard table variant by default
- `NxScrollableTableContainer` does not set `variant="compact"` — the default (standard) variant is used for main data tables
- Use `variant="compact"` only for dense, supplementary tables (e.g., activity state tables inside panels) where space is constrained
- Always include `<Thead>` with column headers
- Actions column is rightmost
- Header includes title and primary actions for the whole page
- Columns should be sortable if applicable
  - **Sort state lives in the URL**, not local component state. `useSortState` (`hooks/useSortState.ts`) reads/writes a `sort` query param in `field` / `-field` form (leading `-` = descending). `useCursorPagination` (`hooks/useCursorPagination.tsx`) composes `useSortState` together with filter state and cursor paging into a single hook, and resets to page 1 whenever the sort changes. Standalone panels that don't need filters/pagination can use `useSortableTable` directly to wire `<Th sort>` to the same URL-backed state. This is the standard across all server-sorted list pages (Workflows, Executions, Run History, Approvals, Integrations, Assignments) — do not reintroduce index-based, client-only sort state for new tables.
- Clicking the name of a resource should navigate to the details view — use `LinkCell` (built on `NxLink`) for the name column
- **Navigational text uses `NxLink`, not `Button` + `navigate`** — Any text that acts purely as a link to another route (resource names, cross-entity references in a detail view or table) should render `NxLink` (`components/NxLink.tsx`), a real anchor styled as a PatternFly inline link. Don't reach for `Button variant="link"` with an `onClick` that calls `navigate()` — that renders `role="button"` on something that is semantically navigation, breaking "open in new tab," "copy link address," and link-role accessibility/test queries.
- **Table columns:**
  - Columns for "created" or "modified" should have username (linked) + date together
  - This pattern should be used for any column that includes a date/time and a who
  - Date/time format: `MMM DD, YYYY, H:MM:SS AM/PM` — e.g., "Jan 15, 2026, 2:30:45 PM". Comma between date and time. Seconds included. Always render read-only date/time values through `DateCell` / `UserTimestamp` (`components/table/DateCell.tsx`), which wrap PatternFly's [`Timestamp`](https://www.patternfly.org/components/timestamp) component with `dateFormat="medium" timeFormat="medium"` — never call `toLocaleString()` or hand-roll date-fns formatting directly in a component. `Timestamp` renders smaller (`body-sm`) text than default body copy by design (PF's built-in `--pf-v6-c-timestamp--FontSize` token) — do not override this per-instance; it is the accepted look project-wide.
- **Row Actions:**
  - Every table row has a kebab menu (⋮) in the rightmost column containing all available actions for that resource
  - The actions column has no column header label
  - All row actions live inside the kebab — no direct buttons or links in the actions column
  - **Exception — inline enable/disable**: A `Switch` toggle may appear in a dedicated "State" column (not the actions column) for resources where toggling the enabled state is the most frequent action (e.g., credentials, identity providers). The switch patches the resource directly. **Note:** Workflows no longer use an inline Switch — they use the Publish lifecycle with status badges (see §17).
  - **Full labels:** Always use `"Action + resource"` format in kebab menus — e.g., "Edit credential", "Delete credential", "Duplicate workflow" (not just "Edit" or "Delete"). Each item includes an icon via the `IconLabel` pattern.
  - Destructive items use `isDanger: true` (e.g., "Delete credential" renders in red)
  - Action order: non-destructive actions first (e.g., "Edit credential", "Duplicate workflow", "Disable credential"), then a divider, then destructive actions last (e.g., "Delete credential", "Remove integration")
  - On the **details page header**, the same actions appear in a kebab menu. Frequently used actions (e.g., Edit) are promoted to direct buttons in the header — primary button with icon for the most common action (e.g., `RhUiEditIcon` + "Edit credential"), remaining actions stay in the kebab.
- **Text truncation** — All text-heavy columns (names, descriptions, emails, URLs) must use PatternFly's `<Truncate>` component. Long values show ellipsis with the full text in a tooltip on hover.
  - `NxScrollableTableContainer` uses `table-layout: fixed` for equal column distribution — do not opt out with `useFixedLayout={false}`
  - Wrap cell text in `<Truncate content={value} />` for any column that may contain user-generated or variable-length content
  - `LinkCell` children support `<Truncate>` — the link button constrains overflow automatically
- **`NxKebabMenu` component** — Use `NxKebabMenu` (from `frontend/packages/syntara-ui/src/components/NxKebabMenu.tsx`) for table row actions and contextual overflow menus. API:
  - `actions`: array of `{ key, title, onClick, isSeparator?, isDanger?, isAriaDisabled?, tooltipProps? }`
  - `aria-label`: must be unique per row (e.g., `` `Actions for ${resource.name}` ``)
  - Action ordering: non-destructive first → `isSeparator: true` → destructive last (`isDanger: true`)
  - Use `IconLabel` for action titles: `<IconLabel icon={<RhUiEditIcon />}>Edit workflow</IconLabel>`
  - Permission-gated items: `isAriaDisabled: true` + `tooltipProps: { content: tooltip }` (visible but non-actionable, stays focusable)
  - **Only one kebab open at a time** — this is built into `NxKebabMenu` itself via a module-level registry of open-menu close callbacks; opening any `NxKebabMenu` automatically closes every other one on the page. Callers don't opt in or manage this — it's automatic across separate table rows and between a table row and an adjacent panel (e.g., a history panel row).
- **Expandable rows** — When a table uses expandable rows to show nested detail (e.g., policies under a role, execution steps in a workflow run):
  - Pass `isExpandable` to `NxScrollableTableContainer` for proper PF6 table styling
  - Include an expand-all / collapse-all toggle in the `<Thead>` using the `expand` prop on the first `<Th>`
  - Use `ExpandableRowContent` for the expanded row body
  - Expanded content should use compact gray `Label` components for list-style data (e.g., attached policies)
  - Column order left to right: expand/collapse chevron → [checkbox if selectable] → data columns → actions
- **Footer/pagination** — use `PaginationFooter` via the `NxScrollableTableContainer` `footer` prop. `PaginationFooter` wraps PatternFly's [Pagination](https://www.patternfly.org/components/pagination) component; supports `page`, `perPage`, `total` (optional), `hasNext`, `onPrev`, `onNext`, and `onPerPageChange`. When `total` is unknown (cursor-based APIs), item count is estimated from `page`, `perPage`, and `hasNext`. Pair with `useCursorPagination` from `src/hooks/useCursorPagination.tsx` for cursor state management

### Form Component

- Use PatternFly's [Basic Form component](https://www.patternfly.org/components/forms/form/#basic)
- Forms should be left-aligned, one column, max-width of 600px
- Header includes title, primary action button, and secondary cancel
- **Inputs/fields:**
  - Use PatternFly's [typeahead component](https://www.patternfly.org/components/menus/select/#multiple-typeahead-with-labels) to easily find options in a list of items (use when there are 10+ options)
  - Use PatternFly's [Read-only Clipboard Copy](https://www.patternfly.org/components/clipboard-copy/#clipboardcopy) when an input is pre-populated by the system and the user needs to copy
  - Use PatternFly's [Validated component](https://www.patternfly.org/components/forms/form/#validated) for general form validation
  - Use PatternFly's [Number Input component](https://www.patternfly.org/components/number-input/#numberinput) for number input fields
  - Use PatternFly's [DatePicker](https://www.patternfly.org/components/date-and-time/date-picker) for date inputs — never use native `<TextInput type="date">`. DatePicker provides a consistent cross-browser calendar popover, date validation via the `validators` prop, and proper formatting/parsing via `dateFormat`/`dateParse`. Use `appendTo={() => document.body}` for correct popover positioning. Pass validation state through `inputProps={{ validated: ... }}`.
  - Use PatternFly's [popover help text](https://www.patternfly.org/components/popover/design-guidelines) on form field labels. In the workflow builder, use the shared `FieldHelpPopover` component (`components/FieldHelpPopover.tsx`, wrapping PF6 `FormGroupLabelHelp` + `Popover`) rather than inline `Popover` JSX per field, fed from a central copy registry (`routes/builder/node-forms/shared/nodeFieldHelp.tsx`) so help text is defined once and reused across node forms instead of duplicated per component.
  - Use PatternFly's [`HelperText`](https://www.patternfly.org/components/forms/helper-text) / `HelperTextItem` below form inputs to provide brief, contextual guidance (e.g., accepted formats, valid ranges, constraints). The help popover icon on the field label is for longer explanatory descriptions. When both are present, inline helper text gives at-a-glance guidance while the popover provides full context. Validation errors (`validated="error"`) take priority — replace the helper text with the error message when the field is invalid.
  - **`autoComplete` on sensitive create-form fields** — Browsers aggressively offer saved-credential autofill on username/password-shaped inputs even on "Create new resource" forms, where that's semantically wrong (there's no existing account to autofill). Set `autoComplete="off"` on username-shaped fields and `autoComplete="new-password"` on password/secret fields for any create-account or create-credential form.
- **Dropdowns:** Never use native `<select>` or PatternFly's legacy `FormSelect` / `FormSelectOption` — this is enforced by a `no-restricted-imports` ESLint rule (`eslint.config.js`) that errors on any `FormSelect`/`FormSelectOption` import. Always use the PF6 `Select` + `MenuToggle` + `SelectList` + `SelectOption` pattern. Inside modals, use `popperProps={{ appendTo: 'inline' }}` for correct dropdown positioning — **except** for long menus (see "Long menus" below), which should not use `appendTo: 'inline'`. Add `shouldFocusToggleOnSelect` for keyboard accessibility after selection. When dropdown options represent policies or modes where the label alone isn't self-explanatory, use the `description` prop on `SelectOption` to provide inline context (e.g., "Skip" with description "Only one run at a time; skip if the previous run is still in progress").
  - **Long menus** — Any `Select`/`SelectList` with many options (credential type pickers, project pickers, filter dropdowns) — not just typeaheads — needs a bounded max height so the menu doesn't grow unbounded or get clipped. Use the shared `longSelectMenu.ts` utility (`components/longSelectMenu.ts`), which sets `max-height: min(40vh, 25rem)`, `preventOverflow`, and scroll containment, and deliberately does **not** use `appendTo: 'inline'` so the menu isn't clipped by modal bounds.
- **Auth method selector for mutually exclusive field groups** — When a resource's schema declares mutually exclusive field groups (e.g., a credential type offering "OAuth2 Token" vs. "Basic Auth"), show an "Auth method" dropdown above the dynamic field list; render only the selected group's fields, and clear the previous group's values when the user switches groups. In edit mode, auto-detect which group is active from the existing values rather than defaulting to the first option. See `routes/configuration/credentials/form/AuthMethodSelector.tsx`.
- **Validation behavior:**
  - The primary action (Save / Create) is **always clickable** — never disable it because of missing required fields
  - When the user clicks Save with invalid or missing fields, apply `validated="error"` (danger styling) to the invalid fields and show a toast notification explaining what needs attention
  - Selecting/filling the required field clears the danger styling immediately
  - **Human-readable validation copy:** Never expose raw regex patterns or API validation strings to users. Use plain-language error messages (e.g., "Project name can only contain letters, numbers, hyphens, underscores, or colons. It must start and end with a letter or number."). Provide proactive field guidance via inline hint text (using `HintOrError` or `HelperText`) that displays before the user triggers an error; the hint is replaced by the error message on validation failure. Use example-style placeholders (e.g., `'my-project-name'`) instead of generic `"Enter project name"`.
- **Read-only system values:** Never use a disabled `TextInput` to display system-provided, non-editable values. Disabled inputs imply the field could be editable in another context. Instead use `DescriptionList isCompact` (term + description), `ClipboardCopy` (when copying is the primary action), or plain text to make clear the value is informational.
- **Cascading field resets:** When one field change should clear or reset dependent fields (e.g., changing "Resource type" resets "Action"), put the reset logic in the field's `onChange` handler -- not in a `useEffect` watching the field value. See [.claude/skills/frontend-coding-standards/SKILL.md §23](../frontend-coding-standards/SKILL.md) and [React docs](https://react.dev/learn/you-might-not-need-an-effect).
- **Credential-managed field locking:** When a credential selection controls a field's value at runtime (e.g., a "Secret URL" credential manages the URL), disable the field, change its placeholder to explain the override (e.g., "URL managed by credential"), add helper text ("This value will be injected at execution time and is never stored in the workflow definition."), clear any user-entered value, and remove the `required` attribute. When the credential is deselected, restore the field to its normal editable state. See `httpCredentialSection.tsx` for the pattern.
- **Auto-save before dependent actions:** When a user action depends on the current form state being persisted (e.g., "Run Step" depends on saved step configuration), programmatically submit any open editor form before proceeding. Use a `data-step-editor-form` attribute on forms and `requestSubmit()` to trigger save, then continue with the dependent action. See `useRunStepDialog.ts` for the pattern.
- **FormSection for complex forms:** When a single form step has 10+ fields spanning logical domains, group them with PatternFly `FormSection`:
  - `title="Section Name"` + `titleElement="h3"` for each group
  - **Grouping logic:** General (identity/metadata) -> Connection (endpoints/secrets) -> Options (toggles/advanced)
  - Section-scoped actions belong inside their section (e.g., "Test connection" inside the Connection section, not the global footer)
- **Scrollable form panels:** Full-page forms that may exceed viewport height need `SynPanel isFullHeight isScrollable`. Without `isScrollable`, bottom fields overflow outside the panel boundary. Constrain form width with `maxWidth: '600px'` inside a `Stack hasGutter`.
- **Validation errors must be visible in collapsible forms:** When a form uses collapsible sections (accordion, expandable panels), validation errors inside collapsed sections must either (a) auto-expand the section containing the error, or (b) show a summary indicator on the collapsed header (e.g., error count badge, danger styling). Users must never submit a form and see no feedback because errors are hidden inside a collapsed panel. Every invalid field must show an inline error message below it -- `validated="error"` styling alone (red border with no message) is insufficient.

### Typeahead Selector Patterns

All typeahead dropdown menus should have a **max height** to prevent the dropdown from growing unbounded. Use the shared `longSelectMenu.ts` utility (see "Long menus" under Form Component above) rather than a one-off `menuHeight` value — the same constraint applies to any long `Select`/`SelectList`, not just typeaheads.

#### Project Selector (with favorites)

The project selector is a special typeahead that supports favorites. This pattern is specific to the project selector — resource pickers (e.g., credential selectors, integration pickers) do **not** include favorites.

- **Visible prefix label** — The masthead project selector includes a static `"Project:"` prefix inside the toggle using `InputGroupItem` + `Content`. When enabled, use `--pf-t--global--text--color--regular` for the prefix (subtle text color lacks contrast on MenuToggle's light grey background in dark mode). When disabled, use `color: inherit` so the prefix matches PatternFly's disabled toggle text color. See `getProjectTogglePrefixLabelStyle()` in `projectSelectorUtils.ts`. Global scope selectors must label what they control, not rely on placeholder alone.
- **Favorites** — star icon to mark items as favorites; favorites appear in a grouped section at the top of the dropdown
- **Grouped sections** — separate "Favorites" and "All" groups when favorites are active
- **Sticky footer** — a persistent "Create [resource]" action pinned at the bottom of the dropdown, always visible regardless of scroll position
- **Clear filter** — a clear button (×) in the search field to reset the typeahead filter
- **Data persistence during filtering** — preserve existing data while filtering to avoid loading/error flash states; only show loading on initial fetch

#### Resource Pickers (without favorites)

Resource pickers (credential selectors, integration pickers, etc.) use a standard typeahead without favorites:

- **Typeahead search** — filter options by typing
- **Clear filter** — a clear button (×) to reset the typeahead filter
- **Max height** — constrain the dropdown to prevent unbounded growth
- **Richer pickers may add, on top of the base pattern:** an optional "No {resource}" clearing option when the field isn't required; an inline "Create new {resource}" option that opens the create modal without leaving the current form; a `projectId`-scoped mode that limits results to global + current-project resources (see "Project-scoped resource dropdowns" in §17); and a warning when the currently-selected resource exists but the user lacks permission to use it. See `routes/builder/components/CredentialSelector.tsx` for a picker that implements all four.

#### Multi-Select Typeahead with Label Chips

For fields where users can select multiple items (e.g., group assignment on user creation), use `MenuToggle variant="typeahead"` + `TextInputGroup` + `LabelGroup` + **`NxLabel color="blue"`** (filled, default variant) for selected items:

- **Filter-as-you-type** with checkbox options
- **Selected items as chips** — `NxLabel color="blue"` with close (×) button for individual removal; clear-all button with `aria-label` for removing all selections. Do **not** use `variant="outline"` for picker chips — outline is for filter chips and user tags, not multi-select selections.
- **Empty filter message** — `"No results match \"{filter}\""` when typeahead filter matches nothing
- **Options with descriptions** — show supplementary text below option labels when available
- **Create-only fields:** Some multi-select fields (e.g., group assignment) appear on the Create form only; editing is done through a dedicated panel on the detail page (e.g., `UserGroupsPanel`). This avoids overloading the edit form with group management.

### Details Component

- Use `NxDetailList` + `NxDetail` for detail page fields (from `frontend/packages/syntara-ui/src/components/details/`)
  - **Vertical** (default) for standard detail pages
  - **`isHorizontal`** for compact contexts (e.g., canvas step detail panels)
- `NxDetail` with empty/null/undefined children **renders nothing automatically** — optional fields can be passed unconditionally without manual null checks
- Use `NxCodeBlock` (from `frontend/packages/syntara-ui/src/components/details/NxCodeBlock.tsx`) for scripts, JSON payloads, or log output
  - Supports `enableCopy` (clipboard), `enableExpand` (full-screen modal), and `jsonObject` (auto-formatted JSON)
  - Default max height of 24rem with scroll; use `noMaxHeight` when inside a height-constrained parent
- Use consistent formatting for dates and durations — follow PatternFly's [Date/Time guidelines](https://www.patternfly.org/ux-writing/numerics/#date-and-time-formats)
- Header includes title and primary actions for the specific resource (pulled from the table row actions)
- **Title:** Pass the resource name as a plain string to `SynPageHeader` / `title` — no decorative icons in h1
- **Informational metadata as plain text:** Attributes like credential type, authentication method, or resource category are plain text — not `Label` badges. Use `Label` only when visual distinction or status communication is needed (see §11).
- **Created / Modified columns in tables:** Use inline `UserTimestamp` mode — `username · date` on one line. Stacked mode is for detail views only.
- **User name display:**
  - Table "Name" column: composed display name via `userDisplayName(user)` — `[first_name, last_name].filter(Boolean).join(' ')`
  - Detail pages: separate "First Name" / "Last Name" fields in `DescriptionList`
  - Forms: separate inputs — "First Name" (required), "Last Name" (optional)
  - Breadcrumbs: `userDisplayName(user) || user.username` (fallback to username)
  - Sorting: by `first_name` (not composed name)
  - Filtering: separate "First Name" / "Last Name" filters (not a single "Name" filter)

For live examples and story-driven documentation:

```
list-all-documentation → find "NxDetailList" / "NxDetail" / "NxCodeBlock" → get-documentation(...)
```

---

## 4. Empty States

Use PatternFly's [Basic Empty State component](https://www.patternfly.org/components/empty-state#basic).

Empty states replace the main content area when there is no data to display.

| Scenario             | Title                          | CTA: Primary button                  | Filter?                          |
| -------------------- | ------------------------------ | ------------------------------------ | -------------------------------- |
| No data exists       | `"No [resources] yet"`         | If applicable: `"Create [resource]"` | No                               |
| No filter results    | `"No results found"`           | `"Clear all filters"`                | Yes, with active filters showing |
| Service error        | `"Unable to load [resources]"` | `"Retry"`                            | No                               |
| Invalid ID (bad URL) | `"Invalid [resource type]"`    | Link back to list page               | No                               |
| Not found (404)      | `"[Resource type] not found"`  | Link back to list page               | No                               |

### Empty State Icons, Statuses, and Variants

Each empty state scenario maps to a specific icon, optional `status` prop, and size variant. Follow PatternFly's [empty state design guidelines](https://www.patternfly.org/components/empty-state/design-guidelines) for icon and color conventions.

| Scenario               | Icon                    | `status` prop | `variant`       | Notes                                                                |
| ---------------------- | ----------------------- | ------------- | --------------- | -------------------------------------------------------------------- |
| No data / creation     | `PlusCircleIcon`        | —             | `lg`            | Resource has never had data created; gray icon by default            |
| No filter results      | `SearchIcon`            | —             | `sm`            | Inside tables when filters match nothing                             |
| Service error          | `ExclamationCircleIcon` | `danger`      | `lg`            | Data cannot be loaded; red icon via danger status                    |
| No access / forbidden  | `LockIcon`              | —             | `lg`            | User role doesn't have permission to view the page                   |
| Configuration required | `WrenchIcon`            | —             | `lg`            | User must configure or connect something before using a feature      |
| Invalid ID / not found | `SearchIcon`            | —             | `lg`            | Detail page with bad URL param or 404; include a link back to list   |
| Success / completion   | `CheckCircleIcon`       | `success`     | default or `xl` | Task or process completed; green icon via success status             |
| Getting started        | `RocketIcon`            | —             | `xl`            | First-time onboarding; can use a custom app-specific graphic instead |

**General rules:**

- Use the `status` prop (`danger`, `warning`, `success`, `info`) for status-driven empty states — PatternFly applies the correct icon color automatically
- For non-status empty states (no data, no results, configuration, no access), icons render in **gray by default** — do not manually set a color
- Variant sizing: `sm` inside tables, modals, or wizards; `lg` for full-page empty states; `xl` for getting started or full-page success; `xs` (with `headingLevel="h3"`) for narrow, height-constrained panel-embedded contexts, e.g. builder side panels (step Input/Output panels) or node execution detail panels, where even `sm` is too tall
- **CTA deduplication:** When the empty state includes a primary create/configure CTA button, **hide the page-header primary button** to avoid duplicate CTAs. The empty state CTA is sufficient — the header button reappears once data exists.
- **Tab-level empty states:** Use the shared `NxEmptyStateNoData` component (not ad-hoc `EmptyState`) with the correct heading level (`h2` inside tabs) and `isFullHeight` prop
- **Three-state list page pattern:** Every list page must handle three states in this order:
  1. Query error/loading → `useQueryState(query, { title, onRetry })` returns a loading or error component
  2. Truly empty (no data AND no active filters) → `NxEmptyStateNoData` with create CTA; **hide FilterBar entirely**
  3. Has data OR has active filters → show `FilterBar`; if data is empty with filters, show `NxEmptyStateFilter` inside the scroll area
- **Access denied empty state:** Use `EmptyStateAccessDenied` (with `RhUiLockIcon`) when a user navigates directly to a page they cannot read. Message format: "You don't have permission to view {resource}. Contact your administrator to request access."

---

## 5. Page Layout Checklist

When building or reviewing any page, verify every item:

### Structure

- [ ] Uses `SynPage` as outer wrapper
- [ ] Uses `SynPageHeader` for title and actions
- [ ] Uses `StackItem isFilled` + `SynPanel isFullHeight` for content
- [ ] Uses `SynPanelContentStack` for the main content column inside `SynPanel`
- [ ] Loading / empty states use `SynPageBody isCentered`
- [ ] Inner content has consistent padding

### Header

- [ ] Title is clear and matches navigation
- [ ] Primary action is the rightmost button
- [ ] Action buttons follow standard order

### Filter Bar

- [ ] Visible when data exists or when filters are active
- [ ] Hidden only when the resource type has never had data created

### Main Content

- [ ] Tables use `NxScrollableTableContainer`
- [ ] Main data tables use `NxScrollableTableContainer` (standard variant by default)
- [ ] `variant="compact"` only used for dense, supplementary tables where space is constrained
- [ ] Tables have proper column headers
- [ ] Forms have max-width of 600px
- [ ] Canvas views use `hasNoPadding`

### Footer

- [ ] Only present for tables
- [ ] Shows item count on left
- [ ] Navigation controls on right
- [ ] Buttons disabled when at boundary

### Empty States

- [ ] Correct empty state for the scenario (no data / no results / error)
- [ ] CTA button when applicable

### Button Placement Rules

Button alignment differs by context — this is intentional and follows PatternFly convention:

| Context           | Primary action position               | Example                                                            |
| ----------------- | ------------------------------------- | ------------------------------------------------------------------ |
| Page headers      | **Rightmost**                         | "Create credential" button on the far right of the header          |
| Modals            | **Leftmost**                          | "Delete" danger button on the far left, "Cancel" link on the right |
| Forms (full page) | **Leftmost**                          | "Save" button on the far left, "Cancel" link on the right          |
| Toolbars          | **Leftmost**, kebab menu on far right | "Create" button left, bulk action kebab on right                   |

---

## 6. CRUD Patterns

Use consistent action verb pairings across the UI:

- "Create" is paired with "Delete"
- "Add" is paired with "Remove" — when the resources being added and removed are native, in-platform resources
- "Add" is paired with "Disconnect" — when the resource is coming from an external source
- "Assign" is paired with "Unassign"
- "Transfer" is used when moving ownership of a resource between entities (e.g., "Transfer identity" — moving a federated identity from one user to another). Not "Attach" or "Connect".
- "Configure" is used for integrations — not "Add integration". Integrations are external connections being configured, not in-platform resources being created. Use "Configure integration" for list header button, empty state CTA, and form submit button.

### Create: Full Page

Use for complex resources with many fields or multi-step creation.

- Multi-step wizards
- Forms with 5+ fields

### Create: Full-Page Wizard

Use a full-page PatternFly Wizard (at a dedicated route) when:

- Flow has 2+ steps with independent data requirements
- Each step needs tables with filter, sort, and pagination (too large for a modal)
- UX prototype specifies a dedicated route

**Wizard step anatomy:**

```text
h2 step title
  → explanatory paragraph (with bolded target entity name)
  → compact FilterBar
  → ScrollableTableContainer (radio selection, sortable columns, pagination)
```

**Footer conventions:**

- Step 1: disabled Back, conditional Next, Cancel as `variant="link"` (not button)
- Final step: Back, primary action with loading state, Cancel link
- Cancel navigates back to origin route (not `onClose`)

**State management:**

- Going back clears current step's selection + filters
- Changing selection on step 1 resets step 2 selections
- `isVisitRequired` on wizard prevents skipping ahead

**Layout:** `SynPage` → `SynPageHeader` → `SynPanel isFullHeight hasNoPadding` → `Wizard height="100%"`

**Terminology alignment:** Action verb must be consistent across button text, loading state, toast, and error message (e.g., "Transfer identity" → "Transferring..." → "Identity transferred" → "Failed to transfer identity").

### Create: Modal

Use for simple resources with few fields.

- Simple resources (2–4 fields)
- Quick creation without leaving context
- Tags, labels, simple configurations

### Read/Detail: Full Page

Use for resources with rich information.

### Update/Edit: Full Page

Use for editing complex resources with many fields or multi-step creation.

- Multi-step wizards
- Forms with 5+ fields
- If the create form is full page

**Key behaviors:**

- Pre-populate all fields with existing values
- Track dirty state (unsaved changes)
- Warn on navigation with unsaved changes
- Show loading state while saving

### Update/Edit: Modal

Use for simple resources with few fields.

- Simple resources (2–4 fields)
- Quick creation without leaving context
- Tags, labels, simple configurations
- If the create form is a modal

### Update/Edit: Dedicated Edit Page (from Read-Only Tab)

Use when the edit experience is too complex for inline editing on a detail tab:

- Form has many editable rows + advanced sections + nested modals (e.g., create sub-resource)
- Flow includes external actions (e.g., test sign-in popup, group discovery)
- Save/Cancel toolbar with unsaved state tracking is needed
- Permission gating requires a full-page access-denied state

**Pattern:**

- Detail tab stays **read-only** with an "Edit [resource]" button navigating to the edit route
- Edit page at a dedicated route (e.g., `.../group-mapping/edit`)
- Page shell: `SynPage` → `SynPageHeader` with breadcrumbs + toolbar (Save primary + Cancel link)
- Permission check: `useCanI('update', 'resource')` → `EmptyStateAccessDenied` if denied
- Query params for entry mode variants: `?discover=1`, `?new=1`

### Update/Edit: Inline

Use for single-field quick edits.

- Renaming resources (when save happens elsewhere)
- Toggling settings — use PatternFly's [Switch Checked with Label component](http://patternfly.org/components/switch#checked-with-label)
  - Do not use `isReversed` on the PatternFly Switch. The default behavior — toggle on the left, label on the right — is the standard. `isReversed` flips them and should be avoided.
- Single-value changes

### View: Read-Only Detail Modal (from Kebab)

Use when users need to inspect structured data (JSON, policy definitions, configuration) without leaving the list page. Triggered from a kebab menu action (e.g., "View policy JSON").

| Element       | Specification                                                                                                                     |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Modal variant | Large — PatternFly's [Modal Sizes](https://www.patternfly.org/components/modal#modal-sizes); dense read-only content (e.g., JSON) needs the extra width |
| Title         | Descriptive label (e.g., "Policy definition")                                                                                     |
| Body          | Read-only content with PatternFly's [Clipboard Copy](https://www.patternfly.org/components/clipboard-copy) when copying is useful |
| Close button  | `variant="primary"` — the only action (no Cancel, no secondary)                                                                   |

### Confirmation Dialog — Three-Tier Severity Model

`NxConfirmationDialog` supports three escalation tiers. Each tier maps to a Storybook story with canonical copy examples.

| Tier                            | Story                        | When                                     | Title icon | Confirm button | Checkbox |
| ------------------------------- | ---------------------------- | ---------------------------------------- | ---------- | -------------- | -------- |
| **Default / Disable**           | `Disable`                    | Reversible state changes                 | None       | `primary`      | No       |
| **Danger**                      | `Danger`                     | Reversible but risky (remove / unassign) | Warning    | `danger`       | No       |
| **Destructive Acknowledgement** | `DestructiveAcknowledgement` | Permanent delete                         | Warning    | `danger`       | Required |

For canonical copy patterns per tier → see Storybook: `list-all-documentation → find "NxConfirmationDialog" → get-documentation("NxConfirmationDialog")`

### Delete: Destructive Confirmation Modal with Checkbox

**Always** use `NxConfirmationDialog` from `frontend/packages/syntara-ui/src/components/dialogs/NxConfirmationDialog.tsx` for delete actions. Never build modals from raw `Modal` + `ModalHeader` + `ModalBody` + `ModalFooter`.

There are three delete variants depending on what happens downstream when the resource is deleted.

#### Simple Delete

Use when deleting a standalone resource with no downstream effects (e.g., role, policy, group, user, identity provider).

| Element       | Specification                                                 |
| ------------- | ------------------------------------------------------------- |
| Component     | `NxConfirmationDialog` with `destructiveAcknowledgement` prop |
| Modal variant | Small (default)                                               |
| Action button | `confirmVariant="danger"`, `confirmLabel="Delete"`            |
| Cancel button | `variant="link"` (handled by NxConfirmationDialog)            |

For title, body copy, and checkbox label patterns → see Storybook `NxConfirmationDialog` → **DestructiveAcknowledgement** story.

#### Cascade Delete

Use when deleting the resource also permanently deletes other records (e.g., workflow → executions, tool provider → tools).

| Element       | Specification                                                                                                                                                                                            |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Component     | `NxConfirmationDialog` with `destructiveAcknowledgement` prop                                                                                                                                            |
| Modal variant | Small (default)                                                                                                                                                                                          |
| Title         | `"Delete [resource type]?"` with `titleIconVariant="warning"`                                                                                                                                            |
| Body          | `"The [resource] <strong>[name]</strong> will be deleted. This cannot be undone."`                                                                                                                       |
| Body 2        | `"Resources that will be deleted"` as a header, then one row per resource type each with its own [Badge](https://www.patternfly.org/components/badge/#read) count — e.g., "Executions [12]", "Tools [3]" |
| Checkbox      | `"I understand this [resource] and the resources shown above will be permanently deleted."` — Delete button stays disabled until checked                                                                 |
| Action button | `confirmVariant="danger"`, `confirmLabel="Delete"`                                                                                                                                                       |
| Cancel button | `variant="link"` (handled by NxConfirmationDialog)                                                                                                                                                       |

#### Ripple Effect Delete

Use when deleting the resource leaves other resources in a broken or invalid state without deleting them (e.g., credential → referencing workflows fail, project → credentials/workflows orphaned, workflow → parent workflows become invalid).

| Element       | Specification                                                                                                                                                                                                 |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Component     | `NxConfirmationDialog` with `destructiveAcknowledgement` prop                                                                                                                                                 |
| Modal variant | Small (default)                                                                                                                                                                                               |
| Title         | `"Delete [resource type]?"` with `titleIconVariant="warning"`                                                                                                                                                 |
| Body          | `"The [resource] <strong>[name]</strong> will be deleted. This cannot be undone."`                                                                                                                            |
| Body 2        | `"Resources that will be affected"` as a header, then one row per resource type each with its own [Badge](https://www.patternfly.org/components/badge/#read) count — e.g., "Workflows [2]", "Credentials [5]" |
| Checkbox      | `"I understand this [resource] and the resources shown above will be affected by this deletion."` — Delete button stays disabled until checked                                                                |
| Action button | `confirmVariant="danger"`, `confirmLabel="Delete"`                                                                                                                                                            |
| Cancel button | `variant="link"` (handled by NxConfirmationDialog)                                                                                                                                                            |

**When badge counts are unavailable:** Use a `Stack` layout with an introductory sentence (e.g., "This will immediately:") followed by PatternFly `List` / `ListItem` bullet points enumerating the downstream consequences. **Never use raw `<ul>`, `<ol>`, or `<li>`** — always use PF `List` / `ListItem` components (enforced by the `prefer-pf-list-components` ESLint rule).

**Shared dialog components:** Extract one shared confirmation dialog component per destructive action type (e.g., `IdentityProviderDeleteDialog`, `WorkflowDeleteDialog`) and consume it from both the list and detail views — single source of truth for copy and structure.

> **Note:** A resource can combine both cascade and ripple effects. For example, deleting a workflow both cascade-deletes its executions and ripple-affects parent workflows that reference it as a step. In this case, show both Body 2 sections.

**Surfacing usage/dependencies beyond the delete dialog:** For resources that can be referenced by others (e.g., a credential used by integrations), don't limit dependency visibility to the delete confirmation. Give the detail page a dedicated usage tab listing the referencing resources with a count (e.g., a "Integrations" tab on a credential's detail page), and degrade gracefully to a generic warning if the dependency check itself fails to load rather than blocking the destructive action entirely. This is broadly reusable across projects, credentials, integrations, and users — anywhere one resource can be "in use" by another.

**Post-delete behavior:**

- From list/table view → stay on list, item removed
- From details page → navigate back to list/table
- Show feedback → PatternFly's [Dismissible Success Toast Alert](https://www.patternfly.org/components/alert#alert-variations)

### Remove/Unassign/Cancel/Stop: Confirmation Modal without Checkbox

These are reversible actions. Use `NxConfirmationDialog` with warning icon but no checkbox.

| Element       | Specification                                                      |
| ------------- | ------------------------------------------------------------------ |
| Component     | `NxConfirmationDialog` (no `destructiveAcknowledgement`)           |
| Modal variant | Small (default)                                                    |
| Action button | `confirmVariant="danger"`, `confirmLabel="[Remove/Unassign/etc.]"` |
| Cancel button | `variant="link"` (handled by NxConfirmationDialog)                 |

For title and body copy patterns → see Storybook `NxConfirmationDialog` → **Danger** story.

**Post-cancel/stop behavior:**

- From list/table view → stay on list, item updated
- From details page → stay on details page
- Show feedback → PatternFly's [Dismissible Success Toast Alert](https://www.patternfly.org/components/alert#alert-variations)

### Scoped Destructive Actions (e.g., Token Revocation)

When the same destructive action exists at multiple scopes (global, user, resource), use escalating severity:

| Scope                      | Location           | Trigger                      | Confirmation depth                                                |
| -------------------------- | ------------------ | ---------------------------- | ----------------------------------------------------------------- |
| **Global** (platform-wide) | Dedicated page/tab | `variant="danger"` button    | `NxConfirmationDialog` + **destructive acknowledgement checkbox** |
| **User-scoped**            | Table kebab menu   | `RhUiBanIcon` + action label | Standard danger confirmation naming the user                      |
| **Resource-scoped**        | Table kebab menu   | Same icon/label              | Standard danger confirmation naming the resource                  |

- Global actions may trigger auto-logout (admin's own tokens invalidated)
- Scoped confirmations bold the affected entity name: `"All tokens for **{username}** will be revoked."`
- Global actions get a status card showing current state (e.g., "Last revoked: {date}") before the action button

### Disable: Standard Confirmation Modal

Disable is **not** a destructive action — use a standard confirmation modal (no warning icon, no danger button). **Enable does not require a confirmation dialog** — the toggle takes effect immediately. Only **disable** requires confirmation because it has user-facing consequences (e.g., users can no longer sign in via a disabled identity provider).

**Dependency warnings apply here too:** If the resource being disabled can be referenced by others (e.g., a credential used by integrations), inject the same kind of dependency warning used for Ripple Effect Delete into the disable confirmation body — naming the affected resources — rather than treating disable as a bare "are you sure?" prompt. See `CredentialIntegrationWarning` for the pattern.

| Element        | Specification                                                                                       |
| -------------- | --------------------------------------------------------------------------------------------------- |
| Modal variant  | Small — PatternFly's [Small Variant Modal](https://www.patternfly.org/components/modal#modal-sizes) |
| Confirm button | `variant="primary"`                                                                                 |
| Cancel button  | `variant="link"`                                                                                    |

For title and body copy patterns → see Storybook `NxConfirmationDialog` → **Disable** story.

**Post-disable behavior:**

- From list/table view → stay on list, item updated
- From details page → stay on details page
- Show feedback → PatternFly's [Dismissible Success Toast Alert](https://www.patternfly.org/components/alert#alert-variations)

### Integration Configuration Wizard

Integrations (e.g., tool providers) use a 3-step PatternFly Wizard for initial configuration:

**Wizard steps:**

1. **Select type** — radio or card selection for integration type
2. **Configure connection** — credentials, endpoint URL, authentication fields
3. **Review & confirm** — summary of configuration, "Test connection" button

**Post-creation detail page:**

- Header: integration name with enabled/disabled `Switch` toggle (inline, not modal-gated)
- "Test connection" secondary button in the detail header — must pass before enabling tools
- **Tools tab:** Table of available tools from the integration, each with an individual `Switch` to enable/disable
- Enable/disable the integration itself via the header Switch; enable/disable individual tools via per-row Switches
- All Switches follow standard PF behavior — toggle takes effect immediately, no confirmation for enable, standard confirmation for disable

### Access Management UX

Access Management uses consistent terminology and navigation:

- **Tab label:** "Check access" (not "Can I") — verb-first label for the self-service permission-checking tab
- **Self-service flows** (Check access, My tokens) are moved to the **My Profile** page, not Access Management
- Access Management contains only admin-level tabs: Users, Groups, Projects, Roles, Policies, Assignments

### My Profile Page

The My Profile page (`/my-profile`) reuses the existing `UserDetail` component with an `isMyProfile` flag:

- **No breadcrumbs** — this is a top-level self-service route, not a child of Access Management
- **Route:** `/my-profile` (not `/access-management/users/:id`)
- **Reuse:** Same `UserDetail` component renders both the admin user detail view and the self-service My Profile view
- **Extra tabs** (only on My Profile): "My tokens", "Check access"
- **Nav entry:** Accessible from user avatar menu in the masthead, not from the side navigation

---

## 7. Modals

Modal size is chosen by content, not a single fixed default — pick the [variant](https://www.patternfly.org/components/modal#modal-sizes) that matches what the modal actually contains:

| Variant    | When to use                                                                                                  | Examples                                                                                        |
| ---------- | ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| **Small**  | Confirmation dialogs (`NxConfirmationDialog` defaults to `small` — see §6) and single-purpose forms with ~1–3 fields | Publish workflow, edit version name/description, assign a single role, import workflow           |
| **Medium** | The default for most create/edit forms — typeahead/multi-select fields, dynamic schema-driven forms, JSON editors used for input. This is the right starting point for a new create/edit modal, not Small. | Create/edit credential, create/edit project, assign roles, add member, run workflow (mock input) |
| **Large**  | Read-only dense content or review panels with substantial body content                                       | View JSON/policy definition, expanded code block, run-step mock data editor, approval review     |

- Delete modals should use PatternFly's [Title Icon Modal component](https://www.patternfly.org/components/modal#title-icon)
- **Buttons:**
  - Left-aligned in the modal
  - Primary action on the far left, then secondary, then tertiary
  - If there is a primary action and a cancel, the cancel should be a link button (`variant="link"`)
  - This applies to all modals, including delete confirmations

### Non-Dismissible Modal

Some modals must not be closable via the header X button or the Escape key — the user must resolve them through an explicit in-modal action. Two established use cases:

- **Security-critical time-based warnings** (e.g., Session Timeout Warning, see §9) — pass empty/undefined `onClose`/`onEscapePress` handlers so the modal can't be dismissed except by choosing one of its explicit actions.
- **One-time secret reveal** (e.g., a newly generated service-account credential) — omit the header close button and Escape handling entirely so the secret can't be dismissed before the user has copied it, and disable the eventual "Close" button until the user checks an explicit "I have saved the new secret" acknowledgment.

Both achieve the same outcome (no X button, no Escape dismissal) — omit `onClose` from `Modal` entirely, rather than passing a no-op, so PatternFly doesn't render the close button at all.

### Unsaved-Changes Confirmation Modal

When a user attempts to navigate away from a form or builder with unsaved changes, show a confirmation modal with three actions:

| Position | Button              | Variant     |
| -------- | ------------------- | ----------- |
| Left     | Save [resource]     | `primary`   |
| Middle   | Exit without saving | `secondary` |
| Right    | Cancel              | `link`      |

- **Modal variant:** Medium — three buttons plus explanatory body copy need more width than Small
- Use specific action labels: `"Save workflow"` instead of generic `"Save"` when the resource type matters
- Cancel dismisses the modal and returns the user to their current context without saving or discarding

---

## 8. Buttons

- Use sentence case for all button labels
- **Primary buttons** (in UI and dropdown menu items): `Icon + Action + Resource` — e.g., "Create project"
- **Secondary / tertiary / link buttons**: `Action + Resource` — e.g., "Edit project" (no icon required)
- When multiple buttons appear together, primary comes first then secondary — unless PatternFly specifies otherwise (e.g., wizards)
- Delete should always use `variant="danger"` and must always be the last item in a dropdown menu, separated by a divider
- **Only one primary button per header toolbar at a time:** A header toolbar must never render two `variant="primary"` buttons simultaneously, even when one is conditionally shown. When a conditional primary action can appear alongside another button that's normally primary, demote the other button to `variant="secondary"` whenever the conditional action is present — e.g., on the execution detail page, "Back to editor" drops from primary to secondary whenever a "Review approval" primary action strip is also shown. This is distinct from the empty-state/page-header CTA deduplication rule in §4 — it applies within a single toolbar.
- **Login button text:** Always "Log in" — never role-specific (e.g., not "Log in as administrator"). Non-admin users can log in locally; role assumptions in button text are misleading.
- **Login page never allows password reveal:** The login form's password field must always render masked, with no show/hide toggle — do not set PatternFly `LoginForm`'s `isShowPasswordEnabled` prop, even though PatternFly supports it as a general-purpose convenience. This is a deliberate security decision, not an oversight; it's easy to "helpfully" re-add the prop believing it's a UX nicety, so treat any PR adding it back as a regression.

---

## 9. Feedback & Notifications

### Success Feedback

- Use PatternFly's [Dismissible Success Toast Alert component](https://www.patternfly.org/components/alert#alert-variations) for success messages after create, update, delete, and other actions
- Toast alerts should auto-dismiss after a reasonable duration
- Message format: Title in sentence case, past tense — `"[Resource type] [past-tense action]"` (e.g., "Role created"). Description includes entity name — `"The role {name} has been created successfully."`
- **Verb consistency:** Toast copy must match the triggering action's verb. If the button says "Create role", the toast says "Role created" — not "Role added". Error toast titles mirror the action verb: `"Failed to create role"`

**When NOT to show a success toast:**

Success toasts are **not required** when the UI already communicates the outcome through other means:

| Scenario                          | Why toast is redundant                              |
| --------------------------------- | --------------------------------------------------- |
| Inline control state change       | `Switch` toggle updates visibly after refetch       |
| Navigation confirms the action    | Starting a run → navigates to execution view        |
| Dirty/saved state reflected in UI | Save button disables; tooltip shows last-saved time |
| Bulk status change                | Table rows update visibly after refetch             |

- **Error toasts are always retained** regardless — errors must always be surfaced
- **Create actions** still show a success toast (the new resource may not be immediately visible)
- Special-case alerts kept when they carry essential context (e.g., admin disable → sign-out warning message)

### Async / Background Status Changes

Any async or background status change (e.g., a canvas-visible resource transitioning to a failed state while the user is elsewhere on the page) should be routed through the shared global toast system (`useAlerts()`), not a bespoke, hand-rolled overlay — no custom absolutely-positioned `Alert`, manual dismiss state, or z-index/`pointerEvents` hacks layered on top of other content. The toast system already handles stacking, dismissal, and positioning correctly.

**Persistent warning toast for partial-success outcomes:** Not every async outcome is a clean success or failure — "succeeded, but with a caveat" needs its own treatment. When an action succeeds but a dependent, non-fatal step fails (e.g., publishing a workflow succeeds but syncing its schedule fails), show a warning-variant toast with `autoDismiss: false` instead of the normal auto-dismissing success toast, since the user needs to actually notice it and follow up rather than have it disappear unread.

**Polling as a lighter alternative to WebSocket streaming:** For list pages where server-side status can change without a sub-second latency requirement (e.g., an integration's health status), prefer `refetchInterval` (e.g., 30 seconds) over standing up a full WebSocket subscription. Reserve WebSocket/streaming for cases that genuinely need near-real-time updates (e.g., live execution logs).

### Error Feedback

- For page-level data loading errors, use `useQueryState(query, { title: '...', onRetry: ... })` — this hooks up the `NxErrorState` component with a retry button automatically for retryable (5xx) errors
- For mutation errors (create/update/delete), use `useMutationErrorHandler` — this wires up `NxErrorState` and toast alerts automatically
- For form validation errors, use inline field-level errors via PatternFly's Validated component (see Form Component section)
- **Error state placement:** Error states render **inside `SynPanel`** using `SynPageBody isCentered` + `NxErrorState` — not as a bare centered message outside the content frame. The page header and app shell remain visible so the user can navigate away.

### Session Timeout Warning

For security-critical time-based warnings, use a non-dismissible alert dialog pattern:

- PatternFly `Modal` with `variant="small"`, `role="alertdialog"`, `titleIconVariant="warning"`
- **Non-dismissible:** `onClose={undefined}`, empty `onEscapePress` — user must explicitly choose
- **Live countdown:** Body text with `aria-live="assertive"` + `aria-atomic="true"` for screen reader updates
- **Actions:** Primary "Continue session" (`variant="primary"`) + "Log out" (`variant="link"`)
- **Centralized constants:** All timing thresholds in a constants file with JSDoc — no inline magic numbers
- **Idle detection:** Activity-based via refs (no re-renders on `mousemove`), passive event listeners, visibility API integration
- **Post-expiry:** Preserve return path (relative path only, validated against application routes) in sessionStorage before logout redirect to prevent open redirect attacks

### Loading States

- Show PatternFly's [Spinner component](https://www.patternfly.org/components/spinner) during async operations
- For page-level loading, use a centered spinner in the content area
- For button actions (save, submit), show a loading spinner on the button and disable it during the operation
- For tables, show a skeleton or spinner in the content area while data loads

---

## 10. Bulk Actions

### Table with Selection Checkboxes

- Use PatternFly's [Selectable with Checkbox Table component](https://www.patternfly.org/components/table#selectable-with-checkbox)
- If the table is expandable, column order left to right: expand/collapse chevron → checkbox → table columns
- Bulk actions are found in the kebab menu in the toolbar, to the right of the primary button
- If applicable, delete/remove option is always last
- Will have a bulk action confirmation modal

### Exception: Header Toolbar Bulk Actions (Approvals)

For high-frequency bulk decisions where speed matters (e.g., Approvals), bulk actions may use **direct header toolbar buttons** instead of the kebab menu. This is an exception to the standard kebab-based bulk action pattern.

**Selection model:**

- Checkbox column on **actionable rows only** (e.g., pending approvals); decided/completed rows render no checkbox
- Checkboxes disabled when user lacks the required permission on that row's project (permission-gated via `/authz/what-can-i`)
- **Selection persists across pagination**; **clears on filter or sort change**
- Header "select all" selects only selectable rows on the current page

**Bulk action toolbar:**

- Lives in the `SynPageHeader` toolbar — always visible, not inside a kebab
- Shows `"{n} selected"` when selection > 0
- **Approve:** secondary button + `RhUiLikeIcon`
- **Reject:** secondary `isDanger` button + `RhUiDislikeIcon`
- Buttons disabled with tooltip when nothing selected: `"At least one [item] needs to be selected to take action"`

**Approve vs. Reject modal differentiation:**

| Modal   | Note field   | Confirm button              | Icon              |
| ------- | ------------ | --------------------------- | ----------------- |
| Approve | Optional     | Primary "Approve"           | —                 |
| Reject  | **Required** | `variant="danger"` "Reject" | `RhUiDislikeIcon` |

- Both modals are medium-sized with `maxLength={1000}` on the note textarea
- Cancel closes dialog but **preserves selection**; reopening resets note fields

---

## 11. Statuses and Labels

Use `Label` only when visual distinction is needed — for statuses, categorical metadata where users need to differentiate between types at a glance (e.g., User vs. Group), and user-authored tags. For informational text that doesn't require visual emphasis, use plain text.

### Component Selection

| Content type                                                                          | Component                                           | Visual treatment            |
| -------------------------------------------------------------------------------------- | ---------------------------------------------------- | ---------------------------- |
| Live status of a monitored entity (execution, activity, approval, integration health) | `NxLabel variant="outline"` with `status` + icon     | Outlined with status color   |
| Categorical metadata (System, Project, Built-in)                                      | `NxLabel` with `color`                              | Filled                        |
| Counts, callouts (single-value, no type distinction)                                  | `NxLabel color="grey"`                              | Filled grey                   |
| Informational context (e.g., "Test run", "Default")                                  | `NxLabel color="purple"` or `color="blue"`          | Filled colored                 |
| User-authored tags, workflow tags                                                     | `NxUserTag`                                         | Outlined compact                |
| Filter chips (active filters)                                                        | `Label variant="outline" isCompact` in `LabelGroup` | Outlined compact, removable      |

**`NxLabel`** (from `frontend/packages/syntara-ui/src/components/labels/NxLabel.tsx`) — thin wrapper over PF `Label` with UX defaults: `isCompact={true}`, `variant="filled"`. Never use PF `Label` directly.

**`NxUserTag`** (from `frontend/packages/syntara-ui/src/components/labels/NxUserTag.tsx`) — outline-only wrapper for user-authored content. Always use for content typed by users (workflow tags, custom labels).

### Filled vs. Outline — When to Use Each Variant

The distinguishing axis is **"live status of a monitored entity" vs. "fixed categorical/contextual metadata,"** not how often the value happens to change:

| Variant                           | When to use                                                                                                                              | Examples                                      |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| **Outline** (`variant="outline"`) | The label reports the current condition of a monitored entity — a process, resource, or decision whose state is determined by the system | Execution status (Running, Completed, Failed), activity status (Pending, Retrying), approval decisions (Approved, Rejected), "Pending approval" badge, integration health (Available, Error, Validating) |
| **Filled** (default)              | The label classifies a resource into a fixed category, or conveys single-value contextual info                                          | Version status (Published, Draft), role type (Built-in, Custom), scope (System, Project), counts, informational badges (Test run, Default) |

**Rule of thumb:** If the label is reporting the *live health/state of an entity* (an execution's progress, an integration's connectivity, an approval's decision) — regardless of how often that state actually changes — use **outline**. If the label is classifying *what kind of thing this is* (a role is built-in, a version is a draft) or conveying a one-off contextual fact (a count, "Test run"), use **filled**.

This mirrors common status-indicator conventions in comparable products (CI/CD pipeline status, service health badges): a single, consistent treatment is used for "current condition of a monitored entity" everywhere it appears, rather than varying by how volatile the state happens to be. A lighter outline treatment for statuses that repeat down a table column (executions list, integrations list) also keeps dense lists scannable — reserve heavier filled/saturated labels for lower-frequency categorical or single-value badges to avoid visual fatigue.

### Building Domain Status Labels

All domain status labels follow a consistent implementation pattern — a status-to-variant map, a status-to-icon map, and a thin component:

```tsx
const statusMap: Record<MyStatus, 'success' | 'danger' | 'warning' | 'info' | 'custom'> = {
  completed: 'success',
  failed: 'danger',
  running: 'custom',
}

const statusIcons: Record<MyStatus, React.ComponentType> = {
  completed: RhUiCheckCircleIcon,
  failed: RhUiCloseCircleIcon,
  running: RhUiSyncIcon,
}

export function MyStatusLabel({ status }: Readonly<{ status: MyStatus }>) {
  const Icon = statusIcons[status]
  return (
    <NxLabel variant="outline" status={statusMap[status]} icon={<Icon />}>
      {displayLabels[status]}
    </NxLabel>
  )
}
```

Keep display labels in a separate constants file (e.g., `executionStatusConstants.ts`) to decouple display text from the component. Use `Record<Status, string>` for display labels rather than string manipulation like `charAt(0).toUpperCase() + slice(1)`.

### General Label Rules

- If labels on a table reference a resource, make them clickable labels, navigating to the details page of the resource if one exists
- Use outline (unfilled) `RhUi*Icon` variants when passing icons to `NxLabel`
- If a label is used for a single thing (a count, a callout) and not to distinguish between 2+ types, use a filled gray label (`color="grey"`)

#### System-generated labels

- Use `NxLabel` (defaults to filled, compact) and default to gray
- If used to categorize types (e.g., User vs. Group), use a colored variant
- Color variants should have enough contrast to distinguish between them

#### Filter labels

- Use PatternFly's gray Filled Non-status Label component

#### User-generated labels

- Use `NxUserTag` (outlined, compact) for any user-entered values (tags, custom names in filter chips)

#### Label colors

**General**

- If a label is used for a single thing (a count, a callout) and not to distinguish between 2+ different types, use a filled gray label

**Workflow versioning**

| State               | Style         |
| ------------------- | ------------- |
| Published           | Filled green  |
| Unpublished changes | Filled yellow |
| Draft               | Filled gray   |

**Workflow builder**

| Context              | Style          |
| -------------------- | -------------- |
| Test run badge       | Filled purple  |
| Viewing version date | Filled grey    |

**Integrations**

| Context           | Style        |
| ----------------- | ------------ |
| Default model     | Filled blue  |

**Access Management — Assignments**

| Dimension       | Value            | Style         |
| --------------- | ---------------- | ------------- |
| Type            | User             | Filled teal   |
| Type            | Group            | Filled orange |
| Type            | Service Account  | Filled purple |
| Scope           | System           | Filled blue   |
| Scope           | Project          | Filled green  |
| Role name       | *(any)*          | Plain text (`Truncate`) — not a label |
| Policy names    | *(any)*          | Filled grey   |

**Assignment table columns**

- **Principal Type** — `NxLabel` with color from `principalTypeDisplay` in `routes/access-management/RoleAssignmentTypes.ts` (single source of truth for Assignments and Project Role Assignments tabs).
- **Role Name** — `<Truncate content={roleName} />`. Role names are identifiers, not categorical metadata; do not use colored labels (e.g., purple) for this column.
- **Scope** — filled label per the Scope row above (`ScopeLabel` / `SCOPE_DISPLAY` in `routes/access/ScopeLabel.tsx`: System=blue, Project=green).
- **Policies** — default grey filled `NxLabel` when shown as a chip group.

Principal type and scope are **different dimensions** — use colors from their respective rows in this table.

**Access Management — Roles**

| Value    | Style       |
| -------- | ----------- |
| Built-in | Filled gray |
| Custom   | Filled blue |
| Policy   | Filled gray |

**Access Management — Policies**

| Value            | Style        |
| ---------------- | ------------ |
| Built-in         | Filled gray  |
| Statement: Allow | Filled green |
| Statement: Deny  | Filled red   |
| Scope & resource | Filled gray  |

**Counts and grouping**

| Context              | Style       |
| -------------------- | ----------- |
| Single-value callout | Filled grey |

Do **not** show per-group item count badges on project group headers in All projects views — row counts are misleading when groups are paginated or filtered (see AAP-85112).

### Grace-Period / Time-Remaining Indicator

For a status that is actively counting down to expiry (e.g., a credential secret in a rotation grace period), pair an outline info-status label with a clock icon and remaining time in the label text (e.g., "Rotating — {remaining} left") in its own dedicated table column — not the actions column — with a tooltip giving the exact expiry timestamp and a secondary small-text expiry line. If the corresponding action offers a grace-period selector (e.g., a rotate dialog), warn the user if the action would overwrite an already-active grace period rather than silently replacing it.

### Deleted-Entity Reference Indicator

When a table or detail view references a related resource that has since been soft-deleted (e.g., a service account's owning project), don't render it as a dead link. Show it as plain text (a link would point at nothing) plus a grey "Deleted" label wrapped in a tooltip explaining what happened. Apply this consistently in both list and detail views for the same resource — don't handle it differently depending on where the reference appears.

---

## 12. Icons

All icons **must** use the `RhUi` prefix. Examples: `RhUiAddIcon`, `RhUiEditIcon`, `RhUiTrashIcon`, `RhUiHistoryIcon`, `RhUiKeyIcon`, `RhUiPublishIcon`, `RhUiDuplicateIcon`.

**Do not use** legacy PatternFly icon names (e.g., `PlusCircleIcon`, `PencilAltIcon`, `TrashIcon`). These are the old standard. The `RhUi*` icons are enforced via an ESLint `no-restricted-imports` rule that blocks non-`RhUi` icon imports on action buttons.

> **Exception:** PatternFly empty state icons (`PlusCircleIcon`, `SearchIcon`, `ExclamationCircleIcon`, `LockIcon`, `WrenchIcon`, `CheckCircleIcon`, `RocketIcon`) are still used in `EmptyState` components because they are part of the PF empty state pattern, not action buttons.

---

## 13. Expand/Collapse Chevrons

- Use PatternFly's [Expandable Table component](https://www.patternfly.org/components/table#expandable) to ensure expand/collapse chevrons are correct

---

## 14. Content Rules

- Use **sentence case** by default across the application
- Use **title case** only for navigation items and page titles
- **User-generated strings** are displayed exactly as the user entered them — do not transform casing
- **Alert titles** (`showSuccess`, `showError`, `showWarning`, `showInfo`) must use sentence case — e.g., "Workflow created successfully", not "Workflow Created Successfully"

### No Raw HTML for Text Content

Never use raw `<span>`, `<p>`, or `<div>` for text content. Use PatternFly typography components instead — they pick up design tokens for font size, color, and spacing automatically and stay theme-compatible.

| Scenario                           | Use                                                                                        |
| ---------------------------------- | ------------------------------------------------------------------------------------------ |
| Body text, helper text, muted text | [`Content`](https://www.patternfly.org/components/content) with `ContentVariants`          |
| Form field hints                   | [`HelperText`](https://www.patternfly.org/components/forms/helper-text) / `HelperTextItem` |
| Inline status                      | [`Label`](https://www.patternfly.org/components/label)                                     |
| Empty state descriptions           | `EmptyStateBody`                                                                           |
| Headings                           | [`Title`](https://www.patternfly.org/components/title) or semantic `<h1>`–`<h6>`           |

```tsx
// ❌ BAD
<span style={{ fontSize: '12px', color: 'gray' }}>Type to refine results</span>

// ✅ GOOD
<Content component={ContentVariants.small}>Type to refine results</Content>
```

---

## 15. Role-Based UI States & Permission Gating

Pages that support role-based access must adapt their UI based on the authenticated user's permissions. The platform uses a layered gating strategy with shared infrastructure.

### Permission Tiers

| Permission Level         | Navigation             | Controls                               | Actions                               |
| ------------------------ | ---------------------- | -------------------------------------- | ------------------------------------- |
| **No read permission**   | Hidden from navigation | `EmptyStateAccessDenied` on direct URL | None                                  |
| **Read only** (auditor)  | Visible in navigation  | All controls rendered as **read-only** | Action buttons disabled with tooltips |
| **Read + write** (admin) | Visible in navigation  | All controls editable                  | Full CRUD actions available           |

### Permission Hook Pattern

Every domain creates a `use{Domain}Permissions()` hook that encapsulates all permission checks:

```tsx
// Return type pattern
type WorkflowPermissions = {
  canCreate: boolean
  canUpdate: boolean
  canDelete: boolean
  canRun: boolean
  isLoading: boolean
  tooltips: {
    create: string
    update: string
    delete: string
    run: string
  }
}
```

**Naming conventions:**

- List/page actions: `use{Entity}Permissions()` (e.g., `useWorkflowPermissions`, `useUserPermissions`)
- Detail page tabs: `use{Entity}DetailPermissions()` (e.g., `useUserDetailPermissions`)
- Specialized domains: `useBuilderPermissions(isNew)`, `useSettingsPermissions()`

**Implementation rules:**

- Use `useCanI(action, resourceType)` for individual checks
- Default to **deny** while `isLoading` (safe-false principle — prevents flash of unauthorized content)
- Build tooltip text via `permissionTooltip(actionDescription, policyName)` for consistent messaging
- Always use `isAriaDisabled` (not `isDisabled`) on gated buttons — keeps elements focusable for tooltip hover and screen readers
- Set `onClick` to `undefined` when permission denied (defense in depth)

### Gating Strategy Decision Tree

```text
Can user read this section?
├─ No → Hide nav item / tab OR show EmptyStateAccessDenied (if direct URL)
└─ Yes → Can user perform action?
    ├─ No, action is primary CTA in empty state → Hide button (pass undefined callback)
    ├─ No, action is toolbar/button → Disable with isAriaDisabled + DisabledWithTooltip
    ├─ No, action is row/kebab item → isAriaDisabled + tooltipProps, onClick undefined
    ├─ No, action is form field → readOnly prop / hide save toolbar
    └─ No, action is create/edit route → ProtectedRoute → EmptyStateAccessDenied
```

### Navigation Gating

- Nav items declare `requiredPermissions` (OR logic — visible if **any** granted)
- `useFilteredNavigationItems()` batch-checks all permissions and filters the tree
- Parent sections auto-hide when all children are filtered out
- Hidden routes (create/edit forms) use `routePermission` + `ProtectedRoute` for direct-URL access

### Tab Gating

- Hub pages (Access Management): filter tab array by permission; redirect to first visible tab
- Detail pages: use `NxUrlTabs validTabs={visibleTabs}` to hide unauthorized tabs
- **Loading stability:** Hide permission-gated tabs until permissions resolve (see "Hide-Until-Confirmed" below). Never show gated tabs during loading -- a brief absence is less disruptive than a flash of unauthorized content.
- **Self-permission override:** Users viewing their own profile always see their Groups/Identities/Assignments tabs

### Action Gating

**Toolbar buttons — `DisabledWithTooltip` wrapper:**

```tsx
<DisabledWithTooltip isDisabled={!permissions.canCreate} content={permissions.tooltips.create}>
  <Button
    variant="primary"
    isAriaDisabled={!permissions.canCreate}
    onClick={permissions.canCreate ? handleCreate : undefined}
  >
    Create user
  </Button>
</DisabledWithTooltip>
```

**`DisabledWithTooltip` isn't RBAC-only — reuse it for business quota/limit gating too:** The same disabled-with-explanatory-tooltip mechanism applies whenever an action is blocked by a non-permission business rule, not just insufficient permissions. For example, "Create credential" is disabled with a tooltip once a service account hits its max-credentials quota, with the limit sourced from the API response rather than hardcoded. Treat "the user is allowed to do this, but a quota/limit currently blocks it" as a second, distinct reason to reach for `DisabledWithTooltip` — the component and pattern are identical; only the condition and tooltip copy change.

**Row actions — `isAriaDisabled` + `tooltipProps`:**

```tsx
{
  title: <IconLabel icon={<RhUiEditFillIcon />}>Edit</IconLabel>,
  isAriaDisabled: !permissions.canUpdate,
  tooltipProps: permissions.canUpdate ? undefined : { content: permissions.tooltips.update },
  onClick: permissions.canUpdate ? () => navigate(...) : undefined,
}
```

**Empty state CTA — hide button entirely:**

```tsx
onCreateWorkflow={permissions.canCreate ? handler : undefined}
// NxEmptyStateNoData only renders button when addData callback is defined
```

### Read-Only Mode (Builder)

When a user can view but not edit a workflow:

1. **Info banner** — `Alert variant="info" isInline` explaining read-only mode
2. **Hide editing affordances** — Add Node panel hidden, toolbar actions disabled
3. **Canvas lockdown** — `nodesDraggable={false}`, `nodesConnectable={false}`, `deleteKeyCode={null}`
4. **Toolbar actions** — Save/Publish disabled via `DisabledWithTooltip`; Run has its own `canRun` check

### Permission Tooltip Message Format

Standard format via `permissionTooltip()`:

> "To {action}, you need a role with the {policy} policy. Contact your Admin to request access."

### Route Guards (`ProtectedRoute`)

For create/edit forms accessible via direct URL:

1. `isChecking` → `NxLoadingState`
2. `isError` → `NxErrorState title="Unable to verify permissions"`
3. `!allowed` → `EmptyStateAccessDenied`
4. `allowed` → render children

**Note:** List/detail pages use in-page empty states or tab filtering -- not route guards. Route guards target mutation form routes only.

See [`frontend/docs/permissions-rbac.md`](frontend/docs/permissions-rbac.md) for the full permission gating architecture.

### Empty-State Actions Must Be Permission-Gated

When a list page shows an empty state with a CTA (e.g., "Create credential"), that button must respect the same permission check as the toolbar button it replaces. Otherwise, unauthorized users see and can click the empty-state CTA, only to hit an auth error in the modal or form.

```typescript
// ❌ BAD -- toolbar is gated but empty-state bypasses permissions
<NxEmptyStateNoData addData={() => setAddModalOpen(true)} />

// ✅ GOOD -- pass undefined to hide the CTA when unauthorized
<NxEmptyStateNoData addData={permissions.canCreate ? () => setAddModalOpen(true) : undefined} />
```

Apply this pattern to every component that accepts an `addData` or action callback prop for empty states: `NxEmptyStateNoData`, custom empty states, and `EmptyState` with action buttons.

**The same permission-aware branching applies inline, inside an open form** — not just at the page-empty-state level. When a form field's usefulness depends on another resource existing (e.g., an AI Agent node's "Tools" field is only useful once an MCP integration exists), and no such resource exists yet, show a disabled placeholder plus helper text that includes an actionable link to create one **only if** the current user has permission to create that resource; otherwise show plain, non-actionable helper text. Don't render an actionable link the user can't actually follow through on.

### Hide-Until-Confirmed for Gated UI During Loading

When permissions are loading asynchronously, **hide** permission-gated UI elements (tabs, action buttons, toggle switches) until the permission check resolves. Showing them during the loading window and then removing them causes a flash of unauthorized content that confuses users and can trigger unintended interactions.

```typescript
// ❌ BAD -- tab visible during loading, removed after permission check
const tabs = [
  { title: 'Details', content: <Details /> },
  { title: 'Workflows', content: <Workflows /> },  // always shown, then yanked
]

// ✅ GOOD -- tab only appears after permissions confirm access
const tabs = [
  { title: 'Details', content: <Details /> },
  ...(permissionsLoading ? [] : permissions.canViewWorkflows
    ? [{ title: 'Workflows', content: <Workflows /> }]
    : []),
]
```

**General rule:** When in doubt, prefer "hide until confirmed" over "show until denied." A brief absence during loading is far less disruptive than a visible element that disappears after a permission check.

### Breadcrumbs Must Not Link to Inaccessible Routes

When a user reaches a detail page through a permitted route (e.g., `/users/:userId` via self-read), breadcrumb segments must not link to parent routes the user cannot access (e.g., the "Users" list under Access Management). A breadcrumb that navigates to a forbidden page is worse than no breadcrumb.

- If the user lacks permission for a parent route, either hide the breadcrumb entirely or render it as non-link text
- Consider whether the page needs a dedicated route outside the restricted section (e.g., `/my-profile` instead of nesting under `/access-management/users/:userId`)

---

## 16. Data Panel View Modes

For panels that display structured data (input/output panels in the workflow builder), provide a view toggle:

| View       | Use case                                        | Component                |
| ---------- | ----------------------------------------------- | ------------------------ |
| **Schema** | Tree view showing data shape with type labels   | `TreeView` (read-only)   |
| **Table**  | Tabular view with column headers from data keys | `DataTableView` (shared) |
| **JSON**   | Formatted JSON with search                      | `CodeEditor` (read-only) |

- Use a shared `ViewToggle` component with `ToggleGroup` for switching between views
- Use `isCompact` on the `ToggleGroup` in constrained panel contexts (e.g., builder data panels) to reduce vertical/horizontal footprint
- Show the toggle **only when data exists** — hide it and show an empty state when no data is available
- Default view may differ by context (e.g., JSON for output panels, Schema for input panels)
- Output panels are **read-only** (no drag-and-drop); input panels may support drag-and-drop from schema fields

---

## 17. Workflow Builder

The automation builder experience is based on [React Flow](https://reactflow.dev/) as the underlying graph/canvas foundation, with PatternFly as the visual wrapper. The canvas is built **left to right**.

### Builder Toolbar Action Hierarchy

Primary actions are always visible in the toolbar; secondary actions and views live in a grouped kebab menu.

**Always-visible primary actions (left to right):**

- Add step
- Run (or Run dropdown for multi-trigger)
- Save
- Publish workflow

**Kebab menu (⋮) — grouped with `DropdownGroup`:**

| Group       | Items                                                                                               |
| ----------- | --------------------------------------------------------------------------------------------------- |
| **Views**   | Run history, Workflow details                                                                       |
| **Actions** | Verify workflow, Duplicate workflow, Export workflow, Import workflow, Delete workflow (`isDanger`) |

- Every kebab item has an icon + label (e.g., `RhUiHistoryIcon` + "Run history")
- Delete is always the last item in the kebab and uses `isDanger`
- Header element order: workflow name → edit-details pencil icon → project selector

### Workflow Publish Lifecycle

Workflows use a **Draft → Publish → Unpublish** model instead of enable/disable toggles.

**Builder toolbar:**

- **Save** — persists draft changes; `isAriaDisabled` when `!isDirty` for existing workflows (see Save Behavior below)
- **Publish workflow** — primary button with `RhUiPublishIcon`; promotes the current draft to a named version
- **Unpublish workflow** — kebab action (only when `publishedVersion != null`)

**Status badges (`WorkflowPublishStatusBadge`):**

| State                            | Label               | Style                              |
| -------------------------------- | -------------------- | ---------------------------------- |
| Never published                  | Draft               | Grey filled                        |
| Current version = published      | Published           | Green filled (`status="success"`)  |
| Saved changes after last publish | Unpublished changes | Yellow filled (`status="warning"`) |

These badges use `Label` with no icons — text and color only.

**Publish dialog (`PublishWorkflowDialog`):**

- Small modal, title "Publish workflow?"
- Body explains: overrides prior publish, triggers activate, run history retained
- **Required** version name (defaults to current date/time via `date-fns` `PPp` format)
- **Optional** description ("Describe what changed")
- Primary **Publish** + link **Cancel**

**Unpublish confirmation:**

- `NxConfirmationDialog` with warning icon, `confirmVariant="danger"`, label "Unpublish"
- Body explains workflow will no longer be executable until republished

**Workflow list changes:**

- Status column shows badges (Draft / Published / Unpublished changes) — no inline Switch toggle
- Kebab actions: Publish workflow / Unpublish workflow (conditional on published state)

### Save Behavior

- **Existing workflows:** Save button is `isAriaDisabled` when `!isDirty` (no unsaved changes)
- **New workflows:** Save stays enabled (validation runs on click)
- **Loading:** "Saving…" + spinner via mutation `isPending`
- **Tooltip:** Shows `"Last saved {formatted datetime}"` when previously saved; `"Save workflow"` when never saved
- **Toast policy:** Success toast on **create** (new workflow); **no toast** on update (dirty state clearing + tooltip timestamp are sufficient)

### Step Interactions

| Interaction            | Result                                                                                                 |
| ---------------------- | ------------------------------------------------------------------------------------------------------ |
| Single click on a step | Select the step, expand/collapse step                                                                  |
| Double click on a step | Opens panel view with Input and Output information (also via "View step details" from step kebab menu) |
| Right click on a step  | Same as clicking the kebab menu — opens the menu items                                                 |

### View-Only Views

- Run view
- Run history
- Version history

### Version History Panel

The version history side panel lets users browse, compare, and manage published workflow versions.

- **Trigger:** Kebab menu → "Version history" (under Views group)
- **Layout:** Right-side `SynPanel isFullHeight` with `SidePanelHeader` titled "Version history"
- **Version list:** PatternFly `SimpleList` grouped by date headers (e.g., "Jun 25, 2026")
  - Each item shows: version name, publish timestamp
  - Clicking a version loads a **read-only** view of that version on the canvas
- **Status badges per version:**
  - **Published** (`status="success"`, green label) — currently active version
  - **Draft** (grey label) — unpublished working copy
- **Kebab actions per version:** Restore, Export, Publish (contextual based on version state)
- **Mutual exclusivity:** History panel, approval panel, and add-step panel cannot be open simultaneously — opening one closes the others
- **Read-only mode:** When viewing a historical version, the canvas is non-editable — toolbar save/publish buttons are disabled, node interactions are view-only
- **Row layout:** Pin the row kebab to a fixed position (`flex-shrink: 0`) so it doesn't shift when variable-length status badges wrap onto a separate line below it. Use `PaginationFooter` (see Table Component in §3) under the `SimpleList` once the version count can exceed a page — it isn't table-only.

### Add Step

- Opens "Add step" side panel and auto-adjusts the canvas view
- Via "Add step" action from canvas toolbar
- Clicking `+` on the connector line after a step adds a new connected step
- Clicking `+` on the connector line between two steps inserts a new step in between
- **Empty workflow onboarding:** When a workflow has no triggers and no steps (`hasNoWorkflowNodes`):
  - The "Add step" toolbar button is **hidden entirely** (not disabled — hidden) to prevent confusion when the user should be selecting a trigger first
  - The add-step side panel is **forced open** automatically (showing trigger options)
  - The toolbar returns `null` when `!canEdit && hasNoWorkflowNodes && isNew` (brand-new workflow with no permission and no steps)
  - Once the user adds their first trigger or step, the "Add step" button appears in the toolbar
- **Toggle-style button:** When the add-step panel is open (and the workflow has steps), the toolbar button uses `isClicked` + `aria-pressed` for visible active/inactive feedback. Clicking the button toggles the panel open/closed.

### Duplicate Workflow

- Row kebab action with `RhUiDuplicateIcon` + "Duplicate workflow"
- Positioned after Edit / View run history and before Export (non-destructive action block)
- **No confirmation dialog** — duplication runs immediately on click
- **Naming convention:** `{originalName} - duplicate-{base36Timestamp}`
- **Success toast with deep link:** Toast title "Workflow duplicated"; description includes an inline link button (`variant="link" isInline`) to open the new workflow in the builder
- Button disabled while duplicate request is in flight

### Schedule Triggers (Interval + Cron)

Trigger configuration supports two scheduling types:

| Type | UI control | Validation |
| ---- | ---------- | ---------- |
| **Interval** | `DurationInput` component (hours/minutes/seconds fields) | Minimum > 0 |
| **Cron** | `TextInput` with 5-field cron expression (`* * * * *`) | Must be valid 5-field cron syntax |

- "Continuous" trigger type has been **removed** — replaced by interval scheduling
- Cron input uses a plain `TextInput` (not a specialized cron builder component); helper text below the input explains the 5-field format (`minute hour day-of-month month day-of-week`)
- Both types show a "Next run" preview when the schedule is valid
- Schedule triggers are enabled/disabled via the trigger's own enabled state, not a separate toggle

### Run Workflow

- **Single trigger** — Plain "Run" button in the builder toolbar
- **Multiple triggers** — "Run" button becomes a dropdown, letting the user select which trigger to start from
- Run flow:
  1. Confirmation dialog ("Run [workflow name]?") with a "Don't show again" checkbox
  2. `RunWorkflowModal` — JSON code editor for providing mock trigger output data; validates against the trigger's `input_schema` when defined
- After run, the execution visualizer panel opens showing real-time results

**"Don't show again" preference persistence:**

- User can tick "Don't show again" on the run confirmation dialog to skip it in future runs
- Preference is stored in browser `localStorage` per user — NOT in backend settings
- When preference is set, clicking "Run" skips the confirmation and goes straight to `RunWorkflowModal`
- Use `useLocalStorage` hook for read/write; key format includes user ID for multi-user machines

### Test Step (Run Step)

- Triggered from a step's kebab menu → "Run step"
- Opens a two-step dialog flow:
  1. **Choice dialog** — "Run all previous steps" or "Set mock input data"
  2. **Mock data editor** — PatternFly `CodeEditor` with JSON syntax highlighting, validate/format/clear toolbar actions
- All upstream steps in the graph are mocked and show as "skipped" in execution details
- After clicking "Run", the execution visualizer panel opens (same as full workflow Run) showing real-time results
- Test executions are visible in run history

### Cancel run:

- Secondary destructive button (`variant="secondary"` + `isDanger`) placed directly in the builder live-run header and execution detail header toolbar
- **No confirmation dialog** — inline cancel for running executions (intentional exception to the standard confirmation pattern)
- **Visibility:** Only shown when execution status is `pending` or `running` (`isExecutionCancellable`)
- **Label:** "Cancel run"
- **Feedback:** Success toast "Execution cancellation requested"; error toast "Failed to cancel execution" + API message
- **Loading state:** Button shows spinner and disables while mutation is pending

**Same pattern as a table kebab action:** "Cancel run" is also available as a danger-styled kebab item on the executions table (matching the header behavior above) — it fires immediately with no confirmation, then self-disables and shows an "Cancellation in progress…" tooltip until the execution's status changes. Generalize this as its own reusable pattern for any kebab action that triggers a slow, one-shot async operation: immediate-fire + self-disabling in-progress tooltip, distinct from both the no-confirm-toggle pattern (Node Disable/Enable) and the confirmation-dialog tiers (§6).

### Canvas Controls

- Should be anchored to the **bottom-left corner** of the canvas view
- Canvas overlays (controls, step legend, undo/redo) use `SynPanel` with `variant="raised"` for opaque + shadow
- Legend toggle uses accessible labels **Show step legend** / **Hide step legend**
- Workflow steps on the canvas also use `variant="raised"` with a border-radius override to match `Card` / canvas chrome
- **Minimum supported viewport:** The React Flow canvas is gated by a width-only check (currently 1024px, defined in `constants/viewport.ts`) — there is no height gate. Below the threshold, `SynReactFlowViewportGuard` shows a full-page "viewport too small" empty state while keeping the nav bar visible, rather than rendering a broken or unusably cramped canvas.

### Canvas step styling

- Step cards have a fixed width (240px) — all dynamic text elements (`Title`, `Content`) must use `overflow-wrap: anywhere` to prevent text overflow from long expressions, template names, or URLs
- Use `anywhere` instead of `break-word` because it also influences `min-content` intrinsic sizing, preventing overflow in fixed-width flex containers

### Verify Workflow

Verify validates the entire workflow graph against the backend and surfaces errors inline on the canvas.

- **Trigger:** Kebab action "Verify workflow" with `RhUiCheckCircleIcon`
- **API:** `POST /workflows/validate` — returns an array of `ValidationError` objects with `nodeId`, message, and severity
- **Loading state:** Toolbar shows a "Verifying..." button with spinner during the API call
- **`ValidationBanner`:** Expandable inline `Alert` rendered above the canvas; dismissing the banner clears all node badges
- **Per-node error badges:** Failed nodes show a circular warning badge (bottom-right, matching execution badge positioning) via `data.__validationError` on the node
- **Clickable node links:** Node-specific errors in the banner are inline links (`Button variant="link" isInline`) that navigate to the node editor panel via `useNodePanelNavigation`. Fallback label "Go to step" when name is unparseable; global errors (`nodeId: null`) stay as plain text
- **Grouped/humanized errors:** `parseValidationMessage()` / `humanizeValidationMessage()` extract node names and error lists; the banner uses compact horizontal `DescriptionList` (`isCompact isFluid isHorizontal`) — term = node name link, description = comma-separated messages. Display key "Workflow" for global errors

### Two-Tier Validation Severity

Validation findings have two severity levels that drive different UI behavior:

| Severity | Save behavior | Publish behavior | Banner variant |
| -------- | ------------- | ---------------- | -------------- |
| **Error** (`severity: 'error'`) | Save still succeeds; issues are surfaced inline | Always blocks publish | `danger` |
| **Warning** (`severity: 'warning'`) | Save succeeds | Does not block publish | `warning` |

**Save flow (`useBuilderSaveWorkflow`) — single request, no retry:** Save is always one request. The save response includes `has_validation_issues: boolean` plus an inline `validation_result` with the findings. When `has_validation_issues` is true, `reportSaveValidationIssues()` extracts the findings from `validation_result` and calls `onSaveWithValidationIssues` / `onValidationFindings` for node-level display — there is no second request, no `force_save` query parameter, and no retry loop. (This replaces an earlier two-request `force_save=true` retry flow, which was removed; `ImportWorkflowDialog`'s corresponding "Save anyway" retry option was removed at the same time since there's no longer a save-rejection case for warnings.)

**ValidationBanner variant logic:**

- Any finding with `severity !== 'warning'` → banner uses `variant="danger"`, title "Verification failed — N issue(s) found"
- All findings are warnings → banner uses `variant="warning"`, title "Saved with N warning(s)"
- Dismissible via `AlertActionCloseButton`

**Verify-then-publish gate (`PublishWorkflowButton`):**

- Publish button always runs verification first before opening the publish dialog
- Publish is `isAriaDisabled` when `validationErrorCount > 0` or during verification
- Disabled tooltips: "Verifying workflow…" or "Verify your workflow before publishing — N error(s) found"
- Permission gating: `DisabledWithTooltip` when `!canEdit`
- Auto re-verify: `BuilderContent` silently re-verifies on load when the workflow has existing validation issues

### Node Settings

Every activity node form uses `NodeFormTabsLayout` to split configuration into **Parameters** and **Settings** tabs.

- **Parameters tab:** Node-specific configuration fields (the existing form)
- **Settings tab:** Shared `NodeSettingsForm` component for:
  - **Continue on failure:** Three-way select (System default / On / Off) via `COF_OPTIONS`
  - **Timeout:** `DurationInput` component
  - **Retry policy:** Retry count + delay configuration
- **System defaults:** Live placeholders from `GET /settings?category=workflow_execution` via `useWorkflowEngineDefaults` — e.g., "System default — 30m"
- **Hidden for control flow:** `hideSettingsTab` is set for Condition, Switch, and trigger nodes (they have no configurable execution settings)

### Explaining Non-Obvious Node Semantics

For node types whose purpose is easy to misread (e.g., a Converge node can look "unnecessary" at first glance, since edges can be dragged directly between other steps), add a collapsed-by-default, expandable info `Alert` (`variant="info" isInline isExpandable`) at the top of the node's Parameters tab explaining when the step is and isn't needed. This is distinct from the always-visible trigger "activation" alerts described in Schedule Trigger Form, which explain *publish timing*, not *step purpose* — don't conflate the two; a purpose-explainer stays collapsed by default since it's reference material, not a warning.

### Three-Column Node Editor Layout

When a node is opened for editing, the builder can display a three-column layout for advanced node types:

| Column | Content | Panel style |
| ------ | ------- | ----------- |
| **Left** | Input data (upstream output / trigger data) | Default `SynPanel` |
| **Center** | Node parameters (the form) | `SynPanel variant="raised"` — visually elevated to signal "this is where you edit" |
| **Right** | Output data (downstream preview / schema) | Default `SynPanel` |

- Input/Output panels support Schema / Table / JSON view toggle (see Data Panel View Modes)
- **Branching nodes** (Condition, Switch): The center column header includes a branch-handle dropdown (`MenuToggle` with branch icon) for selecting which output path to inspect in the Output panel
- Columns use `ResizableDivider` for user-adjustable widths
- Center panel uses `variant="raised"` to maintain visual hierarchy — Input/Output panels stay flat

### Node Panel Navigation

The node editor panel provides **Previous/Next arrow controls** for navigating connected steps in graph order.

- **Single upstream/downstream:** Plain icon button with tooltip showing the connected step name
- **Multiple targets:** Dropdown menu on the arrow listing all connected steps
- **Components:** `NodePanelNavigationArrow`, `useNodePanelNavigation`, `useAdjacentNodes`, `getAdjacentNodesFromFlow`
- **Icons:** `RhUiCaretLeftIcon` (previous) / `RhUiCaretRightIcon` (next)
- **Positioning:** Tab-style arrows on panel edges via CSS module (`NodePanelNavigationArrow.module.css`)

### Node Disable/Enable

Activity nodes (Task, Approval) support toggling their enabled state directly from the canvas kebab menu.

- **Kebab actions:** "Disable step" / "Enable step" — **no confirmation dialog** (immediate toggle)
- **Visual treatment:** Disabled nodes show dashed gray border + 50% opacity (matches skipped execution state)
- **Persistence:** State stored in `settings.disabled` on the node definition
- **Control flow nodes** (Loop, Condition, Switch, Converge, Wait) use `MenuNodeType.CONTROL_FLOW` and show only **Replace** and **Delete** in their kebab — no disable/enable option
- **CSS note:** Use individual border-side CSS properties (`borderTopStyle`, `borderRightStyle`, etc.) instead of shorthand `border` for dashed/solid toggling — avoids React diffing issues

### Switch Node Expression Builder

Switch node paths share the same `ExpressionBuilderCore` used by Condition nodes, providing visual AND/OR expression groups with a custom expression mode toggle.

- **Expression groups:** Level-0 groups have no border; nested groups get a left accent border for visual hierarchy
- **Path reordering:** Drag-reorder paths via `@dnd-kit/sortable` with inline `RhUiGripVerticalFillIcon` grip handle, `DragOverlay`, and `restrictToVerticalAxis`
- **Path identity:** Each path uses `caseId` (not `id`) for stable edge remapping during reorder
- **Dividers:** Visual dividers separate path sections in the form

### Project-Scoped Resource Dropdowns

Builder dropdowns that reference other resources (integrations, AAP integrations, LLM models, credentials — see also "Richer pickers" under Resource Pickers in §3) should accept a `projectId` threaded from the workflow's own project context. When set, results are scoped server-side to global + that project's resources, intersected with RBAC visibility, so a workflow can never end up wired to a resource scoped to a different project. This scoping is specific to the builder — it does not apply to the unscoped Settings admin page, which intentionally shows everything.

### Webhook/EDA Trigger Form

Payload-validation UI for webhook and event-driven (EDA) triggers uses a **Simple/Advanced `ToggleGroup`**: Simple mode is a visual field-row builder that round-trips to JSON Schema; Advanced keeps the raw JSON editor for full control. Switching from Advanced back to Simple is blocked with an inline error when the current JSON is too complex to represent visually — don't silently drop or corrupt the schema. Pair the schema builder with a shared `WebhookUrlPreview` (method badge + copyable URL) and a collapsible, auto-generated sample `curl` command — both are reused identically across webhook and EDA trigger forms, so build new webhook-shaped triggers on the same shared components rather than one-off variants.

### Approval Side Panel

Pending approval review happens inline in the execution viewer rather than on a dedicated full-page route.

- **Layout:** Right-side `SynPanel isFullHeight` + `SidePanelHeader` + scrollable `ApprovalDetailContent`; mirrors `WorkflowHistoryCard` layout pattern
- **Mutual exclusivity:** History panel and approval panel cannot be open simultaneously
- **Auto-open:** `useAutoApprovalDetection` automatically opens the panel when a pending approval is detected on the current execution
- **Components:** `ApprovalSidePanel`, `useExecutionApprovalPanel`, `ApprovalDetailContent`

**Multi-approval navigation (`ApprovalNavigationHeader`):**

When an execution contains multiple approval steps (pending or completed), the panel provides sequential navigation:

- **Header:** "Approval 2 of 5" counter with Previous/Next arrow buttons
- **Navigation:** `RhUiCaretLeftIcon` / `RhUiCaretRightIcon` buttons cycle through approval nodes in graph order
- **Keyboard support:** Arrow-key navigation for accessibility
- **Auto-focus:** Panel auto-scrolls to the first pending approval on open
- **Canvas sync:** Navigating approvals highlights the corresponding node on the canvas

### Wait Node Canvas Countdown

During active execution, Wait nodes display a live countdown timer on the canvas.

- **Format:** `HH:MM:SS` for durations under 24h; `Xd HH:MM:SS` for longer durations
- **Implementation:** `useWaitCountdown` hook with 1-second interval, calculating remaining time from `started_at` + configured duration
- **Visibility:** Only shown when node execution status is `waiting` or `running`; clears on terminal status
- **Display:** Rendered as a detail row below the static duration label on the canvas node

### Import Workflow Confirmation

Importing a workflow into an existing saved builder shows a choice dialog before proceeding.

- **Condition:** Only shown for existing saved workflows; new/empty builders import directly without modal
- **Component:** `ImportConfirmationDialog` — small `Modal` (not `NxConfirmationDialog`) with **radio choices**:
  - "Import as new workflow" — creates a fresh workflow from the import
  - "Import into current workflow" — replaces the current builder content
- **Unsaved changes:** When `isDirty`, the dialog includes a warning about losing unsaved changes
- **Buttons:** Primary "Import" + link "Cancel"
- **Radio descriptions:** Each option has a `description` prop explaining the behavior

### Conditional Settings Visibility

Node settings sections should only show controls that are relevant to the current node type. Use a `supportsRetryPolicy` prop (or similar capability flag) to hide settings that have no effect on a given node type. For example, retry policy settings are hidden for AI Agent nodes, script action nodes, and approval nodes — only HTTP request action nodes show them. This prevents user confusion about settings that would be silently ignored.

### Canvas Auto-Layout

The canvas layout engine uses unified spacing constants shared between auto-layout (`layoutEngine.ts`) and manual positioning (`useNodePositioning.ts`) to ensure consistent spacing regardless of how nodes are placed.

- **Unified constants:** `LOOP_BODY_SPACING` from `layoutConstants.ts` — `horizontal` (80px), `vertical` (100px), `nodeGap` (40px). Never use magic numbers for loop body positioning.
- **Branch ordering:** Branching nodes (condition, approval, switch, loop) use edge weight-based ordering via `buildBranchNodeOrdering()`. Higher-weight branches render first (leftmost/topmost): true/approved branches get weight 2, false/rejected get weight 1. Switch cases use descending weights (case_0=50, case_1=49, ..., default=1).
- **Layout algorithm:** Uses `network-simplex` ranker with `nodesep: 90` for proper horizontal spacing between branch targets.

### Execution View Panels

- The **run details panel** provides an Overview/Details toggle for inspecting execution state
- Panels use `SynPanel isFullHeight` for proper internal scroll behavior — do not hand-roll `display: flex; flexDirection: column` inline styles when `isFullHeight` exists
- Panels may use a `ResizableDivider` to allow users to resize panel split areas
- The most recent run details can display inline in the editor after workflow execution
- **Activity filtering:** The execution details panel includes a `FilterBar` toolbar (role="search", aria-label="Filters") for filtering activities by name. Filter state persists across Overview/Details tab switches. When no activities match, show `NxEmptyStateFilter` with a "Clear all filters" button.
- **Human-readable error messages:** Execution error messages must resolve internal activity IDs to human-readable node names. Use a name map (`Map<activityId, nodeName>`) and `resolveErrorDetails()` to replace IDs in error strings before displaying them to users. Never show raw activity IDs in user-facing error alerts.

### AI Agent Reasoning Trace ("Agent Steps")

Agentic node execution details use a second tab, alongside the standard Input/Output tabs, specifically for inspecting how the agent arrived at its result:

- **Tab:** "Agent steps" — only shown for agentic-type activities
- **Header:** A stats strip (model, tokens used, trace time, tool-call count)
- **Body:** Reasoning blocks, tool-call cards with expandable request/response detail, and a final-answer block
- **Structured content rendering:** Structured JSON content (tool call args/results) renders as a detail list plus a copyable code block — never dump raw JSON as plain text; use the same `NxCodeBlock` conventions as elsewhere (§3 Details Component)

### Run History Panel

The run history panel displays execution history for a workflow using a scrollable, paginated list.

- **Pagination:** Use cursor-based pagination via `useCursorPagination` hook + `PaginationFooter` component for any list that can exceed ~20 items. Time-ordered lists (executions, history entries) should always use cursor pagination, not offset pagination.
- **Filter integration:** Filters and pagination share state via `useCursorPagination` — changing filters resets the cursor to page 1.
- **Layout:** Execution rows use `Flex` with `flex_1` on the content side and `flexShrink: 0` on the status side to prevent layout shifts with varying content lengths.

### File Upload UX

- **Dropzone layout:** Use vertical layout for `MultipleFileUpload` (not `isHorizontal`)
- **Collapsible file list:** Use `ExpandableSection` (not `MultipleFileUploadStatus`) for the attached file list. The section auto-expands when new files are dropped and can start collapsed via `defaultStatusExpanded={false}`.
- **Status text:** Use "N files attached" (or "1 file attached") when all files are successfully uploaded — not "N/N files uploaded". Show "N/M files uploaded" only during active upload or when errors occur.
- **Disabled opacity:** Use `var(--syntara-disabled-opacity)` CSS variable for disabled dropzone opacity, not hardcoded `0.5`.
- **Post-upload download:** Once a file has successfully uploaded, show a download icon button on its list item that fetches the file and triggers a browser download preserving the server-provided filename. While the download is in progress, show a loading spinner plus a "Cancel" link in place of the download button, and hide the remove action for that item until the download finishes or is cancelled.

### Schedule Trigger Form

- **Optional start date:** The schedule start date field is optional — if left empty, the schedule starts upon publishing. An info `Alert` (variant="info", isInline) above the schedule fields explains: "This schedule will only take effect once the workflow is published. Changes to the schedule are applied on the next publish."
- **Execution conflict policy:** The "Execution conflict policy" dropdown (formerly "Missed schedule behavior") uses `SelectOption` with `description` props to explain each option inline: Skip (default), Run once, Run all.

---

## 18. Accessibility Guidelines

While PatternFly provides a strong foundation with accessibility built into its individual components, achieving full [WCAG 2.1 AA](https://www.w3.org/WAI/WCAG2AA-Conformance) and [Section 508](https://www.section508.gov/) compliance requires careful implementation within this codebase.

An accessible component can still be used in an inaccessible way. The goal is to ensure that the holistic user journey — including page structure, dynamic content, and complex workflows — remains fully inclusive and navigable for all users, including those relying on assistive technologies.

### Where PatternFly Isn't Enough

PatternFly handles the internal accessibility of its elements (e.g., a dropdown menu will have correct internal focus management), but developers are responsible for the **contextual accessibility** of the application:

- **Page Structure & Landmark Roles:** Ensuring the macro-layout of the application is navigable.
- **Focus Management:** Handling user focus when views change, modals open/close, or elements are dynamically added/removed from the DOM.
- **Custom Components:** Ensuring any UI elements built outside of PatternFly (such as workflow canvases built on React Flow) adhere to strict accessibility standards.

### Core Implementation Standards

#### Semantic HTML & Page Structure

- **Proper Heading Hierarchy:** Headings (`<h1>` through `<h6>`) must be used sequentially without skipping levels. Screen reader users rely on headings to map out the page.
- **Landmarks:** Use semantic tags (`<main>`, `<nav>`, `<header>`, `<footer>`, `<aside>`) or ARIA landmark roles so users can quickly jump to specific regions of the application.
- **Dynamic per-page browser tab titles:** Every routed page must render a dynamic browser title via React 19's native title hoisting, using the shared `SynPageTitle` / `toPageTitle(segments)` utility. Segments run narrow to broad (most specific first); `null`/blank entries are auto-scrubbed and the app-name suffix is appended automatically. This is machine-enforced: the `require-page-title` ESLint rule (`eslint-plugin-syntara/rules/require-page-title.js`) fails any route file missing it.

#### Keyboard Navigation & Focus Management

- **Keyboard Operability:** Every interactive element (buttons, links, form fields, drag-and-drop interfaces) must be fully operable using only a keyboard.
- **Tooltips need a focusable host:** A PatternFly `Tooltip` wrapping a non-interactive element (a `Label`/badge rather than a button or link) is invisible to keyboard users unless that element is in the tab order. Whenever a `Tooltip` wraps something that isn't already focusable, add `tabIndex={0}` to the wrapped element (or wrap it in a focusable `span`) so the tooltip is keyboard-discoverable — apply this once per component rather than rediscovering it per usage.
- **Visible Focus Indicator:** Never remove the default focus outline (`outline: none;`) unless providing a highly visible custom alternative with a contrast ratio of at least 3:1 against the background.
- **Routing and Modals:** When navigating between routes in a SPA, focus should be programmatically managed (e.g., sent to the new page's main heading). When opening a modal, focus must be trapped inside it until dismissed, and returned to the triggering element upon closing.
  - **Concrete recipe:** `useRouteChangeFocus` (`hooks/useRouteChangeFocus.ts`), wired once in `AppShell.tsx`, moves focus to the main content region (`role="main"`, `tabIndex={-1}`) whenever the router's resolved pathname changes — it ignores query/hash-only changes so filter/sort updates don't steal focus. Defer the focus call via `requestAnimationFrame` so it runs after the new view has painted. This mirrors the focus behavior a full page load gives you natively, which SPA route changes don't get for free.

#### Dynamic Content & State Changes

- **Live Regions:** Use `aria-live` attributes (`polite` or `assertive`) to announce dynamic updates (e.g., job completing, failing, notification toast appearing) without requiring a page refresh.
- **State Communication:** Use attributes like `aria-expanded`, `aria-disabled`, and `aria-current` to ensure screen readers understand the current state of toggleable or actionable UI elements.

#### Forms & Error Handling

- **Explicit Labeling:** Every input field must have an associated `<label>`. Do not rely solely on placeholder text, as it disappears on input and often fails color contrast standards.
- **Accessible Validation:** Form errors must be communicated to assistive tech. Use `aria-invalid="true"` on the input and `aria-describedby` to link the input to the specific error message text.

#### Color, Contrast, and Iconography

- **Color Contrast:** All text and meaningful icons must meet the WCAG AA minimum contrast ratio of 4.5:1 for normal text and 3:1 for large text/UI components against their background.
- **Don't Rely Solely on Color:** Information must never be conveyed by color alone. If a job fails, include an error icon and descriptive text (e.g., "Status: Failed"), not just red text.
- **Alternative Text:** Provide concise `alt` text for informative images. Use empty `alt=""` or `aria-hidden="true"` for purely decorative images or icons so screen readers can ignore them.

### Testing & Validation

- **Automated Testing:** Integrate accessibility tools into unit tests and CI/CD pipelines to catch basic DOM-level violations (e.g., missing labels, contrast failures).
- **Manual Keyboard Testing:** Test features using only `Tab`, `Shift+Tab`, `Enter`, `Space`, and Arrow keys.
- **Screen Reader Testing:** Features should be tested using standard screen readers to verify the actual user experience.

---

## 19. Styling Rules

### No Global, Unscoped CSS

**Never write global CSS rules** that target element types, PatternFly class names, or broad selectors from a shared stylesheet. Global styles bleed across component boundaries, override PatternFly's design tokens silently, and break theming and upgrade-compatibility.

```css
/* ❌ BAD: global rules that affect all matching elements */
.pf-v6-c-menu__item {
  min-height: 0;
}

p {
  margin-bottom: 8px;
}
```

```css
/* ✅ GOOD: scoped to a CSS Module, applied via className */
/* MyComponent.module.css */
.menuItem {
  min-height: 0;
}
```

```tsx
/* ✅ GOOD: apply the scoped class in the component */
import styles from './MyComponent.module.css'
;<MenuItem className={styles.menuItem} />
```

### Styling Priority Order

Follow this hierarchy when applying styles — always start from the top:

1. **PatternFly props and variants** — use built-in component props (`variant`, `isCompact`, `hasNoPadding`, etc.) before writing any CSS.
2. **PF6 design tokens** — use `var(--pf-t--global--*)` custom properties for spacing, color, and sizing. Never use hardcoded `px` values for these concerns.
3. **CSS Modules** (`.module.css`) — for component-specific overrides that cannot be expressed via tokens or props. Styles must be scoped to the module; never use `:global()` selectors inside a module.
4. **Inline `style` prop** — acceptable only for dynamic values (e.g., a width computed at runtime) that cannot be expressed as a token or class.

### Semantic Tokens Only

- **No hard-coded border colors** — use `--pf-t--global--border--color--default` and `--pf-t--global--border--width--divider--default` for borders and pagination footer dividers. Never use custom rgba hex overrides (e.g., `rgba(196, 181, 253, 0.2)`) on table or layout components. Semantic tokens adapt to light/dark/glass themes automatically.
- **No breadcrumb CSS overrides** — breadcrumbs use PF6 default styling (dashed underline, default link colors). Do not override `--pf-v6-c-breadcrumb__link--*` tokens to force solid underlines or custom link colors.
- **Compact inline form controls** — for time pickers or number inputs that need explicit widths, use PF spacer tokens (e.g., `--pf-t--global--spacer--4xl`) in CSS modules. Use `flexWrap: nowrap` + `flex={{ default: 'flexNone' }}` to prevent inline fields from collapsing.

### When a Global Style Seems Necessary

If you believe a global style is the only option, follow the PatternFly gaps process (see "Design System" → "PatternFly gaps" above): check PatternFly docs and tokens first, raise with UX, then engage PatternFly upstream. Approved temporary exceptions must be documented with a `patternfly-override` label.

---

## 20. Use Chrome DevTools MCP to Verify Implementation

This project ships with a Chrome DevTools MCP server configured in `.mcp.json`. Use it to inspect the live application while implementing or reviewing UI — verify that PatternFly components render correctly, design tokens are applied, and layouts match the spec.

### Available Capabilities

| Capability                | What it helps verify                                                     |
| ------------------------- | ------------------------------------------------------------------------ |
| **DOM inspection**        | Correct PatternFly component structure, semantic HTML, landmark roles    |
| **Computed styles**       | Design tokens (`var(--pf-t--global--*)`) applied instead of hardcoded px |
| **Layout inspection**     | Page structure matches Compass layout, spacing is consistent             |
| **Network monitoring**    | API calls use typed clients, responses match expected contracts          |
| **Console monitoring**    | No runtime errors, warnings, or accessibility violations in console      |
| **JavaScript evaluation** | Inspect component state, verify Zustand store, check React props         |

### When to Use

| Situation                                           | What to check                                                    |
| --------------------------------------------------- | ---------------------------------------------------------------- |
| Implementing a new page or component                | Verify PatternFly classes and tokens render correctly            |
| Reviewing spacing or alignment issues               | Inspect computed styles for hardcoded px vs design tokens        |
| Checking empty states, loading states, error states | Navigate to each state and verify correct component usage        |
| Verifying accessibility                             | Inspect DOM for landmark roles, heading hierarchy, aria attrs    |
| Debugging layout issues                             | Check flex/grid containers, overflow, and responsive breakpoints |
| Validating modal/dialog behavior                    | Verify focus trap, button order, variant usage                   |

### Workflow

1. **Start the dev server** (`npm start`)
2. **Navigate to the page** in the browser
3. **Inspect the DOM** — verify PatternFly component structure (e.g., `pf-v6-c-table`, `pf-v6-c-empty-state`)
4. **Check computed styles** — confirm spacing uses design tokens, not hardcoded values
5. **Monitor console** — watch for React warnings, accessibility violations, or runtime errors
6. **Fix issues** before submitting for review

### Checklist for UI Verification

- [ ] PatternFly components used (no custom equivalents)
- [ ] Design tokens applied for spacing and colors (`var(--pf-t--global--*)`)
- [ ] No hardcoded `px` for spacing or colors
- [ ] Semantic HTML and ARIA attributes present
- [ ] Heading hierarchy correct (h1 → h2 → h3, no skipping)
- [ ] No console errors or warnings in the page
- [ ] Empty, loading, and error states all render correctly

---

## 21. Storybook Review Workflow

The project ships with Storybook for documenting and reviewing `Nx*` components. Use it alongside the dev server for UI verification.

- **Start Storybook:** `npm run storybook` (port 5174)
- **Light and dark mode:** Preview components in both themes via the Storybook toolbar (System / Light / Dark) before sign-off
- **Composed stories over isolated demos:** Stories should reflect real app compositions (e.g., a full list page layout), not isolated prop playgrounds
- **Autodocs:** Foundational `Nx*` components have `autodocs` enabled — browse auto-generated API docs alongside live examples
- **Available stories:** `SynPage`, `SynPageHeader`, `SynPageBreadcrumbs`, `SynPanel`, `SynPanelContentStack`, `NxUrlTabs`, `NxConfirmationDialog`, `NxCodeBlock`, `NxDetail`, `NxDetailList`, `NxErrorState`, `NxLoadingState`, `NxEmptyStateNoData`, `NxEmptyStateFilter`, `NxEmptyStateServiceUnavailable`, `NxListPanel`, `NxKebabMenu`, `NxLabel`, `NxUserTag`, `NxScrollableTableContainer`

---

## 22. Getting Started for Developers

- Point to the UI repository for implementation references
- Utilize the UI/UX skills defined in this document and the Cursor rules
- Follow the accessibility guidelines in section 18
- Follow the styling rules in section 19
- Use Chrome DevTools MCP (section 20) to verify your implementation against the live app
- Use Storybook (section 21) to review `Nx*` component documentation and test in light/dark mode

---

## Quick Reference: Component Selection

When implementing a new page or feature, use this decision tree:

```text
What are you building?
├── List/table view
│   ├── Use NxScrollableTableContainer (standard variant by default, "compact" only for dense supplementary tables)
│   ├── Add SynPageHeader with title + primary action
│   ├── Add FilterBar (Attribute Search)
│   ├── Add cursor-based pagination footer via NxScrollableTableContainer's footer prop
│   ├── "Created"/"Modified" columns: username (linked) + date together
│   └── Handle 3 empty states (no data / no results / error)
│
├── Detail view
│   ├── Use NxDetailList + NxDetail (vertical default; isHorizontal for compact)
│   ├── Add SynPageBreadcrumbs + SynPageHeader with title + resource actions
│   ├── NxDetail with empty children renders nothing (no placeholder needed)
│   └── Use NxCodeBlock for JSON/script/log display
│
├── Create/Edit form
│   ├── 5+ fields or multi-step? → Full page
│   ├── 2–4 simple fields? → Modal
│   ├── Use PatternFly Basic Form, left-aligned, one column, max-width 600px
│   ├── Use Zod + react-hook-form for validation
│   └── Save/Cancel buttons in SynPanel footer (sticky), NOT in page header
│
├── Delete/Remove/Cancel/Stop (destructive)
│   ├── Always use confirmation modal (Small variant)
│   ├── Title with warning icon
│   ├── Action button variant="danger", Cancel variant="link"
│   └── Post-delete: remove from list or navigate back + toast
│
├── Disable (non-destructive)
│   ├── Standard confirmation modal (Small variant, no warning icon)
│   ├── Confirm button variant="primary", Cancel variant="link"
│   └── Post-disable: stay in place + toast
│
├── View read-only detail (from kebab)
│   ├── Medium modal with descriptive title
│   ├── Read-only content with optional ClipboardCopy
│   └── Single "Close" button (variant="primary")
│
├── Log / event viewer (read-only)
│   ├── Use NxScrollableTableContainer with expandable rows (isExpandable)
│   ├── Add expand-all/collapse-all toggle in header
│   ├── Add FilterBar with multiple attribute filters (category, date range, status, severity, etc.)
│   ├── All columns sortable
│   ├── Expanded row shows full event details (metadata, request/response payloads)
│   ├── Resource column links to the resource detail page when applicable
│   └── Handle 2 empty states (no events yet / no filter results)
│
├── Role-based access page
│   ├── No read → hide from nav/tab; EmptyStateAccessDenied on direct URL
│   ├── Read only → controls disabled via isAriaDisabled + DisabledWithTooltip
│   ├── Read + write → full edit capability
│   └── Use permission hooks (use{Domain}Permissions) for all gating
│
├── Full-page wizard (multi-step with tables)
│   ├── Dedicated route (not modal)
│   ├── Each step: title + description + FilterBar + ScrollableTableContainer
│   ├── Footer: Back/Next/Cancel (link) per step
│   └── Cancel navigates back to origin route
│
├── Dedicated edit page (complex inline editing)
│   ├── Parent tab stays read-only with "Edit" button
│   ├── Edit page at sub-route with Save/Cancel toolbar
│   └── Permission-gated with EmptyStateAccessDenied fallback
│
├── Canvas/builder view
│   ├── Use React Flow + PatternFly wrapper
│   ├── Left-to-right layout
│   ├── Canvas controls at bottom-left (SynPanel variant="raised")
│   ├── Side panel for step details (not modal)
│   ├── Three-column node editor: Input | Parameters (raised) | Output
│   ├── Version history panel: SimpleList grouped by date, view-only mode
│   └── Input/Output panels with Schema/Table/JSON view toggle
│
└── Integration configuration
    ├── 3-step wizard: type → connection → review
    ├── Header Switch for enable/disable (no confirmation for enable)
    ├── "Test connection" before enabling tools
    └── Per-tool Switch toggles in Tools tab
```
