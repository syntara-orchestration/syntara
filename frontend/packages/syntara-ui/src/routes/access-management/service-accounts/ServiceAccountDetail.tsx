import { Button, DescriptionList, Switch, Tab, TabTitleText, Tooltip } from '@patternfly/react-core'
import { RhUiCheckCircleIcon, RhUiEditIcon, RhUiMinusCircleIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useCallback } from 'react'

import { AppRoute } from '../../../app/AppRoute'
import {
  breadcrumbsServiceAccountDetail,
  breadcrumbsServiceAccountDetailEarlyShell,
} from '../../../app/breadcrumbBuilders'
import { NxDetail } from '../../../components/details/NxDetail'
import { NxConfirmationDialog } from '../../../components/dialogs/NxConfirmationDialog'
import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { IconLabel } from '../../../components/IconLabel'
import { SynLabel } from '../../../components/labels/SynLabel'
import { SynPage, SynPageBody } from '../../../components/layout/SynPage'
import { SynPageHeader } from '../../../components/layout/SynPageHeader'
import { NxListPanel, NxListPanelTabs, NxListPanelView } from '../../../components/panels/list/NxListPanel'
import { useQueryState } from '../../../components/states/useQueryState'
import { SynKebabMenu } from '../../../components/SynKebabMenu'
import { SynLink } from '../../../components/SynLink'
import { SynPageTitle } from '../../../components/SynPageTitle'
import { DateCell } from '../../../components/table/DateCell'
import { useDeleteAction } from '../../../hooks/useDeleteAction'
import { useDialogState } from '../../../hooks/useDialogState'
import { useMutationErrorHandler } from '../../../hooks/useMutationErrorHandler'
import { useUrlTab } from '../../../hooks/useUrlTab'
import { detachPromise } from '../../../utils/detachPromise'
import { useDocLink } from '../../../utils/docs/useDocLink'
import { accessClient } from '../../access/accessClient'
import { getProjectDetailPath } from '../accessManagementPaths'
import { DetailPageShell } from '../DetailPageShell'
import { RoleAssignmentsPanel } from '../RoleAssignmentsPanel'
import { RolePrincipalType } from '../RoleAssignmentTypes'

import { CredentialsTab } from './CredentialsTab'
import { EditServiceAccountModal } from './EditServiceAccountModal'
import { ServiceAccountNotFoundState } from './ServiceAccountNotFoundState'
import type { ServiceAccountRead } from './serviceAccountTypes'
import { useServiceAccountPermissions } from './useServiceAccountPermissions'

