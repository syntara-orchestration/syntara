import {
  ActionGroup,
  Badge,
  Button,
  DescriptionList,
  Flex,
  FlexItem,
  LabelGroup,
  Skeleton,
  Stack,
  StackItem,
  Switch,
  Tab,
  Tooltip,
} from '@patternfly/react-core'
import { RhUiCheckCircleIcon, RhUiEditIcon, RhUiTrashIcon, RhUiWarningIcon } from '@patternfly/react-icons'
import type { IntegrationsAPI } from '@syntara/contracts'
import { IntegrationTypeEnum } from '@syntara/contracts'
import { useNavigate } from '@tanstack/react-router'
import type { ReactNode } from 'react'

import { AppRoute } from '../../../app/AppRoute'
import { breadcrumbsIntegrationDetail, breadcrumbsIntegrationDetailEarlyShell } from '../../../app/breadcrumbBuilders'
import { credentialsClient, integrationsClient } from '../../../client'
import { SynDetail } from '../../../components/details/SynDetail'
import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { IconLabel } from '../../../components/IconLabel'
import { SynLabel } from '../../../components/labels/SynLabel'
import { SynPage, SynPageBody } from '../../../components/layout/SynPage'
import { SynPageHeader } from '../../../components/layout/SynPageHeader'
import { SynPanel } from '../../../components/layout/SynPanel'
import type { KebabAction } from '../../../components/SynKebabMenu'
import { SynKebabMenu } from '../../../components/SynKebabMenu'
import { SynLink } from '../../../components/SynLink'
import { SynPageTitle } from '../../../components/SynPageTitle'
import { DateCell } from '../../../components/table/DateCell'
import { SynUrlTabs } from '../../../components/tabs/SynUrlTabs'
import { useUrlTab } from '../../../hooks/useUrlTab'
import { detachPromise } from '../../../utils/detachPromise'
import { useDocLink } from '../../../utils/docs/useDocLink'

import { EditIntegrationNameModal } from './EditIntegrationNameModal'
import styles from './IntegrationDetail.module.css'
import { IntegrationDialogs } from './IntegrationDialogs'
import { INTEGRATION_TYPE_LABELS, PROVIDER_HINT_LABELS } from './integrationFilters'
import {
  getBaseUrl,
  getEnabledResourceCount,
  getProviderHint,
  getResourceNoun,
  getTotalResourceCount,
  isLLMProvider,
} from './integrationUtils'
import { ResourcesTabContent } from './ResourcesTabContent'
import { SecuritySection } from './SecuritySection'
import { StatusLabel } from './StatusLabel'
import { useAllIntegrationTools } from './useAllIntegrationTools'
import { useIntegrationActions } from './useIntegrationActions'
import { useIntegrationModelsState } from './useIntegrationModelsState'
import { type IntegrationPermissions, useIntegrationPermissions } from './useIntegrationPermissions'
import { useItemSelection } from './useItemSelection'
import { useResourcesSave } from './useResourcesSave'

type IntegrationRead = IntegrationsAPI.components['schemas']['IntegrationRead']
type IntegrationDetailTab = 'details' | 'resources' | 'edit'

function IntegrationProjectsList({ integrationId }: Readonly<{ integrationId: string }>) {
  const { data, isPending } = integrationsClient.useQuery('get', '/integrations/{integration_id}/projects', {
    params: { path: { integration_id: integrationId } },
  })

  if (isPending) return <Skeleton width="200px" />

  const assignments = data?.resources ?? []
  if (assignments.length === 0) return <>—</>

  return (
    <LabelGroup numLabels={5}>
      {assignments.map((a) => (
        <SynLabel key={a.project_id}>{a.project_name}</SynLabel>
      ))}
    </LabelGroup>
  )
}

