# Frontend dependency upstream research

Reviewed: 2026-10-07. Scope: the frontend root and its UI, mock API, and contracts workspaces. This note supports the dependency usage audit with primary upstream sources and selected local evidence. Recommendations are proposed changes; no dependency manifests or application code were changed, and no installation or tests were run for this research. No existing research directory convention was found under `frontend/docs/`.

## Native replacements worth considering

### `uuid`: replace v4 generation, subject to browser origin support

The direct `uuid` declarations occur in the UI and mock API. Observed callers generate v4 identifiers, including `src/utils/generateUUID.ts`, `src/utils/expressions/defaults.ts`, and mock `src/handlers.ts`. Node provides `randomUUID()` in `node:crypto`, returning a cryptographically generated v4 UUID. It has existed since Node 14.17.0, below this repository's CI Node 22.13.0 and container Node 24 versions. [Node documentation](https://nodejs.org/download/release/latest-v14.x/docs/api/crypto.html#crypto_crypto_randomuuid_options)

The browser alternative is `crypto.randomUUID()`. The Web Cryptography specification explicitly marks it `SecureContext`, while `getRandomValues()` has no such restriction. Therefore browser replacement is conditional on supported deployment origins: non-localhost HTTP deployments can lose UUID generation. Verify deployment policy and supported browsers before removing the browser dependency. Preserve the existing `generateUUID()` seam and v4 behavior. The installed `uuid/dist/v4.js` already delegates its ordinary no-options call to native `crypto.randomUUID()` when present, so this is primarily dependency simplification, with no demonstrated performance benefit. [Web Cryptography specification](https://w3c.github.io/webcrypto/#Crypto-method-randomUUID)

Replacing both direct declarations does not prove `uuid` disappears from the lockfile: transitive consumers exist, including the root `istanbul-lib-processinfo` override.

### `dotenv`: small Node replacement with behavior checks

This package is used: `packages/syntara-ui/playwright.config.ts` loads `.env.local` with `config({ path, quiet: true })`. Node's `process.loadEnvFile()` supplies equivalent basic environment loading and accepts a URL. It is available on the pinned CI version, where the API still has active-development status, and is stable beginning with Node 24.10.0. [Pinned Node 22.13 documentation](https://nodejs.org/download/release/v22.13.0/docs/api/process.html#processloadenvfilepath), [Node 24 documentation](https://nodejs.org/download/release/latest-v24.x/docs/api/process.html#processloadenvfilepath)

Proposed migration: use the native loader and preserve optional absence of `.env.local`, existing process-environment precedence, and parsing behavior relied on by local development. Do not blindly replace the call: current `dotenv.config()` returns a missing-file error without throwing, whereas loading a nonexistent file through the native API needs explicit handling. URL support also avoids the current `.pathname` path conversion. This reduces one direct development dependency; Vite's own environment parser still uses dotenv internally. [Vite 7.3.2 environment-loader source](https://github.com/vitejs/vite/blob/v7.3.2/packages/vite/src/node/env.ts)

## Existing-library consolidation

### `nyc`: replace coverage orchestration with Vitest's own merge support

`nyc` is used by `scripts/merge-coverage.js` and the UI's `test:coverage:report` script. The merge script collects shard `coverage-final.json` files, invokes report generation, and enforces an 85% global statements threshold. `.github/workflows/ci-frontend.yml` uploads four shard artifacts and runs this merge. Removal without replacement would break a CI gate.

Vitest 4.1.10 documents its blob reporter and `--merge-reports` for runs across machines. Its exact-version core source also initializes the coverage provider and calls `coverageProvider.mergeReports(coverages)`, confirming that coverage merging is part of the operation. This is a credible consolidation candidate because Vitest and its V8 coverage provider are already direct dependencies. [Vitest 4.1.10 reporter documentation](https://github.com/vitest-dev/vitest/blob/v4.1.10/docs/guide/reporters.md#blob-reporter), [Vitest 4.1.10 merge implementation](https://github.com/vitest-dev/vitest/blob/v4.1.10/packages/vitest/src/node/core.ts)

Migration needs new blob artifacts and associated coverage data, CI upload/download changes, reporter configuration, and the 85% threshold at the merge stage. Preserve coverage scope, HTML/LCOV/JSON reports, failure behavior, and reported totals. The existing JSON artifacts are not interchangeable with blobs. Treat this as a separate tooling change requiring validation of combined multi-shard coverage, rather than immediate unused-package removal.

### `@vitest/browser`: reconcile the optional browser configuration

The UI declares `@vitest/browser`, but its `vitest.browser.config.ts` imports `@vitest/browser-playwright`, which is absent from direct declarations. An ambient declaration in `types/vitest-browser-playwright.d.ts` substitutes `any` for the missing provider. The configuration advertises `npm run test:browser`, but the UI manifest does not define that script, and a file search found no `*.browser.test.*` files.

Vitest 4's official release instructions moved browser providers into separate packages, including `@vitest/browser-playwright`. The current browser-mode guide uses that package's factory. [Vitest 4 release announcement](https://vitest.dev/blog/vitest-4), [Browser-mode installation](https://vitest.dev/guide/browser/)

Decide whether browser component testing remains intended. If retained, declare the correct provider, restore a documented executable workflow, and use actual package types. If retired, removing the package alone leaves stale configuration and type shims; removal should address these together while observing the repository's feature-preservation instructions. Existing Playwright E2E coverage does not automatically replace browser component tests.

## Upstream migrations that need a product-preserving plan

### Legacy `@dnd-kit/*`: plan migration to current dnd-kit

All four direct packages (`core`, `modifiers`, `sortable`, `utilities`) are imported by `SwitchNodeForm.tsx`. Official docs now label the core family legacy and recommend the current version. The upstream migration guide targets `@dnd-kit/react`, supplies a new provider and event model, and replaces `SortableContext` with automatic sortable registration. It maps vertical-axis restriction to `@dnd-kit/abstract/modifiers` and sorting helpers to `@dnd-kit/helpers`. [Legacy installation notice](https://dndkit.com/legacy/introduction/installation/), [Migration guide](https://dndkit.com/react/guides/migration/)

This has a bounded source footprint, but is an API migration, not an import rename. Preserve switch case ordering, drag handles, keyboard sorting, screen-reader feedback, focus, and pointer activation behavior. The legacy label does not establish a vulnerability or a removal deadline. Fewer direct manifest entries would not prove fewer transitive packages or a smaller production bundle.

### `jmespath` and `@types/jmespath`: investigate compatibility before adopting a fork

The original project's latest visible tag is 0.16.0 from January 19, 2022. This is a release-age signal; it does not prove abandonment or insecurity. Its search and compile APIs are actively used for OIDC group mapping in the UI and mock API. [Original upstream tags](https://github.com/jmespath/jmespath.js/tags), [Original API documentation](https://github.com/jmespath/jmespath.js)

`@jmespath-community/jmespath` is a possible typed alternative with search/compile APIs and ESM/CommonJS builds. Its upstream README also documents language extensions, experimental ternary syntax, and an MPL-2.0 license. These differences make it a compatibility investigation, not a drop-in recommendation. [Alternative upstream documentation](https://github.com/jmespath-community/typescript-jmespath)

Validate expressions, accepted syntax, errors, and output against the real backend evaluator before changing either frontend consumer. UI validation must not accept expressions the backend rejects. No current maintenance cadence, bundle-size benefit, or security improvement was established for the fork; replacing solely to eliminate the separate type package is insufficient justification.

## Packages that should not be removed from superficial evidence

- **`date-fns`** supplies ISO parsing, durations, history labels, calendar-day operations, and credential-expiration calculations. PatternFly timestamps already handle common displayed timestamps, but that does not replace these computations. Native formatting alone is not equivalent; retain unless an explicit behavior-preserving simplification justifies the work.
- **`fuse.js`** is used by the glossary via `useFuse`, with fuzzy threshold 0.7 and token search. A native substring filter changes matching and ranking, so it would be a product behavior change rather than straightforward dependency removal.
- **Root `@emnapi/core` / `@emnapi/runtime`** have a verified reason to remain direct declarations. The lockfile records both as required peers of `@napi-rs/wasm-runtime` 1.2.0. Repository commit `257cb5cd698dde3acdcdbbc433c942d4bf32ba9f` explicitly added these pins because npm 11 rewrote the lockfile without WebAssembly peer entries and npm 10 `npm ci` then failed in contract-drift CI. Keep them unless a separate change demonstrates that the cross-version installation regression is resolved. Import absence is irrelevant to this recorded purpose.
- **PatternFly, TanStack Query/Router, Zustand/zundo, React Hook Form/Zod, OpenAPI tooling, React Flow, and Dagre** implement established project conventions or substantive product capabilities. This upstream pass established no reason to replace them. Avoid introducing parallel libraries or hand-written substitutes without a specific measured benefit.

## Evidence limits

This research did not execute Knip, perform an install, measure bundle size, validate a migration, or assess every dependency's advisory history. Static absence of imports is not proof that a script, peer dependency, optional platform binding, or plugin is unused. Candidate ordering should combine this upstream evidence with the full usage inventory and migration effort, keeping claimed direct-declaration savings separate from lockfile, installation, and production-bundle savings.
