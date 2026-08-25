import {
  Badge,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  FlexItem,
  Label,
  LabelGroup,
  Tab,
  TabTitleText,
} from '@patternfly/react-core'
import type { User } from '@syntara/contracts'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useMemo } from 'react'

import { AppRoute } from '../../../app/AppRoute'
import { breadcrumbsUserDetail } from '../../../app/breadcrumbBuilders'
import { authClient } from '../../../client'
import { SynPage, SynPageBody } from '../../../components/layout/SynPage'
import { SynPageHeader } from '../../../components/layout/SynPageHeader'
import { NxListPanel, NxListPanelTabs } from '../../../components/panels/list/NxListPanel'
import { useQueryState } from '../../../components/states/useQueryState'
import { SynPageTitle } from '../../../components/SynPageTitle'
import { DateCell } from '../../../components/table/DateCell'
import { useDeleteAction } from '../../../hooks/useDeleteAction'
import { useDialogState } from '../../../hooks/useDialogState'
import { useUrlTab } from '../../../hooks/useUrlTab'
import { detachPromise } from '../../../utils/detachPromise'
import { useDocLink } from '../../../utils/docs/useDocLink'
import { isValidUUID } from '../../../utils/generateUUID'
import { accessClient } from '../../access/accessClient'
import { CheckAccessView } from '../../access/CheckAccessView'
import { MyPermissionsView } from '../../access/MyPermissionsView'
import { useResourceActions } from '../../access/useResourceActions'
import { AUTH_TYPE_LOCAL } from '../adminConstants'
import { DisabledBadge } from '../DisabledBadge'
import { RoleAssignmentsPanel } from '../RoleAssignmentsPanel'
import { RolePrincipalType } from '../RoleAssignmentTypes'
import { useRevokeUserTokens } from '../useRevokeUserTokens'
import { useUserPermissions } from '../useUserPermissions'

import type { UserIdentity } from './identityUtils'
import { UserDetailConfirmationDialogs, UserDetailToolbar } from './UserDetailActions'
import { renderUserDetailEarlyShell } from './userDetailEarlyShell'
import { computeGroupCount, computeRoleAssignmentCount } from './userDetailUtils'
import { userDisplayName } from './userDisplayName'
import { UserGroupsPanel } from './UserGroupsPanel'
import { UserIdentitiesPanel } from './UserIdentitiesPanel'
import { useUserDetailPermissions } from './useUserDetailPermissions'

function useUserDetailData(userId: string | undefined) {
  const isValidId = !!userId && isValidUUID(userId)
  const safeUserId = userId ?? ''

  const userQuery = accessClient.useQuery(
    'get',
    '/users/{user_id}',
    { params: { path: { user_id: safeUserId } } },
    { enabled: isValidId, retry: false }
  )

  const groupsQuery = accessClient.useQuery(
    'get',
    '/users/{user_id}/groups',
    { params: { path: { user_id: safeUserId } } },
    { enabled: isValidId }
  )

  const identitiesQuery = accessClient.useQuery(
    'get',
    '/users/{user_id}/identities',
    { params: { path: { user_id: safeUserId } } },
    { enabled: isValidId }
  )

  const roleAssignmentsQuery = accessClient.useQuery(
    'get',
    '/users/{user_id}/role_assignments',
    { params: { path: { user_id: safeUserId } } },
    { enabled: isValidId }
  )

  const meQuery = authClient.useQuery('get', '/auth/me')

  const groupCount = computeGroupCount(groupsQuery.data)
  const identitiesData = identitiesQuery.data?.resources ?? []
  let roleAssignmentCount = 0
  if (roleAssignmentsQuery.data) {
    roleAssignmentCount = computeRoleAssignmentCount(roleAssignmentsQuery.data)
  }

  return {
    userQuery,
    groupCount,
    identitiesData,
    roleAssignmentCount,
    currentUserId: meQuery.data?.id,
  }
}