function IntegrationDetailsTab({
  integration,
  enabledResourceCount,
  credentialName,
  credentialEnabled,
}: Readonly<{
  integration: IntegrationRead
  enabledResourceCount: number
  credentialName: string | undefined
  credentialEnabled: boolean
}>) {
  const credentialId = integration.management_credential_id
  const resourceNoun = getResourceNoun(integration)

  return (
    <Stack hasGutter className={styles.tabContent}>
      <StackItem>
        <DescriptionList isHorizontal>
          <SynDetail label={isLLMProvider(integration) ? 'Name' : 'Server name / ID'}>{integration.name}</SynDetail>
          <SynDetail label="Description">{integration.description}</SynDetail>
          <SynDetail label="Integration type">
            {INTEGRATION_TYPE_LABELS[integration.integration_type ?? ''] ?? integration.integration_type ?? ''}
          </SynDetail>
          <SynDetail label="Status">
            <StatusLabel
              status={integration.validation_status ?? 'unknown'}
              errorMessage={integration.validation_error}
            />
          </SynDetail>
          <SynDetail label="Last checked">
            <DateCell dateString={integration.last_validated_at} />
          </SynDetail>
          <SynDetail label="Scope">{integration.scope === 'project' ? 'Project' : 'Global'}</SynDetail>
          {integration.scope === 'project' && integration.id && (
            <SynDetail label="Assigned projects">
              <IntegrationProjectsList integrationId={integration.id} />
            </SynDetail>
          )}
          {isLLMProvider(integration) && (
            <SynDetail label="Provider type">
              {PROVIDER_HINT_LABELS[getProviderHint(integration)] ?? getProviderHint(integration)}
            </SynDetail>
          )}
          <SynDetail label="URL">{getBaseUrl(integration) || '—'}</SynDetail>
          <SynDetail label="Connection credential">
            {!credentialId || !credentialName ? (
              <>None</>
            ) : (
              <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
                <FlexItem>
                  <SynLink to={AppRoute.Configuration.Credentials.Detail.replace(':credentialId', credentialId)}>
                    {credentialName}
                  </SynLink>
                </FlexItem>
                {!credentialEnabled && (
                  <FlexItem>
                    <SynLabel variant="outline" status="warning" icon={<RhUiWarningIcon />}>
                      Credential disabled
                    </SynLabel>
                  </FlexItem>
                )}
              </Flex>
            )}
          </SynDetail>
          {(isLLMProvider(integration) || integration.integration_type === IntegrationTypeEnum.MCP_SERVER) && (
            <SynDetail label={`Enabled ${resourceNoun}`}>{String(enabledResourceCount)}</SynDetail>
          )}
        </DescriptionList>
      </StackItem>
      <SecuritySection configuration={integration.configuration} />
    </Stack>
  )
}

function IntegrationToolbar({
  integration,
  kebabActions,
  onToggleEnabled,
  onEdit,
  editLabel,
  permissions,
}: Readonly<{
  integration: IntegrationRead
  kebabActions: KebabAction[]
  onToggleEnabled: () => void
  onEdit: () => void
  editLabel: string
  permissions: IntegrationPermissions
}>) {
  return (
    <>
      {permissions.isLoading || !permissions.canUpdate ? (
        <Tooltip content={permissions.tooltips.enable}>
          <Switch
            id="integration-enabled-toggle"
            label={integration.enabled ? 'Enabled' : 'Disabled'}
            isChecked={integration.enabled ?? true}
            isDisabled
            aria-label={`Toggle ${integration.name}`}
          />
        </Tooltip>
      ) : (
        <Switch
          id="integration-enabled-toggle"
          label={integration.enabled ? 'Enabled' : 'Disabled'}
          isChecked={integration.enabled ?? true}
          onChange={onToggleEnabled}
          aria-label={`Toggle ${integration.name}`}
        />
      )}
      <DisabledWithTooltip isDisabled={!permissions.canUpdate} content={permissions.tooltips.update}>
        <Button
          variant="primary"
          icon={<RhUiEditIcon />}
          isAriaDisabled={!permissions.canUpdate}
          onClick={permissions.canUpdate ? onEdit : undefined}
        >
          {editLabel}
        </Button>
      </DisabledWithTooltip>
      <SynKebabMenu actions={kebabActions} aria-label="Integration actions" />
    </>
  )
}

function ResourcesFooter({
  isDirty,
  isSaving,
  onSave,
  saveLabel = 'Save tools',
}: Readonly<{ isDirty: boolean; isSaving: boolean; onSave: () => void; saveLabel?: string }>) {
  return (
    <ActionGroup>
      <Button variant="primary" onClick={isDirty ? onSave : undefined} isAriaDisabled={!isDirty} isLoading={isSaving}>
        {saveLabel}
      </Button>
    </ActionGroup>
  )
}

function hasResourcesTab(integration: IntegrationRead): boolean {
  return isLLMProvider(integration) || integration.integration_type === IntegrationTypeEnum.MCP_SERVER
}

