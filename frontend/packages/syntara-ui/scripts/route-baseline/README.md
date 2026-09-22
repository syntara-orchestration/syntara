# Route baseline

`manifest.gen.json` is the UI route compatibility contract.

## Commands

```bash
# Compare live sources to the committed manifest (contract only — fast)
npm run route-baseline:check

# Regenerate manifest.gen.json after an intentional route change (+ Prettier)
npm run route-baseline:update
```

**CI:** `(Frontend) Route Baseline` in `ci-frontend.yml` runs `route-baseline:check`.
That job is the single contract gate.

**Layout:** tooling, docs, and `manifest.gen.json` all live in this directory
(`scripts/route-baseline/`).

**Vitest:** collector / update helpers in this directory run with the normal
package suite (`npm run vitest` / `npm test`). Those tests use fixtures; they do
**not** re-assert the live committed manifest.

Commit an updated `manifest.gen.json` in the same PR as the route change.

## Expectation model

The baseline is a **committed contract**, not “routes look fine.”

| Situation                                      | `route-baseline:check` | `route-baseline:update`        |
| ---------------------------------------------- | ---------------------- | ------------------------------ |
| Accidental break vs committed manifest         | **Fail**               | N/A — fix the source           |
| Intentional route change, sources consistent   | **Fail** until regen   | **Succeed**, then check passes |
| AppRoute/nav out of sync with router           | **Fail** (parity)      | **Refuse** until fixed         |
| Non-contract change (page copy, search params) | **Pass**               | No-op                          |

**Router-only routes are allowed.** A new `createRoute` without an `AppRoute` /
nav entry fails check with “Added”, then update succeeds. Hidden/detail URLs do
not need AppRoute. Incomplete AppRoute-only adds still refuse update.

## When check fails

**Intentional change**

1. From the frontend workspace (or `@syntara/ui` package): `npm run route-baseline:update`
2. Review `scripts/route-baseline/manifest.gen.json`
3. Commit the updated manifest in the same PR

**Unintentional drift**

Fix the route sources (`src/app/routes/*`, `AppRoute.tsx`, `navigationItems.tsx`,
`tanstackRouteTree.tsx`, `App.tsx`, or `routes/__root.ts`), then re-run
`npm run route-baseline:check`.

## Collector notes

- Redirect targets may be string literals **or** `AppRoute.Foo.Bar` references.
- Mounted modules may be reached through static `export { ... } from './other'`
  re-exports under `src/app/routes/` (text follow, not runtime import).
- Search params, page JSX, and non-redirect `beforeLoad` logic are out of scope.

## Known exception

`/auth/test-signin-callback` is `kind: "app"` — handled in `App.tsx` before the
router so the identity-provider test-signin popup skips `AppShell`. Planned
follow-up after the file-based routing migration: move it to a public /
layout-less TanStack route, or revisit and keep the escape hatch.
