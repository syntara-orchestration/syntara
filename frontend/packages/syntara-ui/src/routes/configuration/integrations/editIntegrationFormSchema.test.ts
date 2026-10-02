import { describe, expect, it } from 'vitest'

import { buildEditSchema, buildConfiguration } from './editIntegrationFormSchema'

const schema = buildEditSchema(true)
const schemaOptionalBaseUrl = buildEditSchema(false)

const securityDefaults = {
  allow_http: false,
  insecure_skip_tls_verify: false,
  ca_certificate: null as string | null,
}

const validMcp = {
  name: 'My MCP Server',
  description: '',
  integration_type: 'mcp_server',
  base_url: 'https://example.com',
  scope: 'global' as const,
  management_credential_id: null,
  ...securityDefaults,
}

const validAap = {
  name: 'My AAP',
  description: '',
  integration_type: 'ansible_automation_platform',
  base_url: 'https://aap.example.com',
  scope: 'global' as const,
  management_credential_id: null,
  ...securityDefaults,
}

const validLlm = {
  name: 'My LLM',
  description: '',
  integration_type: 'llm_provider',
  base_url: 'https://api.example.com',
  scope: 'global' as const,
  management_credential_id: null,
  ...securityDefaults,
}

const validTfe = {
  name: 'My TFE',
  description: '',
  integration_type: 'terraform_enterprise',
  base_url: 'https://app.terraform.io',
  organization: 'acme',
  scope: 'global' as const,
  management_credential_id: null,
  ...securityDefaults,
}

