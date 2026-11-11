import { useParams } from '@tanstack/react-router'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { expectPageTitle } from '../../test/pageTitle'
import { routerTestState } from '../../test/setup'

let mockWorkflowQuery: { data: unknown; error: unknown; isLoading: boolean } = {
  data: undefined,
  error: null,
  isLoading: true,
}

vi.mock('../../client', () => ({
  workflowClient: {
    useQuery: () => mockWorkflowQuery,
  },
  executionsClient: {
    useQuery: () => ({ data: undefined }),
  },
}))

vi.mock('./BuilderContent', () => ({
  BuilderContent: (props: { initialViewVersion?: number | null }) => (
    <div data-testid="builder-content" data-version={props.initialViewVersion ?? 'none'} />
  ),
}))

describe('BuilderEdit', () => {
  beforeEach(() => {
    vi.resetModules()
    routerTestState.searchStr = ''
    vi.mocked(useParams).mockReturnValue({ workflowId: 'wf-1' })
    mockWorkflowQuery = { data: undefined, error: null, isLoading: true }
  })

  it('renders loading state', async () => {
    const { default: BuilderEdit } = await import('./BuilderEdit')
    render(<BuilderEdit />)

    expect(screen.getByText('Loading workflow')).toBeInTheDocument()
    expectPageTitle('Loading workflow | Workflows | Syntara')
  })

  it('renders error state when query fails', async () => {
    mockWorkflowQuery = { data: undefined, error: new Error('Not found'), isLoading: false }
    const { default: BuilderEdit } = await import('./BuilderEdit')
    render(<BuilderEdit />)

    expect(screen.getByRole('heading', { level: 1, name: 'Error loading workflow' })).toBeInTheDocument()
    expectPageTitle('Error loading workflow | Workflows | Syntara')
  })

  it('renders BuilderContent with valid version param', async () => {
    routerTestState.searchStr = '?version=3'
    mockWorkflowQuery = { data: { id: 'wf-1', name: 'test' }, error: null, isLoading: false }
    const { default: BuilderEdit } = await import('./BuilderEdit')
    render(<BuilderEdit />)

    const content = screen.getByTestId('builder-content')
    expect(content).toHaveAttribute('data-version', '3')
  })

  it('passes null initialViewVersion when no version param', async () => {
    routerTestState.searchStr = ''
    mockWorkflowQuery = { data: { id: 'wf-1', name: 'test' }, error: null, isLoading: false }
    const { default: BuilderEdit } = await import('./BuilderEdit')
    render(<BuilderEdit />)

    const content = screen.getByTestId('builder-content')
    expect(content).toHaveAttribute('data-version', 'none')
  })

  it('passes null for non-numeric version param', async () => {
    routerTestState.searchStr = '?version=abc'
    mockWorkflowQuery = { data: { id: 'wf-1', name: 'test' }, error: null, isLoading: false }
    const { default: BuilderEdit } = await import('./BuilderEdit')
    render(<BuilderEdit />)

    const content = screen.getByTestId('builder-content')
    expect(content).toHaveAttribute('data-version', 'none')
  })

  it('passes null for negative version param', async () => {
    routerTestState.searchStr = '?version=-1'
    mockWorkflowQuery = { data: { id: 'wf-1', name: 'test' }, error: null, isLoading: false }
    const { default: BuilderEdit } = await import('./BuilderEdit')
    render(<BuilderEdit />)

    const content = screen.getByTestId('builder-content')
    expect(content).toHaveAttribute('data-version', 'none')
  })

  it('passes null for zero version param', async () => {
    routerTestState.searchStr = '?version=0'
    mockWorkflowQuery = { data: { id: 'wf-1', name: 'test' }, error: null, isLoading: false }
    const { default: BuilderEdit } = await import('./BuilderEdit')
    render(<BuilderEdit />)

    const content = screen.getByTestId('builder-content')
    expect(content).toHaveAttribute('data-version', 'none')
  })
})
