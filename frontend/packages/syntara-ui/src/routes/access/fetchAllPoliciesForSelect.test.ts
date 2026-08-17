import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchAllPages, type FetchPageResult } from '../../utils/fetchAllPages'

import { accessFetchClient } from './accessClient'
import { fetchAllPoliciesForSelect, fetchAllProjectPoliciesForSelect } from './fetchAllPoliciesForSelect'
import { filterPoliciesForRoleSelect, type PolicySelectListItem } from './policySelectConstants'

vi.mock('../../utils/fetchAllPages', () => ({
  fetchAllPages: vi.fn(),
  MAX_PAGE_SIZE: 100,
}))

vi.mock('./accessClient', () => ({
  accessFetchClient: {
    GET: vi.fn(),
  },
}))

vi.mock('./policySelectConstants', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./policySelectConstants')>()
  return {
    ...actual,
    filterPoliciesForRoleSelect: vi.fn(actual.filterPoliciesForRoleSelect),
  }
})

describe('fetchAllPoliciesForSelect', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('delegates to fetchAllPages with scoped query params', async () => {
    const policies = [{ name: 'policy-a', is_project_eligible: true }]
    vi.mocked(accessFetchClient.GET).mockResolvedValue({
      data: { resources: policies, next: null },
    } as never)
    vi.mocked(fetchAllPages).mockImplementation(async (fetchPage): Promise<PolicySelectListItem[]> => {
      const page = (await fetchPage(undefined)) as FetchPageResult<PolicySelectListItem>
      if (page.error) throw new Error(JSON.stringify(page.error))
      if (!page.data) throw new Error('Empty response')
      return [...(page.data.resources ?? [])]
    })

    const result = await fetchAllPoliciesForSelect({
      scopeProjectId: 'proj-1',
      projectEligible: true,
      nameContains: 'admin',
    })

    expect(result).toEqual(policies)
    expect(accessFetchClient.GET).toHaveBeenCalledWith('/policies', {
      params: {
        query: {
          sort: 'name',
          limit: 100,
          cursor: undefined,
          'name[contains]': 'admin',
          project_id: 'proj-1',
          project_eligible: true,
        },
      },
    })
  })

  it('filters out project-only policies for global role select-all', async () => {
    const policies = [
      { name: 'workflow-admin', is_project_eligible: false },
      { name: 'policy:update:project', is_project_eligible: true },
    ]
    vi.mocked(fetchAllPages).mockResolvedValue(policies as never)

    const result = await fetchAllPoliciesForSelect({})

    expect(filterPoliciesForRoleSelect).toHaveBeenCalledWith(policies, {})
    expect(result).toEqual([policies[0]])
  })
})

describe('fetchAllProjectPoliciesForSelect', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns all project policies when no filter is provided', async () => {
    const policies = [
      { id: '1', name: 'read-policy' },
      { id: '2', name: 'write-policy' },
    ]
    vi.mocked(fetchAllPages).mockResolvedValue(policies as never)

    const result = await fetchAllProjectPoliciesForSelect('proj-1')

    expect(result).toEqual(policies)
  })

  it('filters project policies client-side when nameContains is provided', async () => {
    vi.mocked(fetchAllPages).mockResolvedValue([
      { id: '1', name: 'read-policy' },
      { id: '2', name: 'write-policy' },
      { id: '3', name: 'admin-policy' },
    ] as never)

    const result = await fetchAllProjectPoliciesForSelect('proj-1', 'read')

    expect(result).toEqual([{ id: '1', name: 'read-policy' }])
  })
})
