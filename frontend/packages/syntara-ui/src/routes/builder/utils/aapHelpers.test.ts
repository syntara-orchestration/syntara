import { describe, expect, it } from 'vitest'

import type { AAPJobTemplateFormData } from '../node-forms/aapJobTemplateSchema'
import type { AAPWorkflowTemplateFormData } from '../node-forms/aapWorkflowTemplateSchema'

import {
  buildAAPConfig,
  buildAAPWorkflowTemplateConfig,
  buildExpressionModeActivity,
  buildWorkflowExpressionModeActivity,
  hasExpressionValue,
  validateJobTemplateId,
  validateWorkflowTemplateId,
} from './aapHelpers'

function makeFormData(overrides: Partial<AAPJobTemplateFormData> = {}): AAPJobTemplateFormData {
  return {
    name: 'Test step',
    organization_name: '',
    job_template_name: '',
    job_template_id: undefined,
    settings: {},
    ...overrides,
  }
}

describe('validateJobTemplateId', () => {
  it('returns valid positive integer', () => {
    expect(validateJobTemplateId(123)).toBe(123)
  })

  it('throws on undefined', () => {
    expect(() => validateJobTemplateId(undefined)).toThrow('Job Template ID must be a valid positive integer')
  })

  it('throws on zero', () => {
    expect(() => validateJobTemplateId(0)).toThrow('Job Template ID must be a valid positive integer')
  })

  it('throws on negative number', () => {
    expect(() => validateJobTemplateId(-1)).toThrow('Job Template ID must be a valid positive integer')
  })

  it('throws on non-integer (float)', () => {
    expect(() => validateJobTemplateId(1.5)).toThrow('Job Template ID must be a valid positive integer')
  })
})

