import { Badge, Button, DescriptionList, Stack, StackItem, Switch, Tab } from '@patternfly/react-core'
import {
  RhUiCheckCircleIcon,
  RhUiEditIcon,
  RhUiLockIcon,
  RhUiMinusCircleIcon,
  RhUiTrashIcon,
} from '@patternfly/react-icons'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useMemo, useState } from 'react'

import { AppRoute } from '../../../app/AppRoute'
import { breadcrumbsCredentialDetail, breadcrumbsCredentialEarlyShell } from '../../../app/breadcrumbBuilders'
import { credentialsClient } from '../../../client'
import { NxDetail } from '../../../components/details/NxDetail'
import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { IconLabel } from '../../../components/IconLabel'
import { SynLabel } from '../../../components/labels/SynLabel'
import { SynPage, SynPageBody } from '../../../components/layout/SynPage'
import { SynPageHeader } from '../../../components/layout/SynPageHeader'
import { SynPanel } from '../../../components/layout/SynPanel'
import { SynErrorState } from '../../../components/states/SynErrorState'
import { useQueryState } from '../../../components/states/useQueryState'
import type { KebabAction } from '../../../components/SynKebabMenu'
import { SynKebabMenu } from '../../../components/SynKebabMenu'
import { SynPageTitle } from '../../../components/SynPageTitle'
import { UserTimestamp } from '../../../components/table/UserTimestamp'
import { NxUrlTabs } from '../../../components/tabs/NxUrlTabs'
import { useDeleteAction } from '../../../hooks/useDeleteAction'
import { useUrlTab } from '../../../hooks/useUrlTab'
import { useAlerts } from '../../../providers/alerts'
import { getErrorMessage } from '../../../utils/apiErrors'
import { detachPromise } from '../../../utils/detachPromise'
import { useDocLink } from '../../../utils/docs/useDocLink'

import { ENCRYPTED_SENTINEL, type Credential } from './credentialConstants'
import styles from './CredentialDetail.module.css'
import { CredentialIntegrationsTab } from './CredentialIntegrationsTab'
import { CredentialWorkflowsTab } from './CredentialWorkflowsTab'
import { DeleteCredentialDialog } from './DeleteCredentialDialog'
import { DisableCredentialDialog } from './DisableCredentialDialog'
import { CredentialFormModal } from './form/CredentialFormModal'
import type { FieldDefinition } from './form/DynamicFieldRenderer'
import { useCredentialDetailPermissions } from './useCredentialDetailPermissions'
import { useCredentialPermissions } from './useCredentialPermissions'
import { useDeleteCredentialState } from './useDeleteCredentialState'
import { useDisableCredentialState } from './useDisableCredentialState'

type CredentialTab = 'details' | 'workflows' | 'integrations'
const ALL_CREDENTIAL_TABS: CredentialTab[] = ['details', 'workflows', 'integrations']

function getTypeDisplayText(typeName: string | undefined, typeLoadError: boolean): string {
  if (typeName) return typeName
  if (typeLoadError) return 'Failed to load type'
  return '\u2014'
}

function formatCount(count: number | null | undefined): string | number {
  return count != null && count > 0 ? count : '—'
}

function EnabledStateLabel({ enabled }: Readonly<{ enabled: boolean }>) {
  return enabled ? (
    <SynLabel variant="outline" status="success" icon={<RhUiCheckCircleIcon />}>
      Enabled
    </SynLabel>
  ) : (
    <SynLabel variant="outline" icon={<RhUiMinusCircleIcon />}>
      Disabled
    </SynLabel>
  )
}

type DynamicFieldsProps = { typeFields: FieldDefinition[]; credInputs: Record<string, unknown> }

function DynamicCredentialFields({ typeFields, credInputs }: Readonly<DynamicFieldsProps>) {
  return typeFields.map((field) => {
    const value = credInputs[field.id]
    const isEncrypted = value === ENCRYPTED_SENTINEL
    return (
      <NxDetail key={field.id} label={field.label}>
        {isEncrypted ? (
          <SynLabel variant="outline" icon={<RhUiLockIcon />}>
            Encrypted
          </SynLabel>
        ) : (
          String((value as string | number | boolean) ?? '—')
        )}
      </NxDetail>
    )
  })
}

