import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useFetchFormPromptForUrlParam } from './useFetchFormPromptForUrlParam'

const mockUseQuery = vi.fn()

vi.mock('../../../client', () => ({
  formsClient: {
    useQuery: (...args: unknown[]): unknown => mockUseQuery(...args),
  },
}))

describe('useFetchFormPromptForUrlParam', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('does not enable query when form_prompt param is missing', () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false, isError: false, error: null, refetch: vi.fn() })

    renderHook(() => useFetchFormPromptForUrlParam('history=closed'))

    expect(mockUseQuery).toHaveBeenCalledWith(
      'get',
      '/form_prompts/{form_prompt_id}',
      { params: { path: { form_prompt_id: '' } } },
      { enabled: false }
    )
  })

  it('enables query and returns parsed prompt when param is present', () => {
    const prompt = {
      id: 'fp-1',
      form_definition: { fields: [] },
      execution_id: 'exec-1',
    }
    mockUseQuery.mockReturnValue({ data: prompt, isLoading: false, isError: false, error: null, refetch: vi.fn() })

    const { result } = renderHook(() => useFetchFormPromptForUrlParam('?form_prompt=fp-1'))

    expect(mockUseQuery).toHaveBeenCalledWith(
      'get',
      '/form_prompts/{form_prompt_id}',
      { params: { path: { form_prompt_id: 'fp-1' } } },
      { enabled: true }
    )
    expect(result.current.formPrompt).toEqual(prompt)
    expect(result.current.isError).toBe(false)
  })

  it('returns undefined prompt when response is not a form prompt read shape', () => {
    mockUseQuery.mockReturnValue({
      data: { id: 'fp-1' },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })

    const { result } = renderHook(() => useFetchFormPromptForUrlParam('?form_prompt=fp-1'))

    expect(result.current.formPrompt).toBeUndefined()
  })
})
