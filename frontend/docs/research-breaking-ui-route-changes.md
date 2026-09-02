# Research: detecting breaking UI route changes in CI

## Recommendation

Treat browser URLs as a compatibility contract. Removing or renaming a route,
or changing its parameters, can break bookmarks, deep links, documentation, and
links used outside this repository.

Generate a stable route manifest from the TanStack Router definitions and
compare the pull request with its target branch. TanStack Router provides the
route list and type-safe navigation, but it does not provide a built-in CI check
for breaking route changes. The repository must define that policy and check.

## What TanStack Router provides

TanStack Router supports code-based and file-based route trees. File-based
routing generates a route-tree source file. At runtime, the router also keeps
indexes such as `routesByPath`.

- [Route trees](https://tanstack.com/router/latest/docs/routing/route-trees)
- [File-based routing](https://tanstack.com/router/latest/docs/routing/file-based-routing)
- [Creating a router](https://tanstack.com/router/latest/docs/guide/creating-a-router)
- [Router source (`routesByPath`)](https://github.com/TanStack/router/blob/main/packages/router-core/src/router.ts)
- [Type safety](https://tanstack.com/router/latest/docs/guide/type-safety)

Type-safe links and navigation calls can find callers inside this repository.
They cannot find bookmarks, documentation links, customer automation, or other
consumers outside the TypeScript program.

Route masking and URL rewrites can make an internal route different from the
public URL. The manifest must say whether it records internal paths, public
browser URLs, or both.

- [Route masking](https://tanstack.com/router/latest/docs/guide/route-masking)
- [URL rewrites](https://tanstack.com/router/latest/docs/guide/url-rewrites)

## What this means for this repository

This UI uses code-based route definitions in
`packages/syntara-ui/src/app/routes/`, assembled by
`packages/syntara-ui/src/app/tanstackRouteTree.tsx`. It also has a central
`AppRoute` catalog and a visual-regression page registry. File-based routing
would make routes easier to find, but it is not required for the CI check.

There are about 47 `createRoute()` definitions in 10 route modules. The page
components are already mostly isolated and lazy-loaded. The main migration work
would be changing route definitions and navigation wiring, not rewriting pages.

The first CI check should extract a manifest from the existing route definitions
or from a small route-contract module. For example:

```json
{
  "/workflows": { "kind": "static" },
  "/workflows/$workflowId": { "kind": "parameterized" }
}
```

Before comparison, convert `:id` and `$id` to one standard form.

## CI options

| Option                                 | Good for                                            | Limitation                                                                            |
| -------------------------------------- | --------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Changed-file heuristic                 | Very small initial check                            | Misses indirect route definitions and cannot classify behavior reliably               |
| Runtime extraction from `routesByPath` | Reflects the assembled router                       | Requires executing application code in Node and relies on a lower-level runtime index |
| Static generated manifest              | Deterministic, reviewable, and easy to diff         | Requires policy for redirects, rewrites, masks, and dynamic parameters                |
| E2E checks against a URL inventory     | Verifies that important public URLs still load      | Slower, potentially flaky, and only covers maintained URLs                            |
| TanStack file-based routing migration  | Makes route ownership and generation highly visible | Larger migration; still needs a compatibility diff and migration policy               |

## CI workflow

1. Generate a normalized route manifest for the pull request.
2. Generate the same manifest for the target branch.
3. Compare route templates, parameter names, and any declared public aliases.
4. Report removed or incompatible entries in the CI log and job summary.
5. Fail by default for removals, renames, and incompatible parameter changes.
6. Allow an intentional break only through an explicit, reviewed migration
   entry that records the old route and its redirect/replacement.
7. Add tests for additions, removals, renames, parameter changes, redirects,
   and normalization.

Use a checked-out `git diff BASE...HEAD` or another local comparison. Do not
rely only on a changed-files API: GitHub's compare-commits API has a 300-file
limit. GitHub Actions supports path filters, job outputs, and job summaries.

- [GitHub Actions workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [GitHub compare commits API](https://docs.github.com/en/rest/commits/commits#compare-two-commits)
- [GitHub job summaries](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#adding-a-job-summary)

## Decisions to make

- Is a route with the same shape but a renamed parameter breaking? Recommended:
  yes.
- Is changing only search-parameter validation breaking? Decide per parameter;
  required/removed parameters should be treated as breaking.
- Should a server redirect preserve compatibility? Recommended: yes, when the
  redirect is tested and recorded in the migration allowlist.
- Should hidden/detail routes count? Recommended: yes if users can reach them
  through links or bookmarks. Being hidden from navigation does not make a URL
  safe to break.
- Does the contract include route component behavior, or only URL reachability?
  Start with URL reachability; use E2E and visual tests for behavior.

## Suggested exploration ticket

Investigate and implement a route-manifest compatibility check in frontend CI,
using the existing TanStack code-based route tree. Define route normalization,
public URL aliases, redirect/migration approvals, search-parameter rules, and
the CI failure policy. Track file-based routing as a separate migration; it may
make routes easier to find, but it is not required for the detector.