function filterTabsByPermission(
  permissionsLoading: boolean,
  canReadWorkflows: boolean,
  canReadIntegrations: boolean
): CredentialTab[] {
  if (permissionsLoading) return ['details']
  const tabPermissions: Record<string, boolean> = { workflows: canReadWorkflows, integrations: canReadIntegrations }
  return ALL_CREDENTIAL_TABS.filter((tab) => tabPermissions[tab] ?? true)
}

// eslint-disable-next-line max-lines-per-function -- detail page with multiple tabs, dialogs, and toolbar actions
export default function CredentialDetail() {
  const credentialsDocLink = useDocLink('credentials')
  const { credentialId }: { credentialId: string } = useParams({ strict: false })
  const navigate = useNavigate()
  const credentialBasePath = AppRoute.Configuration.Credentials.Detail.replace(':credentialId', credentialId ?? '')
  const [activeTab] = useUrlTab<CredentialTab>(credentialBasePath)
  const { canReadWorkflows, canReadIntegrations, isLoading: permissionsLoading } = useCredentialDetailPermissions()

  const validTabs = useMemo(
    () => filterTabsByPermission(permissionsLoading, canReadWorkflows, canReadIntegrations),
    [canReadWorkflows, canReadIntegrations, permissionsLoading]
  )
  const [editModalOpen, setEditModalOpen] = useState(false)
  const { canUpdate, canDelete, tooltips } = useCredentialPermissions()
  const {
    credentialToDelete,
    affectedWorkflows: deleteAffectedWorkflows,
    workflowsFetchError: deleteWorkflowsFetchError,
    isLoadingWorkflows: deleteIsLoadingWorkflows,
    affectedIntegrations: deleteAffectedIntegrations,
    integrationsFetchError: deleteIntegrationsFetchError,
    isLoadingIntegrations: deleteIsLoadingIntegrations,
    openDeleteDialog,
    closeDeleteDialog,
  } = useDeleteCredentialState()

  // Disable credential dialog state
  const {
    credentialToDisable,
    affectedWorkflows,
    workflowsFetchError,
    isLoadingWorkflows: disableIsLoadingWorkflows,
    affectedIntegrations: disableAffectedIntegrations,
    integrationsFetchError: disableIntegrationsFetchError,
    isLoadingIntegrations: disableIsLoadingIntegrations,
    openDisableDialog,
    closeDisableDialog,
  } = useDisableCredentialState()

  const { showAlert } = useAlerts()

  // Fetch credential
  const credQuery = credentialsClient.useQuery(
    'get',
    '/credentials/{credential_id}',
    { params: { path: { credential_id: credentialId } } },
    { enabled: !!credentialId }
  )
  const credential = credQuery.data

  // Fetch credential type
  const typeQuery = credentialsClient.useQuery(
    'get',
    '/credential_types/{credential_type_id}',
    { params: { path: { credential_type_id: credential?.credential_type_id ?? '' } } },
    { enabled: !!credential?.credential_type_id }
  )
  const credType = typeQuery.data
  const typeLoadError = typeQuery.isError

  // Parse type fields
  const typeFields = useMemo(() => {
    if (!credType) return []
    const inputs = credType.inputs as Record<string, unknown>
    return (inputs?.fields as FieldDefinition[]) ?? []
  }, [credType])

  // Mutations
  const { mutate: patchCredential, isPending: isPatchPending } = credentialsClient.useMutation(
    'patch',
    '/credentials/{credential_id}'
  )
  const { mutate: deleteCredentialMut, isPending: isDeletePending } = credentialsClient.useMutation(
    'delete',
    '/credentials/{credential_id}'
  )

  function handleToggleEnabled() {
    if (!credential?.id) return
    if (credential.enabled) {
      openDisableDialog(credential)
      return
    }
    patchCredential(
      { params: { path: { credential_id: credential.id } }, body: { enabled: true } },
      {
        onSuccess: () => {
          detachPromise(credQuery.refetch())
        },
        onError: (error: unknown) => {
          showAlert({
            title: 'Failed to enable credential',
            description: getErrorMessage(error),
            variant: 'danger',
            autoDismiss: true,
          })
        },
      }
    )
  }

  function handleConfirmDisable() {
    if (!credentialToDisable?.id) return
    patchCredential(
      { params: { path: { credential_id: credentialToDisable.id } }, body: { enabled: false } },
      {
        onSuccess: () => {
          detachPromise(credQuery.refetch())
        },
        onError: (error: unknown) => {
          showAlert({
            title: 'Failed to disable credential',
            description: getErrorMessage(error),
            variant: 'danger',
            autoDismiss: true,
          })
        },
        onSettled: closeDisableDialog,
      }
    )
  }

  const handleConfirmDelete = useDeleteAction<Credential, { params: { path: { credential_id: string } } }>({
    deleteFn: (params, callbacks) => deleteCredentialMut(params, callbacks),
    // eslint-disable-next-line @typescript-eslint/no-non-null-assertion -- safe: credentials opened for deletion always have an id (server-assigned); ?? '' would produce an invalid path param
    buildParams: (cred) => ({ params: { path: { credential_id: cred.id! } } }),
    entityLabel: 'credential',
    getItemName: (cred) => cred.name,
    onSuccess: () => {
      detachPromise(navigate({ to: AppRoute.Configuration.Credentials.Root }))
    },
    onSettled: closeDeleteDialog,
  })

  const kebabActions: KebabAction[] = [
    {
      key: 'delete',
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete credential</IconLabel>,
      isDanger: true,
      isAriaDisabled: !canDelete,
      tooltipProps: canDelete ? undefined : { content: tooltips.delete },
      onClick: () => {
        if (credential) openDeleteDialog(credential)
      },
    },
  ]

  const queryState = useQueryState(credQuery, {
    title: 'Error loading credential',
    onRetry: () => detachPromise(credQuery.refetch()),
  })

  if (!credentialId) {
    return (
      <SynPage>
        <SynPageTitle segments={['Credential', 'Credentials']} />
        <SynPageHeader title="Error" breadcrumbs={breadcrumbsCredentialEarlyShell('Error')} />
        <SynPageBody>
          <SynPanel isFullHeight>
            <SynErrorState title="Invalid credential" message="No credential ID provided" />
          </SynPanel>
        </SynPageBody>
      </SynPage>
    )
  }

  if (queryState) {
    return (
      <SynPage>
        <SynPageTitle segments={['Credential', 'Credentials']} />
        <SynPageHeader title="Credential" breadcrumbs={breadcrumbsCredentialEarlyShell('Credential')} />
        <SynPageBody>
          <SynPanel isFullHeight>{queryState}</SynPanel>
        </SynPageBody>
      </SynPage>
    )
  }

  if (!credential?.id) return null

  const credInputs = credential.inputs ?? {}
  const credentialTypeDisplayText = getTypeDisplayText(credType?.name, typeLoadError)
  const hasDescription = Boolean(credential.description?.trim())

  const credentialCrumbs = breadcrumbsCredentialDetail(credential.id, credential.name, activeTab)

  return (
    <SynPage>
      <SynPageTitle segments={[credential.name, 'Credentials']} />
      <SynPageHeader
        breadcrumbs={credentialCrumbs}
        title={credential.name}
        docLink={credentialsDocLink}
        toolbar={
          <>
            <DisabledWithTooltip isDisabled={!canUpdate} content={tooltips.enable}>
              <Switch
                id="credential-detail-toggle"
                label="Enabled"
                isChecked={credential.enabled}
                isDisabled={!canUpdate}
                onChange={handleToggleEnabled}
              />
            </DisabledWithTooltip>
            <DisabledWithTooltip isDisabled={!canUpdate} content={tooltips.update}>
              <Button
                variant="primary"
                icon={<RhUiEditIcon />}
                isAriaDisabled={!canUpdate}
                onClick={() => setEditModalOpen(true)}
              >
                Edit credential
              </Button>
            </DisabledWithTooltip>
            <SynKebabMenu actions={kebabActions} aria-label="Credential actions" />
          </>
        }
      />

      <SynPageBody>
        <SynPanel isFullHeight className={styles.tabsFullHeight}>
          <NxUrlTabs
            basePath={credentialBasePath}
            defaultTab="details"
            validTabs={validTabs}
            aria-label="Credential details"
          >
            <Tab eventKey="details" title="Details">
              <Stack hasGutter style={{ padding: 'var(--pf-t--global--spacer--lg)' }}>
                <StackItem>
                  <DescriptionList isHorizontal>
                    <NxDetail label="Name">{credential.name}</NxDetail>
                    {hasDescription ? <NxDetail label="Description">{credential.description}</NxDetail> : null}
                    <NxDetail label="Type">{credentialTypeDisplayText}</NxDetail>
                    <NxDetail label="Workflows">{formatCount(credential.workflow_count)}</NxDetail>
                    <NxDetail label="Integrations">{formatCount(credential.integration_count)}</NxDetail>
                    <NxDetail label="Last modified">
                      <UserTimestamp
                        user={credential.updated_by}
                        timestamp={credential.updated_at}
                        subtleTimestamp={false}
                      />
                    </NxDetail>
                    <NxDetail label="Created">
                      <UserTimestamp
                        user={credential.created_by}
                        timestamp={credential.created_at}
                        subtleTimestamp={false}
                      />
                    </NxDetail>
                    <NxDetail label="State">
                      <EnabledStateLabel enabled={credential.enabled ?? false} />
                    </NxDetail>

                    <DynamicCredentialFields typeFields={typeFields} credInputs={credInputs} />
                  </DescriptionList>
                </StackItem>
              </Stack>
            </Tab>

            {validTabs.includes('workflows') && (
              <Tab
                eventKey="workflows"
                title={
                  <>
                    Workflows <Badge isRead>{credential.workflow_count ?? 0}</Badge>
                  </>
                }
              >
                <CredentialWorkflowsTab credentialId={credential.id} />
              </Tab>
            )}

            {validTabs.includes('integrations') && (
              <Tab
                eventKey="integrations"
                title={
                  <>
                    Integrations <Badge isRead>{credential.integration_count ?? 0}</Badge>
                  </>
                }
              >
                <CredentialIntegrationsTab credentialId={credential.id} />
              </Tab>
            )}
          </NxUrlTabs>
        </SynPanel>
      </SynPageBody>

      <DisableCredentialDialog
        credential={credentialToDisable}
        affectedWorkflows={affectedWorkflows}
        workflowsFetchError={workflowsFetchError}
        isLoadingWorkflows={disableIsLoadingWorkflows}
        affectedIntegrations={disableAffectedIntegrations}
        integrationsFetchError={disableIntegrationsFetchError}
        isLoadingIntegrations={disableIsLoadingIntegrations}
        isLoading={isPatchPending}
        onConfirm={handleConfirmDisable}
        onClose={closeDisableDialog}
      />

      <DeleteCredentialDialog
        credential={credentialToDelete}
        affectedWorkflows={deleteAffectedWorkflows}
        workflowsFetchError={deleteWorkflowsFetchError}
        isLoadingWorkflows={deleteIsLoadingWorkflows}
        affectedIntegrations={deleteAffectedIntegrations}
        integrationsFetchError={deleteIntegrationsFetchError}
        isLoadingIntegrations={deleteIsLoadingIntegrations}
        isLoading={isDeletePending}
        onConfirm={() => handleConfirmDelete(credentialToDelete)}
        onClose={closeDeleteDialog}
      />

      <CredentialFormModal
        isOpen={editModalOpen}
        onClose={() => setEditModalOpen(false)}
        credentialToEdit={credential}
        onSuccess={() => detachPromise(credQuery.refetch())}
      />
    </SynPage>
  )
}
