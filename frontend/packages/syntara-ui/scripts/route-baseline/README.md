# Route baseline

`manifest.gen.json` records the UI's public route contract.

## Commands

```bash
npm run route-baseline:check
npm run route-baseline:update
```

The frontend CI workflow checks this manifest. Regenerate and review it with
every intentional URL or redirect change.

## Source model

The collector reads the mounted code-based TanStack route tree, the app-level
sign-in callback path, the not-found fallback, and navigation route references.
It resolves route exports through the TypeScript compiler API without importing
application modules or CSS. Unresolved route references, cycles, unsupported
route factories, and unmounted route modules fail with source locations.

Navigation entries must use references exported from
`src/app/routes/routeReferences.ts`. Their path templates are resolved from the
actual `createRoute` declarations. Navigation group identities have no target
route and are ignored by route parity.

Route definitions own URL literals. Search parameters, page content, and
non-redirect `beforeLoad` logic are outside this compatibility contract.

## Known app-level route

`/auth/test-signin-callback` is handled by `App.tsx` before the authenticated
router mounts, so the identity-provider popup can complete sign-in. Its path is
defined in `src/app/routes/appLevelPaths.ts` and included in the manifest as
`kind: "app"`.