describe('buildEditSchema', () => {
  describe('MCP Server', () => {
    it('accepts valid MCP data', () => {
      const result = schema.safeParse(validMcp)
      expect(result.success).toBe(true)
    })

    it('rejects empty base_url', () => {
      const result = schema.safeParse({ ...validMcp, base_url: '' })
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues.some((i) => i.message === 'API URL is required')).toBe(true)
      }
    })

    it('rejects missing base_url', () => {
      const result = schema.safeParse({
        name: validMcp.name,
        description: validMcp.description,
        integration_type: validMcp.integration_type,
        scope: validMcp.scope,
        management_credential_id: validMcp.management_credential_id,
        allow_http: validMcp.allow_http,
        insecure_skip_tls_verify: validMcp.insecure_skip_tls_verify,
      })
      expect(result.success).toBe(false)
    })

    it('rejects invalid URL', () => {
      const result = schema.safeParse({ ...validMcp, base_url: 'not-a-url' })
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues.some((i) => i.message === 'Must be a valid URL')).toBe(true)
      }
    })

    it.each([
      ['URL with port', 'https://mcp.example.com:9443'],
      ['URL with path', 'https://example.com/mcp/v1'],
      ['URL with trailing slash', 'https://example.com/'],
    ])('accepts %s', (_label, url) => {
      const result = schema.safeParse({ ...validMcp, base_url: url })
      expect(result.success).toBe(true)
    })

    it('rejects HTTP URL for non-loopback host when allow_http is false', () => {
      const result = schema.safeParse({ ...validMcp, base_url: 'http://mcp.example.com/mcp' })
      expect(result.success).toBe(false)
    })

    it('accepts HTTP URL for loopback host when allow_http is false', () => {
      const result = schema.safeParse({ ...validMcp, base_url: 'http://localhost:8765/mcp' })
      expect(result.success).toBe(true)
    })

    it('accepts HTTP URL when allow_http is true', () => {
      const result = schema.safeParse({ ...validMcp, base_url: 'http://mcp.example.com/mcp', allow_http: true })
      expect(result.success).toBe(true)
    })

    it('rejects FTP scheme', () => {
      const result = schema.safeParse({ ...validMcp, base_url: 'ftp://example.com' })
      expect(result.success).toBe(false)
    })
  })

  describe('Ansible Automation Platform', () => {
    it('accepts valid AAP data', () => {
      const result = schema.safeParse(validAap)
      expect(result.success).toBe(true)
    })

    it.each([
      ['empty base_url', '', 'API URL is required'],
      ['HTTP URL (HTTPS only)', 'http://aap.example.com', 'Must be an HTTPS URL'],
      ['invalid URL', 'not-a-url', 'Must be a valid URL'],
    ])('rejects %s', (_label, url, expectedMessage) => {
      const result = schema.safeParse({ ...validAap, base_url: url })
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues.some((i) => i.message === expectedMessage)).toBe(true)
      }
    })

    it('accepts HTTP URL when allow_http is true', () => {
      const result = schema.safeParse({ ...validAap, base_url: 'http://aap.example.com', allow_http: true })
      expect(result.success).toBe(true)
    })

    it('accepts HTTPS URL with port', () => {
      const result = schema.safeParse({ ...validAap, base_url: 'https://aap.example.com:8443' })
      expect(result.success).toBe(true)
    })

    it('rejects FTP scheme', () => {
      const result = schema.safeParse({ ...validAap, base_url: 'ftp://aap.example.com' })
      expect(result.success).toBe(false)
    })
  })

  describe('Terraform Enterprise', () => {
    it('accepts valid TFE data', () => {
      const result = schema.safeParse(validTfe)
      expect(result.success).toBe(true)
    })

    it.each([
      ['empty base_url', { base_url: '' }, 'TFE URL is required'],
      ['HTTP URL (HTTPS only)', { base_url: 'http://tfe.example.com' }, 'Must be an HTTPS URL'],
      ['invalid URL', { base_url: 'not-a-url' }, 'Must be a valid URL'],
      ['empty organization', { organization: '' }, 'Organization is required'],
    ])('rejects %s', (_label, overrides, expectedMessage) => {
      const result = schema.safeParse({ ...validTfe, ...overrides })
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues.some((i) => i.message === expectedMessage)).toBe(true)
      }
    })

    it('accepts HTTP URL when allow_http is true', () => {
      const result = schema.safeParse({
        ...validTfe,
        base_url: 'http://tfe.example.com',
        allow_http: true,
      })
      expect(result.success).toBe(true)
    })
  })

  describe('LLM Provider', () => {
    it('accepts valid LLM data', () => {
      const result = schema.safeParse(validLlm)
      expect(result.success).toBe(true)
    })

    it('rejects empty base_url when requiresBaseUrl is true', () => {
      const result = schema.safeParse({ ...validLlm, base_url: '' })
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues.some((i) => i.message === 'API URL is required')).toBe(true)
      }
    })

    it('allows empty base_url when requiresBaseUrl is false', () => {
      const result = schemaOptionalBaseUrl.safeParse({ ...validLlm, base_url: '' })
      expect(result.success).toBe(true)
    })

    it('allows missing base_url when requiresBaseUrl is false', () => {
      const { name, description, integration_type, scope, management_credential_id, ...security } = validLlm
      const result = schemaOptionalBaseUrl.safeParse({
        name,
        description,
        integration_type,
        scope,
        management_credential_id,
        ...security,
      })
      expect(result.success).toBe(true)
    })

    it('rejects HTTP URL for non-loopback host when allow_http is false', () => {
      const result = schema.safeParse({ ...validLlm, base_url: 'http://api.example.com' })
      expect(result.success).toBe(false)
    })

    it('accepts HTTP URL for loopback host when allow_http is false', () => {
      const result = schema.safeParse({ ...validLlm, base_url: 'http://localhost:11434' })
      expect(result.success).toBe(true)
    })

    it('accepts HTTP URL when allow_http is true', () => {
      const result = schema.safeParse({ ...validLlm, base_url: 'http://api.example.com', allow_http: true })
      expect(result.success).toBe(true)
    })

    it('accepts HTTPS URL', () => {
      const result = schema.safeParse({ ...validLlm, base_url: 'https://api.openai.com/v1' })
      expect(result.success).toBe(true)
    })

    it('rejects FTP scheme', () => {
      const result = schema.safeParse({ ...validLlm, base_url: 'ftp://api.example.com' })
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues.some((i) => i.message === 'Must be an HTTPS URL')).toBe(true)
      }
    })

    it('rejects invalid URL when provided', () => {
      const result = schema.safeParse({ ...validLlm, base_url: 'not-a-url' })
      expect(result.success).toBe(false)
    })

    it('validates non-empty base_url even when not required', () => {
      const result = schemaOptionalBaseUrl.safeParse({ ...validLlm, base_url: 'not-a-url' })
      expect(result.success).toBe(false)
    })
  })

  describe('shared fields', () => {
    it('rejects empty name', () => {
      const result = schema.safeParse({ ...validMcp, name: '' })
      expect(result.success).toBe(false)
    })

    it('accepts project scope with project_ids', () => {
      const result = schema.safeParse({ ...validMcp, scope: 'project', project_ids: ['p-001'] })
      expect(result.success).toBe(true)
    })

    it('rejects project scope with empty project_ids', () => {
      const result = schema.safeParse({ ...validMcp, scope: 'project', project_ids: [] })
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues.some((i) => i.message === 'At least one project must be selected')).toBe(true)
      }
    })

    it('does not require project_ids when scope is global', () => {
      const result = schema.safeParse({ ...validMcp, scope: 'global' })
      expect(result.success).toBe(true)
    })

    it('rejects invalid scope', () => {
      const result = schema.safeParse({ ...validMcp, scope: 'invalid' })
      expect(result.success).toBe(false)
    })
  })
})