describe('buildAAPConfig', () => {
  it('returns undefined when no fields are set', () => {
    const result = buildAAPConfig(makeFormData())
    expect(result).toBeUndefined()
  })

  it('includes organization and jobTemplateName when set', () => {
    const result = buildAAPConfig(makeFormData({ organization_name: 'Default', job_template_name: 'Deploy' }))
    expect(result).toEqual(expect.objectContaining({ organization: 'Default', jobTemplateName: 'Deploy' }))
  })

  it('includes inventoryId and inventoryName when set', () => {
    const result = buildAAPConfig(makeFormData({ inventory_id: 42, inventory_name: 'Production' }))
    expect(result?.inventory).toBe(42)
    expect(result?.inventoryName).toBe('Production')
  })

  it('handles inventoryId of 0 (falsy but defined)', () => {
    // inventoryId = 0 is defined and not null, so it should be included
    const result = buildAAPConfig(makeFormData({ inventory_id: 0, organization_name: 'Default' }))
    expect(result?.inventory).toBe(0)
  })

  it('excludes inventoryId when undefined', () => {
    const result = buildAAPConfig(makeFormData({ organization_name: 'Default' }))
    expect(result?.inventory).toBeUndefined()
  })

  it('parses valid JSON extra vars', () => {
    const result = buildAAPConfig(makeFormData({ extra_vars: '{"key": "value"}' }))
    expect(result?.extraVars).toEqual({ key: 'value' })
  })

  it('ignores invalid JSON extra vars', () => {
    const result = buildAAPConfig(makeFormData({ extra_vars: 'not json' }))
    expect(result?.extraVars).toBeUndefined()
  })

  it('rejects array JSON extra vars (arrays are not valid objects)', () => {
    // parseExtraVars should reject arrays (they're not Record<string, unknown>)
    // The Zod schema already rejects arrays with 'Extra variables must be a JSON object'
    const result = buildAAPConfig(makeFormData({ extra_vars: '[1,2,3]' }))
    // Arrays should be rejected - extraVars should be undefined
    expect(result?.extraVars).toBeUndefined()
  })

  it('ignores null JSON extra vars', () => {
    const result = buildAAPConfig(makeFormData({ extra_vars: 'null' }))
    expect(result?.extraVars).toBeUndefined()
  })

  it('parses valid verbosity (0-5)', () => {
    const result = buildAAPConfig(makeFormData({ verbosity: '3' }))
    expect(result?.verbosity).toBe(3)
  })

  it('ignores verbosity > 5', () => {
    const result = buildAAPConfig(makeFormData({ verbosity: '6' }))
    expect(result?.verbosity).toBeUndefined()
  })

  it('ignores non-numeric verbosity', () => {
    const result = buildAAPConfig(makeFormData({ verbosity: 'abc' }))
    expect(result?.verbosity).toBeUndefined()
  })

  it('includes job_credentials array when set', () => {
    const result = buildAAPConfig(makeFormData({ job_credentials: [1, 2, 3] }))
    expect(result?.jobCredentials).toEqual([1, 2, 3])
  })

  it('excludes empty job_credentials array', () => {
    const result = buildAAPConfig(makeFormData({ job_credentials: [], organization_name: 'Default' }))
    expect(result?.jobCredentials).toBeUndefined()
  })

  it('includes diffMode when set', () => {
    const result = buildAAPConfig(makeFormData({ diff_mode: true }))
    expect(result?.diffMode).toBe(true)
  })

  it('includes string fields (limit, tags, skip_tags, job_type, execution_environment, instance_group, labels)', () => {
    const result = buildAAPConfig(
      makeFormData({
        limit: 'host1',
        tags: 'deploy',
        skip_tags: 'debug',
        job_type: 'run',
        execution_environment: 'Default EE',
        instance_group: 'default',
        labels: ['prod'],
      })
    )
    expect(result).toEqual(
      expect.objectContaining({
        limit: 'host1',
        tags: 'deploy',
        skipTags: 'debug',
        jobType: 'run',
        executionEnvironment: 'Default EE',
        instanceGroupName: 'default',
        labels: ['prod'],
      })
    )
  })

  it('includes number fields (forks, job_slice_count) when finite', () => {
    const result = buildAAPConfig(makeFormData({ forks: 10, job_slice_count: 2 }))
    expect(result?.forks).toBe(10)
    expect(result?.jobSlicing).toBe(2)
  })

  it('excludes NaN number fields', () => {
    const result = buildAAPConfig(makeFormData({ forks: Number.NaN, organization_name: 'Default' }))
    expect(result?.forks).toBeUndefined()
  })

  it('excludes empty string fields', () => {
    const result = buildAAPConfig(makeFormData({ limit: '', tags: '', organization_name: 'Default' }))
    expect(result?.limit).toBeUndefined()
    expect(result?.tags).toBeUndefined()
  })

  it('includes credentialId when set', () => {
    const result = buildAAPConfig(makeFormData({ credential_id: 'cred-123' }))
    expect(result?.credentialId).toBe('cred-123')
  })

  it('includes integrationId when integration_id is set', () => {
    const result = buildAAPConfig(makeFormData({ integration_id: 'int-aap-1' }))
    expect(result?.integrationId).toBe('int-aap-1')
  })

  it('includes both credentialId and integrationId when both set', () => {
    const result = buildAAPConfig(makeFormData({ credential_id: 'cred-123', integration_id: 'int-aap-1' }))
    expect(result?.credentialId).toBe('cred-123')
    expect(result?.integrationId).toBe('int-aap-1')
  })

  it('includes organizationId when set', () => {
    const result = buildAAPConfig(makeFormData({ organization_id: 5 }))
    expect(result?.organizationId).toBe(5)
  })

  it('handles organizationId of 0 (falsy but defined)', () => {
    const result = buildAAPConfig(makeFormData({ organization_id: 0 }))
    expect(result?.organizationId).toBe(0)
  })

  it('includes instanceGroupId when set', () => {
    const result = buildAAPConfig(makeFormData({ instance_group_id: 3 }))
    expect(result?.instanceGroupId).toBe(3)
  })

  it('handles instanceGroupId of 0 (falsy but defined)', () => {
    const result = buildAAPConfig(makeFormData({ instance_group_id: 0 }))
    expect(result?.instanceGroupId).toBe(0)
  })
})

