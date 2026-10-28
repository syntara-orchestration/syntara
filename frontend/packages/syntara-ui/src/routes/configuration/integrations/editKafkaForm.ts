import { IntegrationTypeEnum } from '@syntara/contracts'

import type { IntegrationRead } from './editIntegrationFormSchema'
import { PROVIDERS_HIDING_BASE_URL, PROVIDERS_REQUIRING_BASE_URL } from './integrationFilters'
import { getProviderHint, isLLMProvider } from './integrationUtils'

export function usesServiceName(isLLM: boolean, integrationType: string | undefined): boolean {
  return isLLM || integrationType === IntegrationTypeEnum.KAFKA
}

export function shouldHideBaseUrl(integration: IntegrationRead): boolean {
  if (integration.integration_type === IntegrationTypeEnum.KAFKA) return true
  return isLLMProvider(integration) && PROVIDERS_HIDING_BASE_URL.has(getProviderHint(integration))
}

export function editFormRequiresBaseUrl(integration: IntegrationRead): boolean {
  if (integration.integration_type === IntegrationTypeEnum.KAFKA) return false
  if (isLLMProvider(integration)) return PROVIDERS_REQUIRING_BASE_URL.has(getProviderHint(integration))
  return true
}
