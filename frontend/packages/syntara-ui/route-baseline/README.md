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
