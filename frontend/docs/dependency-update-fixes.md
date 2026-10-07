# Dependency update compatibility fixes

The October 2026 frontend dependency update prevented Vite from loading its
configuration. The UI requested Vite 8 and React plugin 6, but the root npm
override still installed Vite 7. React plugin 6 imports `vite/internal`, which
Vite 7 does not export.

## Changes

- Align the root Vite override with the UI's Vite 8 dependency.
- Preserve React Compiler using React plugin 6's documented
  `reactCompilerPreset()` and `@rolldown/plugin-babel` integration in the app,
  unit-test, and browser-test configurations. Declare the Babel peer
  dependencies in the UI workspace.
- Use Dagre 3's named `Graph` type export in the workflow layout engine.
- Align the root Playwright overrides with `@playwright/test` 1.63.0 and
  regenerate the lockfile. After upgrading Playwright, run
  `npm exec --workspace=@syntara/ui -- playwright install chromium` to install
  its matching browser.
- Apply the formatting required by Prettier 3.9 and update the documented
  TypeScript and Vite versions.
- Set each package's ESLint TypeScript root explicitly so the upgraded parser
  can lint staged files from multiple packages in one pre-commit invocation.
- Adapt navigation to the updated PatternFly API and reuse the existing router
  link adapter for client-side navigation and modified clicks.
- Hold Unicorn at 64.0.0, the effect-analysis plugin at 0.10.2, and the Fast
  Refresh lint plugin at 0.5.4. Their newer releases introduce lint-policy
  changes across existing code, including condition reordering that requires
  manual review. Upgrade these separately from the runtime compatibility repair.

The other dependency upgrades and existing navigation edits are retained.

## Reproduction and verification

The smallest startup reproduction is:

```sh
node --input-type=module -e "await import('@vitejs/plugin-react')"
```

Before the fix it fails with `ERR_PACKAGE_PATH_NOT_EXPORTED` for `vite/internal`.
After installing the corrected dependency graph it succeeds. The development
server and Storybook also start, and the production build succeeds with React
Compiler enabled. Existing layout and navigation tests cover the behavior
affected by the Dagre upgrade; no application test can replace validating the
installed Vite/plugin combination.

Verified after the runtime fixes:

- Production build and Vite/Storybook startup succeed.
- UI tests: 910 files passed, 14,675 tests passed, one skipped, one todo.
- Mock API tests: three files and seven tests passed.
- A Playwright smoke check renders the workflows list and correct page title
  with no JavaScript errors or axe accessibility violations.
- `npm run check` passes: Mermaid validation, TypeScript, ESLint, formatting,
  and Knip. ESLint reports 309 warnings and zero errors; the changed build/test
  configurations and layout engine lint without warnings.

Run `npm run check` and `npm test` after installation for the broader static
analysis and regression checks. These checks need permission to bind local
ports for mock API tests.

## Local startup configuration

If login requests return HTTP 502, check whether the configured backend is
running. To use the mock API explicitly, run:

```sh
VITE_API_URL=http://localhost:3000 npm start
```

Environment variables override `.env.local` without changing the file. Ensure
ports 3000, 5173, and 5174 are available before starting the development services.

References: [React plugin's compiler integration](https://github.com/vitejs/vite-plugin-react/tree/main/packages/plugin-react#babel-react-compiler),
[Vite 8 migration](https://vite.dev/guide/migration).