function DetailsTab({ serviceAccount }: Readonly<{ serviceAccount: ServiceAccountRead }>) {
  return (
    <DescriptionList isHorizontal>
      <NxDetail label="Name">{serviceAccount.name}</NxDetail>
      <NxDetail label="Owning project">
        {serviceAccount.project_name && !serviceAccount.is_project_deleted ? (
          <SynLink to={getProjectDetailPath(serviceAccount.project_id)}>{serviceAccount.project_name}</SynLink>
        ) : (
          <>
            {serviceAccount.project_name ?? serviceAccount.project_id}
            {serviceAccount.is_project_deleted && (
              <>
                {' '}
                <Tooltip content="The owning project for this service account has been deleted">
                  {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
                  <span tabIndex={0}>
                    <SynLabel color="grey">Deleted</SynLabel>
                  </span>
                </Tooltip>
              </>
            )}
          </>
        )}
      </NxDetail>
      <NxDetail label="Description">{serviceAccount.description}</NxDetail>
      <NxDetail label="State">
        {serviceAccount.status === 'active' ? (
          <SynLabel variant="outline" status="success" icon={<RhUiCheckCircleIcon />}>
            Enabled
          </SynLabel>
        ) : (
          <SynLabel variant="outline" icon={<RhUiMinusCircleIcon />}>
            Disabled
          </SynLabel>
        )}
      </NxDetail>
      <NxDetail label="Created">
        <DateCell dateString={serviceAccount.created_at} />
      </NxDetail>
      <NxDetail label="Last authenticated">
        {serviceAccount.last_authenticated_at ? (
          <DateCell dateString={serviceAccount.last_authenticated_at} />
        ) : (
          'Never'
        )}
      </NxDetail>
    </DescriptionList>
  )
}

function ServiceAccountToolbar({
  permissions,
  isEnabled,
  onToggleStatus,
  onEdit,
  onDelete,
}: Readonly<{
  permissions: ReturnType<typeof useServiceAccountPermissions>
  isEnabled: boolean
  onToggleStatus: () => void
  onEdit: () => void
  onDelete: () => void
}>) {
  return (
    <>
      <DisabledWithTooltip isDisabled={!permissions.canUpdate} content={permissions.tooltips.update}>
        <Switch
          id="sa-status-toggle"
          label={isEnabled ? 'Enabled' : 'Disabled'}
          isChecked={isEnabled}
          // Gate with isDisabled (not a missing onChange) so useCanI's safe-false
          // window can't swallow clicks before permission resolves.
          isDisabled={!permissions.canUpdate}
          onChange={onToggleStatus}
          aria-label="Toggle service account status"
        />
      </DisabledWithTooltip>
      <DisabledWithTooltip isDisabled={!permissions.canUpdate} content={permissions.tooltips.update}>
        <Button
          variant="primary"
          icon={<RhUiEditIcon />}
          isAriaDisabled={!permissions.canUpdate}
          onClick={permissions.canUpdate ? onEdit : undefined}
        >
          Edit service account
        </Button>
      </DisabledWithTooltip>
      <SynKebabMenu
        actions={[
          {
            key: 'delete',
            title: <IconLabel icon={<RhUiTrashIcon />}>Delete service account</IconLabel>,
            isDanger: true,
            onClick: onDelete,
            isAriaDisabled: !permissions.canDelete,
            tooltipProps: permissions.canDelete ? undefined : { content: permissions.tooltips.delete },
          },
        ]}
        aria-label="Service account actions"
      />
    </>
  )
}

type ServiceAccountTab = 'details' | 'credentials' | 'assignments'

const VALID_TABS = ['details', 'credentials', 'assignments']
const noop = () => {}

export function ServiceAccountDetail() {
  const { serviceAccountId }: { serviceAccountId: string } = useParams({ strict: false })
  const navigate = useNavigate()
  const basePath = AppRoute.AccessManagement.ServiceAccountDetail.replace(':serviceAccountId', serviceAccountId ?? '')
  const [activeTab] = useUrlTab<ServiceAccountTab>(basePath)
  const docLink = useDocLink('serviceAccounts')
  const editDialog = useDialogState()
  const deleteDialog = useDialogState()
  const disableDialog = useDialogState()

  const saQuery = accessClient.useQuery(
    'get',
    '/service_accounts/{service_account_id}',
    { params: { path: { service_account_id: serviceAccountId ?? '' } } },
    { enabled: !!serviceAccountId, retry: false }
  )

  const serviceAccount = saQuery.data
  const permissions = useServiceAccountPermissions({
    resourceProject: serviceAccount?.project_id ?? serviceAccount?.project_name ?? undefined,
  })
  const refetchSa = saQuery.refetch

  const navigateBack = useCallback(
    () => detachPromise(navigate({ to: AppRoute.AccessManagement.ServiceAccounts })),
    [navigate]
  )

  const { mutate: deleteServiceAccount } = accessClient.useMutation('delete', '/service_accounts/{service_account_id}')

  const handleDelete = useDeleteAction({
    deleteFn: deleteServiceAccount,
    buildParams: () => ({ params: { path: { service_account_id: serviceAccountId ?? '' } } }),
    entityLabel: 'service account',
    getItemName: () => serviceAccount?.name ?? '',
    onSuccess: navigateBack,
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

  const handleToggleStatus = () => {
    if (!serviceAccount) return
    if (serviceAccount.status === 'active') {
      disableDialog.open(undefined)
      return
    }
    enableServiceAccount(
      { params: { path: { service_account_id: serviceAccount.id } } },
      {
        onSuccess: () => detachPromise(refetchSa()),
        onError: handleMutationError({ title: 'Failed to enable service account' }),
      }
    )
  }

  const handleDisable = () => {
    if (!serviceAccount) return
    disableServiceAccount(
      { params: { path: { service_account_id: serviceAccount.id } } },
      {
        onSuccess: () => detachPromise(refetchSa()),
        onError: handleMutationError({ title: 'Failed to disable service account' }),
        onSettled: () => disableDialog.close(),
      }
    )
  }

  const queryState = useQueryState(saQuery, {
    title: 'Error loading service account',
    onRetry: () => {
      detachPromise(refetchSa())
    },
  })

  if (saQuery.error) {
    return (
      <DetailPageShell title="Service Account Details" breadcrumbs={breadcrumbsServiceAccountDetailEarlyShell()}>
        <ServiceAccountNotFoundState
          onBack={navigateBack}
          onRetry={() => {
            detachPromise(refetchSa())
          }}
        />
      </DetailPageShell>
    )
  }

  if (queryState) {
    return (
      <DetailPageShell title="Service Account Details" breadcrumbs={breadcrumbsServiceAccountDetailEarlyShell()}>
        {queryState}
      </DetailPageShell>
    )
  }

  if (!serviceAccount) return null

  const crumbs = breadcrumbsServiceAccountDetail(serviceAccount.name, basePath, activeTab)
  const isEnabled = serviceAccount.status === 'active'

  return (
    <SynPage>
      <SynPageTitle segments={[serviceAccount.name, 'Service Accounts']} />
      <SynPageHeader
        title={serviceAccount.name}
        breadcrumbs={crumbs}
        docLink={docLink}
        toolbar={
          <ServiceAccountToolbar
            permissions={permissions}
            isEnabled={isEnabled}
            onToggleStatus={handleToggleStatus}
            onEdit={() => editDialog.open(undefined)}
            onDelete={() => deleteDialog.open(undefined)}
          />
        }
      />
      <SynPageBody>
        <NxListPanel>
          <NxListPanelTabs
            basePath={basePath}
            defaultTab="details"
            validTabs={VALID_TABS}
            aria-label="Service account details"
          >
            <Tab eventKey="details" title={<TabTitleText>Details</TabTitleText>} />
            <Tab eventKey="credentials" title={<TabTitleText>Credentials</TabTitleText>} />
            <Tab eventKey="assignments" title={<TabTitleText>Assignments</TabTitleText>} />
          </NxListPanelTabs>
          {activeTab === 'details' && (
            <NxListPanelView
              tabKey="details"
              tabLabel="Details"
              isPending={false}
              error={null}
              isEmpty={false}
              hasActiveFilters={false}
              onRetry={noop}
              onClearAllFilters={noop}
              body={<DetailsTab serviceAccount={serviceAccount} />}
            />
          )}
          {activeTab === 'credentials' && (
            <CredentialsTab
              serviceAccountId={serviceAccount.id}
              serviceAccountName={serviceAccount.name}
              resourceProject={serviceAccount.project_id ?? serviceAccount.project_name ?? undefined}
            />
          )}
          {activeTab === 'assignments' && (
            <RoleAssignmentsPanel
              principalType={RolePrincipalType.SERVICE_ACCOUNT}
              principalId={serviceAccount.id}
              hiddenColumns={['scope']}
            />
          )}
        </NxListPanel>
      </SynPageBody>

      <EditServiceAccountModal
        serviceAccount={serviceAccount}
        isOpen={editDialog.isOpen}
        onClose={editDialog.close}
        onSuccess={() => {
          detachPromise(saQuery.refetch())
        }}
      />

      <NxConfirmationDialog
        isOpen={deleteDialog.isOpen}
        onClose={deleteDialog.close}
        onConfirm={() => handleDelete(undefined)}
        title="Delete service account?"
        confirmLabel="Delete"
        confirmVariant="danger"
        titleIconVariant="warning"
        destructiveAcknowledgement={{
          checkboxId: 'delete-sa-detail-ack',
          label: 'I understand this service account will be permanently deleted and all OAuth tokens revoked.',
        }}
      >
        The service account <strong>{serviceAccount.name}</strong> will be deleted. This cannot be undone.
      </NxConfirmationDialog>

      <NxConfirmationDialog
        isOpen={disableDialog.isOpen}
        onClose={disableDialog.close}
        onConfirm={handleDisable}
        title="Disable service account?"
        confirmLabel="Disable"
        confirmVariant="primary"
      >
        You are about to disable the service account <strong>{serviceAccount.name}</strong>. You can re-enable the
        service account at any time.
      </NxConfirmationDialog>
    </SynPage>
  )
}
