import { describe, expect, it } from 'vitest'

import { FilterOperatorEnum } from '../../types/filters'

import { filterExecutionTargets, type ExecutionTarget } from './filterExecutionTargets'

const targets: ExecutionTarget[] = [
  {
    id: '1',
    cluster_id: 'c1',
    name: 'Alpha',
    backend_type: 'kubernetes',
    endpoint: 'https://a.example.com',
    placement: { type: 'kubernetes', namespace: 'ns', node_selectors: [], tolerations: [] },
    status: 'ready',
    enabled: true,
    is_default: false,
    labels: {},
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: '2',
    cluster_id: 'c2',
    name: 'Beta',
    backend_type: 'kubernetes',
    endpoint: 'https://b.example.com',
    placement: { type: 'kubernetes', namespace: 'ns', node_selectors: [], tolerations: [] },
    status: 'provisioning',
    enabled: false,
    is_default: false,
    labels: {},
    created_at: '2026-01-01T00:00:00Z',
  },
]

describe('filterExecutionTargets', () => {
  it('filters by name contains', () => {
    const result = filterExecutionTargets(targets, [
      { key: 'name', operator: FilterOperatorEnum.CONTAINS, value: 'bet' },
    ])
    expect(result.map((t) => t.name)).toEqual(['Beta'])
  })

  it('returns all targets when no name filter is set', () => {
    expect(filterExecutionTargets(targets, []).map((t) => t.name)).toEqual(['Alpha', 'Beta'])
  })
})