describe('buildExpressionModeActivity', () => {
  it('preserves credential_id in expression mode config', () => {
    const data = makeFormData({
      credential_id: 'cred-abc-123',
      organization_name: '${trigger.org}',
      job_template_name: '${trigger.template}',
    })

    const activity = buildExpressionModeActivity('node-1', 'AAP Job', data)

    expect(activity.parameters.credential_id).toBe('cred-abc-123')
  })

  it('expression mode config has job_template_name but no job_template_id', () => {
    const data = makeFormData({
      organization_name: '${trigger.org}',
      job_template_name: '${trigger.template}',
    })

    const activity = buildExpressionModeActivity('node-1', 'AAP Job', data)

    expect(activity.parameters.job_template_name).toBe('${trigger.template}')
    expect(activity.parameters.organization_name).toBe('${trigger.org}')
    expect(activity.parameters).not.toHaveProperty('job_template_id')
  })
})

describe('hasExpressionValue', () => {
  it('returns true when any value contains ${', () => {
    expect(hasExpressionValue('${trigger.value}')).toBe(true)
    expect(hasExpressionValue('normal', '${expr}')).toBe(true)
    expect(hasExpressionValue(undefined, '${expr}', 'test')).toBe(true)
  })

  it('returns true for extra_vars JSON that embeds ${ expressions', () => {
    expect(hasExpressionValue(undefined, undefined, '{"app_version": "${inputs.version}"}')).toBe(true)
    expect(hasExpressionValue(JSON.stringify({ app_version: '${inputs.version}' }, null, 2))).toBe(true)
  })

  it('returns false when no values contain ${', () => {
    expect(hasExpressionValue('normal', 'text')).toBe(false)
    expect(hasExpressionValue(undefined, undefined)).toBe(false)
    expect(hasExpressionValue()).toBe(false)
  })

  it('handles undefined values', () => {
    expect(hasExpressionValue(undefined, 'text', undefined)).toBe(false)
  })
})

describe('validateWorkflowTemplateId', () => {
  it('returns valid positive integer', () => {
    expect(validateWorkflowTemplateId(456)).toBe(456)
  })

  it('throws on undefined', () => {
    expect(() => validateWorkflowTemplateId(undefined)).toThrow('Workflow Template ID must be a valid positive integer')
  })

  it('throws on zero', () => {
    expect(() => validateWorkflowTemplateId(0)).toThrow('Workflow Template ID must be a valid positive integer')
  })

  it('throws on negative number', () => {
    expect(() => validateWorkflowTemplateId(-5)).toThrow('Workflow Template ID must be a valid positive integer')
  })

  it('throws on non-integer (float)', () => {
    expect(() => validateWorkflowTemplateId(2.7)).toThrow('Workflow Template ID must be a valid positive integer')
  })
})

function makeWorkflowFormData(overrides: Partial<AAPWorkflowTemplateFormData> = {}): AAPWorkflowTemplateFormData {
  return {
    name: 'Test workflow step',
    organization_name: '',
    workflow_job_template_name: '',
    workflow_job_template_id: undefined,
    settings: {},
    ...overrides,
  }
}

