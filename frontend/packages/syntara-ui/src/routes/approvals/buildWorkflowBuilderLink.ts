import type { AppRouteNavigationOptions } from '../../app/routeNavigationOptions'
import * as routeRefs from '../../app/routes/routeReferences'

/** Builds typed workflow builder navigation for an approval's workflow and optional version. */
export function buildWorkflowBuilderLink(
  workflowId: string,
  workflowVersion: number | null | undefined
): AppRouteNavigationOptions {
  const destination = { to: routeRefs.builderEditRoute.fullPath, params: { workflowId } }
  return workflowVersion != null ? { ...destination, search: { version: String(workflowVersion) } } : destination
}
