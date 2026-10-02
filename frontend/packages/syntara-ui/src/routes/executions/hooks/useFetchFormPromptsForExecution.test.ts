import type { FormsAPI } from '@syntara/contracts'
import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { formsFetchClient } from '../../../client'

import { useFetchFormPromptsForExecution } from './useFetchFormPromptsForExecution'

vi.mock('../../../client', () => ({
  formsFetchClient: {
    GET: vi.fn(),
  },
}))

type FormPromptSummary = FormsAPI.components['schemas']['FormPromptSummary']

const mockPrompts: FormPromptSummary[] = [
  {
    id: 'fp-1',
    execution_id: 'exec-1',
    project_id: 'proj-1',
    prompt_node_id: 'collect_input',
    name: 'Collect input',
    status: 'pending',
    temporal_activity_id: 'collect_input',
  },
]

describe('useFetchFormPromptsForExecution', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(formsFetchClient.GET).mockResolvedValue({
      data: { resources: mockPrompts, next: null },
      error: undefined,
      response: { ok: true, status: 200 } as Response,
    })
  })

  it('initializes with not loading', () => {
    const { result } = renderHook(() => useFetchFormPromptsForExecution('exec-1'))
    expect(result.current.isLoading).toBe(false)
  })

  it('fetchPendingFormPrompts calls GET with execution and pending filters', async () => {
    const { result } = renderHook(() => useFetchFormPromptsForExecution('exec-1'))

    let fetched: FormPromptSummary[] = []
    await act(async () => {
      fetched = await result.current.fetchPendingFormPrompts()
    })

    expect(fetched).toEqual(mockPrompts)
    expect(formsFetchClient.GET).toHaveBeenCalledWith('/form_prompts', {
      params: {
        query: {
          execution_id: 'exec-1',
          limit: 100,
          status: 'pending',
        },
      },
    })
  })

  it('fetchFormPromptsForExecution calls GET without status filter', async () => {
    const { result } = renderHook(() => useFetchFormPromptsForExecution('exec-1'))

    await act(async () => {
      await result.current.fetchFormPromptsForExecution()
    })

    expect(formsFetchClient.GET).toHaveBeenCalledWith('/form_prompts', {
      params: {
        query: {
          execution_id: 'exec-1',
          limit: 100,
        },
      },
    })
  })

  it('returns empty array without fetching when executionId is empty', async () => {
    const { result } = renderHook(() => useFetchFormPromptsForExecution(''))

    let fetched: unknown
    await act(async () => {
      fetched = await result.current.fetchPendingFormPrompts()
    })

    expect(fetched).toEqual([])
    expect(formsFetchClient.GET).not.toHaveBeenCalled()
  })

  it('paginates until next cursor is empty', async () => {
    vi.mocked(formsFetchClient.GET)
      .mockResolvedValueOnce({
        data: {
          resources: [mockPrompts[0]],
          next: 'cursor-2',
        },
        error: undefined,
        response: { ok: true, status: 200 } as Response,
      })
      .mockResolvedValueOnce({
        data: {
          resources: [{ ...mockPrompts[0], id: 'fp-2', prompt_node_id: 'other' }],
          next: null,
        },
        error: undefined,
        response: { ok: true, status: 200 } as Response,
      })

    const { result } = renderHook(() => useFetchFormPromptsForExecution('exec-1'))

    let fetched: FormPromptSummary[] = []
    await act(async () => {
      fetched = await result.current.fetchFormPromptsForExecution()
    })

    expect(fetched).toHaveLength(2)
    expect(formsFetchClient.GET).toHaveBeenCalledTimes(2)
  })

  it('throws when API returns an error response', async () => {
    vi.mocked(formsFetchClient.GET).mockResolvedValue({
      data: undefined,
      error: { type: 'about:blank', title: 'Error', detail: 'boom', code: 'INTERNAL', retryable: false },
      response: { ok: false, status: 500 } as Response,
    })

    const { result } = renderHook(() => useFetchFormPromptsForExecution('exec-1'))

    await act(async () => {
      await expect(result.current.fetchFormPromptsForExecution()).rejects.toThrow('Failed to list form prompts (500)')
    })
  })

  it('filters invalid resources and normalizes defaults', async () => {
    vi.mocked(formsFetchClient.GET).mockResolvedValue({
      data: {
        resources: [
          mockPrompts[0],
          { id: 'bad', prompt_node_id: 123 } as unknown as FormPromptSummary,
          {
            id: 'fp-minimal',
            prompt_node_id: 'step',
            execution_id: 'EXEC-1',
          } as FormPromptSummary,
        ],
        next: null,
      },
      error: undefined,
      response: { ok: true, status: 200 } as Response,
    })

    const { result } = renderHook(() => useFetchFormPromptsForExecution('exec-1'))

    let fetched: FormPromptSummary[] = []
    await act(async () => {
      fetched = await result.current.fetchPendingFormPrompts()
    })

    expect(fetched.map((p) => p.id)).toEqual(['fp-1', 'fp-minimal'])
    expect(fetched[1]?.name).toBe('step')
    expect(fetched[1]?.temporal_activity_id).toBe('')
  })
})
