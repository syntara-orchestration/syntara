# Frontend feature flags

## Strategy

A feature flag enables temporary behavior in the frontend. A flag does not grant access or protect data. The backend must still check permissions.

Flags are off unless browser local storage sets a registered flag to the string value `true` under its `syn.flags.<name>` key. `FeatureFlagsProvider` reads a snapshot when it mounts. Reload the page after you change a saved value.

## Add and use a flag

Add each flag name to `FEATURE_FLAG_NAMES` in `packages/syntara-ui/src/utils/feature-flags.ts`. TypeScript builds the `FeatureFlag` union from this list. It rejects names that are not in the list. `FeatureFlagConfig` is a partial record of enabled states for those keys.

Use `useFeatureFlag` in a React component:

```tsx
import { useFeatureFlag } from '../../providers/use-feature-flag'

function Example() {
  const isEnabled = useFeatureFlag('workflow_builder_qol')
  return isEnabled ? <span>Feature enabled</span> : null
}
```

The app provides `FeatureFlagsProvider`. Tests that render a component with this hook must also render the provider.

Do not cast a string to `FeatureFlag` to skip the TypeScript check.

## Set a local value

Use the browser developer console to turn on a registered flag:

```js
localStorage.setItem('syn.flags.workflow_builder_qol', 'true')
location.reload()
```

Set the value to `false` to turn it off:

```js
localStorage.setItem('syn.flags.workflow_builder_qol', 'false')
location.reload()
```

Remove one saved value to turn that flag off:

```js
localStorage.removeItem('syn.flags.workflow_builder_qol')
location.reload()
```

Remove every saved feature flag value to turn all flags off:

```js
for (const key of Object.keys(localStorage)) {
  if (key.startsWith('syn.flags.')) localStorage.removeItem(key)
}
location.reload()
```

The module checks each `syn.flags.` key and value in storage. A missing flag is off. An unknown flag name or a value other than the strings `true` and `false` turns all flags off. Only the string value `true` turns a flag on.

The previous `flags.<name>` keys and the former `feature-flags` JSON key are no longer read. Remove stale values with `localStorage.removeItem('flags.workflow_builder_qol')` and `localStorage.removeItem('feature-flags')` if needed.

## Test a flagged component

In tests, do not mock `useFeatureFlag`. Set `localStorage` before you render `FeatureFlagsProvider`. This tests storage validation and context wiring. The provider reads the values when it mounts. In this example, `Example` is the flagged component from the earlier example.

```tsx
import { render } from '@testing-library/react'

import { FeatureFlagsProvider } from '../../providers/feature-flags-provider'
import { toFeatureFlagKey } from '../../utils/feature-flags'

localStorage.setItem(toFeatureFlagKey('workflow_builder_qol'), 'true')

render(
  <FeatureFlagsProvider>
    <Example />
  </FeatureFlagsProvider>
)
```

Clear the storage key after each test so one test does not affect another.

## Gate a route

Use TanStack Router's typed router context when a flag controls route loading. The app passes the `FeatureFlagsProvider` snapshot to `<RouterProvider context={...} />`. Read flags from `context.featureFlags` in `beforeLoad`; do not read local storage there or call a React hook. This works with code-based routes created with `createRoute`; file-based routing is not required.

```tsx
import { createRootRouteWithContext, createRoute, redirect } from '@tanstack/react-router'

import type { FeatureFlagConfig } from '../../utils/feature-flags'

type AppRouterContext = {
  featureFlags: FeatureFlagConfig
}

const rootRoute = createRootRouteWithContext<AppRouterContext>()({ component: App })

const featureRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/feature-example',
  beforeLoad: ({ context }) => {
    if (context.featureFlags.workflow_builder_qol !== true) {
      throw redirect({ to: '/workflows', replace: true })
    }
  },
  component: Example,
})
```

Create the router with a safe default:

```tsx
const tanstackRouter = createRouter({
  routeTree,
  context: { featureFlags: {} },
})
```

Then inject the provider snapshot from React:

```tsx
import { RouterProvider } from '@tanstack/react-router'

import { useFeatureFlags } from '../providers/use-feature-flag'
import { tanstackRouter } from './tanstackRouter'

function AppRouter() {
  const featureFlags = useFeatureFlags()
  return <RouterProvider router={tanstackRouter} context={{ featureFlags }} />
}
```

The root route context and initial router context keep the values typed. React components should continue to use `useFeatureFlag`; route guards should use `context.featureFlags`.

Hide the route's navigation link when the flag is off. A route guard controls frontend navigation. It does not protect backend data or actions.

## Further reading

- [TanStack Router context](https://tanstack.com/router/latest/docs/guide/router-context)
- [GitLab feature flag development guidance](https://docs.gitlab.com/development/feature_flags/)
