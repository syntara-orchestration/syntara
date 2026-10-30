import { describe, expect, it } from 'vitest'

import {
  EXECUTION_TARGET_FORM_DEFAULT_VALUES,
  executionTargetFormSchema,
  isKubernetesLabelKey,
  isKubernetesLabelValue,
  toExecutionTargetCreateBody,
} from './executionTargetFormSchema'

describe('isKubernetesLabelKey / isKubernetesLabelValue', () => {
  it('accepts simple keys and values', () => {
    expect(isKubernetesLabelKey('region')).toBe(true)
    expect(isKubernetesLabelValue('us-east')).toBe(true)
    expect(isKubernetesLabelValue('')).toBe(true)
  })

  it('accepts prefixed keys', () => {
    expect(isKubernetesLabelKey('kubernetes.io/hostname')).toBe(true)
  })

  it('rejects invalid keys and values', () => {
    expect(isKubernetesLabelKey('')).toBe(false)
    expect(isKubernetesLabelKey('-bad')).toBe(false)
    expect(isKubernetesLabelValue('-bad')).toBe(false)
  })
})

describe('executionTargetFormSchema', () => {
  const validData = {
    name: 'corp-internal-target',
    namespace: 'aao-execution',
    nodeSelectors: [{ key: 'region', value: 'us-east' }],
  }

  it('accepts valid form data', () => {
    expect(executionTargetFormSchema.safeParse(validData).success).toBe(true)
  })

  it('accepts empty node selector rows', () => {
    const result = executionTargetFormSchema.safeParse({
      ...validData,
      nodeSelectors: [{ key: '', value: '' }],
    })
    expect(result.success).toBe(true)
  })

  it('rejects missing name', () => {
    const result = executionTargetFormSchema.safeParse({ ...validData, name: '  ' })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues[0]?.message).toMatch(/name is required/i)
    }
  })

  it('rejects missing namespace', () => {
    const result = executionTargetFormSchema.safeParse({ ...validData, namespace: '' })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.some((issue) => /namespace is required/i.test(issue.message))).toBe(true)
    }
  })

  it('rejects invalid namespace pattern', () => {
    const result = executionTargetFormSchema.safeParse({ ...validData, namespace: 'Invalid_Namespace' })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.some((issue) => /invalid namespace/i.test(issue.message))).toBe(true)
    }
  })

  it('rejects selector row with key but invalid value', () => {
    const result = executionTargetFormSchema.safeParse({
      ...validData,
      nodeSelectors: [{ key: 'region', value: '-bad' }],
    })
    expect(result.success).toBe(false)
  })

  it('rejects selector row with value but missing key', () => {
    const result = executionTargetFormSchema.safeParse({
      ...validData,
      nodeSelectors: [{ key: '', value: 'us-east' }],
    })
    expect(result.success).toBe(false)
  })
})

describe('toExecutionTargetCreateBody', () => {
  it('maps form data to ExecutionTargetCreate payload', () => {
    const body = toExecutionTargetCreateBody({
      name: ' corp-internal-target ',
      namespace: ' aao-execution ',
      nodeSelectors: [
        { key: 'region', value: 'us-east' },
        { key: '', value: '' },
      ],
    })
    expect(body).toEqual({
      name: 'corp-internal-target',
      placement: {
        type: 'kubernetes',
        namespace: 'aao-execution',
        node_selectors: ['region=us-east'],
      },
    })
  })

  it('omits node_selectors when all rows are empty', () => {
    const body = toExecutionTargetCreateBody({
      name: 'target',
      namespace: 'ns',
      nodeSelectors: EXECUTION_TARGET_FORM_DEFAULT_VALUES.nodeSelectors,
    })
    expect(body.placement).toEqual({
      type: 'kubernetes',
      namespace: 'ns',
    })
  })
})
