# Route baseline

`manifest.json` is the UI route compatibility contract.

## Do not edit `manifest.json` by hand

This file is generated. Hand edits are overwritten and will fail CI/tests when
they drift from the live route sources.

To update after an intentional route change:

```bash
npm run route-baseline:update --prefix packages/syntara-ui
```

Then commit the regenerated `manifest.json` in the same PR.

To verify locally:

```bash
npm run route-baseline:check --prefix packages/syntara-ui
# or
npx vitest run src/app/route-baseline --prefix packages/syntara-ui
```
