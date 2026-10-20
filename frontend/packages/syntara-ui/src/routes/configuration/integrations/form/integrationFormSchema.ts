import { IntegrationTypeEnum, LLMProviderHintEnum } from '@syntara/contracts'
import { z } from 'zod'

import { PROVIDERS_REQUIRING_BASE_URL } from '../integrationFilters'

const securityFields = {
  allow_http: z.boolean(),
  insecure_skip_tls_verify: z.boolean(),
  ca_certificate: z.string().optional().nullable(),
}

const sharedFields = {
  name: z.string().min(1, 'Server name / ID is required'),
  description: z.string().optional().nullable(),
  management_credential_id: z.string().optional().nullable(),
  scope: z.enum(['global', 'project']),
  project_ids: z.array(z.string()).default([]),
}

function isLoopback(hostname: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1' || hostname === '[::1]'
}

function isAllowedScheme(url: string, allowHttp: boolean): boolean {
  if (allowHttp) return url.startsWith('http://') || url.startsWith('https://')
  try {
    const parsed = new URL(url)
    if (parsed.protocol === 'http:' && isLoopback(parsed.hostname)) return true
  } catch {
    return false
  }
  return url.startsWith('https://')
}

const mcpServerSchema = z.object({
  ...sharedFields,
  integration_type: z.literal(IntegrationTypeEnum.MCP_SERVER),
  configuration: z
    .object({
      integration_type: z.literal(IntegrationTypeEnum.MCP_SERVER),
      base_url: z.string().min(1, 'API URL is required').url('API URL must be a valid URL'),
      ...securityFields,
    })
    .superRefine((data, ctx) => {
      if (!isAllowedScheme(data.base_url, data.allow_http)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: data.allow_http ? 'Must be an HTTP or HTTPS URL' : 'Must be an HTTPS URL',
          path: ['base_url'],
        })
      }
    }),
})

const aapSchema = z.object({
  ...sharedFields,
  integration_type: z.literal(IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM),
  configuration: z
    .object({
      integration_type: z.literal(IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM),
      base_url: z.string().min(1, 'AAP URL is required').url('Must be a valid URL'),
      ...securityFields,
    })
    .superRefine((data, ctx) => {
      if (!isAllowedScheme(data.base_url, data.allow_http)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: data.allow_http ? 'Must be an HTTP or HTTPS URL' : 'Must be an HTTPS URL',
          path: ['base_url'],
        })
      }
    }),
})

const llmProviderSchema = z.object({
  ...sharedFields,
  integration_type: z.literal(IntegrationTypeEnum.LLM_PROVIDER),
  configuration: z
    .object({
      integration_type: z.literal(IntegrationTypeEnum.LLM_PROVIDER),
      provider_hint: z.enum([LLMProviderHintEnum.RED_HAT_AI, LLMProviderHintEnum.OPENAI, LLMProviderHintEnum.CUSTOM]),
      base_url: z.string().url('Must be a valid URL').optional().or(z.literal('')),
      ...securityFields,
    })
    .superRefine((data, ctx) => {
      if (PROVIDERS_REQUIRING_BASE_URL.has(data.provider_hint) && (!data.base_url || data.base_url === '')) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Base URL is required for this provider',
          path: ['base_url'],
        })
      }
      if (data.base_url && data.base_url !== '' && !isAllowedScheme(data.base_url, data.allow_http)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: data.allow_http ? 'Must be an HTTP or HTTPS URL' : 'Must be an HTTPS URL',
          path: ['base_url'],
        })
      }
    }),
})

/**
 * Zod schema for the integration create form.
 * Discriminated union on integration_type — each type has its own configuration shape.
 * Backend 422 errors are still applied via useFormMutationErrorHandler.
 */
export const integrationFormSchema = z
  .discriminatedUnion('integration_type', [mcpServerSchema, aapSchema, llmProviderSchema])
  .superRefine((data, ctx) => {
    if (data.scope === 'project' && data.project_ids.length === 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'At least one project must be selected',
        path: ['project_ids'],
      })
    }
  })

export type IntegrationFormData = z.infer<typeof integrationFormSchema>

const SECURITY_DEFAULTS = {
  allow_http: false,
  insecure_skip_tls_verify: false,
  ca_certificate: null,
} as const

/** Fields validated on step 1 (Integration details) before advancing. Type-specific because each integration type has a different URL field. */
export function getStep1Fields(integrationType: string, scope?: string): string[] {
  const shared = ['name']
  if (scope === 'project') shared.push('project_ids')
  switch (integrationType) {
    case IntegrationTypeEnum.MCP_SERVER:
      return [...shared, 'configuration.base_url']
    case IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM:
      return [...shared, 'configuration.base_url']
    case IntegrationTypeEnum.LLM_PROVIDER:
      return [...shared, 'configuration.provider_hint', 'configuration.base_url']
    default:
      return shared
  }
}

export function getDefaultConfiguration(integrationType: string): IntegrationFormData['configuration'] {
  switch (integrationType) {
    case IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM:
      return {
        integration_type: 'ansible_automation_platform' as const,
        base_url: '',
        ...SECURITY_DEFAULTS,
      }
    case IntegrationTypeEnum.LLM_PROVIDER:
      return {
        integration_type: 'llm_provider' as const,
        provider_hint: LLMProviderHintEnum.RED_HAT_AI,
        base_url: '',
        ...SECURITY_DEFAULTS,
      }
    default:
      return { integration_type: 'mcp_server' as const, base_url: '', ...SECURITY_DEFAULTS }
  }
}

export const INTEGRATION_TYPE_OPTIONS = [
  { value: IntegrationTypeEnum.MCP_SERVER, label: 'MCP Server' },
  { value: IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM, label: 'Ansible Automation Platform' },
  { value: IntegrationTypeEnum.LLM_PROVIDER, label: 'LLM Provider' },
] as const

export const PROVIDER_HINT_OPTIONS = [
  { value: LLMProviderHintEnum.RED_HAT_AI, label: 'Red Hat AI' },
  { value: LLMProviderHintEnum.OPENAI, label: 'OpenAI' },
  { value: LLMProviderHintEnum.CUSTOM, label: 'Custom' },
] as const
