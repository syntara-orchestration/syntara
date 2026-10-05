import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ProjectRead } from '../../access/types'

import { useFormResponsesData } from './useFormResponsesData'

const mockUseQuery = vi.hoisted(() => vi.fn())

vi.mock('../../../client', () => ({
  formsClient: {
    useQuery: mockUseQuery,
  },
}))

const projects: ProjectRead[] = [
  { id: 'proj-a', name: 'Project A', description: null, labels: {}, created_at: '', updated_at: '' },
]

describe('useFormResponsesData', () => {
  it('does not fetch until the project selector is ready', () => {
    mockUseQuery.mockReturnValue({ data: undefined, isPending: true, isFetching: false, error: null })

    renderHook(() =>
      useFormResponsesData({
        projectSelectorReady: false,
        isAllProjects: true,
        stableProjectId: undefined,
        queryParams: {},
        projects,
      })
    )

    expect(mockUseQuery).toHaveBeenCalledWith('get', '/form_prompts', { params: { query: {} } }, { enabled: false })
  })

  it('enriches list rows with workflow display fields', () => {
    mockUseQuery.mockReturnValue({
      data: {
        resources: [
          {
            id: 'fp-1',
            name: 'Collect input',
            workflow_name: 'Onboarding',
            workflow_id: 'wf-1',
            workflow_version: 2,
            project_id: 'proj-a',
            status: 'pending',
          },
        ],
      },
      isPending: false,
      isFetching: false,
      error: null,
    })

    const { result } = renderHook(() =>
      useFormResponsesData({
        projectSelectorReady: true,
        isAllProjects: true,
        stableProjectId: undefined,
        queryParams: {},
        projects,
      })
    )

    expect(result.current.enrichedRows).toEqual([
      expect.objectContaining({
        id: 'fp-1',
        workflowName: 'Onboarding',
        workflowId: 'wf-1',
        workflowVersion: 2,
      }),
    ])
  })

  it('groups rows by project when all projects is selected', () => {
    mockUseQuery.mockReturnValue({
      data: {
        resources: [
          { id: 'fp-1', name: 'A', workflow_name: 'W', project_id: 'proj-a', status: 'pending' },
          { id: 'fp-2', name: 'B', workflow_name: 'W', project_id: 'unknown', status: 'pending' },
        ],
      },
      isPending: false,
      isFetching: false,
      error: null,
    })

    const { result } = renderHook(() =>
      useFormResponsesData({
        projectSelectorReady: true,
        isAllProjects: true,
        stableProjectId: undefined,
        queryParams: {},
        projects,
      })
    )

    expect(result.current.groupedRows?.get('proj-a')?.rows).toHaveLength(1)
    expect(result.current.groupedRows?.get('unknown')?.rows).toHaveLength(1)
    expect(result.current.groupedRows?.get('proj-a')?.project?.name).toBe('Project A')
  })

  it('returns null grouped rows when a single project is selected', () => {
    mockUseQuery.mockReturnValue({
      data: { resources: [] },
      isPending: false,
      isFetching: false,
      error: null,
    })

    const { result } = renderHook(() =>
      useFormResponsesData({
        projectSelectorReady: true,
        isAllProjects: false,
        stableProjectId: 'proj-a',
        queryParams: { project_id: 'proj-a' },
        projects,
      })
    )

    expect(result.current.groupedRows).toBeNull()
  })
})
