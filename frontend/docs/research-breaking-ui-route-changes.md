# Research: detecting breaking UI route changes in CI

## Conclusion

Treat browser-visible UI routes as a compatibility contract. A route removal,
rename, or incompatible parameter change can break bookmarks, deep links,
documentation, and links held by systems outside this repository.

The recommended design is a deterministic route manifest generated from the
application's TanStack Router definitions, compared between the pull request
head and its target branch. TanStack Router can supply the route inventory and
compile-time navigation safety, but it does not provide a turnkey breaking
route-change checker. The compatibility policy and CI comparison should remain
repository-owned.

## What TanStack Router provides

TanStack Router supports both code-based and file-based route trees. Its
file-based generator creates a route-tree source file, while the runtime router
maintains route indexes such as `routesByPath`.

- [Route trees](https://tanstack.com/router/latest/docs/routing/route-trees)
- [File-based routing](https://tanstack.com/router/latest/docs/routing/file-based-routing)
- [Creating a router](https://tanstack.com/router/latest/docs/guide/creating-a-router)
- [Router source (`routesByPath`)](https://github.com/TanStack/router/blob/main/packages/router-core/src/router.ts)
- [Type safety](https://tanstack.com/router/latest/docs/guide/type-safety)

Type-safe links and navigation calls help find in-repository callers of a
changed route. They cannot find bookmarks, documentation links, customer
automation, or other consumers outside the TypeScript program.

TanStack Router's route masking and URL rewrite features also mean that an
internal route definition is not necessarily the same thing as the public URL.
The manifest must explicitly decide whether it records internal paths, public
browser URLs, or both.

- [Route masking](https://tanstack.com/router/latest/docs/guide/route-masking)
- [URL rewrites](https://tanstack.com/router/latest/docs/guide/url-rewrites)

## Current-repository implications

This UI currently uses code-based route definitions in
`packages/syntara-ui/src/app/routes/`, assembled by
`packages/syntara-ui/src/app/tanstackRouteTree.tsx`. It also has a centralized
`AppRoute` catalog and a visual-regression page registry. A migration to
TanStack file-based routing would make route ownership more conventional, but
it is not necessary to solve CI detection and would be a larger architectural
change.

The current inventory is approximately 47 `createRoute()` definitions across
10 route modules. The route components themselves are mostly already isolated
and lazy-loaded, so the main migration cost is route-definition and navigation
wiring rather than rewriting page UI.

The first implementation should extract a manifest from the existing route
definitions or from a small explicit route-contract module. Example:

```json
{
  "/workflows": { "kind": "static" },
  "/workflows/$workflowId": { "kind": "parameterized" }
}
```

Normalize the current `:id` and TanStack `$id` spellings to one canonical
representation before comparing manifests.

## CI options

| Option                                 | Strength                                            | Limitation                                                                            |
| -------------------------------------- | --------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Changed-file heuristic                 | Very small initial check                            | Misses indirect route definitions and cannot classify behavior reliably               |
| Runtime extraction from `routesByPath` | Reflects the assembled router                       | Requires executing application code in Node and relies on a lower-level runtime index |
| Static generated manifest              | Deterministic, reviewable, and easy to diff         | Requires policy for redirects, rewrites, masks, and dynamic parameters                |
| E2E checks against a URL inventory     | Verifies that important public URLs still load      | Slower, potentially flaky, and only covers maintained URLs                            |
| TanStack file-based routing migration  | Makes route ownership and generation highly visible | Larger migration; still needs a compatibility diff and migration policy               |

## Recommended workflow

1. Generate a normalized route manifest for the PR revision.
2. Generate the same manifest for the target branch.
3. Compare route templates, parameter names, and any declared public aliases.
4. Report removed or incompatible entries in the CI log and job summary.
5. Fail by default for removals, renames, and incompatible parameter changes.
6. Allow an intentional break only through an explicit, reviewed migration
   entry that records the old route and its redirect/replacement.
7. Add tests for additions, removals, renames, parameter changes, redirects,
   and normalization.

Use a checked-out `git diff BASE...HEAD` or equivalent local comparison rather
than relying solely on a changed-files API. GitHub's compare-commits API has a
300-file limit. GitHub Actions supports workflow path filters, job outputs,
and job summaries that can host the result.

- [GitHub Actions workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [GitHub compare commits API](https://docs.github.com/en/rest/commits/commits#compare-two-commits)
- [GitHub job summaries](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#adding-a-job-summary)

## Policy questions for follow-up

- Is a route with the same shape but a renamed parameter breaking? Recommended:
  yes, unless parameter names are explicitly declared non-contractual.
- Is changing only search-parameter validation breaking? Decide per parameter;
  required/removed parameters should be treated as breaking.
- Should a server redirect preserve compatibility? Recommended: yes, when the
  redirect is tested and recorded in the migration allowlist.
- Should hidden/detail routes count? Recommended: yes if users can reach them
  through links or bookmarks; visibility in navigation is not a compatibility
  boundary.
- Does the contract include route component behavior, or only URL reachability?
  Start with URL reachability; use E2E and visual tests for behavior.

## Recommendation for the exploration ticket

Investigate and implement a route-manifest compatibility check in frontend CI,
backed by the existing TanStack code-based route tree. Define canonical route
normalization, public URL aliases, redirect/migration acknowledgements, search
parameter compatibility, and the failure/reporting policy. Reassess a
file-based TanStack Router migration separately; it may improve route
discoverability but is not required for the detector.
