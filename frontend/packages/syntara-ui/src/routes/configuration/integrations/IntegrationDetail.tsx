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
import { useNavigate, useParams } from '@tanstack/react-router'

import { AppRoute } from '../../../app/AppRoute'
import {
  breadcrumbsIntegrationDetail,
  breadcrumbsIntegrationDetailEarlyShell,
  type IntegrationDetailBreadcrumbTab,
} from '../../../app/breadcrumbBuilders'
import { credentialsClient, integrationsClient } from '../../../client'
import { NxDetail } from '../../../components/details/NxDetail'
import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { IconLabel } from '../../../components/IconLabel'
import { NxLabel } from '../../../components/labels/NxLabel'
import { SynPage, SynPageBody } from '../../../components/layout/SynPage'
import { SynPageHeader } from '../../../components/layout/SynPageHeader'
import { SynPanel } from '../../../components/layout/SynPanel'
import type { KebabAction } from '../../../components/NxKebabMenu'
import { NxKebabMenu } from '../../../components/NxKebabMenu'
import { NxLink } from '../../../components/NxLink'
import { SynErrorState } from '../../../components/states/SynErrorState'
import { useQueryState } from '../../../components/states/useQueryState'
import { SynPageTitle } from '../../../components/SynPageTitle'
import { DateCell } from '../../../components/table/DateCell.tsx'
import { NxUrlTabs } from '../../../components/tabs/NxUrlTabs'
import { useUrlTab } from '../../../hooks/useUrlTab'
import { detachPromise } from '../../../utils/detachPromise'
import { useDocLink } from '../../../utils/docs/useDocLink'

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
        <NxLabel key={a.project_id}>{a.project_name}</NxLabel>
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
          <NxDetail label={isLLMProvider(integration) ? 'Name' : 'Server name / ID'}>{integration.name}</NxDetail>
          <NxDetail label="Description">{integration.description}</NxDetail>
          <NxDetail label="Integration type">
            {INTEGRATION_TYPE_LABELS[integration.integration_type ?? ''] ?? integration.integration_type ?? ''}
          </NxDetail>
          <NxDetail label="Status">
            <StatusLabel
              status={integration.validation_status ?? 'unknown'}
              errorMessage={integration.validation_error}
            />
          </NxDetail>
          <NxDetail label="Last checked">
            <DateCell dateString={integration.last_validated_at} />
          </NxDetail>
          <NxDetail label="Scope">{integration.scope === 'project' ? 'Project' : 'Global'}</NxDetail>
          {integration.scope === 'project' && integration.id && (
            <NxDetail label="Assigned projects">
              <IntegrationProjectsList integrationId={integration.id} />
            </NxDetail>
          )}
          {isLLMProvider(integration) && (
            <NxDetail label="Provider type">
              {PROVIDER_HINT_LABELS[getProviderHint(integration)] ?? getProviderHint(integration)}
            </NxDetail>
          )}
          <NxDetail label="URL">{getBaseUrl(integration) || '—'}</NxDetail>
          <NxDetail label="Connection credential">
            {!credentialId || !credentialName ? (
              <>None</>
            ) : (
              <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
                <FlexItem>
                  <NxLink to={AppRoute.Configuration.Credentials.Detail.replace(':credentialId', credentialId)}>
                    {credentialName}
                  </NxLink>
                </FlexItem>
                {!credentialEnabled && (
                  <FlexItem>
                    <NxLabel variant="outline" status="warning" icon={<RhUiWarningIcon />}>
                      Credential disabled
                    </NxLabel>
                  </FlexItem>
                )}
              </Flex>
            )}
          </NxDetail>
          {(isLLMProvider(integration) || integration.integration_type === IntegrationTypeEnum.MCP_SERVER) && (
            <NxDetail label={`Enabled ${resourceNoun}`}>{String(enabledResourceCount)}</NxDetail>
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
  permissions,
}: Readonly<{
  integration: IntegrationRead
  kebabActions: KebabAction[]
  onToggleEnabled: () => void
  onEdit: () => void
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
          Edit integration
        </Button>
      </DisabledWithTooltip>
      <NxKebabMenu actions={kebabActions} aria-label="Integration actions" />
    </>
  )
}

function buildKebabActions(
  integration: IntegrationRead | undefined,
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
      onClick: permissions.canUpdate
        ? () => {
            if (integration) validateDialog.open(integration)
          }
        : undefined,
    },
    { key: 'separator', isSeparator: true },
    {
      key: 'delete',
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete integration</IconLabel>,
      isDanger: true,
      isAriaDisabled: !permissions.canDelete,
      tooltipProps: permissions.canDelete ? undefined : { content: permissions.tooltips.delete },
      onClick: permissions.canDelete
        ? () => {
            if (integration) deleteDialog.open(integration)
          }
        : undefined,
    },
  ]
}

function ResourcesFooter({
  isDirty,
  isSaving,
  onSave,
  saveLabel = 'Save changes',
}: Readonly<{ isDirty: boolean; isSaving: boolean; onSave: () => void; saveLabel?: string }>) {
  return (
    <ActionGroup>
      <Button variant="primary" onClick={isDirty ? onSave : undefined} isAriaDisabled={!isDirty} isLoading={isSaving}>
        {saveLabel}
      </Button>
    </ActionGroup>
  )
}

