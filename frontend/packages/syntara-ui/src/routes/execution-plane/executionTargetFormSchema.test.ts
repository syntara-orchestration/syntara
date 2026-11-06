import type { ExecutionPlaneAPI } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import {
  EXECUTION_TARGET_FORM_DEFAULT_VALUES,
  executionTargetFormSchema,
  isExecutionTargetFieldDirty,
  isKubernetesLabelKey,
  isKubernetesLabelValue,
  mapExecutionTargetUpdateFieldPath,
  parseNodeSelectorPairs,
  toExecutionTargetCreateBody,
  toExecutionTargetFormErrorField,
  toExecutionTargetFormValues,
  toExecutionTargetUpdateBody,
} from './executionTargetFormSchema'

type ExecutionTargetRead = ExecutionPlaneAPI.components['schemas']['ExecutionTargetRead']

function makeTarget(overrides?: Partial<ExecutionTargetRead>): ExecutionTargetRead {
  return {
    id: 'et-001',
    cluster_id: 'cluster-1',
    name: 'corp-internal-target',
    backend_type: 'kubernetes',
    endpoint: 'https://api.openshift.example.com:6443',
    placement: {
      type: 'kubernetes',
      namespace: 'aao-execution',
      node_selectors: ['region=us-east', 'tier=worker'],
    },
    status: 'active',
    enabled: true,
    is_default: false,
    status_message: null,
    labels: { integration_id: 'int-1' },
    created_at: '2026-01-01T00:00:00Z',
    last_ran_at: null,
    ...overrides,
  }
}

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

describe('parseNodeSelectorPairs', () => {
  it('parses key=value strings and keeps a blank row when empty', () => {
    expect(parseNodeSelectorPairs(['region=us-east', 'tier=worker'])).toEqual([
      { key: 'region', value: 'us-east' },
      { key: 'tier', value: 'worker' },
    ])
    expect(parseNodeSelectorPairs([])).toEqual([{ key: '', value: '' }])
  })

  it('treats selectors without "=" as key-only rows', () => {
    expect(parseNodeSelectorPairs(['region'])).toEqual([{ key: 'region', value: '' }])
  })
})

describe('toExecutionTargetFormValues', () => {
  it('pre-populates name, namespace, and node selectors from a loaded target', () => {
    expect(toExecutionTargetFormValues(makeTarget())).toEqual({
      name: 'corp-internal-target',
      namespace: 'aao-execution',
      nodeSelectors: [
        { key: 'region', value: 'us-east' },
        { key: 'tier', value: 'worker' },
      ],
    })
  })

  it('uses a blank selector row when placement has none', () => {
    expect(
      toExecutionTargetFormValues(
        makeTarget({
          placement: { type: 'kubernetes', namespace: 'ns' },
        })
      )
    ).toEqual({
      name: 'corp-internal-target',
      namespace: 'ns',
      nodeSelectors: [{ key: '', value: '' }],
    })
  })
})

describe('isExecutionTargetFieldDirty', () => {
  it('detects nested dirty field-array entries', () => {
    expect(isExecutionTargetFieldDirty(true)).toBe(true)
    expect(isExecutionTargetFieldDirty(undefined)).toBe(false)
    expect(isExecutionTargetFieldDirty([{ key: true }])).toBe(true)
    expect(isExecutionTargetFieldDirty([{ key: false, value: false }])).toBe(false)
  })
})

describe('toExecutionTargetUpdateBody', () => {
  const formData = {
    name: 'renamed-target',
    namespace: 'new-ns',
    nodeSelectors: [{ key: 'region', value: 'us-west' }],
  }

  it('includes only the changed name for a partial update', () => {
    expect(toExecutionTargetUpdateBody(formData, { name: true })).toEqual({
      name: 'renamed-target',
    })
  })

  it('sends full placement when namespace or node selectors change', () => {
    expect(toExecutionTargetUpdateBody(formData, { namespace: true })).toEqual({
      placement: {
        type: 'kubernetes',
        namespace: 'new-ns',
        node_selectors: ['region=us-west'],
      },
    })
    expect(toExecutionTargetUpdateBody(formData, { nodeSelectors: [{ key: true }] })).toEqual({
      placement: {
        type: 'kubernetes',
        namespace: 'new-ns',
        node_selectors: ['region=us-west'],
      },
    })
  })

  it('preserves existing tolerations when rebuilding placement', () => {
    const existing = makeTarget({
      placement: {
        type: 'kubernetes',
        namespace: 'old-ns',
        node_selectors: ['region=us-east'],
        tolerations: ['workload=automation:NoSchedule'],
      },
    })

    expect(toExecutionTargetUpdateBody(formData, { namespace: true }, existing)).toEqual({
      placement: {
        type: 'kubernetes',
        namespace: 'new-ns',
        node_selectors: ['region=us-west'],
        tolerations: ['workload=automation:NoSchedule'],
      },
    })
    expect(toExecutionTargetUpdateBody(formData, { nodeSelectors: [{ value: true }] }, existing)).toEqual({
      placement: {
        type: 'kubernetes',
        namespace: 'new-ns',
        node_selectors: ['region=us-west'],
        tolerations: ['workload=automation:NoSchedule'],
      },
    })
  })

  it('does not wipe an explicit empty tolerations list when rebuilding placement', () => {
    const existing = makeTarget({
      placement: {
        type: 'kubernetes',
        namespace: 'old-ns',
        tolerations: [],
      },
    })

    expect(toExecutionTargetUpdateBody(formData, { namespace: true }, existing).placement).toEqual({
      type: 'kubernetes',
      namespace: 'new-ns',
      node_selectors: ['region=us-west'],
      tolerations: [],
    })
  })

  it('returns an empty object when nothing is dirty', () => {
    expect(toExecutionTargetUpdateBody(formData, {})).toEqual({})
  })
})

describe('mapExecutionTargetUpdateFieldPath', () => {
  it('maps placement paths onto form field names', () => {
    expect(mapExecutionTargetUpdateFieldPath('name')).toBe('name')
    expect(mapExecutionTargetUpdateFieldPath('placement.namespace')).toBe('namespace')
    expect(mapExecutionTargetUpdateFieldPath('placement.node_selectors')).toBe('nodeSelectors')
    expect(mapExecutionTargetUpdateFieldPath('placement.node_selectors.0')).toBe('nodeSelectors')
  })
})

describe('toExecutionTargetFormErrorField', () => {
  it('returns only known form fields', () => {
    expect(toExecutionTargetFormErrorField('name')).toBe('name')
    expect(toExecutionTargetFormErrorField('placement.namespace')).toBe('namespace')
    expect(toExecutionTargetFormErrorField('placement.node_selectors')).toBe('nodeSelectors')
  })

  it('returns null for unexpected server paths', () => {
    expect(toExecutionTargetFormErrorField('labels.integration_id')).toBeNull()
    expect(toExecutionTargetFormErrorField('is_default')).toBeNull()
    expect(toExecutionTargetFormErrorField('placement.tolerations')).toBeNull()
  })
})
