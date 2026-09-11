import { Button, ClipboardCopy, Switch } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiRefreshIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import { useCallback, useMemo, useState } from 'react'

import { SynConfirmationDialog } from '../../../components/dialogs/SynConfirmationDialog'
import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { IconLabel } from '../../../components/IconLabel'
import { SynListPanelTable, SynListPanelToolbar, SynListPanelView } from '../../../components/panels/list/SynListPanel'
import { SynEmptyStateNoData } from '../../../components/states/SynEmptyStateNoData'
import type { KebabAction } from '../../../components/SynKebabMenu'
import { SynKebabMenu } from '../../../components/SynKebabMenu'
import { DateCell } from '../../../components/table/DateCell'
import { useCursorPagination, useCursorReset } from '../../../hooks/useCursorPagination'
import { useDialogState } from '../../../hooks/useDialogState'
import { useMutationErrorHandler } from '../../../hooks/useMutationErrorHandler'
import { useTableSort } from '../../../hooks/useTableSort'
import { useAlerts } from '../../../providers/alerts'
import type { FilterFieldDefinition } from '../../../types/filters'
import { FilterOperatorEnum, FilterTypeEnum } from '../../../types/filters'
import { formatExpirationDate } from '../../../utils/dateUtils'
import { detachPromise } from '../../../utils/detachPromise'
import { accessClient } from '../../access/accessClient'

import { CreateCredentialModal } from './CreateCredentialModal'
import { RotateDialogBody } from './RotateDialogBody'
import { DEFAULT_GRACE_PERIOD, GRACE_PERIOD_OPTIONS } from './rotateDialogUtils'
import { RotationGraceIndicator } from './RotationGraceIndicator'
import { SecretRevealModal } from './SecretRevealModal'
import type { ServiceAccountCredentialRead } from './serviceAccountTypes'
import { useServiceAccountPermissions } from './useServiceAccountPermissions'

type SecretRevealState = {
  identifier: string
  clientSecret: string
  title: string
  expiresAt?: string | null
  gracePeriodSeconds?: number
}

const SORT_FIELDS = ['identifier', 'created_at', 'last_used_at', 'expires_at', 'status'] as const

