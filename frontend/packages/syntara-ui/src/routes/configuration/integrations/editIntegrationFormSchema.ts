import type { IntegrationsAPI } from '@syntara/contracts'
import { IntegrationTypeEnum } from '@syntara/contracts'
import { z } from 'zod'

import { openshiftConfigurationSchema } from './form/integrationFormSchema'

function isLoopback(hostname: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1' || hostname === '[::1]'
}

function validateUrl(
  url: string | undefined,
  opts: { required: boolean; allowHttp?: boolean; fieldLabel?: string }
): string | undefined {
  if (!url || url === '') {
    return opts.required ? `${opts.fieldLabel ?? 'URL'} is required` : undefined
  }
  try {
    const parsed = new URL(url)
    const effectiveAllowHttp = (opts.allowHttp ?? false) || isLoopback(parsed.hostname)
    if (effectiveAllowHttp) {
      if (!/^https?:$/.test(parsed.protocol)) return 'Must be an HTTP or HTTPS URL'
    } else if (parsed.protocol !== 'https:') {
      return 'Must be an HTTPS URL'
    }
  } catch {
    return 'Must be a valid URL'
  }
  return undefined
}

function validateOpenShiftFields(
  data: Omit<Partial<z.input<typeof openshiftConfigurationSchema>>, 'integration_type'> & {
    management_credential_id: string | null
  },
  ctx: z.RefinementCtx
) {
  const result = openshiftConfigurationSchema.safeParse({ ...data, integration_type: IntegrationTypeEnum.OPENSHIFT })
  if (!result.success) {
    for (const issue of result.error.issues) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: issue.message, path: issue.path })
    }
  }
  if (!data.management_credential_id) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'A bearer token credential is required',
      path: ['management_credential_id'],
    })
  }
}

export function buildEditSchema(requiresBaseUrl: boolean) {
  return z
    .object({
      name: z.string().min(1, 'Server name / ID is required'),
      description: z.string(),
      integration_type: z.string(),
      base_url: z.string().optional(),
      namespace: z.string().optional(),
      script_image: z.string().optional().nullable(),
      allow_http: z.boolean(),
      insecure_skip_tls_verify: z.boolean(),
      ca_certificate: z.string().optional().nullable(),
      scope: z.enum(['global', 'project']),
      project_ids: z.array(z.string()).default([]),
      management_credential_id: z.string().nullable(),
    })
    .superRefine((data, ctx) => {
      if (data.scope === 'project' && data.project_ids.length === 0) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'At least one project must be selected',
          path: ['project_ids'],
        })
      }
      if (data.integration_type === IntegrationTypeEnum.OPENSHIFT) {
        validateOpenShiftFields(data, ctx)
      }
      if (data.integration_type === IntegrationTypeEnum.MCP_SERVER) {
        const err = validateUrl(data.base_url, {
          required: true,
          allowHttp: data.allow_http,
          fieldLabel: 'API URL',
        })
        if (err) ctx.addIssue({ code: z.ZodIssueCode.custom, message: err, path: ['base_url'] })
      }
      if (data.integration_type === IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM) {
        const err = validateUrl(data.base_url, {
          required: true,
          allowHttp: data.allow_http,
          fieldLabel: 'API URL',
        })
        if (err) ctx.addIssue({ code: z.ZodIssueCode.custom, message: err, path: ['base_url'] })
      }
      if (data.integration_type === IntegrationTypeEnum.LLM_PROVIDER) {
        const err = validateUrl(data.base_url, {
          required: requiresBaseUrl,
          allowHttp: data.allow_http,
          fieldLabel: 'API URL',
        })
        if (err) ctx.addIssue({ code: z.ZodIssueCode.custom, message: err, path: ['base_url'] })
      }
    })
}

export const editIntegrationSchema = buildEditSchema(true)

export type EditIntegrationFormValues = z.infer<typeof editIntegrationSchema>

export type DiscoverResult = IntegrationsAPI.components['schemas']['DiscoverResult']
export type IntegrationRead = IntegrationsAPI.components['schemas']['IntegrationRead']

function securityFields(values: EditIntegrationFormValues) {
  return {
    allow_http: values.allow_http,
    insecure_skip_tls_verify: values.insecure_skip_tls_verify,
    ca_certificate: values.ca_certificate,
  }
}

export function buildConfiguration(integrationType: string, values: EditIntegrationFormValues, providerHint?: string) {
  if (integrationType === IntegrationTypeEnum.OPENSHIFT) {
    return {
      integration_type: IntegrationTypeEnum.OPENSHIFT,
      base_url: values.base_url ?? '',
      namespace: values.namespace ?? '',
      script_image: values.script_image?.trim() || null,
      ...securityFields(values),
    }
  }
  if (integrationType === IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM) {
    return {
      integration_type: IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM,
      base_url: values.base_url ?? '',
      ...securityFields(values),
    }
  }
  if (integrationType === IntegrationTypeEnum.LLM_PROVIDER && providerHint) {
    return {
      integration_type: IntegrationTypeEnum.LLM_PROVIDER,
      provider_hint: providerHint as IntegrationsAPI.components['schemas']['LLMProviderConfiguration']['provider_hint'],
      base_url: values.base_url || undefined,
      ...securityFields(values),
    }
  }
  return { integration_type: 'mcp_server' as const, base_url: values.base_url ?? '', ...securityFields(values) }
}