function shouldShowResourcesFooter(
  isLLM: boolean,
  tools: ReturnType<typeof useAllIntegrationTools>['tools'],
  modelsState: ReturnType<typeof useIntegrationModelsState>
): boolean {
  if (isLLM) {
    if (modelsState.isLoading || modelsState.error) return false
    return modelsState.models.length > 0
  }
  return tools.length > 0
}

function getEditToolbarProps(
  integration: IntegrationRead,
  editPath: string,
  navigate: ReturnType<typeof useNavigate>,
  renameDialog: ReturnType<typeof useIntegrationActions>['renameDialog']
) {
  if (integration.integration_type === IntegrationTypeEnum.OPENSHIFT) {
    return {
      editLabel: 'Edit name',
      onEdit: () => renameDialog.open(integration),
    }
  }
  return {
    editLabel: 'Edit integration',
    onEdit: () => detachPromise(navigate({ to: editPath })),
  }
}

function ResourcesTabTitle({
  integration,
  enabledResourceCount,
}: Readonly<{ integration: IntegrationRead; enabledResourceCount: number }>) {
  return <>Enabled resources {getTotalResourceCount(integration) > 0 && <Badge isRead>{enabledResourceCount}</Badge>}</>
}

function buildKebabActions(
  integration: IntegrationRead,
  validateDialog: { open: (item: IntegrationRead) => void },
  deleteDialog: { open: (item: IntegrationRead) => void },
  permissions: IntegrationPermissions
): KebabAction[] {
  return [
    {
      key: 'validate',
      title: <IconLabel icon={<RhUiCheckCircleIcon />}>Validate integration</IconLabel>,
      isAriaDisabled: !permissions.canUpdate,
      tooltipProps: permissions.canUpdate ? undefined : { content: permissions.tooltips.validate },
      onClick: permissions.canUpdate ? () => validateDialog.open(integration) : undefined,
    },
    { key: 'separator', isSeparator: true },
    {
      key: 'delete',
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete integration</IconLabel>,
      isDanger: true,
      isAriaDisabled: !permissions.canDelete,
      tooltipProps: permissions.canDelete ? undefined : { content: permissions.tooltips.delete },
      onClick: permissions.canDelete ? () => deleteDialog.open(integration) : undefined,
    },
  ]
}

function getFooterState({
  isLLM,
  modelsState,
  toolsDirty,
  isToolsSaving,
  handleToolsSave,
}: {
  isLLM: boolean
  modelsState: ReturnType<typeof useIntegrationModelsState>
  toolsDirty: boolean
  isToolsSaving: boolean
  handleToolsSave: () => void
}) {
  if (isLLM) {
    return {
      isDirty: modelsState.isDirty,
      isSaving: modelsState.isSaving,
      onSave: modelsState.handleSave,
      saveLabel: 'Save models',
    }
  }
  return { isDirty: toolsDirty, isSaving: isToolsSaving, onSave: handleToolsSave, saveLabel: 'Save tools' }
}

export function IntegrationDetailEarlyShell({ title, children }: Readonly<{ title: string; children: ReactNode }>) {
  return (
    <SynPage>
      <SynPageTitle segments={['Integration', 'Integrations']} />
      <SynPageHeader title={title} breadcrumbs={breadcrumbsIntegrationDetailEarlyShell()} />
      <SynPageBody>
        <SynPanel isFullHeight>{children}</SynPanel>
      </SynPageBody>
    </SynPage>
  )
}

type IntegrationDetailContentProps = Readonly<{
  integration: IntegrationRead
  onRefetch: () => Promise<{ data?: IntegrationRead }>
}>

