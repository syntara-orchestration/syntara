import { z } from 'zod'

/** Non-null, non-array object — used when walking unknown nested catalogs. */
export const plainObjectSchema = z.record(z.string(), z.unknown())

/** Key used for the generated-file banner. Looks like a comment in JSON. */
export const ROUTE_MANIFEST_COMMENT_KEY = '//' as const

/** Standard banner written into every generated manifest. */
export const ROUTE_MANIFEST_NOTICE =
  'GENERATED FILE. Do not edit by hand. Regenerate with: npm run route-baseline:update'

/**
 * Route role recorded in the baseline manifest.
 *
 * - `page` — normal UI route with a component
 * - `redirect` — route that only redirects to another path
 * - `fallback` — catch-all for unmatched URLs
 * - `app` — bookmarkable path handled in `App.tsx` before `RouterProvider`
 *   (today only `/auth/test-signin-callback`; not part of the TanStack tree)
 */
export const routeKindSchema = z.enum(['page', 'redirect', 'fallback', 'app'])

/**
 * Where a path template was discovered when building the manifest.
 *
 * - `router` — `createRoute` in `src/app/routes`
 * - `appRoute` — declared in the `AppRoute` catalog
 * - `navigation` — linked from `navigationItems`
 * - `app` — handled in `App.tsx` before the router mounts
 */
export const routeSourceSchema = z.enum(['router', 'appRoute', 'navigation', 'app'])

/**
 * One normalized route in the compatibility contract.
 *
 * Path templates always use TanStack `$param` syntax.
 * `parameters` lists path params only (search params are out of scope for Phase 0).
 */
export const normalizedRouteSchema = z.object({
  /** Canonical pathname template, for example `/users/$userId`. */
  template: z.string().min(1),
  /** Ordered path-parameter names extracted from `template`. */
  parameters: z.array(z.string()),
  /** How this route behaves at runtime. */
  kind: routeKindSchema,
  /** Target path when `kind` is `redirect` or `fallback`. */
  redirectTo: z.string().min(1).optional(),
  /**
   * Sources that declare this template.
   * The manifest is built from router definitions; AppRoute and navigation
   * annotations are added for review and consistency checks.
   */
  sources: z.array(routeSourceSchema).min(1),
})

/**
 * Committed route baseline artifact written to `route-baseline/manifest.gen.json`.
 */
export const routeManifestSchema = z.object({
  /**
   * Human-readable warning that this file is generated.
   * JSON has no comments; the `//` key makes the banner read like one.
   */
  [ROUTE_MANIFEST_COMMENT_KEY]: z.literal(ROUTE_MANIFEST_NOTICE),
  /** Manifest schema version. Bump only when the JSON shape changes. */
  version: z.literal(1),
  /** Deterministically sorted route entries. */
  routes: z.array(normalizedRouteSchema),
})

export type PlainObject = z.infer<typeof plainObjectSchema>
export type RouteKind = z.infer<typeof routeKindSchema>
export type RouteSource = z.infer<typeof routeSourceSchema>
export type NormalizedRoute = z.infer<typeof normalizedRouteSchema>
export type RouteManifest = z.infer<typeof routeManifestSchema>
