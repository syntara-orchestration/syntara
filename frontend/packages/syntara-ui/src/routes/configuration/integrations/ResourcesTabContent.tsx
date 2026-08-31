import type { IntegrationsAPI, Tool } from '@syntara/contracts'

import { SynPanelContentStack } from '../../../components/layout/SynPanelContentStack'

import styles from './IntegrationDetail.module.css'
import { IntegrationModelsTab } from './IntegrationModelsTab'
import { IntegrationResourcesTab } from './IntegrationResourcesTab'
import type { useIntegrationModelsState } from './useIntegrationModelsState'

export function ResourcesTabContent({
  integration,
  isLLM,
  modelsState,
  tools,
  enabledToolIds,
  toolEnabledCount,
  handleSelectTool,
  refetchTools,
  onRefreshed,
  canUpdate,
  updateTooltip,
}: Readonly<{
  integration: IntegrationsAPI.components['schemas']['IntegrationRead']
  isLLM: boolean
  modelsState: ReturnType<typeof useIntegrationModelsState>
  tools: Tool[]
  enabledToolIds: Set<string>
  toolEnabledCount: number
  handleSelectTool: (id: string, enabled: boolean) => void
  refetchTools: () => Promise<unknown>
  onRefreshed: () => Promise<IntegrationsAPI.components['schemas']['IntegrationRead'] | undefined>
  canUpdate: boolean
  updateTooltip?: string
}>) {
  const integrationId = integration.id ?? ''
  if (isLLM) {
    return (
      <SynPanelContentStack className={styles.resourcesTabContent}>
        <IntegrationModelsTab
          integrationId={integrationId}
          models={modelsState.models}
          isLoading={modelsState.isLoading}
          error={modelsState.error?.message ?? null}
          refetchModels={() => modelsState.refetchModels()}
          enabledModelIds={modelsState.enabledModelIds}
          enabledCount={modelsState.enabledCount}
          allSelected={modelsState.allSelected}
          handleSelectAll={modelsState.handleSelectAll}
          defaultModelId={modelsState.defaultModelId}
          handleSelectWithDefaultClear={modelsState.handleSelectWithDefaultClear}
          handleSetDefault={modelsState.handleSetDefault}
          handleRemoveDefault={modelsState.handleRemoveDefault}
          resetSelectionToServer={modelsState.resetSelectionToServer}
          resetDefault={modelsState.resetDefault}
          lastRefreshedAt={integration.last_successful_refresh_at}
          refreshStatus={integration.refresh_status}
          refreshError={integration.refresh_error}
          canUpdate={canUpdate}
          updateTooltip={updateTooltip}
          onRefreshed={onRefreshed}
        />
      </SynPanelContentStack>
    )
  }

  return (
    <SynPanelContentStack className={styles.resourcesTabContent}>
      <IntegrationResourcesTab
        integrationId={integrationId}
        tools={tools}
        enabledToolIds={enabledToolIds}
        enabledCount={toolEnabledCount}
        handleSelectTool={handleSelectTool}
        lastRefreshedAt={integration.last_successful_refresh_at}
        canUpdate={canUpdate}
        onRefreshed={onRefreshed}
        refetchTools={refetchTools}
      />
    </SynPanelContentStack>
  )
}
