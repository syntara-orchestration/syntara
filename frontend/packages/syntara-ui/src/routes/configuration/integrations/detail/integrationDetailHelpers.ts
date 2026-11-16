import type { IntegrationsAPI } from '@syntara/contracts'
import { IntegrationTypeEnum } from '@syntara/contracts'

import { isLLMProvider } from '../integrationUtils'

import type { useAllIntegrationTools } from './useAllIntegrationTools'
import type { useIntegrationModelsState } from './useIntegrationModelsState'

type IntegrationRead = IntegrationsAPI.components['schemas']['IntegrationRead']

export function hasResourcesTab(integration: IntegrationRead): boolean {
  return isLLMProvider(integration) || integration.integration_type === IntegrationTypeEnum.MCP_SERVER
}

export function shouldShowResourcesFooter(
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

export function getFooterState({
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
