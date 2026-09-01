import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

import { workflowClient } from '../client'

import { WorkflowName } from './WorkflowName'

vi.mock('../client', () => ({
  workflowClient: {
    useQuery: vi.fn(),
  },
}))

describe('WorkflowName', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('displays workflow name when loaded', () => {
    vi.mocked(workflowClient.useQuery).mockReturnValue({
      data: { id: 'workflow-1', name: 'Test Workflow' },
      isLoading: false,
      isError: false,
    })

    render(<WorkflowName workflowId="workflow-1" />)

    expect(screen.getByText('Test Workflow')).toBeInTheDocument()
  })

  it('displays workflow ID while loading', () => {
    vi.mocked(workflowClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    })

    render(<WorkflowName workflowId="workflow-1" />)

    expect(screen.getByText('workflow-1')).toBeInTheDocument()
  })

  it('displays workflow ID on error', () => {
    vi.mocked(workflowClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    })

    render(<WorkflowName workflowId="workflow-1" />)

    expect(screen.getByText('workflow-1')).toBeInTheDocument()
  })

  it('displays custom fallback while loading', () => {
    vi.mocked(workflowClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    })

    render(<WorkflowName workflowId="workflow-1" fallback="Loading..." />)

    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('displays workflow ID when data has no name', () => {
    vi.mocked(workflowClient.useQuery).mockReturnValue({
      data: { id: 'workflow-1' },
      isLoading: false,
      isError: false,
    })

    render(<WorkflowName workflowId="workflow-1" />)

    expect(screen.getByText('workflow-1')).toBeInTheDocument()
  })
})
