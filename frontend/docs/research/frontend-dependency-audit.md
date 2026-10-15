# Frontend dependency removal and replacement audit

Reviewed: 2026-10-07. Snapshot: `02c68b27b` plus the existing working tree.

## Recommendation

All 25 UI runtime declarations have live consumers. There is no demonstrated unused runtime package to delete outright. Start with dependency ownership and the dormant browser-test setup, replace mock API UUID generation with Node's API, and plan the bounded migration from legacy dnd-kit. Browser UUID replacement is conditional on deployment origins. Consolidating coverage into Vitest is worthwhile to investigate separately; replacing the design system, router, forms, API client, or canvas is not justified by this audit.

The strongest unused declaration candidate is UI `@vitest/browser`, subject to deciding whether the dormant browser component testing capability should be restored or retired. Other candidates require preserving existing behavior or explicitly approving a product change.

## Scope and evidence

- Examined the root manifest, all three workspace manifests, the lockfile, application imports, configuration, scripts, CI consumers, relevant documentation, and selected dependency history.
- There are **104 direct declarations across four manifests**, representing **87 unique package names**: root 12 development; UI 25 runtime and 51 development; mock API 7 runtime and 5 development; contracts 4 development. The UI and mock API runtime counts include the local contracts workspace.
- The lockfile contains 1,231 `node_modules` entries. These include nested versions and optional platform packages; this is not an installed-package count or a browser payload estimate.
- Followed low-import candidates through their consumers. Plugins, CLI tools, peer dependencies, types, Storybook addons, and coverage tools cannot be classified from source imports alone.
- Current upstream APIs and migration claims were researched against primary sources. See [upstream evidence](frontend-dependency-upstream-research.md) for exact-version Vitest evidence and compatibility details.
- This is a static usage and consolidation audit. Installation, Knip, lint, builds, tests, bundle measurements, and a security advisory scan were not executed. The repository requires `make install` before checks; no implementation was changed, so installation and implementation checks were not needed for this report. No dependency is certified safe or migration validated by this audit.
- Recommendations below are proposed work. No manifests, lockfile, application code, or existing user changes were modified.

## Prioritized actions

Effort describes relative migration scope, not a delivery estimate. Priority accounts for maintenance benefit and regression risk; package-count reduction alone is not the objective.

| Priority | Action                                                                            | Evidence and benefit                                                                                  | Effort / condition                                                                 |
| -------- | --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| 1        | Declare dependencies in the workspace that imports them; strengthen Knip coverage | Direct imports rely on hoisted transitives and root declarations; `unlisted` and `types` are excluded | Small configuration change; retain legitimate CLI/plugin exceptions                |
| 1        | Resolve dormant `@vitest/browser` setup                                           | No browser component test files or `test:browser` script; config imports an undeclared provider       | Small if retired with approval; larger if restoring useful coverage                |
| 1        | Replace mock API `uuid` v4 with `node:crypto.randomUUID`                          | One importing file, all calls use v4; native UUID generation is already used elsewhere in mock API    | Small; preserve ID format and fixture determinism                                  |
| 2        | Consolidate UI UUID generation and conditionally replace `uuid`                   | Two wrappers duplicate v4 generation                                                                  | Small code footprint; supported origins must allow browser `randomUUID`            |
| 2        | Migrate the four legacy `@dnd-kit/*` packages                                     | All four imports are in `SwitchNodeForm.tsx`; upstream documents migration to current dnd-kit         | Medium; preserve pointer, keyboard, screen-reader, focus, and case-order behavior  |
| 2        | Investigate replacing `nyc` with Vitest coverage merging                          | Used solely for merged shard reports and the 85% statements gate                                      | Medium; migrate artifacts and CI together, preserve threshold/report outputs       |
| 3        | Replace direct `dotenv` use with Node environment loading                         | One call in Playwright config; CI Node 22.13 and containers Node 24 provide the API                   | Small; optional-file behavior, precedence, and parsing must match                  |
| 3        | Evaluate migrating two SVG assets to code-native components                       | `vite-plugin-svgr` supports five importing files and two SVGs                                         | Small/medium; retain visual fidelity, icon types, accessibility, styling, and docs |
| 3        | Measure editor loading before considering an editor replacement                   | PatternFly editor wraps Monaco and provides substantive editing features; loader defaults to a CDN    | Investigation first; replacement would be a substantial UI migration               |
| Monitor  | Evaluate a JMESPath successor only with backend conformance evidence              | Old release signal; typed alternatives also introduce language and licensing differences              | Medium; no proven maintenance/security/bundle benefit from switching               |

