import { IntegrationTypeEnum, LLMProviderHintEnum } from '@syntara/contracts'
import { z } from 'zod'

import { AppRoute } from '../../../app/AppRoute'

import type { IntegrationRead } from './integrationTypes'

const integrationTypeSchema = z.discriminatedUnion('integration_type', [
  z.object({ integration_type: z.literal(IntegrationTypeEnum.MCP_SERVER) }),
  z.object({ integration_type: z.literal(IntegrationTypeEnum.LLM_PROVIDER) }),
  z.object({ integration_type: z.literal(IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM) }),
  z.object({ integration_type: z.literal(IntegrationTypeEnum.KAFKA) }),
])

const PROVIDER_DEFAULT_URLS: Record<string, string> = {
  [LLMProviderHintEnum.OPENAI]: 'https://api.openai.com/v1',
  [LLMProviderHintEnum.ANTHROPIC]: 'https://api.anthropic.com/v1',
  [LLMProviderHintEnum.GEMINI]: 'https://generativelanguage.googleapis.com/v1',
}

export function getStoredConfiguration(integration: IntegrationRead) {
  return integration.configuration
}

export function getBaseUrl(integration: IntegrationRead): string {
  const config = getStoredConfiguration(integration)
  if (!config) return ''
  if ('base_url' in config) {
    if (config.base_url) return String(config.base_url)
    if ('provider_hint' in config && typeof config.provider_hint === 'string') {
      return PROVIDER_DEFAULT_URLS[config.provider_hint] ?? ''
    }
    return ''
  }
  if ('bootstrap_servers' in config && Array.isArray(config.bootstrap_servers)) {
    return config.bootstrap_servers.join(', ')
  }
  return ''
}

export function isLLMProvider(integration: IntegrationRead): boolean {
  const result = integrationTypeSchema.safeParse(integration)
  return result.success && result.data.integration_type === IntegrationTypeEnum.LLM_PROVIDER
}

export function getProviderHint(integration: IntegrationRead): string {
  const config = integration.configuration
  if (config && 'provider_hint' in config) return String(config.provider_hint ?? '')
  return ''
}

export function getTotalResourceCount(integration: IntegrationRead): number {
  if (isLLMProvider(integration)) return integration.total_model_count ?? 0
  return integration.total_tool_count ?? 0
}

export function getEnabledResourceCount(integration: IntegrationRead): number {
  if (isLLMProvider(integration)) return integration.enabled_model_count ?? 0
  return integration.enabled_tool_count ?? 0
}

export function getResourceNoun(integration: IntegrationRead, plural = true): string {
  if (isLLMProvider(integration)) return plural ? 'models' : 'model'
  return plural ? 'tools' : 'tool'
}

export function getIntegrationPaths(isKafka: boolean, integrationId: string) {
  const routes = isKafka
    ? {
        resourcePath: '/kafka_integrations/{integration_id}' as const,
        detail: AppRoute.Configuration.Integrations.KafkaDetail,
        edit: AppRoute.Configuration.Integrations.KafkaEdit,
      }
    : {
        resourcePath: '/integrations/{integration_id}' as const,
        detail: AppRoute.Configuration.Integrations.Detail,
        edit: AppRoute.Configuration.Integrations.Edit,
      }
  return {
    resourcePath: routes.resourcePath,
    detailPath: routes.detail.replace(':integrationId', integrationId),
    editPath: routes.edit.replace(':integrationId', integrationId),
  }
}
