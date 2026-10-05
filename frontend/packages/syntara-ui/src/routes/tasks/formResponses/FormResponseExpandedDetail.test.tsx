import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createElement } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FormResponseExpandedDetail } from './FormResponseExpandedDetail'
import type { FormResponseListRow } from './useFormResponsesData'

const mockUseQuery = vi.hoisted(() => vi.fn())

vi.mock('../../../client', () => ({
  formsClient: {
    useQuery: mockUseQuery,
  },
}))

const baseRow: FormResponseListRow = {
  id: 'fp-1',
  execution_id: 'exec-1',
  project_id: 'proj-1',
  prompt_node_id: 'node-1',
  name: 'Collect input',
  status: 'submitted',
  workflow_name: 'Onboarding',
  workflowName: 'Onboarding',
  created_at: '2026-01-01T00:00:00Z',
  timeout_at: '2026-01-02T00:00:00Z',
}

function renderDetail(isExpanded: boolean) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)

  return render(
    <Wrapper>
      <FormResponseExpandedDetail row={baseRow} isExpanded={isExpanded} />
    </Wrapper>
  )
}

describe('FormResponseExpandedDetail', () => {
  it('does not fetch detail when the row is collapsed', () => {
    mockUseQuery.mockReturnValue({ isLoading: false, isError: false, data: undefined })
    renderDetail(false)

    expect(mockUseQuery).toHaveBeenCalledWith(
      'get',
      '/form_prompts/{form_prompt_id}',
      { params: { path: { form_prompt_id: 'fp-1' } } },
      { enabled: false }
    )
  })

  it('renders message and submitted data when expanded', () => {
    mockUseQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        message: 'Please review',
        response_data: { approved: true },
        timeout_at: '2026-01-02T00:00:00Z',
      },
    })

    renderDetail(true)

    expect(screen.getByText('Please review')).toBeInTheDocument()
    expect(screen.getByText(/"approved": true/)).toBeInTheDocument()
  })

  it('shows SynErrorState with retry when the detail query fails', async () => {
    const refetch = vi.fn()
    mockUseQuery.mockReturnValue({
      isLoading: false,
      isError: true,
      error: { title: 'Server error', detail: 'Network error', retryable: true },
      refetch,
    })

    renderDetail(true)

    expect(screen.getByText('Error loading details')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(refetch).toHaveBeenCalled()
  })

  it('has no accessibility violations when detail is loaded', async () => {
    mockUseQuery.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { message: 'Hello', response_data: null },
    })

    const { container } = renderDetail(true)
    expect(await axe(container)).toHaveNoViolations()
  })
})
