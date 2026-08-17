import { Button, Content, Switch, Tooltip, Truncate } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiEditFillIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import { useCallback, useMemo } from 'react'

import { NxConfirmationDialog } from '../../../components/dialogs/NxConfirmationDialog'
import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { IconLabel } from '../../../components/IconLabel'
import { NxLabel } from '../../../components/labels/NxLabel'
import type { KebabAction } from '../../../components/NxKebabMenu'
import { NxKebabMenu } from '../../../components/NxKebabMenu'
import { NxLink } from '../../../components/NxLink'
import { NxListPanelTable, NxListPanelToolbar, NxListPanelView } from '../../../components/panels/list/NxListPanel'
import { NxEmptyStateNoData } from '../../../components/states/NxEmptyStateNoData'
import { DateCell } from '../../../components/table/DateCell'
import { useCursorPagination, useCursorReset } from '../../../hooks/useCursorPagination'
import { useDeleteAction } from '../../../hooks/useDeleteAction'
import { useDialogState } from '../../../hooks/useDialogState'
import { useMutationErrorHandler } from '../../../hooks/useMutationErrorHandler'
import { useTableSort } from '../../../hooks/useTableSort'
import { FilterOperatorEnum, FilterTypeEnum } from '../../../types/filters'
import type { FilterFieldDefinition } from '../../../types/filters'
import { detachPromise } from '../../../utils/detachPromise'
import { accessClient } from '../../access/accessClient'
import { getProjectDetailPath, getServiceAccountDetailPath } from '../accessManagementPaths'

import { CreateServiceAccountModal } from './CreateServiceAccountModal'
import { EditServiceAccountModal } from './EditServiceAccountModal'
import type { ServiceAccountRead } from './serviceAccountTypes'
import { useServiceAccountPermissions } from './useServiceAccountPermissions'

const SORT_FIELDS = ['name', 'created_at', 'last_authenticated_at'] as const

const filterFieldDefinitions: FilterFieldDefinition[] = [
  {
    key: 'name',
    label: 'Name',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by name',
  },
  {
    key: 'status',
    label: 'Status',
    type: FilterTypeEnum.SELECT,
    operators: [FilterOperatorEnum.EQ],
    defaultOperator: FilterOperatorEnum.EQ,
    options: [
      { label: 'Enabled', value: 'active' },
      { label: 'Disabled', value: 'disabled' },
    ],
  },
]

function getRowActions(
  sa: ServiceAccountRead,
  onEdit: (sa: ServiceAccountRead) => void,
  onDelete: (sa: ServiceAccountRead) => void,
  permissions: ReturnType<typeof useServiceAccountPermissions>
): KebabAction[] {
  return [
    {
      key: 'edit',
      title: <IconLabel icon={<RhUiEditFillIcon />}>Edit service account</IconLabel>,
      isAriaDisabled: !permissions.canUpdate,
      tooltipProps: permissions.canUpdate ? undefined : { content: permissions.tooltips.update },
      onClick: () => onEdit(sa),
    },
    { key: 'separator', isSeparator: true },
    {
      key: 'delete',
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete service account</IconLabel>,
      isDanger: true,
      isAriaDisabled: !permissions.canDelete,
      tooltipProps: permissions.canDelete ? undefined : { content: permissions.tooltips.delete },
      onClick: () => onDelete(sa),
    },
  ]
}