describe('buildConfiguration', () => {
  const baseValues = {
    name: 'Test',
    description: '',
    integration_type: 'mcp_server',
    base_url: 'https://example.com',
    scope: 'global' as const,
    project_ids: [] as string[],
    management_credential_id: null,
    ...securityDefaults,
  }

  const expectedSecurityDefaults = {
    allow_http: false,
    insecure_skip_tls_verify: false,
    ca_certificate: null,
  }

  describe('MCP Server', () => {
    it('returns MCP configuration with base_url and security fields', () => {
      const config = buildConfiguration('mcp_server', baseValues)
      expect(config).toEqual({
        integration_type: 'mcp_server',
        base_url: 'https://example.com',
        ...expectedSecurityDefaults,
      })
    })

    it('falls back to empty string when base_url is undefined', () => {
      const withoutUrl = { ...baseValues, base_url: undefined } as unknown as typeof baseValues
      const config = buildConfiguration('mcp_server', withoutUrl)
      expect(config).toHaveProperty('base_url', '')
    })
  })

  describe('Ansible Automation Platform', () => {
    it('returns AAP configuration with security fields', () => {
      const aapValues = {
        ...baseValues,
        integration_type: 'ansible_automation_platform',
        base_url: 'https://aap.example.com',
      }
      const config = buildConfiguration('ansible_automation_platform', aapValues)
      expect(config).toEqual({
        integration_type: 'ansible_automation_platform',
        base_url: 'https://aap.example.com',
        ...expectedSecurityDefaults,
      })
    })

    it('defaults insecure_skip_tls_verify to false when undefined', () => {
      const config = buildConfiguration('ansible_automation_platform', baseValues)
      expect(config).toHaveProperty('insecure_skip_tls_verify', false)
    })

    it('preserves insecure_skip_tls_verify=true', () => {
      const aapValues = { ...baseValues, base_url: 'https://aap.example.com', insecure_skip_tls_verify: true }
      const config = buildConfiguration('ansible_automation_platform', aapValues)
      expect(config).toHaveProperty('insecure_skip_tls_verify', true)
    })
  })

  describe('Terraform Enterprise', () => {
    it('returns TFE configuration with organization and security fields', () => {
      const tfeValues = {
        ...baseValues,
        integration_type: 'terraform_enterprise',
        base_url: 'https://app.terraform.io',
        organization: 'acme',
      }
      const config = buildConfiguration('terraform_enterprise', tfeValues)
      expect(config).toEqual({
        integration_type: 'terraform_enterprise',
        base_url: 'https://app.terraform.io',
        organization: 'acme',
        ...expectedSecurityDefaults,
      })
    })

    it('defaults organization to empty string when undefined', () => {
      const tfeValues = {
        ...baseValues,
        integration_type: 'terraform_enterprise',
        base_url: 'https://app.terraform.io',
        organization: undefined,
      }
      const config = buildConfiguration('terraform_enterprise', tfeValues)
      expect(config).toHaveProperty('organization', '')
    })
  })

  describe('LLM Provider', () => {
    it('returns LLM configuration with provider_hint, base_url, and security fields', () => {
      const llmValues = { ...baseValues, integration_type: 'llm_provider', base_url: 'https://api.example.com' }
      const config = buildConfiguration('llm_provider', llmValues, 'red_hat_ai')
      expect(config).toEqual({
        integration_type: 'llm_provider',
        provider_hint: 'red_hat_ai',
        base_url: 'https://api.example.com',
        ...expectedSecurityDefaults,
      })
    })

    it('sets base_url to undefined when empty', () => {
      const llmValues = { ...baseValues, integration_type: 'llm_provider', base_url: '' }
      const config = buildConfiguration('llm_provider', llmValues, 'openai')
      expect(config).toHaveProperty('base_url', undefined)
    })

    it('falls back to MCP config when providerHint is undefined', () => {
      const config = buildConfiguration('llm_provider', baseValues)
      expect(config).toEqual({
        integration_type: 'mcp_server',
        base_url: 'https://example.com',
        ...expectedSecurityDefaults,
      })
    })
  })

  describe('unknown type', () => {
    it('falls back to MCP configuration', () => {
      const config = buildConfiguration('unknown_type', baseValues)
      expect(config).toEqual({
        integration_type: 'mcp_server',
        base_url: 'https://example.com',
        ...expectedSecurityDefaults,
      })
    })
  })
})
