import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ReactFlowProvider } from '@xyflow/react'
import type { ComponentProps, ReactNode } from 'react'
import * as React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { approvalsClient, executionsClient, workflowClient } from '../../client'
import { AlertProvider } from '../../providers/alerts'

vi.mock('./components/NodeEditorOverlay', () => ({
  NodeEditorOverlay: ({ isOpen }: { isOpen: boolean }) => (isOpen ? <div data-testid="node-editor-overlay" /> : null),
}))

let shouldAutoSelectNode = false

vi.mock('./AddNodePanel', () => {
  return {
    AddNodePanel: ({ onSelectNode }: { onSelectNode: (nodeTypeId: string, nodeSubtypeId?: string | null) => void }) => {
      React.useEffect(() => {
        if (shouldAutoSelectNode) {
          onSelectNode('action', null)
        }
      }, [onSelectNode])
      return <div>Add step</div>
    },
  }
})

vi.mock('../../client', () => ({
  workflowClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  executionsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  approvalsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../app/useUnsavedChanges', () => ({
  useUnsavedChanges: () => ({
    registerSaveHandler: vi.fn(),
    unregisterSaveHandler: vi.fn(),
  }),
}))

vi.mock('./useBuilderPermissions', () => ({
  useBuilderPermissions: () => ({
    canEdit: true,
    canCreate: true,
    canRun: true,
    canDelete: true,
    isLoading: false,
    tooltips: { edit: '', save: '', publish: '', unpublish: '', run: '', delete: '', create: '' },
  }),
}))

import { BuilderContent } from './BuilderContent'

type BuilderContentProps = ComponentProps<typeof BuilderContent>

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>
      <ReactFlowProvider>{children}</ReactFlowProvider>
    </AlertProvider>
  </QueryClientProvider>
)

function renderBuilder(props: BuilderContentProps) {
  return render(<BuilderContent {...props} />, { wrapper })
}

describe('BuilderContent overlay', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    shouldAutoSelectNode = false

    vi.mocked(approvalsClient.useQuery).mockReturnValue({ data: undefined, refetch: vi.fn() })
    vi.mocked(approvalsClient.useMutation).mockReturnValue({ mutate: vi.fn(), isPending: false })

    vi.mocked(executionsClient.useQuery).mockImplementation((method, path) => {
      if (method === 'get' && path === '/executions') {
        return {
          data: { resources: [] },
          isPending: false,
          isError: false,
          error: null,
          refetch: vi.fn(),
        }
      }
      return {
        data: undefined,
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      }
    })
    vi.mocked(workflowClient.useQuery).mockImplementation((method, path) => {
      if (method === 'get' && path === '/workflows') {
        return {
          data: { resources: [] },
          isPending: false,
          isError: false,
          error: null,
          refetch: vi.fn(),
        }
      }
      return {
        data: undefined,
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      }
    })
    vi.mocked(workflowClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      mutateAsync: vi.fn(),
      reset: vi.fn(),
      isPending: false,
      isError: false,
      isSuccess: false,
      isIdle: true,
      error: null,
      data: undefined,
      variables: undefined,
      context: undefined,
      failureCount: 0,
      failureReason: null,
      status: 'idle' as const,
      submittedAt: 0,
    })
    vi.mocked(executionsClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      mutateAsync: vi.fn(),
      reset: vi.fn(),
      isPending: false,
      isError: false,
      isSuccess: false,
      isIdle: true,
      error: null,
      data: undefined,
      variables: undefined,
      context: undefined,
      failureCount: 0,
      failureReason: null,
      status: 'idle' as const,
      submittedAt: 0,
    })
  })

  it('renders node editor overlay after selecting a node to add', async () => {
    const user = userEvent.setup()
    shouldAutoSelectNode = true

    renderBuilder({ workflow: undefined, isNew: true, workflowId: null })

    await user.click(screen.getByRole('button', { name: /add step/i }))

    await waitFor(() => {
      expect(screen.getByTestId('node-editor-overlay')).toBeInTheDocument()
    })
  })
})