function ServiceAccountRow({
  sa,
  onToggleStatus,
  onEdit,
  onDelete,
}: Readonly<{
  sa: ServiceAccountRead
  onToggleStatus: (sa: ServiceAccountRead) => void
  onEdit: (sa: ServiceAccountRead) => void
  onDelete: (sa: ServiceAccountRead) => void
}>) {
  const permissions = useServiceAccountPermissions({
    resourceProject: sa.project_id || sa.project_name || undefined,
  })

  return (
    <Tr>
      <Td dataLabel="Name">
        <NxLink to={getServiceAccountDetailPath(sa.id)}>
          <Truncate content={sa.name} />
        </NxLink>
      </Td>
      <Td dataLabel="Owning project">
        {sa.project_name && !sa.is_project_deleted ? (
          <NxLink to={getProjectDetailPath(sa.project_id)}>{sa.project_name}</NxLink>
        ) : (
          <>
            {sa.project_name ?? sa.project_id}
            {sa.is_project_deleted && (
              <>
                {' '}
                <Tooltip content="The owning project for this service account has been deleted">
                  {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
                  <span tabIndex={0}>
                    <NxLabel color="grey">Deleted</NxLabel>
                  </span>
                </Tooltip>
              </>
            )}
          </>
        )}
      </Td>
      <Td dataLabel="Created">
        <DateCell dateString={sa.created_at} />
      </Td>
      <Td dataLabel="Last authenticated">
        {sa.last_authenticated_at ? <DateCell dateString={sa.last_authenticated_at} /> : 'Never'}
      </Td>
      <Td dataLabel="State">
        <Switch
          id={`sa-toggle-${sa.id}`}
          label={sa.status === 'active' ? 'Enabled' : 'Disabled'}
          isChecked={sa.status === 'active'}
          // Gate with isDisabled (not a missing onChange) so useCanI's safe-false
          // window can't swallow clicks before permission resolves.
          isDisabled={!permissions.canUpdate}
          onChange={() => onToggleStatus(sa)}
          aria-label={`Toggle ${sa.name} status`}
        />
      </Td>
      <Td isActionCell>
        <NxKebabMenu actions={getRowActions(sa, onEdit, onDelete, permissions)} aria-label={`Actions for ${sa.name}`} />
      </Td>
    </Tr>
  )
}

function ServiceAccountTableBody({
  serviceAccounts,
  onToggleStatus,
  onEdit,
  onDelete,
}: Readonly<{
  serviceAccounts: ServiceAccountRead[]
  onToggleStatus: (sa: ServiceAccountRead) => void
  onEdit: (sa: ServiceAccountRead) => void
  onDelete: (sa: ServiceAccountRead) => void
}>) {
  return (
    <Tbody>
      {serviceAccounts.map((sa) => (
        <ServiceAccountRow key={sa.id} sa={sa} onToggleStatus={onToggleStatus} onEdit={onEdit} onDelete={onDelete} />
      ))}
    </Tbody>
  )
}

export function ServiceAccountsTab() {
  const permissions = useServiceAccountPermissions()

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

  const { activeSortIndex, sortDirection, getSortParams } = useTableSort({
    initialDirection: 'asc',
  })

  const finalQueryParams = useMemo(() => {
    const field = SORT_FIELDS[activeSortIndex] ?? 'name'
    const sort = sortDirection === 'desc' ? `-${field}` : field
    return { ...queryParams, sort }
  }, [activeSortIndex, sortDirection, queryParams])

  const query = accessClient.useQuery('get', '/service_accounts', {
    params: { query: finalQueryParams },
  })
  const serviceAccounts = query.data?.resources ?? []
  const refetch = useCallback(() => detachPromise(query.refetch()), [query])

  useCursorReset(serviceAccounts.length, hasActiveFilters, cursor, query.isFetching, resetPagination)

  const createDialog = useDialogState()
  const deleteDialog = useDialogState<ServiceAccountRead>()
  const editDialog = useDialogState<ServiceAccountRead>()
  const disableDialog = useDialogState<ServiceAccountRead>()

  const { mutate: deleteServiceAccount } = accessClient.useMutation('delete', '/service_accounts/{service_account_id}')

  const handleDelete = useDeleteAction({
    deleteFn: deleteServiceAccount,
    buildParams: (sa: ServiceAccountRead) => ({ params: { path: { service_account_id: sa.id } } }),
    entityLabel: 'service account',
    getItemName: (sa: ServiceAccountRead) => sa.name,
    onSuccess: refetch,
    onSettled: deleteDialog.close,
  })

  const handleMutationError = useMutationErrorHandler()

  const { mutate: enableServiceAccount } = accessClient.useMutation(
    'post',
    '/service_accounts/{service_account_id}/enable'
  )
  const { mutate: disableServiceAccount } = accessClient.useMutation(
    'post',
    '/service_accounts/{service_account_id}/disable'
  )

  const handleToggleStatus = useCallback(
    (sa: ServiceAccountRead) => {
      if (sa.status === 'active') {
        disableDialog.open(sa)
        return
      }
      enableServiceAccount(
        { params: { path: { service_account_id: sa.id } } },
        {
          onSuccess: () => detachPromise(query.refetch()),
          onError: handleMutationError({ title: 'Failed to enable service account' }),
        }
      )
    },
    [query, enableServiceAccount, disableDialog, handleMutationError]
  )

  const handleDisable = useCallback(() => {
    const sa = disableDialog.item
    if (!sa) return
    disableServiceAccount(
      { params: { path: { service_account_id: sa.id } } },
      {
        onSuccess: () => detachPromise(query.refetch()),
        onError: handleMutationError({ title: 'Failed to disable service account' }),
        onSettled: () => disableDialog.close(),
      }
    )
  }, [disableServiceAccount, disableDialog, query, handleMutationError])

  return (
    <>
      <NxListPanelView
        tabKey="service-accounts"
        tabLabel="Service accounts"
        isPending={query.isPending}
        isFetching={query.isFetching}
        error={query.error}
        onRetry={refetch}
        isEmpty={serviceAccounts.length === 0}
        hasActiveFilters={hasActiveFilters}
        onClearAllFilters={handleClearAllFilters}
        noDataState={
          <NxEmptyStateNoData
            title="No service accounts yet"
            description="Service accounts provide programmatic access for external applications using OAuth 2.0 client credentials."
            buttonText="Create service account"
            addData={permissions.canCreate ? () => createDialog.open(undefined) : undefined}
          />
        }
        toolbar={
          serviceAccounts.length > 0 || hasActiveFilters ? (
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
                    onClick={permissions.canCreate ? () => createDialog.open(undefined) : undefined}
                  >
                    Create service account
                  </Button>
                </DisabledWithTooltip>
              }
            />
          ) : undefined
        }
        body={
          <>
            <Content>
              Service accounts provide programmatic access for external applications using OAuth 2.0 client credentials.
            </Content>
            <NxListPanelTable caption="Service accounts" footer={getFooterProps(query.data)}>
              <Thead>
                <Tr>
                  <Th sort={getSortParams(0)}>Name</Th>
                  <Th>Owning project</Th>
                  <Th sort={getSortParams(1)}>Created</Th>
                  <Th sort={getSortParams(2)}>Last authenticated</Th>
                  <Th>State</Th>
                  <Th screenReaderText="Actions" />
                </Tr>
              </Thead>
              <ServiceAccountTableBody
                serviceAccounts={serviceAccounts}
                onToggleStatus={handleToggleStatus}
                onEdit={editDialog.open}
                onDelete={deleteDialog.open}
              />
            </NxListPanelTable>
          </>
        }
      />

      <CreateServiceAccountModal
        isOpen={createDialog.isOpen}
        onClose={createDialog.close}
        onSuccess={refetch}
        maxLifetimeDays={query.data?.max_lifetime_days}
      />

      {editDialog.item && (
        <EditServiceAccountModal
          serviceAccount={editDialog.item}
          isOpen={editDialog.isOpen}
          onClose={editDialog.close}
          onSuccess={refetch}
        />
      )}

      <NxConfirmationDialog
        isOpen={deleteDialog.isOpen}
        onClose={deleteDialog.close}
        onConfirm={() => handleDelete(deleteDialog.item)}
        title="Delete service account?"
        confirmLabel="Delete"
        confirmVariant="danger"
        titleIconVariant="warning"
        destructiveAcknowledgement={{
          checkboxId: 'delete-service-account-ack',
          label: 'I understand this service account will be permanently deleted and all OAuth tokens revoked.',
        }}
      >
        The service account <strong>{deleteDialog.item?.name}</strong> will be deleted. This cannot be undone.
      </NxConfirmationDialog>

      <NxConfirmationDialog
        isOpen={disableDialog.isOpen}
        onClose={disableDialog.close}
        onConfirm={handleDisable}
        title="Disable service account?"
        confirmLabel="Disable"
        confirmVariant="primary"
      >
        You are about to disable the service account <strong>{disableDialog.item?.name}</strong>. You can re-enable the
        service account at any time.
      </NxConfirmationDialog>
    </>
  )
}