## Removal and replacement details

### UUID generation: best native replacement

UI imports are in [`generateUUID.ts`](../../packages/syntara-ui/src/utils/generateUUID.ts) and [`expressions/defaults.ts`](../../packages/syntara-ui/src/utils/expressions/defaults.ts). Mock API imports v4 in [`handlers.ts`](../../packages/syntara-mock-api/src/handlers.ts), while that file and `resources/settings.ts` also use native UUID generation. Keep the shared UI helper and have expression factories delegate to it, preserving exported interfaces and the underscore conversion in `generateActivityId`.

Node's `randomUUID()` generates v4 identifiers and predates both repository Node versions. Browser `crypto.randomUUID()` is restricted to secure contexts. A non-localhost HTTP deployment could fail after a blind replacement, even when the current package works through `getRandomValues`. Establish supported origins before removing the UI dependency. Avoid introducing a hand-written UUID fallback solely to remove a small library. [Node UUID API](https://nodejs.org/download/release/latest-v14.x/docs/api/crypto.html#crypto_crypto_randomuuid_options), [Web Cryptography specification](https://w3c.github.io/webcrypto/#Crypto-method-randomUUID)

Removing the two direct declarations would not remove every UUID package: the lockfile also records Mermaid as a UUID consumer and the coverage tooling has a UUID override. This primarily reduces direct dependency ownership; no performance improvement was measured.

### Browser component testing: unused declaration, incomplete workflow

[`vitest.browser.config.ts`](../../packages/syntara-ui/vitest.browser.config.ts) imports `@vitest/browser-playwright`, but that package is absent from the manifests and lockfile. The UI declares `@vitest/browser` and suppresses it in Knip. [`types/vitest-browser-playwright.d.ts`](../../packages/syntara-ui/types/vitest-browser-playwright.d.ts) supplies an `any` declaration, which cannot supply the missing runtime module. The config advertises `npm run test:browser`, but the script and matching test files are absent. Normal unit configuration excludes `*.browser.test.*` files.

