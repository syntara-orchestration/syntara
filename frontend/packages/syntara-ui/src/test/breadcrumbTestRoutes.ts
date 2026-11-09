import type { AppRouteNavigationOptions } from '../app/routeNavigationOptions'
import * as routeRefs from '../app/routes/routeReferences'

export const breadcrumbTestRoutes = {
  accessManagement: { to: routeRefs.accessManagementRoute.fullPath } satisfies AppRouteNavigationOptions,
  users: { to: routeRefs.accessManagementUsersRoute.fullPath } satisfies AppRouteNavigationOptions,
  groups: { to: routeRefs.accessManagementGroupsRoute.fullPath } satisfies AppRouteNavigationOptions,
  projects: { to: routeRefs.accessManagementProjectsRoute.fullPath } satisfies AppRouteNavigationOptions,
  project: (projectId = 'project-1') =>
    ({ to: routeRefs.projectDetailRoute.fullPath, params: { projectId } }) satisfies AppRouteNavigationOptions,
  workflows: { to: routeRefs.workflowsRoute.fullPath } satisfies AppRouteNavigationOptions,
  approvals: { to: routeRefs.approvalsRoute.fullPath } satisfies AppRouteNavigationOptions,
  integrations: { to: routeRefs.integrationsRoute.fullPath } satisfies AppRouteNavigationOptions,
  credentials: { to: routeRefs.credentialsRoute.fullPath } satisfies AppRouteNavigationOptions,
  configuration: { to: routeRefs.configurationOverviewRoute.fullPath } satisfies AppRouteNavigationOptions,
  settings: { to: routeRefs.settingsRoute.fullPath } satisfies AppRouteNavigationOptions,
  settingsCategory: (category = 'infrastructure') =>
    ({ to: routeRefs.settingsCategoryRoute.fullPath, params: { category } }) satisfies AppRouteNavigationOptions,
  identityProviders: { to: routeRefs.authenticationRootRoute.fullPath } satisfies AppRouteNavigationOptions,
  user: (userId = 'user-1') =>
    ({ to: routeRefs.userDetailRoute.fullPath, params: { userId } }) satisfies AppRouteNavigationOptions,
} as const
