import type { WorkflowAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { workflowFetchClient } from '../../client'
import type { DialogState } from '../../hooks/useDialogState'
import { AlertProvider } from '../../providers/alerts'
import { ColorSchemeProvider } from '../../providers/theme/ColorSchemeProvider'

import { WorkflowDialogs } from './WorkflowDialogs'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

vi.mock('../../client', () => ({
  workflowFetchClient: {
    GET: vi.fn(),
  },
  executionsClient: {
    useQuery: vi.fn(() => ({ data: undefined, isLoading: false })),
  },
  workflowClient: {
    useMutation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
    useQuery: vi.fn(() => ({ data: undefined, isPending: false })),
  },
  accessClient: {
    useMutation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
    useQuery: vi.fn(() => ({ data: undefined, isPending: false })),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('./ImportWorkflowDialog', () => ({
  ImportWorkflowDialog: () => null,
}))

vi.mock('../builder/PublishWorkflowDialog', () => ({
  PublishWorkflowDialog: () => null,
}))

vi.mock('../access-management/ProjectFormModal', () => ({
  ProjectFormModal: () => null,
}))

function mockWorkflow(overrides: Partial<Workflow> = {}): Workflow {
  return {
    id: 'wf-1',
    name: 'Important Project Workflow',
    description: null,
    labels: {},
    current_version: 1,
    is_builtin: false,
    is_enabled: true,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    created_by: { id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', name: 'test-user' },
    project_id: 'proj-1',
    published_version_id: 'pub-1',
    published_version_number: 1,
    ...overrides,
  }
}

function createDialogState<T>(item: T | null = null, isOpen = false): DialogState<T> {
  return {
    isOpen,
    item,
    open: vi.fn(),
    close: vi.fn(),
  }
}

function mockGetResponse(data: Record<string, unknown> | undefined, error?: Record<string, unknown>) {
  return { data, error, response: new Response() } as never
}

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

function wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ColorSchemeProvider>
        <AlertProvider>{children}</AlertProvider>
      </ColorSchemeProvider>
    </QueryClientProvider>
  )
}

function renderDialogs(overrides: Partial<React.ComponentProps<typeof WorkflowDialogs>> = {}) {
  const props: React.ComponentProps<typeof WorkflowDialogs> = {
    runDialog: createDialogState<Workflow>(),
    deleteDialog: createDialogState<Workflow>(),
    publishDialog: createDialogState<Workflow>(),
    unpublishDialog: createDialogState<Workflow>(),
    importDialogOpen: false,
    setImportDialogOpen: vi.fn(),
    projectEditDialog: createDialogState(),
    projectDeleteDialog: createDialogState(),
    onRunWorkflow: vi.fn(),
    onDeleteWorkflow: vi.fn(),
    onPublishWorkflow: vi.fn(),
    onUnpublishWorkflow: vi.fn(),
    onDeleteProject: vi.fn(),
    onRefetchWorkflows: vi.fn(),
    onRefetchProjects: vi.fn(),
    isDeleting: false,
    isPublishing: false,
    isDeletingProject: false,
    ...overrides,
  }
  return { ...render(<WorkflowDialogs {...props} />, { wrapper }), props }
}

describe('WorkflowDialogs', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(
      mockGetResponse({
        id: 'wf-1',
        current_version: 1,
        published_version_number: 1,
        version: {
          workflow_definition: {
            triggers: [{ id: 'trigger-1', name: 'Manual Trigger', parameters: {} }],
          },
        },
      })
    )
  })

  it('has no accessibility violations with the run confirmation dialog open', async () => {
    const { container } = renderDialogs({
      runDialog: createDialogState(mockWorkflow(), true),
    })

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations with RunWorkflowModal open', async () => {
    const user = userEvent.setup()
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(
      mockGetResponse({
        id: 'wf-1',
        current_version: 1,
        published_version_number: 1,
        version: {
          workflow_definition: {
            triggers: [
              {
                id: 't-1',
                name: 'Manual Trigger',
                parameters: { input_schema: { type: 'object', properties: { version: { type: 'string' } } } },
              },
            ],
          },
        },
      })
    )
    const { container } = renderDialogs({ runDialog: createDialogState(mockWorkflow(), true) })

    await user.click(screen.getByRole('button', { name: 'Run now' }))
    await screen.findByText('Set mock output data for Manual Trigger')

    expect(await axe(container)).toHaveNoViolations()
  })

  it('runs immediately when the trigger has no input schema', async () => {
    const user = userEvent.setup()
    const onRunWorkflow = vi.fn()
    const runDialog = createDialogState(mockWorkflow(), true)
    renderDialogs({ runDialog, onRunWorkflow })

    await user.click(screen.getByRole('button', { name: 'Run now' }))

    await waitFor(() => {
      expect(onRunWorkflow).toHaveBeenCalledWith(expect.objectContaining({ id: 'wf-1' }), {}, 'trigger-1')
    })
    expect(runDialog.close).toHaveBeenCalled()
    expect(screen.queryByText('Set mock output data for Manual Trigger')).not.toBeInTheDocument()
  })

  it('shows RunWorkflowModal when the trigger has an input schema', async () => {
    const user = userEvent.setup()
    const onRunWorkflow = vi.fn()
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(
      mockGetResponse({
        id: 'wf-1',
        current_version: 1,
        published_version_number: 1,
        version: {
          workflow_definition: {
            triggers: [
              {
                id: 'trigger-1',
                name: 'Manual Trigger',
                parameters: {
                  input_schema: { type: 'object', properties: { version: { type: 'string' } } },
                },
              },
            ],
          },
        },
      })
    )

    const runDialog = createDialogState(mockWorkflow(), true)
    renderDialogs({ runDialog, onRunWorkflow })

    await user.click(screen.getByRole('button', { name: 'Run now' }))

    expect(await screen.findByText('Set mock output data for Manual Trigger')).toBeInTheDocument()
    expect(onRunWorkflow).not.toHaveBeenCalled()
    expect(runDialog.close).toHaveBeenCalled()
  })

  it('passes collected input_data when RunWorkflowModal is confirmed', async () => {
    const user = userEvent.setup()
    const onRunWorkflow = vi.fn()
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(
      mockGetResponse({
        id: 'wf-1',
        current_version: 1,
        published_version_number: 1,
        version: {
          workflow_definition: {
            triggers: [
              {
                id: 'trigger-1',
                name: 'Manual Trigger',
                parameters: {
                  input_schema: { type: 'object', properties: { version: { type: 'string' } } },
                },
              },
            ],
          },
        },
      })
    )

    renderDialogs({
      runDialog: createDialogState(mockWorkflow(), true),
      onRunWorkflow,
    })

    await user.click(screen.getByRole('button', { name: 'Run now' }))
    expect(await screen.findByText('Set mock output data for Manual Trigger')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Run' }))

    await waitFor(() => {
      expect(onRunWorkflow).toHaveBeenCalledWith(
        expect.objectContaining({ id: 'wf-1' }),
        expect.objectContaining({ version: '' }),
        'trigger-1'
      )
    })
  })

  it('shows an error and closes when the workflow has no triggers', async () => {
    const user = userEvent.setup()
    const onRunWorkflow = vi.fn()
    const runDialog = createDialogState(mockWorkflow(), true)
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(
      mockGetResponse({
        id: 'wf-1',
        current_version: 1,
        published_version_number: 1,
        version: { workflow_definition: { triggers: [] } },
      })
    )

    renderDialogs({ runDialog, onRunWorkflow })

    await user.click(screen.getByRole('button', { name: 'Run now' }))

    await waitFor(() => {
      expect(screen.getByText('Cannot run workflow')).toBeInTheDocument()
    })
    expect(onRunWorkflow).not.toHaveBeenCalled()
    expect(runDialog.close).toHaveBeenCalled()
  })

  it('runs immediately when input schema has empty properties', async () => {
    const user = userEvent.setup()
    const onRunWorkflow = vi.fn()
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(
      mockGetResponse({
        id: 'wf-1',
        current_version: 1,
        published_version_number: 1,
        version: {
          workflow_definition: {
            triggers: [
              {
                id: 'trigger-1',
                name: 'Manual Trigger',
                parameters: { input_schema: { type: 'object', properties: {} } },
              },
            ],
          },
        },
      })
    )

    renderDialogs({
      runDialog: createDialogState(mockWorkflow(), true),
      onRunWorkflow,
    })

    await user.click(screen.getByRole('button', { name: 'Run now' }))

    await waitFor(() => {
      expect(onRunWorkflow).toHaveBeenCalledWith(expect.objectContaining({ id: 'wf-1' }), {}, 'trigger-1')
    })
    expect(screen.queryByText('Set mock output data for Manual Trigger')).not.toBeInTheDocument()
  })

  it('shows an error when resolving the trigger throws', async () => {
    const user = userEvent.setup()
    const onRunWorkflow = vi.fn()
    const runDialog = createDialogState(mockWorkflow(), true)
    vi.mocked(workflowFetchClient.GET).mockRejectedValue(new Error('Network down'))

    renderDialogs({ runDialog, onRunWorkflow })

    await user.click(screen.getByRole('button', { name: 'Run now' }))

    await waitFor(() => {
      expect(screen.getByText('Cannot run workflow')).toBeInTheDocument()
      expect(screen.getByText('Network down')).toBeInTheDocument()
    })
    expect(onRunWorkflow).not.toHaveBeenCalled()
    expect(runDialog.close).toHaveBeenCalled()
  })

  it('closes RunWorkflowModal without executing when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const onRunWorkflow = vi.fn()
    vi.mocked(workflowFetchClient.GET).mockResolvedValue(
      mockGetResponse({
        id: 'wf-1',
        current_version: 1,
        published_version_number: 1,
        version: {
          workflow_definition: {
            triggers: [
              {
                id: 'trigger-1',
                name: 'Manual Trigger',
                parameters: {
                  input_schema: { type: 'object', properties: { version: { type: 'string' } } },
                },
              },
            ],
          },
        },
      })
    )

    renderDialogs({
      runDialog: createDialogState(mockWorkflow(), true),
      onRunWorkflow,
    })

    await user.click(screen.getByRole('button', { name: 'Run now' }))
    expect(await screen.findByText('Set mock output data for Manual Trigger')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    await waitFor(() => {
      expect(screen.queryByText('Set mock output data for Manual Trigger')).not.toBeInTheDocument()
    })
    expect(onRunWorkflow).not.toHaveBeenCalled()
  })
})
