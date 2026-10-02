import { describe, expect, it } from 'vitest'

import { aapJobTemplateSchema } from './aapJobTemplateSchema'

const validBase = {
  name: 'Job',
  organization_name: 'Default',
  job_template_name: 'Deploy App',
  job_template_id: 10,
}

describe('aapJobTemplateSchema', () => {
  it('accepts valid minimal form data', () => {
    const result = aapJobTemplateSchema.safeParse(validBase)
    expect(result.success).toBe(true)
  })

  it('accepts valid form data with all optional fields', () => {
    const result = aapJobTemplateSchema.safeParse({
      ...validBase,
      inventory_name: 'Demo Inventory',
      inventory_id: 1,
      extra_vars: '{"key": "value"}',
      limit: 'webservers',
      tags: 'install',
      skip_tags: 'testing',
      verbosity: '2',
      job_type: 'run',
      forks: 10,
      job_slice_count: 2,
      diff_mode: true,
      execution_environment: 'Default EE',
      instance_group: 'group1',
      labels: ['prod', 'deploy'],
    })
    expect(result.success).toBe(true)
  })

  it('accepts empty organization (permissive schema for incomplete nodes)', () => {
    const result = aapJobTemplateSchema.safeParse({ ...validBase, organization_name: '' })
    expect(result.success).toBe(true)
  })

  it('accepts whitespace-only organization (permissive schema for incomplete nodes)', () => {
    const result = aapJobTemplateSchema.safeParse({ ...validBase, organization_name: '   ' })
    expect(result.success).toBe(true)
  })

  it('accepts empty jobTemplateName (permissive schema for incomplete nodes)', () => {
    const result = aapJobTemplateSchema.safeParse({ ...validBase, job_template_name: '' })
    expect(result.success).toBe(true)
  })

  it('accepts valid form data with empty extra_vars', () => {
    const result = aapJobTemplateSchema.safeParse({ ...validBase, extra_vars: '' })
    expect(result.success).toBe(true)
  })

  it('rejects invalid JSON in extra_vars', () => {
    const result = aapJobTemplateSchema.safeParse({ ...validBase, extra_vars: 'not json' })
    expect(result.success).toBe(false)
  })

  it('accepts valid JSON object in extra_vars', () => {
    const result = aapJobTemplateSchema.safeParse({ ...validBase, extra_vars: '{"key": "value"}' })
    expect(result.success).toBe(true)
  })

  it('rejects non-object JSON in extra_vars (array)', () => {
    const result = aapJobTemplateSchema.safeParse({ ...validBase, extra_vars: '[]' })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message === 'Extra variables must be a JSON object')).toBe(true)
    }
  })

  it('rejects non-object JSON in extra_vars (number)', () => {
    const result = aapJobTemplateSchema.safeParse({ ...validBase, extra_vars: '123' })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message === 'Extra variables must be a JSON object')).toBe(true)
    }
  })

  it('rejects non-object JSON in extra_vars (null)', () => {
    const result = aapJobTemplateSchema.safeParse({ ...validBase, extra_vars: 'null' })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message === 'Extra variables must be a JSON object')).toBe(true)
    }
  })

  it('coerces NaN optional number fields to undefined', () => {
    const result = aapJobTemplateSchema.safeParse({ ...validBase, forks: Number.NaN })
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.forks).toBeUndefined()
    }
  })

  it('accepts valid numeric optional fields', () => {
    const result = aapJobTemplateSchema.safeParse({ ...validBase, forks: 5, job_slice_count: 3 })
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.forks).toBe(5)
      expect(result.data.job_slice_count).toBe(3)
    }
  })

  it('accepts data with only the required name field', () => {
    const result = aapJobTemplateSchema.safeParse({ name: 'Incomplete Node' })
    expect(result.success).toBe(true)
  })

  it('accepts use_input_variables without a job template id', () => {
    const result = aapJobTemplateSchema.safeParse({ name: 'Incomplete Node', use_input_variables: true })
    expect(result.success).toBe(true)
  })
})
