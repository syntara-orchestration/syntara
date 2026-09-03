# Route baseline

`manifest.gen.json` is the UI route compatibility contract.

To update after an intentional route change:

```bash
npm run route-baseline:update
```

Then commit the regenerated `manifest.gen.json` in the same PR.

To verify locally:

```bash
npm run route-baseline:check
```

## Known exception

`/auth/test-signin-callback` is `kind: "app"` — handled in `App.tsx` before the
router so the identity-provider test-signin popup skips `AppShell`. Planned
follow-up after the file-based routing migration: move it to a public /
layout-less TanStack route, or revisit and keep the escape hatch. See
`frontend/docs/file-based-routing-migration-plan.md` (Follow-ups).