const credentialFilterDefs: FilterFieldDefinition[] = [
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

function useCredentialActions(
  serviceAccountId: string,
  refetch: () => Promise<unknown>,
  onDisableRequest: (cred: ServiceAccountCredentialRead) => void
) {
  const { showSuccess } = useAlerts()
  const handleMutationError = useMutationErrorHandler()
  const [secretReveal, setSecretReveal] = useState<SecretRevealState | null>(null)
  const [createModalOpen, setCreateModalOpen] = useState(false)

  const { mutate: createCredential, isPending: isCreating } = accessClient.useMutation(
    'post',
    '/service_accounts/{service_account_id}/credentials'
  )
  const { mutate: rotateCredential } = accessClient.useMutation(
    'post',
    '/service_accounts/{service_account_id}/credentials/{credential_id}/rotate'
  )
  const { mutate: enableCredential } = accessClient.useMutation(
    'post',
    '/service_accounts/{service_account_id}/credentials/{credential_id}/enable'
  )
  const { mutate: disableCredential } = accessClient.useMutation(
    'post',
    '/service_accounts/{service_account_id}/credentials/{credential_id}/disable'
  )
  const { mutate: deleteCredential } = accessClient.useMutation(
    'delete',
    '/service_accounts/{service_account_id}/credentials/{credential_id}'
  )

  const openCreateModal = useCallback(() => setCreateModalOpen(true), [])
  const closeCreateModal = useCallback(() => setCreateModalOpen(false), [])

  const handleCreate = useCallback(
    (expiresAt: string) => {
      setCreateModalOpen(false)
      createCredential(
        {
          params: { path: { service_account_id: serviceAccountId } },
          body: { credential_type: 'client_credentials', expires_at: expiresAt },
        },
        {
          onSuccess: (response) => {
            setSecretReveal({
              identifier: response.identifier,
              clientSecret: response.client_secret ?? '',
              title: 'New credential created',
              expiresAt: response.expires_at,
            })
            detachPromise(refetch())
          },
          onError: handleMutationError({ title: 'Failed to create credential' }),
        }
      )
    },
    [createCredential, serviceAccountId, refetch, handleMutationError]
  )

  const handleEnable = useCallback(
    (cred: ServiceAccountCredentialRead) => {
      enableCredential(
        { params: { path: { service_account_id: serviceAccountId, credential_id: cred.id } } },
        {
          onSuccess: () => detachPromise(refetch()),
          onError: handleMutationError({ title: 'Failed to enable credential' }),
        }
      )
    },
    [enableCredential, serviceAccountId, refetch, handleMutationError]
  )

  const handleToggleStatus = useCallback(
    (cred: ServiceAccountCredentialRead) => {
      if (cred.status === 'active') {
        onDisableRequest(cred)
        return
      }
      handleEnable(cred)
    },
    [handleEnable, onDisableRequest]
  )

  const handleDisableConfirm = useCallback(
    (cred: ServiceAccountCredentialRead | null, onSettled: () => void) => {
      if (!cred) return
      disableCredential(
        { params: { path: { service_account_id: serviceAccountId, credential_id: cred.id } } },
        {
          onSuccess: () => detachPromise(refetch()),
          onError: handleMutationError({ title: 'Failed to disable credential' }),
          onSettled,
        }
      )
    },
    [disableCredential, serviceAccountId, refetch, handleMutationError]
  )

  const handleRotateConfirm = useCallback(
    (cred: ServiceAccountCredentialRead | null, gracePeriodSeconds: number, onSettled: () => void) => {
      if (!cred) return
      const validValues = GRACE_PERIOD_OPTIONS.map((opt) => opt.value as number)
      const sanitizedGracePeriod = validValues.includes(gracePeriodSeconds) ? gracePeriodSeconds : DEFAULT_GRACE_PERIOD
      rotateCredential(
        {
          params: { path: { service_account_id: serviceAccountId, credential_id: cred.id } },
          body: { grace_period_seconds: sanitizedGracePeriod },
        },
        {
          onSuccess: (response) => {
            setSecretReveal({
              identifier: response.identifier,
              clientSecret: response.client_secret ?? '',
              title: 'New client secret',
              gracePeriodSeconds: sanitizedGracePeriod,
            })
            detachPromise(refetch())
          },
          onError: handleMutationError({ title: 'Failed to rotate credential' }),
          onSettled,
        }
      )
    },
    [rotateCredential, serviceAccountId, refetch, handleMutationError, setSecretReveal]
  )

  const handleDeleteConfirm = useCallback(
    (cred: ServiceAccountCredentialRead | null, onSettled: () => void) => {
      if (!cred) return
      deleteCredential(
        { params: { path: { service_account_id: serviceAccountId, credential_id: cred.id } } },
        {
          onSuccess: () => {
            showSuccess({ title: 'Credential deleted', description: 'The credential has been permanently deleted.' })
            detachPromise(refetch())
          },
          onError: handleMutationError({ title: 'Failed to delete credential' }),
          onSettled,
        }
      )
    },
    [deleteCredential, serviceAccountId, refetch, showSuccess, handleMutationError]
  )

  return {
    handleCreate,
    openCreateModal,
    closeCreateModal,
    createModalOpen,
    handleToggleStatus,
    handleDisableConfirm,
    handleRotateConfirm,
    handleDeleteConfirm,
    isCreating,
    secretReveal,
    setSecretReveal,
  }
}

function getCredentialActions(
  credential: ServiceAccountCredentialRead,
  permissions: ReturnType<typeof useServiceAccountPermissions>,
  onRotate: (cred: ServiceAccountCredentialRead) => void,
  onDelete: (cred: ServiceAccountCredentialRead) => void
): KebabAction[] {
  return [
    {
      key: 'rotate',
      title: <IconLabel icon={<RhUiRefreshIcon />}>Rotate secret</IconLabel>,
      onClick: () => onRotate(credential),
      isAriaDisabled: !permissions.canRotateSecret,
      tooltipProps: permissions.canRotateSecret ? undefined : { content: permissions.tooltips.rotateSecret },
    },
    { key: 'separator', isSeparator: true },
    {
      key: 'delete',
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete credential</IconLabel>,
      isDanger: true,
      onClick: () => onDelete(credential),
      isAriaDisabled: !permissions.canDelete,
      tooltipProps: permissions.canDelete ? undefined : { content: permissions.tooltips.delete },
    },
  ]
}

function CredentialsTable({
  credentials,
  getSortParams,
  permissions,
  onRotate,
  onToggleStatus,
  onDelete,
}: Readonly<{
  credentials: ServiceAccountCredentialRead[]
  getSortParams: ReturnType<typeof useTableSort>['getSortParams']
  permissions: ReturnType<typeof useServiceAccountPermissions>
  onRotate: (cred: ServiceAccountCredentialRead) => void
  onToggleStatus: (cred: ServiceAccountCredentialRead) => void
  onDelete: (cred: ServiceAccountCredentialRead) => void
}>) {
  return (
    <>
      <Thead>
        <Tr>
          <Th sort={getSortParams(0)}>Client ID</Th>
          <Th sort={getSortParams(1)}>Created</Th>
          <Th sort={getSortParams(2)}>Last used</Th>
          <Th sort={getSortParams(3)}>Expires</Th>
          <Th sort={getSortParams(4)}>State</Th>
          <Th screenReaderText="Rotation status" />
          <Th screenReaderText="Actions" />
        </Tr>
      </Thead>
      <Tbody>
        {credentials.map((cred) => (
          <Tr key={cred.id}>
            <Td dataLabel="Client ID">
              <ClipboardCopy isReadOnly variant="inline-compact" hoverTip="Copy" clickTip="Copied">
                {cred.identifier}
              </ClipboardCopy>
            </Td>
            <Td dataLabel="Created">
              <DateCell dateString={cred.created_at} />
            </Td>
            <Td dataLabel="Last used">
              <DateCell dateString={cred.last_used_at} />
            </Td>
            <Td dataLabel="Expires">{cred.expires_at ? formatExpirationDate(cred.expires_at) : 'Never'}</Td>
            <Td dataLabel="State">
              <Switch
                id={`cred-state-${cred.id}`}
                label={cred.status === 'active' ? 'Enabled' : 'Disabled'}
                isChecked={cred.status === 'active'}
                onChange={permissions.canUpdate ? () => onToggleStatus(cred) : undefined}
                aria-label={`Toggle credential ${cred.identifier} state`}
                aria-disabled={!permissions.canUpdate || undefined}
              />
            </Td>
            <Td dataLabel="Rotation status">
              <RotationGraceIndicator oldSecretValidUntil={cred.old_secret_valid_until} />
            </Td>
            <Td isActionCell>
              <SynKebabMenu
                actions={getCredentialActions(cred, permissions, onRotate, onDelete)}
                aria-label={`Actions for ${cred.identifier}`}
              />
            </Td>
          </Tr>
        ))}
      </Tbody>
    </>
  )
}

function getCreateDisabledTooltip(
  permissions: ReturnType<typeof useServiceAccountPermissions>,
  serviceAccountName: string,
  maxCredentials: number
) {
  if (!permissions.canUpdate) return permissions.tooltips.update
  return `${serviceAccountName} has reached the maximum of ${maxCredentials} credentials`
}

export function CredentialsTab({
  serviceAccountId,
  serviceAccountName = 'This service account',
  resourceProject,
}: Readonly<{ serviceAccountId: string; serviceAccountName?: string; resourceProject?: string }>) {
  const permissions = useServiceAccountPermissions({ resourceProject })
  const deleteDialog = useDialogState<ServiceAccountCredentialRead>()
  const disableDialog = useDialogState<ServiceAccountCredentialRead>()
  const rotateDialog = useDialogState<ServiceAccountCredentialRead>()
  const [rotateGracePeriod, setRotateGracePeriod] = useState(DEFAULT_GRACE_PERIOD)

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
    initialSortIndex: 1,
    initialDirection: 'asc',
  })

  const finalQueryParams = useMemo(() => {
    const field = SORT_FIELDS[activeSortIndex] ?? 'created_at'
    const sort = sortDirection === 'desc' ? `-${field}` : field
    return { ...queryParams, sort }
  }, [activeSortIndex, sortDirection, queryParams])

  const query = accessClient.useQuery('get', '/service_accounts/{service_account_id}/credentials', {
    params: { path: { service_account_id: serviceAccountId }, query: finalQueryParams },
  })
  const credentials = query.data?.resources ?? []
  const maxCredentials = query.data?.max_credentials ?? 10
  const totalCredentials = query.data?.total_credentials ?? 0
  const atLimit = totalCredentials >= maxCredentials
  const createDisabledTooltip = getCreateDisabledTooltip(permissions, serviceAccountName, maxCredentials)

  useCursorReset(credentials.length, hasActiveFilters, cursor, query.isFetching, resetPagination)

  const actions = useCredentialActions(serviceAccountId, query.refetch, disableDialog.open)

  return (
    <>
      <SynListPanelView
        tabKey="credentials"
        tabLabel="Credentials"
        isPending={query.isPending}
        error={query.error}
        onRetry={() => detachPromise(query.refetch())}
        errorTitle="Error loading credentials"
        isEmpty={credentials.length === 0}
        hasActiveFilters={hasActiveFilters}
        onClearAllFilters={handleClearAllFilters}
        noDataState={
          <SynEmptyStateNoData
            title="No credentials yet"
            description="Create a credential to enable API access for this service account."
            buttonText={permissions.canUpdate ? 'Create credential' : undefined}
            addData={permissions.canUpdate ? actions.openCreateModal : undefined}
          />
        }
        toolbar={
          credentials.length > 0 || hasActiveFilters ? (
            <SynListPanelToolbar
              filterDefinitions={credentialFilterDefs}
              filters={filters}
              onFilterChange={handleFilterChange}
              clearAllFilters={handleClearAllFilters}
              actions={
                <DisabledWithTooltip isDisabled={!permissions.canUpdate || atLimit} content={createDisabledTooltip}>
                  <Button
                    variant="primary"
                    icon={<RhUiAddIcon />}
                    isAriaDisabled={!permissions.canUpdate || atLimit}
                    onClick={permissions.canUpdate && !atLimit ? actions.openCreateModal : undefined}
                  >
                    Create credential
                  </Button>
                </DisabledWithTooltip>
              }
            />
          ) : undefined
        }
        body={
          <SynListPanelTable caption="Service account credentials table" footer={getFooterProps(query.data)}>
            <CredentialsTable
              credentials={credentials}
              getSortParams={getSortParams}
              permissions={permissions}
              onRotate={(cred) => rotateDialog.open(cred)}
              onToggleStatus={actions.handleToggleStatus}
              onDelete={(cred) => deleteDialog.open(cred)}
            />
          </SynListPanelTable>
        }
      />

      <SynConfirmationDialog
        isOpen={deleteDialog.isOpen}
        onClose={deleteDialog.close}
        onConfirm={() => actions.handleDeleteConfirm(deleteDialog.item, deleteDialog.close)}
        title="Delete credential?"
        confirmLabel="Delete"
        confirmVariant="danger"
        titleIconVariant="warning"
        destructiveAcknowledgement={{
          checkboxId: 'delete-credential-ack',
          label: 'I understand this credential will be permanently deleted and all associated OAuth tokens revoked.',
        }}
      >
        The credential <strong>{deleteDialog.item?.identifier}</strong> will be deleted. This cannot be undone.
      </SynConfirmationDialog>

      <SynConfirmationDialog
        isOpen={disableDialog.isOpen}
        onClose={disableDialog.close}
        onConfirm={() => actions.handleDisableConfirm(disableDialog.item, disableDialog.close)}
        title="Disable credential?"
        confirmLabel="Disable"
        confirmVariant="primary"
      >
        You are about to disable the credential <strong>{disableDialog.item?.identifier}</strong>. You can re-enable it
        at any time.
      </SynConfirmationDialog>

      <SynConfirmationDialog
        isOpen={rotateDialog.isOpen}
        onClose={() => {
          rotateDialog.close()
          setRotateGracePeriod(DEFAULT_GRACE_PERIOD)
        }}
        onConfirm={() =>
          actions.handleRotateConfirm(rotateDialog.item, rotateGracePeriod, () => {
            rotateDialog.close()
            setRotateGracePeriod(DEFAULT_GRACE_PERIOD)
          })
        }
        title="Rotate client secret?"
        confirmLabel="Rotate secret"
        confirmVariant="primary"
      >
        <RotateDialogBody
          credential={rotateDialog.item}
          gracePeriod={rotateGracePeriod}
          onGracePeriodChange={setRotateGracePeriod}
        />
      </SynConfirmationDialog>

      <CreateCredentialModal
        isOpen={actions.createModalOpen}
        onClose={actions.closeCreateModal}
        onSubmit={actions.handleCreate}
        isPending={actions.isCreating}
        maxLifetimeDays={query.data?.max_lifetime_days}
      />

      {actions.secretReveal && (
        <SecretRevealModal
          isOpen={!!actions.secretReveal}
          onClose={() => actions.setSecretReveal(null)}
          title={actions.secretReveal.title}
          identifier={actions.secretReveal.identifier}
          clientSecret={actions.secretReveal.clientSecret}
          expiresAt={actions.secretReveal.expiresAt}
          gracePeriodSeconds={actions.secretReveal.gracePeriodSeconds}
        />
      )}
    </>
  )
}