function getFooterState(
  isLLM: boolean,
  modelsState: ReturnType<typeof useIntegrationModelsState>,
  toolsDirty: boolean,
  isToolsSaving: boolean,
  handleToolsSave: () => void
) {
  if (isLLM) {
    return {
      isDirty: modelsState.isDirty,
      isSaving: modelsState.isSaving,
      onSave: modelsState.handleSave,
      saveLabel: 'Save model changes',
    }
  }
  return { isDirty: toolsDirty, isSaving: isToolsSaving, onSave: handleToolsSave, saveLabel: 'Save changes' }
}

function hasResourcesTab(integration: IntegrationsAPI.components['schemas']['IntegrationRead']): boolean {
  return isLLMProvider(integration) || integration.integration_type === IntegrationTypeEnum.MCP_SERVER
}

export function IntegrationDetail() {
  const { integrationId }: { integrationId: string } = useParams({ strict: false })
  const navigate = useNavigate()
  const integrationBasePath = AppRoute.Configuration.Integrations.Detail.replace(':integrationId', integrationId)
  const editPath = AppRoute.Configuration.Integrations.Edit.replace(':integrationId', integrationId)
  const [activeTab] = useUrlTab<IntegrationDetailBreadcrumbTab | 'edit'>(integrationBasePath)
  const docLink = useDocLink('integrations')
  const permissions = useIntegrationPermissions()

  const query = integrationsClient.useQuery(
    'get',
    '/integrations/{integration_id}',
    { params: { path: { integration_id: integrationId } } },
    { enabled: integrationId.length > 0 }
  )
  const integration = query.data

  const credentialQuery = credentialsClient.useQuery(
    'get',
    '/credentials/{credential_id}',
    { params: { path: { credential_id: integration?.management_credential_id ?? '' } } },
    { enabled: !!integration?.management_credential_id }
  )
  const credentialName = credentialQuery.data?.name ?? undefined
  const credentialEnabled = credentialQuery.data?.enabled ?? true

  const {
    validateDialog,
    deleteDialog,
    disableDialog,
    handleValidate,
    handleDelete,
    handleToggleEnabled,
    handleDisable,
  } = useIntegrationActions(() => query.refetch())

  const kebabActions = buildKebabActions(integration, validateDialog, deleteDialog, permissions)

  const enabledResourceCount = integration ? getEnabledResourceCount(integration) : 0
  const isLLM = integration ? isLLMProvider(integration) : false

  // Tools state (MCP servers)
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

  // Models state (LLM providers)
  const modelsState = useIntegrationModelsState(integrationId, isLLM)

  const footerState = getFooterState(isLLM, modelsState, toolsDirty, isToolsSaving, handleToolsSave)

  const queryState = useQueryState(query, {
    title: 'Error loading integration',
    onRetry: () => detachPromise(query.refetch()),
  })

  if (activeTab === 'edit') return null

  if (!integrationId) {
    return (
      <SynPage>
        <SynPageTitle segments={['Integration', 'Integrations']} />
        <SynPageHeader title="Error" breadcrumbs={breadcrumbsIntegrationDetailEarlyShell()} />
        <SynPageBody>
          <SynPanel isFullHeight>
            <SynErrorState title="Invalid integration" message="No integration ID provided" />
          </SynPanel>
        </SynPageBody>
      </SynPage>
    )
  }

  if (queryState) {
    return (
      <SynPage>
        <SynPageTitle segments={['Integration', 'Integrations']} />
        <SynPageHeader title="Integration" breadcrumbs={breadcrumbsIntegrationDetailEarlyShell()} />
        <SynPageBody>
          <SynPanel isFullHeight>{queryState}</SynPanel>
        </SynPageBody>
      </SynPage>
    )
  }

  if (!integration?.id) return null

  const integrationCrumbs = breadcrumbsIntegrationDetail(integration.id, integration.name, activeTab)
  const footer = activeTab === 'resources' ? <ResourcesFooter {...footerState} /> : undefined

  return (
    <SynPage>
      <SynPageTitle segments={[integration.name, 'Integrations']} />
      <SynPageHeader
        breadcrumbs={integrationCrumbs}
        title={integration.name}
        docLink={docLink}
        toolbar={
          <IntegrationToolbar
            integration={integration}
            kebabActions={kebabActions}
            onToggleEnabled={() => handleToggleEnabled(integration)}
            onEdit={() => detachPromise(navigate({ to: editPath }))}
            permissions={permissions}
          />
        }
      />

      <SynPageBody>
        <SynPanel isFullHeight isScrollable footer={footer} className={styles.tabsFullHeight}>
          <NxUrlTabs
            basePath={integrationBasePath}
            defaultTab="details"
            validTabs={hasResourcesTab(integration) ? ['details', 'resources'] : ['details']}
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

            {hasResourcesTab(integration) && (
              <Tab
                eventKey="resources"
                title={
                  <>
                    Enabled resources{' '}
                    {getTotalResourceCount(integration) > 0 && <Badge isRead>{enabledResourceCount}</Badge>}
                  </>
                }
              >
                <ResourcesTabContent
                  integration={integration}
                  isLLM={isLLM}
                  modelsState={modelsState}
                  tools={tools}
                  enabledToolIds={enabledToolIds}
                  toolEnabledCount={toolEnabledCount}
                  handleSelectTool={handleSelectTool}
                  refetchTools={() => refetchTools()}
                  onRefreshed={async () => {
                    const result = await query.refetch()
                    return result.data
                  }}
                  canUpdate={permissions.canUpdate}
                  updateTooltip={permissions.tooltips.update}
                />
              </Tab>
            )}
          </NxUrlTabs>
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
    </SynPage>
  )
}
