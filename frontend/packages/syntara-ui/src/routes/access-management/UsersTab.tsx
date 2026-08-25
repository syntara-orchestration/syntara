import { Button, Content, Flex, FlexItem, StackItem, Switch, Tooltip, Truncate } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiBanIcon, RhUiEditFillIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { ActionsColumn, Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { IAction } from '@patternfly/react-table'
import type { User } from '@syntara/contracts'
import { useNavigate } from '@tanstack/react-router'
import { useCallback, useMemo, type ReactNode } from 'react'

import { AppRoute } from '../../app/AppRoute'
import { NxConfirmationDialog } from '../../components/dialogs/NxConfirmationDialog'
import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { IconLabel } from '../../components/IconLabel'
import { SynLabel } from '../../components/labels/SynLabel'
import { NxListPanelTable, NxListPanelToolbar, NxListPanelView } from '../../components/panels/list/NxListPanel'
import { SynEmptyStateNoData } from '../../components/states/SynEmptyStateNoData'
import { SynLink } from '../../components/SynLink'
import { DateCell } from '../../components/table/DateCell'
import { useCursorPagination, useCursorReset } from '../../hooks/useCursorPagination'
import { useDeleteAction } from '../../hooks/useDeleteAction'
import { useDialogState } from '../../hooks/useDialogState'
import { useTableSort } from '../../hooks/useTableSort'
import { useAuthStore } from '../../stores/useAuthStore'
import { FilterOperatorEnum, FilterTypeEnum } from '../../types/filters'
import type { FilterFieldDefinition } from '../../types/filters'
import { detachPromise } from '../../utils/detachPromise'
import { getUserIdFromToken } from '../../utils/jwtUtils'
import { accessClient } from '../access/accessClient'

import { getUserDetailPath } from './accessManagementPaths'
import { AUTH_SOURCE_LOCAL } from './adminConstants'
import { BuiltInAdminCard } from './BuiltInAdminCard'
import { useAdminToggle } from './useAdminToggle'
import { useRevokeUserTokens } from './useRevokeUserTokens'
import { getAuthSourceFilterDefinition } from './userFilters'
import { userDisplayName } from './users/userDisplayName'
import { useUserPermissions } from './useUserPermissions'
import { useUsersEnabledToggle } from './useUsersEnabledToggle'

const SORT_FIELDS = ['username', 'first_name', 'last_name', 'email', 'last_login'] as const

function buildSortedQueryParams(
  queryParams: Record<string, unknown>,
  activeSortIndex: number,
  sortDirection: string
): Record<string, unknown> {
  const field = SORT_FIELDS[activeSortIndex] ?? 'username'
  const sort = sortDirection === 'desc' ? `-${field}` : field
  return { ...queryParams, sort }
}

const filterFieldDefinitions: FilterFieldDefinition[] = [
  {
    key: 'username',
    label: 'Username',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by username',
  },
  {
    key: 'first_name',
    label: 'First name',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by first name',
  },
  {
    key: 'last_name',
    label: 'Last name',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by last name',
  },
  {
    key: 'email',
    label: 'Email',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by email',
  },
  getAuthSourceFilterDefinition(),
]

function buildDeleteParams(user: User) {
  return { params: { path: { user_id: user.id } } }
}

const DELETE_USER_ACKNOWLEDGEMENT = {
  checkboxId: 'delete-user-ack',
  label: 'I understand this user will be permanently deleted.',
}

function getRowActions(
  user: User,
  onDelete: (user: User) => void,
  onRevoke: (user: User) => void,
  permissions: ReturnType<typeof useUserPermissions>,
  onNavigate: (path: string) => void
): IAction[] {
  return [
    {
      title: <IconLabel icon={<RhUiEditFillIcon />}>Edit</IconLabel>,
      isAriaDisabled: !permissions.canUpdate,
      tooltipProps: permissions.canUpdate ? undefined : { content: permissions.tooltips.update },
      onClick: permissions.canUpdate
        ? () => onNavigate(AppRoute.AccessManagement.EditUser.replace(':userId', user.id))
        : undefined,
    },
    {
      title: <IconLabel icon={<RhUiBanIcon />}>Revoke tokens</IconLabel>,
      isAriaDisabled: !permissions.canRevoke,
      tooltipProps: permissions.canRevoke ? undefined : { content: permissions.tooltips.revoke },
      onClick: permissions.canRevoke ? () => onRevoke(user) : undefined,
    },
    { isSeparator: true },
    {
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete</IconLabel>,
      isAriaDisabled: !permissions.canDelete,
      tooltipProps: permissions.canDelete ? undefined : { content: permissions.tooltips.delete },
      onClick: permissions.canDelete ? () => onDelete(user) : undefined,
    },
  ]
}

function disableConfirmCopy(
  user: User | undefined,
  currentUserId: string | null | undefined
): {
  title: string
  confirmLabel: string
  body: ReactNode
} {
  if (!user) {
    return {
      title: 'Disable user?',
      confirmLabel: 'Disable',
      body: null,
    }
  }
  if (user.is_builtin) {
    return {
      title: 'Disable administrator account?',
      confirmLabel: 'Disable and sign out',
      body: (
        <>
          Disabling the built-in administrator account will immediately end your current session. You will need to sign
          in with another admin account to re-enable it.
        </>
      ),
    }
  }
  if (user.id === currentUserId) {
    return {
      title: 'Disable your account?',
      confirmLabel: 'Disable and sign out',
      body: (
        <>
          Disabling your own account will immediately end your current session. You will need another admin to re-enable
          it.
        </>
      ),
    }
  }
  return {
    title: 'Disable user?',
    confirmLabel: 'Disable',
    body: (
      <>
        The user <strong>{user.username}</strong> will be disabled and will no longer be able to sign in.
      </>
    ),
  }
}

function UserStateSwitch({
  user,
  disabledReason,
  onToggle,
}: Readonly<{
  user: User
  disabledReason: string | undefined
  onToggle: (user: User) => void
}>) {
  const stateSwitch = (
    <Switch
      id={`user-toggle-${user.id}`}
      label="Enabled"
      isChecked={user.is_enabled}
      isDisabled={!!disabledReason}
      onChange={() => onToggle(user)}
      aria-label={`Toggle ${user.username} status`}
    />
  )

  if (!disabledReason) {
    return stateSwitch
  }

  return <Tooltip content={disabledReason}>{stateSwitch}</Tooltip>
}

function UserTableRow({
  user,
  permissions,
  toggleDisabledReason,
  onToggleEnabled,
  onDelete,
  onRevoke,
  onNavigate,
}: Readonly<{
  user: User
  permissions: ReturnType<typeof useUserPermissions>
  toggleDisabledReason: string | undefined
  onToggleEnabled: (user: User) => void
  onDelete: (user: User) => void
  onRevoke: (user: User) => void
  onNavigate: (path: string) => void
}>) {
  return (
    <Tr>
      <Td dataLabel="Username">
        <SynLink to={getUserDetailPath(user.id)}>
          <Truncate content={user.username} />
        </SynLink>
      </Td>
      <Td dataLabel="Name">
        <Truncate content={userDisplayName(user)} />
      </Td>
      <Td dataLabel="Email">
        <Truncate content={user.email ?? ''} />
      </Td>
      <Td dataLabel="Authentication">
        <Flex gap={{ default: 'gapXs' }} flexWrap={{ default: 'wrap' }}>
          {(user.auth_sources ?? [AUTH_SOURCE_LOCAL]).map((source) => (
            <FlexItem key={source}>
              <SynLabel color={source === AUTH_SOURCE_LOCAL ? 'grey' : 'blue'}>{source}</SynLabel>
            </FlexItem>
          ))}
        </Flex>
      </Td>
      <Td dataLabel="Last login">
        <DateCell dateString={user.last_login} />
      </Td>
      <Td dataLabel="State" onClick={(e) => e.stopPropagation()}>
        <UserStateSwitch user={user} disabledReason={toggleDisabledReason} onToggle={onToggleEnabled} />
      </Td>
      <Td isActionCell>
        {!user.is_builtin && <ActionsColumn items={getRowActions(user, onDelete, onRevoke, permissions, onNavigate)} />}
      </Td>
    </Tr>
  )
}

export function UsersTab() {
  const navigate = useNavigate()
  const permissions = useUserPermissions()
  const accessToken = useAuthStore((s) => s.accessToken)
  const currentUserId = getUserIdFromToken(accessToken)

  const {
    cursor,
    resetPagination,
    filters,
    hasActiveFilters,
    queryParams,
    handleFilterChange,
    handleClearAllFilters,
    getFooterProps,
  } = useCursorPagination()

  const { revokeDialog, handleRevoke } = useRevokeUserTokens()

  const { activeSortIndex, sortDirection, getSortParams } = useTableSort({
    initialDirection: 'asc',
    onSortChange: resetPagination,
  })

  const finalQueryParams = useMemo(
    () => buildSortedQueryParams(queryParams, activeSortIndex, sortDirection),
    [activeSortIndex, sortDirection, queryParams]
  )

  const query = accessClient.useQuery('get', '/users', { params: { query: finalQueryParams } })
  const data = query.data
  const serverUsers = data?.resources ?? []
  const builtinUser = serverUsers.find((u) => u.is_builtin)
  const isAdminEnabled = builtinUser?.is_enabled ?? true
  const refetch = useCallback(() => query.refetch(), [query])

  useCursorReset(serverUsers.length, hasActiveFilters, cursor, query.isFetching, resetPagination)

  const handleCreateUser = permissions.canCreate
    ? () => detachPromise(navigate({ to: AppRoute.AccessManagement.CreateUser }))
    : undefined
  const handleRowNavigate = (path: string) => detachPromise(navigate({ to: path }))

  const adminToggle = useAdminToggle(builtinUser, () => detachPromise(refetch()))

  const { users, getToggleDisabledReason, handleToggleEnabled, disableConfirm } = useUsersEnabledToggle(
    serverUsers,
    refetch
  )

  const deleteDialog = useDialogState<User>()

  const { mutate: deleteUser } = accessClient.useMutation('delete', '/users/{user_id}')

  const handleDelete = useDeleteAction({
    deleteFn: deleteUser,
    buildParams: buildDeleteParams,
    entityLabel: 'user',
    getItemName: (user: User) => user.username,
    onSuccess: () => detachPromise(refetch()),
    onSettled: deleteDialog.close,
  })

  const disableCopy = disableConfirmCopy(disableConfirm.user, currentUserId)

  return (
    <>
      <NxListPanelView
        tabKey="users"
        tabLabel="Users"
        isPending={query.isPending}
        isFetching={query.isFetching}
        error={query.error}
        onRetry={() => detachPromise(refetch())}
        isEmpty={users.length === 0}
        hasActiveFilters={hasActiveFilters}
        onClearAllFilters={handleClearAllFilters}
        noDataState={
          <SynEmptyStateNoData
            title="No users yet"
            description="Create a user to manage access to the platform."
            buttonText="Create user"
            addData={handleCreateUser}
          />
        }
        toolbar={
          users.length > 0 || hasActiveFilters ? (
            <NxListPanelToolbar
              filters={filters}
              filterDefinitions={filterFieldDefinitions}
              onFilterChange={handleFilterChange}
              clearAllFilters={handleClearAllFilters}
              actions={
                <DisabledWithTooltip isDisabled={!permissions.canCreate} content={permissions.tooltips.create}>
                  <Button
                    variant="primary"
                    icon={<RhUiAddIcon />}
                    isAriaDisabled={!permissions.canCreate}
                    onClick={handleCreateUser}
                  >
                    Create user
                  </Button>
                </DisabledWithTooltip>
              }
            />
          ) : undefined
        }
        body={
          <>
            <Content>
              Users represent individual people who interact with the system. Users are assigned roles directly or
              through the groups they belong to. A user can belong to multiple groups.
            </Content>
            {builtinUser && (
              <StackItem>
                <BuiltInAdminCard
                  userId={builtinUser.id}
                  isEnabled={isAdminEnabled}
                  canToggle={adminToggle.canToggle}
                  onToggle={adminToggle.handleToggle}
                />
              </StackItem>
            )}
            <NxListPanelTable caption="Users" footer={getFooterProps(data)}>
              <Thead>
                <Tr>
                  <Th sort={getSortParams(0)}>Username</Th>
                  <Th sort={getSortParams(1)}>Name</Th>
                  <Th sort={getSortParams(3)}>Email</Th>
                  <Th>Authentication</Th>
                  <Th sort={getSortParams(4)}>Last login</Th>
                  <Th>State</Th>
                  <Th screenReaderText="Actions" />
                </Tr>
              </Thead>
              <Tbody>
                {users.map((user) => (
                  <UserTableRow
                    key={user.id}
                    user={user}
                    permissions={permissions}
                    toggleDisabledReason={getToggleDisabledReason(user)}
                    onToggleEnabled={handleToggleEnabled}
                    onDelete={deleteDialog.open}
                    onRevoke={revokeDialog.open}
                    onNavigate={handleRowNavigate}
                  />
                ))}
              </Tbody>
            </NxListPanelTable>
          </>
        }
      />

      <NxConfirmationDialog
        isOpen={deleteDialog.isOpen}
        onClose={deleteDialog.close}
        onConfirm={() => handleDelete(deleteDialog.item)}
        title="Delete user?"
        confirmLabel="Delete"
        confirmVariant="danger"
        titleIconVariant="warning"
        destructiveAcknowledgement={DELETE_USER_ACKNOWLEDGEMENT}
      >
        The user <strong>{deleteDialog.item?.username}</strong> will be deleted. This cannot be undone.
      </NxConfirmationDialog>
      <NxConfirmationDialog
        isOpen={adminToggle.showConfirm}
        onClose={adminToggle.cancelDisable}
        onConfirm={adminToggle.confirmDisable}
        title="Disable administrator account?"
        confirmLabel="Disable and sign out"
      >
        Disabling the built-in administrator account will immediately end your current session. You will need to sign in
        with another admin account to re-enable it.
      </NxConfirmationDialog>
      <NxConfirmationDialog
        isOpen={disableConfirm.isOpen}
        onClose={disableConfirm.close}
        onConfirm={disableConfirm.confirm}
        title={disableCopy.title}
        confirmLabel={disableCopy.confirmLabel}
      >
        {disableCopy.body}
      </NxConfirmationDialog>
      <NxConfirmationDialog
        isOpen={revokeDialog.isOpen}
        onClose={revokeDialog.close}
        onConfirm={handleRevoke}
        title="Revoke user tokens?"
        confirmLabel="Revoke tokens"
        confirmVariant="danger"
        titleIconVariant="warning"
      >
        All tokens for <strong>{revokeDialog.item?.username}</strong> will be revoked. The user will be signed out and
        must sign in again.
      </NxConfirmationDialog>
    </>
  )
}