Vitest 4 split browser providers into their own packages. If this capability remains intended, use the matching provider version, its real types, a script, and useful tests. If retired, remove the declaration together with the dormant config, shim, configuration references, and Knip exception after the feature-preservation decision. Do not silently delete configuration during implementation. [Vitest 4 migration announcement](https://vitest.dev/blog/vitest-4)

The installed browser package also pulls image-diff and serving utilities. Some are shared with other tools, so removing its dependency subtree does not imply all those packages disappear.

### dnd-kit: current upstream API, bounded migration

`@dnd-kit/core`, `modifiers`, `sortable`, and `utilities` all serve [`SwitchNodeForm.tsx`](../../packages/syntara-ui/src/routes/builder/node-forms/SwitchNodeForm.tsx). This includes sortable cases, vertical restriction, pointer and keyboard sensors, drag state, and react-hook-form field-array ordering.

Official documentation labels this package family legacy and provides a migration to `@dnd-kit/react` and associated helpers/modifiers. Treat this as a maintenance migration, not evidence of a vulnerability or unsupported deadline. Preserve drag handles, ordering, expanded case state, form values, keyboard operation, focus, and announcements. Replacing it with HTML drag events would create custom interaction and accessibility work. [Legacy package notice](https://dndkit.com/legacy/introduction/installation/), [Migration guide](https://dndkit.com/react/guides/migration/)

### nyc: consolidate coverage, preserve the CI gate

[`merge-coverage.js`](../../packages/syntara-ui/scripts/merge-coverage.js) copies four shards' `coverage-final.json` artifacts into `.nyc_output`, invokes `test:coverage:report`, and enforces 85% global statement coverage. [`ci-frontend.yml`](../../../.github/workflows/ci-frontend.yml) uploads those files and executes the merge job. `nyc` is live tooling, despite its Knip exception and absence of application imports.

Vitest 4.1.10 supports blob reports, merging, and coverage merging. A migration must change shard output, artifact upload/download, merge execution, and coverage threshold configuration together. Preserve HTML, LCOV, JSON, summary, text reports, merged totals, coverage scope, and failing behavior below 85%. A successful test-report merge alone is insufficient evidence that the coverage gate is equivalent. [Exact-version reporter docs](https://github.com/vitest-dev/vitest/blob/v4.1.10/docs/guide/reporters.md#blob-reporter), [Exact-version merge source](https://github.com/vitest-dev/vitest/blob/v4.1.10/packages/vitest/src/node/core.ts)

The lockfile shows 27 immediate `nyc` dependencies. This indicates a meaningful tooling subtree to investigate, not 27 guaranteed removable packages. Do not add direct Istanbul packages and custom reporting code unless that is demonstrably simpler than the supported Vitest path.

### dotenv: small simplification

[`playwright.config.ts`](../../packages/syntara-ui/playwright.config.ts) loads `.env.local` using `dotenv.config({ path, quiet: true })`. Native `process.loadEnvFile()` is available in pinned CI Node 22.13; it is stable in the container's Node 24 release. Preserve existing environment precedence, optional absence of the file, path handling, and accepted syntax. The current call does not throw for a missing file; a blind native replacement can change startup behavior. [Pinned CI Node documentation](https://nodejs.org/download/release/v22.13.0/docs/api/process.html#processloadenvfilepath)

The direct declaration can be removed after migration, but Vite still uses dotenv transitively. The benefit is one fewer directly maintained tool dependency, with no browser payload impact established. [Vite 7.3.2 environment source](https://github.com/vitejs/vite/blob/v7.3.2/packages/vite/src/node/env.ts)

### SVG tooling: optional migration, currently used

`vite-plugin-svgr` transforms two assets (`ansible-automation-platform.svg`, `eda.svg`) used in `CanvasLegend`, `nodeMetadata`, `registerAAPNode`, and `registerTriggerNode`. The plugin and `*.svg?react` type declaration are live. `QUICK_START.md` also documents this convention.

A migration to reusable SVG components could remove the direct plugin and some SVGR-only tooling. Preserve inline SVG styling, component-compatible icon types, view boxes, visual fidelity, and accessible naming/decorative behavior. Using image URLs is not automatically equivalent. Only remove the plugin after migrating every consumer and updating types and the step-registry guide. This is an optional build simplification, with no size saving measured.

### Monaco editor: verify loading before replacing

The editor is used by `ExpandableCodeEditor` and `JsonEditorToolbar`. It supports JSON/Python/shell/plaintext, fullscreen editing, imperative focus/value access, cursor insertion, drag/drop, theme behavior, and blur handling. Replacement with a textarea or another editor must preserve those capabilities and PatternFly integration. Routes are already lazy-loaded; do not assume the editor is part of every initial page load.

The installed `@monaco-editor/loader` default points to `monaco-editor@0.55.1` on jsDelivr, whereas the lockfile resolves Monaco 0.56.0. No application loader override was found; the test setup also documents default remote loading. This is a **source-level indication**, not a verified browser network trace. Inspect actual browser requests, CSP/offline behavior, and the loaded version first. Lockfile overrides such as `dompurify` may not control dependencies in a remotely loaded Monaco distribution. Consider controlled/self-hosted loading before an editor replacement. Primary local evidence: `node_modules/@monaco-editor/loader/lib/es/config/index.js`, [`test setup`](../../packages/syntara-ui/src/test/setup.ts), and `package-lock.json`.

## Dependency ownership and audit blind spots

The UI directly imports several packages it does not declare. Hoisting currently makes these available through other tools:

| Package                      | Direct consumer                                                 | Proposed ownership                                                                       |
| ---------------------------- | --------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `@patternfly/react-icons`    | 193 importing files including components, pages, stories, tests | UI runtime dependency aligned with PF6                                                   |
| `@patternfly/react-tokens`   | `src/app/useDockState.ts` breakpoint token                      | UI runtime dependency aligned with PF6                                                   |
| `openapi-typescript-helpers` | `useFilteredQuery.ts` and its test, type imports                | UI explicit dependency; development placement can suit type-only use in this private app |
| `picomatch`                  | Two local ESLint rules                                          | UI development dependency; an override is not a declaration                              |
| `axe-core`                   | `scripts/a11y-audit-report.ts`, type imports                    | UI development dependency                                                                |
| `@vitest/browser-playwright` | Dormant browser config                                          | Declare only if restoring that workflow                                                  |

Root `@testing-library/dom` satisfies required Testing Library peers. Keep it explicitly declared somewhere intentional; moving it to UI improves ownership but is not an unused-package deletion. Root `eslint-plugin-no-only-tests` is imported by the UI ESLint configuration; moving its declaration to UI similarly makes the consumer self-describing.

Root and UI duplicate `@vitest/coverage-v8`, `vitest`, `happy-dom`, Prettier, `eslint-config-prettier`, and `eslint-plugin-import-x`. Do not remove duplicates wholesale. Root Vitest configuration is a supported entry point, root Mermaid lint uses happy-dom, and root formatting invokes Prettier. Root `eslint-config-prettier` and `eslint-plugin-import-x` have only UI config consumers and are already declared there; those two root declarations are plausible ownership cleanup after checking the supported installation layout. Fewer declarations would not reduce the currently deduplicated install.

Root `concurrently` is used by root, UI, and contracts scripts. UI `tsx`, `pngjs`, and `@types/pngjs` serve route-baseline and visual-regression scripts. UI `nyc` serves CI. Storybook addons are strings in config and React Compiler is loaded through Babel configuration. None of these is unused from absence of direct imports.

[`knip.json`](../../packages/syntara-ui/knip.json) currently excludes `unlisted` and `types`, ignores eight dependencies and nine binaries, and restricts explicit project patterns to UI `src`. Config plugins may expand this, but only UI has a Knip script; root, mock API, and contracts dependency ownership is not comprehensively covered by `npm run knip`. Expand workspace/script/config coverage and reinstate unlisted checks after resolving legitimate ownership issues. Retain documented exceptions for genuinely dynamic plugins; avoid replacing broad blind spots with equally broad ignores. This audit did not run Knip and makes no claim about its current output.

Root overrides span build tools, parsers, reporting, Playwright, and native tooling. Review each override against its current consumer and documented reason before removing it. A newer transitive version does not establish that a security override is unnecessary; an override can also force a version outside a consumer's declared range. This audit did not establish any specific override as safe to delete.

## Keep decisions and runtime inventory

The following is the complete UI runtime inventory. Counts are observed production files importing the package directly, excluding ordinary test/story files; downstream use can be much wider.

| Dependency                      | Importing files | Decision and reason                                                                                      |
| ------------------------------- | --------------: | -------------------------------------------------------------------------------------------------------- |
| `@dagrejs/dagre`                |               1 | Keep: layout engine behind the workflow canvas; one import is a meaningful module boundary               |
| `@dnd-kit/core`                 |               1 | Migrate with the other legacy dnd-kit packages                                                           |
| `@dnd-kit/modifiers`            |               1 | Migrate vertical-axis behavior with dnd-kit                                                              |
| `@dnd-kit/sortable`             |               1 | Migrate case sorting with dnd-kit                                                                        |
| `@dnd-kit/utilities`            |               1 | Migrate transform handling with dnd-kit                                                                  |
| `@hookform/resolvers`           |              14 | Keep: Zod/react-hook-form integration mandated by project conventions                                    |
| `@patternfly/react-code-editor` |               2 | Keep pending loading investigation; established editor capabilities                                      |
| `@patternfly/react-core`        |             373 | Keep: required design system and accessible UI primitives                                                |
| `@patternfly/react-table`       |              49 | Keep: table behavior and consistency with PatternFly                                                     |
| `@syntara/contracts`            |             234 | Keep: local generated API types and enum constants                                                       |
| `@tanstack/react-query`         |              58 | Keep: required server-state caching and mutations                                                        |
| `@tanstack/react-router`        |              68 | Keep: active routing, permission integration, Storybook framework                                        |
| `@xyflow/react`                 |              73 | Keep: workflow canvas, connections, selection, viewport behavior                                         |
| `date-fns`                      |               5 | Keep: ISO parsing, calendar days, expiration calculations, durations, string formatting                  |
| `fuse.js`                       |               1 | Keep: `useFuse` serves live glossary fuzzy/token search and weighted ranking                             |
| `jmespath`                      |               1 | Monitor: OIDC group evaluation/validation must match backend syntax                                      |
| `openapi-fetch`                 |               3 | Keep: typed request clients; replacement would disrupt shared client conventions                         |
| `openapi-react-query`           |               2 | Keep: integrates typed API operations with existing Query caching; no demonstrated redundant replacement |
| `react`                         |             507 | Keep: application foundation                                                                             |
| `react-dom`                     |               2 | Keep: application mounting and synchronous canvas update behavior                                        |
| `react-hook-form`               |              79 | Keep: required form state and field arrays                                                               |
| `uuid`                          |               2 | Conditionally replace with native v4 generation                                                          |
| `zod`                           |              50 | Keep: runtime schemas and required form validation                                                       |
| `zundo`                         |               1 | Keep: workflow undo/redo middleware; removing it requires implementing history behavior                  |
| `zustand`                       |               8 | Keep: workflow, auth, preference, and WebSocket state                                                    |

Fuse's only direct importer is a hook, but [`Glossary.tsx`](../../packages/syntara-ui/src/routes/documentation/glossary/Glossary.tsx) uses that hook. Replacing it with `includes()` would change typo tolerance, token matching, and ordering, requiring a product decision. `date-fns` has no runtime dependencies in the lockfile and is also consumed by Currents. Replacing it would require preserving ISO/date-only semantics, time zones, DST/calendar arithmetic, invalid dates, duration output, and localized strings; native formatting alone is insufficient. Keep both.

Mock API runtime decisions: keep `@mswjs/http-middleware`, `msw`, local contracts, `jmespath`, `js-yaml`, and `tsx` (the container start command uses it); replace only direct `uuid` v4 generation. Contracts' `openapi-typescript` is invoked by schema generation and must remain.

### Development tooling disposition

| Group                       | Packages                                                                                                                                                        | Decision                                                                                                                                           |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Native/WASM peers           | `@emnapi/core`, `@emnapi/runtime`                                                                                                                               | Keep root pins: commit `257cb5cd6` documents npm 11 lock regeneration dropping peers and breaking npm 10 CI; `@napi-rs/wasm-runtime` consumes them |
| Unit testing and coverage   | `vitest`, `@vitest/coverage-v8`, `happy-dom`                                                                                                                    | Keep supported root/UI/mock workflows and Mermaid DOM parsing                                                                                      |
| Component assertions        | `@testing-library/dom`, `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom`, `vitest-axe`                                      | Keep accessibility and user-interaction coverage; align workspace ownership                                                                        |
| E2E/accessibility/reporting | `@playwright/test`, `@axe-core/playwright`, `@currents/playwright`                                                                                              | Keep live Playwright config, fixtures, audit tooling, and conditional Currents reporting                                                           |
| Browser component runner    | `@vitest/browser`                                                                                                                                               | Resolve dormant capability as described above                                                                                                      |
| Storybook                   | `storybook`, `@storybook/tanstack-react`, `@storybook/addon-docs`, `@storybook/addon-a11y`, `@storybook/addon-mcp`                                              | Keep documented component exploration, accessibility, and MCP workflows                                                                            |
| Build/compiler              | `vite`, `@vitejs/plugin-react`, `babel-plugin-react-compiler`, `typescript`                                                                                     | Keep configured build, compiler, and typechecking workflows                                                                                        |
| SVG build                   | `vite-plugin-svgr`                                                                                                                                              | Optional migration after preserving both assets and all consumers                                                                                  |
| Scripts                     | `concurrently`, `tsx`, `pngjs`, `@types/pngjs`, `mermaid`                                                                                                       | Keep script and visual-regression consumers                                                                                                        |
| Coverage reports            | `nyc`                                                                                                                                                           | Consider Vitest consolidation; live 85% CI gate                                                                                                    |
| Environment loading         | `dotenv`                                                                                                                                                        | Optional native replacement                                                                                                                        |
| Formatting                  | `prettier`, `eslint-config-prettier`                                                                                                                            | Keep functionality; root config-package declaration may be redundant                                                                               |
| ESLint core                 | `eslint`, `@eslint/js`, `@eslint/compat`, `typescript-eslint`, `globals`                                                                                        | Keep imported config and workspace lint tools                                                                                                      |
| General lint rules          | `eslint-plugin-import-x`, `eslint-plugin-no-only-tests`, `eslint-plugin-barrel-files`, `eslint-plugin-sonarjs`, `eslint-plugin-unicorn`                         | Keep configured rules; align declarations with UI consumers                                                                                        |
| React/a11y lint rules       | `eslint-plugin-react`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`, `eslint-plugin-react-you-might-not-need-an-effect`, `eslint-plugin-jsx-a11y` | Keep configured code-quality/accessibility expectations                                                                                            |
| Tool-specific lint rules    | `@tanstack/eslint-plugin-query`, `@vitest/eslint-plugin`, `eslint-plugin-storybook`, `eslint-plugin-testing-library`                                            | Keep rules for the corresponding retained libraries                                                                                                |
| Unused code detection       | `knip`                                                                                                                                                          | Keep and improve workspace/script/unlisted coverage                                                                                                |
| Types                       | `@types/jmespath`, `@types/node`, `@types/react`, `@types/react-dom`, `@types/js-yaml`                                                                          | Keep types for active consumers; do not infer unused status from import absence                                                                    |
| Contract generation         | `openapi-typescript`                                                                                                                                            | Keep generated schema workflow                                                                                                                     |

## Documentation drift

Wouter is already absent from manifests; the active application uses TanStack Router. It is not a package left to remove. However, README's tech stack, `DEVELOPER_GUIDE.md`, and `docs/architecture.md` still describe Wouter. Architecture's routing section also refers to the old `AppRouter` and old navigation APIs. Update the full routing explanation and linked examples when addressing audit follow-ups; changing only the technology name would leave misleading behavior descriptions. Two tests also contain legacy `vi.mock('wouter')` stubs; inspect their setup before removing those stubs.

Documentation follow-ups for actual migrations: browser-test instructions/config references; coverage commands and `TESTING.md`; step-registry SVG conventions and typings; dependency ownership conventions; date/UUID helpers if their documented behavior changes. No documentation currently establishes a need to introduce another router, form library, state manager, or design system.

## Suggested implementation sequence and evidence required

1. Repair dependency ownership and Knip coverage; update stale routing documentation and investigate obsolete test mocks in a dedicated cleanup. Preserve current package capabilities.
2. Decide the browser component testing capability, then either restore its provider/workflow or retire the dormant configuration with explicit approval.
3. Replace mock API UUID generation; consolidate UI wrappers and replace browser UUIDs only once supported origins are established.
4. Migrate legacy dnd-kit as a focused behavior-preserving change. Review pointer and keyboard sorting, announcements, focus retention, form values, and visual states.
5. Prototype Vitest shard coverage merging and prove equivalent totals, outputs, and the 85% failure gate before removing `nyc`.
6. Consider native dotenv loading and SVG component migration if simplifying direct ownership remains useful. Investigate actual Monaco loading before any editor swap. Keep JMESPath until a replacement passes backend compatibility and license review.

For each implementation, run the required install before checks, the affected static checks and focused tests, and the browser/manual checks needed for changed interactions. Measure direct declarations, lockfile entries, clean install footprint, and production chunks separately if claiming a saving. No size or performance reduction is promised by this report.
