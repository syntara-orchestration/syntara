/**
 * Route role recorded in the baseline manifest.
 *
 * - `page` — normal UI route with a component
 * - `redirect` — route that only redirects to another path
 * - `fallback` — catch-all for unmatched URLs
 * - `app` — handled outside the TanStack route tree (for example in `App.tsx`)
 */
export type RouteKind = 'page' | 'redirect' | 'fallback' | 'app'

/**
 * One normalized route in the compatibility contract.
 *
 * Path templates always use TanStack `$param` syntax. The committed manifest
 * sorts entries by `template`.
 */
export type NormalizedRoute = {
  /** Canonical pathname template, for example `/users/$userId`. */
  template: string
  /** Ordered parameter names extracted from `template`. */
  parameters: string[]
  /** How this route behaves at runtime. */
  kind: RouteKind
  /** Target path when `kind` is `redirect` or `fallback`. */
  redirectTo?: string
  /**
   * Sources that declare this template.
   * The manifest is built from router definitions; AppRoute and navigation
   * annotations are added for review and consistency checks.
   */
  sources: Array<'router' | 'appRoute' | 'navigation' | 'app'>
}

/** Standard banner written into every generated manifest. */
export const ROUTE_MANIFEST_NOTICE =
  'GENERATED FILE. Do not edit by hand. Regenerate with: npm run route-baseline:update --prefix packages/syntara-ui'

/**
 * Committed route baseline artifact written to `route-baseline/manifest.json`.
 */
export type RouteManifest = {
  /**
   * Human-readable warning that this file is generated.
   * JSON has no comments; keep this field so the notice is visible in the file.
   */
  notice: typeof ROUTE_MANIFEST_NOTICE
  /** Manifest schema version. Bump only when the JSON shape changes. */
  version: 1
  /** Deterministically sorted route entries. */
  routes: NormalizedRoute[]
}