describe('buildAAPWorkflowTemplateConfig', () => {
  it('returns undefined when no fields are set', () => {
    const result = buildAAPWorkflowTemplateConfig(makeWorkflowFormData())
    expect(result).toBeUndefined()
  })

  it('includes organization and workflowJobTemplateName when set', () => {
    const result = buildAAPWorkflowTemplateConfig(
      makeWorkflowFormData({ organization_name: 'Default', workflow_job_template_name: 'Deploy Workflow' })
    )
    expect(result).toEqual(
      expect.objectContaining({ organization_name: 'Default', workflow_job_template_name: 'Deploy Workflow' })
    )
  })

  it('includes inventoryId and inventoryName when set', () => {
    const result = buildAAPWorkflowTemplateConfig(makeWorkflowFormData({ inventory_id: 10, inventory_name: 'Staging' }))
    expect(result?.inventory_id).toBe(10)
    expect(result?.inventory_name).toBe('Staging')
  })

  it('includes credentialId when set', () => {
    const result = buildAAPWorkflowTemplateConfig(makeWorkflowFormData({ credential_id: 'cred-xyz' }))
    expect(result?.credential_id).toBe('cred-xyz')
  })

  it('includes integration_id when set', () => {
    const result = buildAAPWorkflowTemplateConfig(makeWorkflowFormData({ integration_id: 'int-aap-2' }))
    expect(result?.integration_id).toBe('int-aap-2')
  })

  it('includes both credential_id and integration_id when both set', () => {
    const result = buildAAPWorkflowTemplateConfig(
      makeWorkflowFormData({ credential_id: 'cred-xyz', integration_id: 'int-aap-2' })
    )
    expect(result?.credential_id).toBe('cred-xyz')
    expect(result?.integration_id).toBe('int-aap-2')
  })

  it('includes labels array when set', () => {
    const result = buildAAPWorkflowTemplateConfig(makeWorkflowFormData({ labels: ['production', 'deploy'] }))
    expect(result?.labels).toEqual(['production', 'deploy'])
  })

  it('excludes empty labels array', () => {
    const result = buildAAPWorkflowTemplateConfig(makeWorkflowFormData({ labels: [], organization_name: 'Default' }))
    expect(result?.labels).toBeUndefined()
  })

  it('parses valid JSON extra vars', () => {
    const result = buildAAPWorkflowTemplateConfig(makeWorkflowFormData({ extra_vars: '{"env": "prod"}' }))
    expect(result?.extra_vars).toEqual({ env: 'prod' })
  })

  it('ignores invalid JSON extra vars', () => {
    const result = buildAAPWorkflowTemplateConfig(makeWorkflowFormData({ extra_vars: 'invalid json' }))
    expect(result?.extra_vars).toBeUndefined()
  })

  it('includes workflow-specific string fields (limit, scm_branch, tags, skip_tags)', () => {
    const result = buildAAPWorkflowTemplateConfig(
      makeWorkflowFormData({
        limit: 'webservers',
        scm_branch: 'main',
        tags: 'deploy,config',
        skip_tags: 'slow',
      })
    )
    expect(result).toEqual(
      expect.objectContaining({
        limit: 'webservers',
        scm_branch: 'main',
        tags: 'deploy,config',
        skip_tags: 'slow',
      })
    )
  })

  it('handles organizationId of 0 (falsy but defined)', () => {
    const result = buildAAPWorkflowTemplateConfig(makeWorkflowFormData({ organization_id: 0 }))
    expect(result?.organization_id).toBe(0)
  })

  it('handles inventoryId of 0 (falsy but defined)', () => {
    const result = buildAAPWorkflowTemplateConfig(
      makeWorkflowFormData({ inventory_id: 0, organization_name: 'Default' })
    )
    expect(result?.inventory_id).toBe(0)
  })
})

describe('buildWorkflowExpressionModeActivity', () => {
  it('creates workflow activity in expression mode with template name', () => {
    const data = makeWorkflowFormData({
      organization_name: '${trigger.org}',
      workflow_job_template_name: '${trigger.workflow}',
      credential_id: 'cred-123',
    })

    const activity = buildWorkflowExpressionModeActivity('node-2', 'AAP Workflow', data)

    expect(activity.parameters.workflow_job_template_name).toBe('${trigger.workflow}')
    expect(activity.parameters.organization_name).toBe('${trigger.org}')
    expect(activity.parameters.credential_id).toBe('cred-123')
    expect(activity.parameters).not.toHaveProperty('workflow_job_template_id')
  })

  it('preserves workflow-specific fields in expression mode', () => {
    const data = makeWorkflowFormData({
      organization_name: '${vars.org}',
      workflow_job_template_name: '${vars.template}',
      scm_branch: '${vars.branch}',
      labels: ['auto-deploy'],
    })

    const activity = buildWorkflowExpressionModeActivity('node-3', 'Deploy', data)

    // Activity config uses snake_case API field names
    expect(activity.parameters.scm_branch).toBe('${vars.branch}')
    expect(activity.parameters.labels).toEqual(['auto-deploy'])
  })
})
