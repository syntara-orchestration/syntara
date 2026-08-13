import type { IntegrationsAPI } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import {
  getBaseUrl,
  getEnabledResourceCount,
  getProviderHint,
  getResourceNoun,
  getTotalResourceCount,
  isLLMProvider,
} from './integrationUtils'

type IntegrationRead = IntegrationsAPI.components['schemas']['IntegrationRead']

const integrationDefaults: IntegrationRead = {
  id: 'int-1',
  name: 'Test',
  integration_type: 'mcp_server',
  configuration: { integration_type: 'mcp_server', base_url: 'https://example.com' },
  total_tool_count: 5,
  enabled_tool_count: 3,
  total_model_count: 0,
  enabled_model_count: 0,
  created_by: 'user-1',
}

function buildIntegration(overrides: Partial<IntegrationRead> = {}): IntegrationRead {
  return { ...integrationDefaults, ...overrides }
}

function buildLLMIntegration(overrides: Partial<IntegrationRead> = {}): IntegrationRead {
  return buildIntegration({
    integration_type: 'llm_provider',
    configuration: {
      integration_type: 'llm_provider',
      provider_hint: 'red_hat_ai',
      base_url: 'https://api.example.com',
    },
    total_tool_count: 0,
    enabled_tool_count: 0,
    total_model_count: 10,
    enabled_model_count: 7,
    ...overrides,
  })
}

describe('integrationUtils', () => {
  describe('isLLMProvider', () => {
    it('returns true for llm_provider integration', () => {
      expect(isLLMProvider(buildLLMIntegration())).toBe(true)
    })

    it('returns false for mcp_server integration', () => {
      expect(isLLMProvider(buildIntegration())).toBe(false)
    })

    it('returns false for ansible_automation_platform integration', () => {
      expect(isLLMProvider(buildIntegration({ integration_type: 'ansible_automation_platform' }))).toBe(false)
    })
  })

  describe('getProviderHint', () => {
    it('extracts provider_hint from LLM provider configuration', () => {
      expect(getProviderHint(buildLLMIntegration())).toBe('red_hat_ai')
    })

    it('returns different provider hints correctly', () => {
      const integration = buildLLMIntegration({
        configuration: { integration_type: 'llm_provider', provider_hint: 'openai' },
      })
      expect(getProviderHint(integration)).toBe('openai')
    })

    it('returns empty string for MCP server (no provider_hint)', () => {
      expect(getProviderHint(buildIntegration())).toBe('')
    })

    it('returns empty string when configuration is undefined', () => {
      expect(getProviderHint(buildIntegration({ configuration: undefined } as never))).toBe('')
    })
  })

  describe('getBaseUrl', () => {
    it('returns base_url from MCP server configuration', () => {
      expect(getBaseUrl(buildIntegration())).toBe('https://example.com')
    })

    it('returns base_url from LLM provider configuration', () => {
      expect(getBaseUrl(buildLLMIntegration())).toBe('https://api.example.com')
    })

    it('returns base_url from AAP configuration', () => {
      const integration = buildIntegration({
        integration_type: 'ansible_automation_platform',
        configuration: { integration_type: 'ansible_automation_platform', base_url: 'https://gateway.example.com' },
      })
      expect(getBaseUrl(integration)).toBe('https://gateway.example.com')
    })

    it('returns empty string when configuration is undefined', () => {
      expect(getBaseUrl(buildIntegration({ configuration: undefined } as never))).toBe('')
    })

    it('resolves default URL for well-known provider when base_url is null', () => {
      const integration = buildLLMIntegration({
        configuration: {
          integration_type: 'llm_provider',
          provider_hint: 'anthropic',
          base_url: null,
        },
      })
      expect(getBaseUrl(integration)).toBe('https://api.anthropic.com/v1')
    })

    it('resolves default URL for OpenAI when base_url is null', () => {
      const integration = buildLLMIntegration({
        configuration: {
          integration_type: 'llm_provider',
          provider_hint: 'openai',
          base_url: null,
        },
      })
      expect(getBaseUrl(integration)).toBe('https://api.openai.com/v1')
    })

    it('resolves default URL for Gemini when base_url is null', () => {
      const integration = buildLLMIntegration({
        configuration: {
          integration_type: 'llm_provider',
          provider_hint: 'gemini',
          base_url: null,
        },
      })
      expect(getBaseUrl(integration)).toBe('https://generativelanguage.googleapis.com/v1')
    })

    it('returns empty string for custom provider when base_url is null', () => {
      const integration = buildLLMIntegration({
        configuration: {
          integration_type: 'llm_provider',
          provider_hint: 'custom',
          base_url: null,
        },
      })
      expect(getBaseUrl(integration)).toBe('')
    })
  })

  describe('getTotalResourceCount', () => {
    it('returns total_model_count for LLM provider', () => {
      expect(getTotalResourceCount(buildLLMIntegration())).toBe(10)
    })

    it('returns total_tool_count for MCP server', () => {
      expect(getTotalResourceCount(buildIntegration())).toBe(5)
    })

    it('returns 0 when count is undefined', () => {
      expect(getTotalResourceCount(buildIntegration({ total_tool_count: undefined }))).toBe(0)
    })

    it('returns 0 when LLM model count is undefined', () => {
      expect(getTotalResourceCount(buildLLMIntegration({ total_model_count: undefined }))).toBe(0)
    })
  })

  describe('getEnabledResourceCount', () => {
    it('returns enabled_model_count for LLM provider', () => {
      expect(getEnabledResourceCount(buildLLMIntegration())).toBe(7)
    })

    it('returns enabled_tool_count for MCP server', () => {
      expect(getEnabledResourceCount(buildIntegration())).toBe(3)
    })

    it('returns 0 when count is undefined', () => {
      expect(getEnabledResourceCount(buildIntegration({ enabled_tool_count: undefined }))).toBe(0)
    })

    it('returns 0 when LLM model count is undefined', () => {
      expect(getEnabledResourceCount(buildLLMIntegration({ enabled_model_count: undefined }))).toBe(0)
    })
  })

  describe('getResourceNoun', () => {
    it('returns "models" for LLM provider (plural)', () => {
      expect(getResourceNoun(buildLLMIntegration())).toBe('models')
    })

    it('returns "model" for LLM provider (singular)', () => {
      expect(getResourceNoun(buildLLMIntegration(), false)).toBe('model')
    })

    it('returns "tools" for MCP server (plural)', () => {
      expect(getResourceNoun(buildIntegration())).toBe('tools')
    })

    it('returns "tool" for MCP server (singular)', () => {
      expect(getResourceNoun(buildIntegration(), false)).toBe('tool')
    })
  })
})
