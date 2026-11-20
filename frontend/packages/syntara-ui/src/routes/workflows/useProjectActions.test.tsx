import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { accessClient } from '../access/accessClient'
import type { ProjectRead } from '../access/types'

import { useProjectActions } from './useProjectActions'

// Mock the access client
vi.mock('../access/accessClient', () => ({
  accessClient: {
    useMutation: vi.fn(() => ({
      mutate: vi.fn(
        (_params: unknown, callbacks?: { onSuccess?: () => void; onSettled?: () => void; onError?: () => void }) => {
          // Simulate successful deletion
          callbacks?.onSuccess?.()
          callbacks?.onSettled?.()
        }
      ),
      isPending: false,
    })),
  },
}))

// Helper to create mock project objects for testing
function mockProject(overrides: Partial<ProjectRead> = {}): ProjectRead {
  return {
    id: 'proj-1',
    name: 'Test Project',
    description: null,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    labels: {},
    ...overrides,
  }
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return { Wrapper, queryClient }
}

describe('useProjectActions', () => {
  const mockShowSuccess = vi.fn()
  const mockShowError = vi.fn()
  const mockOnRefetch = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('onDeleteSettled callback', () => {
    it('calls onDeleteSettled when delete mutation completes', async () => {
      const mockOnDeleteSettled = vi.fn()
      const { Wrapper } = createWrapper()
      const { result } = renderHook(
        () =>
          useProjectActions({
            showSuccess: mockShowSuccess,
            showError: mockShowError,
            onRefetch: mockOnRefetch,
            onDeleteSettled: mockOnDeleteSettled,
          }),
        { wrapper: Wrapper }
      )

      const project = mockProject()
      result.current.handleDeleteProject(project)

      await waitFor(() => {
        expect(mockOnDeleteSettled).toHaveBeenCalledTimes(1)
      })
    })
  })

  describe('success messages', () => {
    it('shows correct delete success message with project name', async () => {
      const { Wrapper } = createWrapper()
      const { result } = renderHook(
        () =>
          useProjectActions({
            showSuccess: mockShowSuccess,
            showError: mockShowError,
            onRefetch: mockOnRefetch,
          }),
        { wrapper: Wrapper }
      )

      const project = { id: 'proj-1', name: 'My Project' }
      result.current.handleDeleteProject(project)

      await waitFor(() => {
        expect(mockShowSuccess).toHaveBeenCalledWith({
          title: 'Project deleted',
          description: 'Project "My Project" has been deleted successfully.',
        })
      })
    })
  })

  describe('refetch behavior', () => {
    it('calls onRefetch after successful delete', async () => {
      const { Wrapper, queryClient } = createWrapper()
      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
      const { result } = renderHook(
        () =>
          useProjectActions({
            showSuccess: mockShowSuccess,
            showError: mockShowError,
            onRefetch: mockOnRefetch,
          }),
        { wrapper: Wrapper }
      )

      const project = { id: 'proj-1', name: 'Test' }
      result.current.handleDeleteProject(project)

      await waitFor(() => {
        expect(mockOnRefetch).toHaveBeenCalledTimes(1)
      })
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['all-projects'] })
    })
  })

  describe('guard conditions', () => {
    it('does not call delete mutation when project has no id', () => {
      const { Wrapper } = createWrapper()
      const { result } = renderHook(
        () =>
          useProjectActions({
            showSuccess: mockShowSuccess,
            showError: mockShowError,
            onRefetch: mockOnRefetch,
          }),
        { wrapper: Wrapper }
      )

      const project = mockProject({ id: undefined })
      result.current.handleDeleteProject(project)

      // Should not show success or refetch if id is missing
      expect(mockShowSuccess).not.toHaveBeenCalled()
      expect(mockOnRefetch).not.toHaveBeenCalled()
    })
  })

  it.each([
    {
      error: {
        code: 'NODE_KIND_WRITE_DENIED',
        title: 'Step types not allowed',
        detail: "You can't delete project: Script (write denied).",
        blocked_step_types: [{ kind: 'script', label: 'Script', reason: 'explicit_deny' }],
      },
      title: 'Cannot delete project "Test Project"',
      description:
        "This project includes workflows with Script steps, but your assigned policies don't allow you to write them.",
    },
    {
      error: new Error('Request failed', {
        cause: {
          data: {
            code: 'NODE_KIND_WRITE_DENIED',
            title: 'Step types not allowed',
            detail: "You can't delete project: Script (no matching write grant); Wait (write denied).",
            blocked_step_types: [
              { kind: 'script', label: 'Script', reason: 'no_matching_allow' },
              { kind: 'wait', label: 'Wait', reason: 'explicit_deny' },
            ],
          },
        },
      }),
      title: 'Cannot delete project "Test Project"',
      description:
        "This project includes workflows with Script, Wait steps, but your assigned policies don't allow you to write them.",
    },
    {
      error: new Error('Permission denied'),
      title: 'Delete failed',
      description: 'Failed to delete project "Test Project": Permission denied',
    },
    {
      error: { title: 'Forbidden', detail: 'Unrelated permission error' },
      title: 'Delete failed',
      description: 'Failed to delete project "Test Project": Unrelated permission error',
    },
    {
      error: { code: 'NODE_KIND_WRITE_DENIED', blocked_step_types: [null, { label: 42 }] },
      title: 'Delete failed',
      description: 'Failed to delete project "Test Project": An unexpected error occurred',
    },
    {
      error: { cause: { code: 'NODE_KIND_WRITE_DENIED', detail: 'Original denial detail' } },
      title: 'Delete failed',
      description: 'Failed to delete project "Test Project": Original denial detail',
    },
  ])('formats structured denials and preserves other errors: $description', ({ error, title, description }) => {
    vi.mocked(accessClient.useMutation).mockReturnValue({
      mutate: vi.fn((_params: unknown, callbacks?: { onError?: (error: unknown) => void }) => {
        callbacks?.onError?.(error)
      }),
      isPending: false,
    })
    const { Wrapper } = createWrapper()
    const { result } = renderHook(
      () =>
        useProjectActions({
          showSuccess: mockShowSuccess,
          showError: mockShowError,
          onRefetch: mockOnRefetch,
        }),
      { wrapper: Wrapper }
    )

    result.current.handleDeleteProject(mockProject())

    expect(mockShowError).toHaveBeenCalledWith({ title, description })
    expect(mockShowSuccess).not.toHaveBeenCalled()
    expect(mockOnRefetch).not.toHaveBeenCalled()
  })
})