function UserDetailsTab({
  user,
  identities,
}: {
  user: User
  identities: Pick<UserIdentity, 'provider_name' | 'identity_provider_id'>[]
}) {
  const navigate = useNavigate()
  const { first_name, last_name } = user

  const isLocal = user.auth_type === AUTH_TYPE_LOCAL
  const uniqueProviders = identities.reduce<Map<string, string>>((acc, i) => {
    if (!acc.has(i.identity_provider_id)) {
      acc.set(i.identity_provider_id, i.provider_name ?? '')
    }
    return acc
  }, new Map())
  // Local users always show exactly one provider: 'Local'
  const totalProviders = isLocal ? 1 : uniqueProviders.size
  const providerLabel = totalProviders > 1 ? 'Identity providers' : 'Identity provider'

  return (
    <DescriptionList isHorizontal isAutoColumnWidths>
      <DescriptionListGroup>
        <DescriptionListTerm>Username</DescriptionListTerm>
        <DescriptionListDescription>{user.username}</DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>User ID</DescriptionListTerm>
        <DescriptionListDescription>
          <code style={{ fontSize: 'var(--pf-t--global--font--size--sm)' }}>{user.id}</code>
        </DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>First name</DescriptionListTerm>
        <DescriptionListDescription>{first_name}</DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Last name</DescriptionListTerm>
        <DescriptionListDescription>{last_name}</DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Email</DescriptionListTerm>
        <DescriptionListDescription>{user.email}</DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>{providerLabel}</DescriptionListTerm>
        <DescriptionListDescription>
          {totalProviders === 0 ? (
            '-'
          ) : (
            <LabelGroup>
              {isLocal && <Label isCompact>Local</Label>}
              {!isLocal &&
                [...uniqueProviders.entries()]
                  .sort(([, a], [, b]) => a.localeCompare(b))
                  .map(([id, name]) => (
                    <Label
                      key={id}
                      isCompact
                      onClick={() =>
                        detachPromise(
                          navigate({
                            to: AppRoute.SystemAdministration.Authentication.IdentityProviderDetail.replace(
                              ':providerId',
                              id
                            ).replace('/:tab?', ''),
                          })
                        )
                      }
                    >
                      {name}
                    </Label>
                  ))}
            </LabelGroup>
          )}
        </DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Last Login</DescriptionListTerm>
        <DescriptionListDescription>
          <DateCell dateString={user.last_login} />
        </DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Created</DescriptionListTerm>
        <DescriptionListDescription>
          <DateCell dateString={user.created_at} />
        </DescriptionListDescription>
      </DescriptionListGroup>
    </DescriptionList>
  )
}

type UserTab = 'details' | 'groups' | 'identities' | 'roles' | 'permissions' | 'check-access'

function computeVisibleTabs(
  canReadGroups: boolean,
  canReadIdentities: boolean,
  canReadAssignments: boolean,
  isOwnProfile: boolean,
  isLoading: boolean
): UserTab[] {
  const tabs: UserTab[] = ['details']
  if (isLoading || canReadGroups) tabs.push('groups')
  if (isLoading || canReadIdentities) tabs.push('identities')
  if (isLoading || canReadAssignments) tabs.push('roles')
  if (isOwnProfile) tabs.push('permissions', 'check-access')
  return tabs
}

function UserCheckAccessTab() {
  const { resourceTypes, actionsByResource, isLoading, error, refetch } = useResourceActions()
  const queryState = useQueryState(
    { isPending: isLoading, error },
    { title: 'Error loading resource actions', onRetry: () => detachPromise(refetch()) }
  )
  if (queryState) return queryState
  return <CheckAccessView resourceTypes={resourceTypes} actionsByResource={actionsByResource} />
}

