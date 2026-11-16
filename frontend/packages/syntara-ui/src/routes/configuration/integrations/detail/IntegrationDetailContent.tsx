import { Tab } from '@patternfly/react-core'
import type { IntegrationsAPI } from '@syntara/contracts'
import { useNavigate } from '@tanstack/react-router'
import type { ReactNode } from 'react'

import { AppRoute } from '../../../../app/AppRoute'
import {
  breadcrumbsIntegrationDetail,
  breadcrumbsIntegrationDetailEarlyShell,
} from '../../../../app/breadcrumbBuilders'
import { credentialsClient } from '../../../../client'
import { SynPage, SynPageBody } from '../../../../components/layout/SynPage'
import { SynPageHeader } from '../../../../components/layout/SynPageHeader'
import { SynPanel } from '../../../../components/layout/SynPanel'
import { SynPageTitle } from '../../../../components/SynPageTitle'
import { SynUrlTabs } from '../../../../components/tabs/SynUrlTabs'
import { useUrlTab } from '../../../../hooks/useUrlTab'
import { useDocLink } from '../../../../utils/docs/useDocLink'
import { IntegrationDialogs } from '../IntegrationDialogs'
import { getEnabledResourceCount, isLLMProvider } from '../integrationUtils'
import { useIntegrationActions } from '../useIntegrationActions'
import { useIntegrationPermissions } from '../useIntegrationPermissions'

import styles from './IntegrationDetail.module.css'
import { getFooterState, hasResourcesTab, shouldShowResourcesFooter } from './integrationDetailHelpers'
import { IntegrationDetailsTab } from './IntegrationDetailsTab'
import { ResourcesFooter, ResourcesTabTitle } from './IntegrationResourcesChrome'
import { IntegrationToolbar } from './IntegrationToolbar'
import { buildKebabActions, getEditToolbarProps } from './integrationToolbarHelpers'
import { ResourcesTabContent } from './ResourcesTabContent'
import { useAllIntegrationTools } from './useAllIntegrationTools'
import { useIntegrationModelsState } from './useIntegrationModelsState'
import { useItemSelection } from './useItemSelection'
import { useResourcesSave } from './useResourcesSave'

type IntegrationRead = IntegrationsAPI.components['schemas']['IntegrationRead']

export type IntegrationDetailTab = 'details' | 'resources' | 'edit'

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
        renameDialog={renameDialog}
        isRenaming={isRenaming}
        onValidate={handleValidate}
        onDelete={handleDelete}
        onDisable={handleDisable}
        onRename={handleRename}
      />
    </SynPage>
  )
}
