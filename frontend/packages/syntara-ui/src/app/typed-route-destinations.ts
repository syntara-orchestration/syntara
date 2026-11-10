import type { NavigateOptions, useNavigate } from '@tanstack/react-router'

import type { tanstackRouter } from './tanstackRouter'

type AppRouter = typeof tanstackRouter
type TypedDestination<TTo extends string, TParams extends Record<string, string>> = {
  to: TTo
  params: TParams
} & Pick<NavigateOptions<AppRouter, string, TTo>, 'to' | 'params'>

export const ACCESS_MANAGEMENT_DETAIL_ROUTES = {
  user: '/system-administration/access-management/users/$userId',
  group: '/system-administration/access-management/groups/$groupId',
  project: '/system-administration/access-management/projects/$projectId',
  serviceAccount: '/system-administration/access-management/service-accounts/$serviceAccountId',
} as const

export type UserDetailDestination = TypedDestination<typeof ACCESS_MANAGEMENT_DETAIL_ROUTES.user, { userId: string }>

export type GroupDetailDestination = TypedDestination<typeof ACCESS_MANAGEMENT_DETAIL_ROUTES.group, { groupId: string }>

export type ProjectDetailDestination = TypedDestination<
  typeof ACCESS_MANAGEMENT_DETAIL_ROUTES.project,
  { projectId: string }
>

export type ServiceAccountDetailDestination = TypedDestination<
  typeof ACCESS_MANAGEMENT_DETAIL_ROUTES.serviceAccount,
  { serviceAccountId: string }
>

export type AccessManagementDetailDestination =
  UserDetailDestination | GroupDetailDestination | ProjectDetailDestination | ServiceAccountDetailDestination

/** Existing string destinations remain supported while typed destinations are adopted gradually. */
export type NavigationTarget = string | AccessManagementDetailDestination

type RouterNavigate = ReturnType<typeof useNavigate>

/** Navigate with a typed destination while keeping the legacy string form available. */
export function navigateToTarget(navigate: RouterNavigate, target: NavigationTarget): Promise<void> {
  if (typeof target === 'string') return navigate({ to: target })
  return navigate(target)
}