function UserDetailTabBar({
  basePath,
  validTabs,
  groupCount,
  identitiesCount,
  roleAssignmentCount,
}: Readonly<{
  basePath: string
  validTabs: UserTab[]
  groupCount: number
  identitiesCount: number
  roleAssignmentCount: number
}>) {
  return (
    <NxListPanelTabs basePath={basePath} defaultTab="details" validTabs={validTabs} aria-label="User details">
      <Tab eventKey="details" title={<TabTitleText>Details</TabTitleText>} />
      {validTabs.includes('groups') && (
        <Tab
          eventKey="groups"
          title={
            <TabTitleText>
              Groups <Badge isRead>{groupCount}</Badge>
            </TabTitleText>
          }
        />
      )}
      {validTabs.includes('identities') && (
        <Tab
          eventKey="identities"
          title={
            <TabTitleText>
              Identities <Badge isRead>{identitiesCount}</Badge>
            </TabTitleText>
          }
        />
      )}
      {validTabs.includes('roles') && (
        <Tab
          eventKey="roles"
          title={
            <TabTitleText>
              Assignments <Badge isRead>{roleAssignmentCount}</Badge>
            </TabTitleText>
          }
        />
      )}
      {validTabs.includes('permissions') && (
        <Tab eventKey="permissions" title={<TabTitleText>Permissions</TabTitleText>} />
      )}
      {validTabs.includes('check-access') && (
        <Tab eventKey="check-access" title={<TabTitleText>Check my access</TabTitleText>} />
      )}
    </NxListPanelTabs>
  )
}

function UserDetailTabContent({
  activeTab,
  validTabs,
  userData,
  userId,
  currentUserId,
  identitiesData,
  isOwnProfile,
}: Readonly<{
  activeTab: string
  validTabs: UserTab[]
  userData: User
  userId: string
  currentUserId: string | undefined
  identitiesData: Pick<UserIdentity, 'provider_name' | 'identity_provider_id'>[]
  isOwnProfile: boolean
}>) {
  return (
    <>
      {activeTab === 'details' && <UserDetailsTab user={userData} identities={identitiesData} />}
      {activeTab === 'groups' && validTabs.includes('groups') && <UserGroupsPanel userId={userId} />}
      {activeTab === 'identities' && validTabs.includes('identities') && (
        <UserIdentitiesPanel
          userId={userId}
          currentUserId={currentUserId}
          isBuiltinUser={!!userData.is_builtin}
          isLocalUser={userData.auth_type === AUTH_TYPE_LOCAL}
          hasPassword={userData.auth_type === AUTH_TYPE_LOCAL}
        />
      )}
      {activeTab === 'roles' && validTabs.includes('roles') && (
        <RoleAssignmentsPanel principalType={RolePrincipalType.USER} principalId={userId} />
      )}
      {activeTab === 'permissions' && isOwnProfile && <MyPermissionsView />}
      {activeTab === 'check-access' && isOwnProfile && <UserCheckAccessTab />}
    </>
  )
}

export type UserDetailProps = {
  /**
   * When true, the page renders as "My Profile" — userId is fetched from
   * `/auth/me`, breadcrumbs are omitted, and the back button navigates to
   * the dashboard instead of the Users list.
   */
  isMyProfile?: boolean
}

function useUserDetailRouting(isMyProfile: boolean | undefined) {
  const { userId: urlUserId }: { userId: string } = useParams({ strict: false })
  const meQuery = authClient.useQuery('get', '/auth/me')
  const meUserId = meQuery.data?.id

  const userId = isMyProfile ? meUserId : urlUserId
  const basePath = isMyProfile
    ? AppRoute.MyProfile.Root
    : AppRoute.AccessManagement.UserDetail.replace(':userId', userId ?? '')

  return { userId, basePath, meQuery }
}