export function IntegrationDetailContent({ integration, onRefetch }: IntegrationDetailContentProps) {
  const navigate = useNavigate()
  const integrationId = integration.id ?? ''
  const integrationBasePath = AppRoute.Configuration.Integrations.Detail.replace(':integrationId', integrationId)
  const editPath = AppRoute.Configuration.Integrations.Edit.replace(':integrationId', integrationId)
  const [activeTab] = useUrlTab<IntegrationDetailTab>(integrationBasePath)
  const docLink = useDocLink('integrations')
  const permissions = useIntegrationPermissions()

  const credentialQuery = credentialsClient.useQuery(
    'get',
    '/credentials/{credential_id}',
    { params: { path: { credential_id: integration.management_credential_id ?? '' } } },
    { enabled: !!integration.management_credential_id }
  )
  const credentialName = credentialQuery.data?.name ?? undefined
  const credentialEnabled = credentialQuery.data?.enabled ?? true

  const {
    validateDialog,
    deleteDialog,
    disableDialog,
    renameDialog,
    isRenaming,
    handleValidate,
    handleDelete,
    handleToggleEnabled,
    handleDisable,
    handleRename,
  } = useIntegrationActions(onRefetch)

  const kebabActions = buildKebabActions(integration, validateDialog, deleteDialog, permissions)
  const editToolbar = getEditToolbarProps(integration, editPath, navigate, renameDialog)

  const enabledResourceCount = getEnabledResourceCount(integration)
  const isLLM = isLLMProvider(integration)
  const showResources = hasResourcesTab(integration)

  const { tools, refetch: refetchTools } = useAllIntegrationTools(integrationId)
  const {
    enabledIds: enabledToolIds,
    enabledCount: toolEnabledCount,
    isDirty: toolsDirty,
    handleSelectItem: handleSelectTool,
    resetToServer: resetToolsToServer,
  } = useItemSelection(tools, tools)
  const { isSaving: isToolsSaving, handleSave: handleToolsSave } = useResourcesSave({
    integrationId,
    tools,
    enabledToolIds,
    isDirty: toolsDirty,
    resetToServer: resetToolsToServer,
    isActive: !isLLM,
  })

  const modelsState = useIntegrationModelsState(integrationId, isLLM)
  const footerState = getFooterState({ isLLM, modelsState, toolsDirty, isToolsSaving, handleToolsSave })
  const showResourcesFooter = shouldShowResourcesFooter(isLLM, tools, modelsState)
  const footer = activeTab === 'resources' && showResourcesFooter ? <ResourcesFooter {...footerState} /> : undefined

  return (
    <SynPage>
      <SynPageTitle segments={[integration.name, 'Integrations']} />
      <SynPageHeader
        breadcrumbs={breadcrumbsIntegrationDetail(integration.name)}
        title={integration.name}
        docLink={docLink}
        toolbar={
          <IntegrationToolbar
            integration={integration}
            kebabActions={kebabActions}
            onToggleEnabled={() => handleToggleEnabled(integration)}
            onEdit={editToolbar.onEdit}
            editLabel={editToolbar.editLabel}
            permissions={permissions}
          />
        }
      />

      <SynPageBody>
        <SynPanel isFullHeight isScrollable footer={footer} className={styles.tabsFullHeight}>
          <SynUrlTabs
            basePath={integrationBasePath}
            defaultTab="details"
            validTabs={showResources ? ['details', 'resources'] : ['details']}
            aria-label="Integration details"
            guardUnsavedChanges
          >
            <Tab eventKey="details" title="Details">
              <IntegrationDetailsTab
                integration={integration}
                enabledResourceCount={enabledResourceCount}
                credentialName={credentialName}
                credentialEnabled={credentialEnabled}
              />
            </Tab>

            {showResources && (
              <Tab
                eventKey="resources"
                title={<ResourcesTabTitle integration={integration} enabledResourceCount={enabledResourceCount} />}
              >
                <ResourcesTabContent
                  integration={integration}
                  isLLM={isLLM}
                  modelsState={modelsState}
                  tools={tools}
                  enabledToolIds={enabledToolIds}
                  toolEnabledCount={toolEnabledCount}
                  handleSelectTool={handleSelectTool}
                  refetchTools={refetchTools}
                  onRefreshed={async () => {
                    const result = await onRefetch()
                    return result.data
                  }}
                  canUpdate={permissions.canUpdate}
                  updateTooltip={permissions.tooltips.update}
                />
              </Tab>
            )}
          </SynUrlTabs>
        </SynPanel>
      </SynPageBody>

      <IntegrationDialogs
        validateDialog={validateDialog}
        deleteDialog={deleteDialog}
        disableDialog={disableDialog}
        onValidate={handleValidate}
        onDelete={handleDelete}
        onDisable={handleDisable}
      />

      <EditIntegrationNameModal
        isOpen={renameDialog.isOpen}
        isSaving={isRenaming}
        initialName={renameDialog.item?.name ?? ''}
        onClose={renameDialog.close}
        onSave={handleRename}
      />
    </SynPage>
  )
}