export function UserDetail({ isMyProfile }: Readonly<UserDetailProps> = {}) {
  const navigate = useNavigate()
  const usersDocLink = useDocLink('users')
  const docLink = isMyProfile ? undefined : usersDocLink
  const { userId, basePath, meQuery } = useUserDetailRouting(isMyProfile)
  const [activeTab] = useUrlTab<UserTab>(basePath)

  const userPermissions = useUserPermissions()
  const deleteDialog = useDialogState<User>()
  const { revokeDialog, handleRevoke } = useRevokeUserTokens()
  const { mutate: deleteUser } = accessClient.useMutation('delete', '/users/{user_id}')
  const { userQuery, groupCount, identitiesData, roleAssignmentCount, currentUserId } = useUserDetailData(userId)
  const {
    canReadGroups,
    canReadIdentities,
    canReadAssignments,
    isLoading: permissionsLoading,
  } = useUserDetailPermissions(userId)

  const isOwnProfile = !!userId && !!currentUserId && userId === currentUserId

  const validTabs = useMemo(
    () => computeVisibleTabs(canReadGroups, canReadIdentities, canReadAssignments, isOwnProfile, permissionsLoading),
    [canReadGroups, canReadIdentities, canReadAssignments, isOwnProfile, permissionsLoading]
  )

  const navigateBack = () =>
    detachPromise(navigate({ to: isMyProfile ? AppRoute.Workflows.Root : AppRoute.AccessManagement.Users }))
  const navigateEdit = () =>
    detachPromise(navigate({ to: AppRoute.AccessManagement.EditUser.replace(':userId', userId ?? '') }))

  const handleDelete = useDeleteAction({
    deleteFn: deleteUser,
    buildParams: (user: User) => ({ params: { path: { user_id: user.id } } }),
    entityLabel: 'user',
    getItemName: (user: User) => user.username,
    onSuccess: navigateBack,
    onSettled: deleteDialog.close,
  })

  const refetchUser = userQuery.refetch
  const queryState = useQueryState(userQuery, {
    title: 'Error loading user',
    onRetry: () => {
      detachPromise(refetchUser())
    },
  })

  const earlyShell = renderUserDetailEarlyShell({
    isMyProfile: !!isMyProfile,
    isMeQueryPending: meQuery.isPending,
    hasUserQueryError: !!userQuery.error,
    queryState,
    navigateBack,
    refetchUser,
  })
  if (earlyShell) return earlyShell

  const userData = userQuery.data
  if (!userData) return null

  const displayName = userDisplayName(userData)
  const pageTitle = isMyProfile ? 'My Profile' : displayName
  const userBreadcrumbs = isMyProfile ? [] : breadcrumbsUserDetail(displayName, basePath, activeTab)

  return (
    <SynPage>
      <SynPageTitle segments={[pageTitle, isMyProfile ? undefined : 'Users']} />
      <SynPageHeader
        title={pageTitle}
        docLink={docLink}
        breadcrumbs={userBreadcrumbs}
        titleAddons={
          !userData.is_enabled ? (
            <FlexItem>
              <DisabledBadge />
            </FlexItem>
          ) : undefined
        }
        toolbar={
          <UserDetailToolbar
            permissions={userPermissions}
            showKebabMenu={!userData.is_builtin}
            onEdit={navigateEdit}
            onRevoke={() => revokeDialog.open(userData)}
            onDelete={() => deleteDialog.open(userData)}
          />
        }
      />
      <SynPageBody>
        <NxListPanel>
          <UserDetailTabBar
            basePath={basePath}
            validTabs={validTabs}
            groupCount={groupCount}
            identitiesCount={identitiesData.length}
            roleAssignmentCount={roleAssignmentCount}
          />
          <UserDetailTabContent
            activeTab={activeTab}
            validTabs={validTabs}
            userData={userData}
            userId={userId ?? ''}
            currentUserId={currentUserId}
            identitiesData={identitiesData}
            isOwnProfile={isOwnProfile}
          />
        </NxListPanel>
      </SynPageBody>

      <UserDetailConfirmationDialogs
        user={userData}
        revokeDialog={revokeDialog}
        deleteDialog={deleteDialog}
        onRevoke={handleRevoke}
        onDelete={() => handleDelete(deleteDialog.item)}
      />
    </SynPage>
  )
}
