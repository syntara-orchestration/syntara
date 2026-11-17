import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useUnsavedChanges } from '../../app/useUnsavedChanges'
import { useWorkflowStore } from '../../stores/useWorkflowStore'
import { resetAll } from '../../stores/workflowStoreActions'
import { routerTestState } from '../../test/setup'

import { UnsavedChangesProvider } from './UnsavedChangesProvider'

// Mock workflow store - needed to control isDirty state
vi.mock('../../stores/useWorkflowStore', () => ({
  useWorkflowStore: vi.fn(),
}))

vi.mock('../../stores/workflowStoreActions', () => ({
  resetAll: vi.fn(),
}))

// Test helper component
function TestConsumer({
  targetPath = '/workflows',
  saveHandler,
}: {
  targetPath?: string
  saveHandler?: () => Promise<boolean>
}) {
  const { requestNavigation, registerSaveHandler } = useUnsavedChanges()

  return (
    <div>
      <button onClick={() => requestNavigation(targetPath)}>Navigate Away</button>
      {saveHandler && <button onClick={() => registerSaveHandler(saveHandler)}>Register Handler</button>}
    </div>
  )
}

describe('UnsavedChangesProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routerTestState.pathname = '/workflow-builder/123'

    vi.mocked(useWorkflowStore).mockReturnValue({})

    vi.mocked(useWorkflowStore).getState = vi.fn().mockReturnValue({
      isDirty: true,
    })
  })

  describe('when navigating with unsaved changes', () => {
    it('shows warning modal', async () => {
      const user = userEvent.setup()
      render(
        <UnsavedChangesProvider>
          <TestConsumer />
        </UnsavedChangesProvider>
      )

      await user.click(screen.getByText('Navigate Away'))

      expect(screen.getByText('Save changes before exiting the workflow builder?')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Save workflow' })).toBeDisabled() // No handler registered
      expect(screen.getByRole('button', { name: 'Exit without saving' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('exits without saving when choosing to discard changes', async () => {
      const user = userEvent.setup()
      render(
        <UnsavedChangesProvider>
          <TestConsumer />
        </UnsavedChangesProvider>
      )

      await user.click(screen.getByText('Navigate Away'))
      await user.click(screen.getByRole('button', { name: 'Exit without saving' }))

      expect(resetAll).toHaveBeenCalled()
      expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/workflows' })
    })

    it('saves and navigates when save succeeds', async () => {
      const user = userEvent.setup()
      const saveHandler = vi.fn().mockResolvedValue(true)

      render(
        <UnsavedChangesProvider>
          <TestConsumer saveHandler={saveHandler} />
        </UnsavedChangesProvider>
      )

      await user.click(screen.getByText('Register Handler'))
      await user.click(screen.getByText('Navigate Away'))
      await user.click(screen.getByRole('button', { name: 'Save workflow' }))

      await waitFor(() => {
        expect(saveHandler).toHaveBeenCalled()
        expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/workflows' })
      })
    })

    it('closes modal without navigating when save fails', async () => {
      const user = userEvent.setup()
      const saveHandler = vi.fn().mockResolvedValue(false)

      render(
        <UnsavedChangesProvider>
          <TestConsumer saveHandler={saveHandler} />
        </UnsavedChangesProvider>
      )

      await user.click(screen.getByText('Register Handler'))
      await user.click(screen.getByText('Navigate Away'))
      await user.click(screen.getByRole('button', { name: 'Save workflow' }))

      await waitFor(() => {
        expect(saveHandler).toHaveBeenCalled()
        expect(screen.queryByText('Save changes before exiting the workflow builder?')).not.toBeInTheDocument()
      })

      expect(routerTestState.navigate).not.toHaveBeenCalled()
    })

    it('stays on page when modal is closed', async () => {
      const user = userEvent.setup()
      render(
        <UnsavedChangesProvider>
          <TestConsumer />
        </UnsavedChangesProvider>
      )

      await user.click(screen.getByText('Navigate Away'))
      await user.click(screen.getByRole('button', { name: /close/i }))

      expect(screen.queryByText('Save changes before exiting the workflow builder?')).not.toBeInTheDocument()
      expect(routerTestState.navigate).not.toHaveBeenCalled()
    })

    it('disables buttons while save is in progress', async () => {
      const user = userEvent.setup()
      let resolveSave!: (value: boolean) => void
      const saveHandler = vi.fn().mockImplementation(() => new Promise((resolve) => (resolveSave = resolve)))

      render(
        <UnsavedChangesProvider>
          <TestConsumer saveHandler={saveHandler} />
        </UnsavedChangesProvider>
      )

      await user.click(screen.getByText('Register Handler'))
      await user.click(screen.getByText('Navigate Away'))
      await user.click(screen.getByRole('button', { name: 'Save workflow' }))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Exit without saving' })).toBeDisabled()
      })

      resolveSave(true)

      await waitFor(() => {
        expect(screen.queryByText('Save changes before exiting the workflow builder?')).not.toBeInTheDocument()
      })
    })
  })

  describe('when navigation should proceed immediately', () => {
    it('navigates without modal when staying within builder', async () => {
      const user = userEvent.setup()
      render(
        <UnsavedChangesProvider>
          <TestConsumer targetPath="/workflow-builder/456" />
        </UnsavedChangesProvider>
      )

      await user.click(screen.getByText('Navigate Away'))

      expect(screen.queryByText('Save changes before exiting the workflow builder?')).not.toBeInTheDocument()
      expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/workflow-builder/456' })
    })

    it('navigates without modal when no unsaved changes', async () => {
      const user = userEvent.setup()
      vi.mocked(useWorkflowStore).getState = vi.fn().mockReturnValue({ isDirty: false })

      render(
        <UnsavedChangesProvider>
          <TestConsumer />
        </UnsavedChangesProvider>
      )

      await user.click(screen.getByText('Navigate Away'))

      expect(screen.queryByText('Save changes before exiting the workflow builder?')).not.toBeInTheDocument()
      expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/workflows' })
    })

    it('navigates without modal when not on builder route', async () => {
      const user = userEvent.setup()
      routerTestState.pathname = '/workflows'

      render(
        <UnsavedChangesProvider>
          <TestConsumer />
        </UnsavedChangesProvider>
      )

      await user.click(screen.getByText('Navigate Away'))

      expect(screen.queryByText('Save changes before exiting the workflow builder?')).not.toBeInTheDocument()
      expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/workflows' })
    })
  })

  describe('save handler registration', () => {
    it('disables save button when no handler is registered', async () => {
      const user = userEvent.setup()

      render(
        <UnsavedChangesProvider>
          <TestConsumer />
        </UnsavedChangesProvider>
      )

      await user.click(screen.getByText('Navigate Away'))

      expect(screen.getByRole('button', { name: 'Save workflow' })).toBeDisabled()
    })

    it('clears save handler when unregisterSaveHandler is called', async () => {
      const user = userEvent.setup()
      const saveHandler = vi.fn().mockResolvedValue(true)

      function TestUnregister() {
        const { requestNavigation, registerSaveHandler, unregisterSaveHandler } = useUnsavedChanges()
        return (
          <div>
            <button onClick={() => registerSaveHandler(saveHandler)}>Register</button>
            <button onClick={unregisterSaveHandler}>Unregister</button>
            <button onClick={() => requestNavigation('/workflows')}>Navigate Away</button>
          </div>
        )
      }

      render(
        <UnsavedChangesProvider>
          <TestUnregister />
        </UnsavedChangesProvider>
      )

      await user.click(screen.getByText('Register'))
      await user.click(screen.getByText('Unregister'))
      await user.click(screen.getByText('Navigate Away'))

      expect(screen.getByRole('button', { name: 'Save workflow' })).toBeDisabled()
    })
  })

  describe('useUnsavedChanges hook', () => {
    it('returns no-op fallback when used outside provider', () => {
      const { container } = render(<TestConsumer />)
      expect(container).toBeTruthy()
    })
  })

  describe('registerDirtyCheck (generic unsaved changes)', () => {
    function DirtyCheckConsumer({
      dirtyCheck,
      saveAndExit,
    }: {
      dirtyCheck: () => boolean
      saveAndExit?: () => Promise<boolean>
    }) {
      const { requestNavigation, registerDirtyCheck } = useUnsavedChanges()

      return (
        <div>
          <button
            onClick={() =>
              registerDirtyCheck({
                check: dirtyCheck,
                saveAndExit,
                title: 'Save resource changes?',
                body: 'You have unsaved changes to enabled resources.',
                saveLabel: 'Save changes',
              })
            }
          >
            Register Dirty
          </button>
          <button onClick={() => requestNavigation('/workflows')}>Navigate Away</button>
        </div>
      )
    }

    it('shows custom modal when dirty check returns true', async () => {
      const user = userEvent.setup()
      routerTestState.pathname = '/configuration/integrations/1/resources'
      vi.mocked(useWorkflowStore).getState = vi.fn().mockReturnValue({ isDirty: false })

      render(
        <UnsavedChangesProvider>
          <DirtyCheckConsumer dirtyCheck={() => true} />
        </UnsavedChangesProvider>
      )

      await user.click(screen.getByText('Register Dirty'))
      await user.click(screen.getByText('Navigate Away'))

      expect(screen.getByText('Save resource changes?')).toBeInTheDocument()
      expect(screen.getByText('You have unsaved changes to enabled resources.')).toBeInTheDocument()
    })

    it('navigates without modal when dirty check returns false', async () => {
      const user = userEvent.setup()
      routerTestState.pathname = '/configuration/integrations/1/resources'
      vi.mocked(useWorkflowStore).getState = vi.fn().mockReturnValue({ isDirty: false })

      render(
        <UnsavedChangesProvider>
          <DirtyCheckConsumer dirtyCheck={() => false} />
        </UnsavedChangesProvider>
      )

      await user.click(screen.getByText('Register Dirty'))
      await user.click(screen.getByText('Navigate Away'))

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/workflows' })
    })

    it('shows save button with custom label when saveAndExit is provided', async () => {
      const user = userEvent.setup()
      routerTestState.pathname = '/configuration/integrations/1/resources'
      vi.mocked(useWorkflowStore).getState = vi.fn().mockReturnValue({ isDirty: false })
      const saveAndExit = vi.fn().mockResolvedValue(true)

      render(
        <UnsavedChangesProvider>
          <DirtyCheckConsumer dirtyCheck={() => true} saveAndExit={saveAndExit} />
        </UnsavedChangesProvider>
      )

      await user.click(screen.getByText('Register Dirty'))
      await user.click(screen.getByText('Navigate Away'))

      expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled()
    })

    it('saves and navigates when save button is clicked', async () => {
      const user = userEvent.setup()
      routerTestState.pathname = '/configuration/integrations/1/resources'
      vi.mocked(useWorkflowStore).getState = vi.fn().mockReturnValue({ isDirty: false })
      const saveAndExit = vi.fn().mockResolvedValue(true)

      render(
        <UnsavedChangesProvider>
          <DirtyCheckConsumer dirtyCheck={() => true} saveAndExit={saveAndExit} />
        </UnsavedChangesProvider>
      )

      await user.click(screen.getByText('Register Dirty'))
      await user.click(screen.getByText('Navigate Away'))
      await user.click(screen.getByRole('button', { name: 'Save changes' }))

      await waitFor(() => {
        expect(saveAndExit).toHaveBeenCalled()
        expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/workflows' })
      })
    })

    it('exits without saving and navigates when discard is clicked', async () => {
      const user = userEvent.setup()
      routerTestState.pathname = '/configuration/integrations/1/resources'
      vi.mocked(useWorkflowStore).getState = vi.fn().mockReturnValue({ isDirty: false })

      render(
        <UnsavedChangesProvider>
          <DirtyCheckConsumer dirtyCheck={() => true} />
        </UnsavedChangesProvider>
      )

      await user.click(screen.getByText('Register Dirty'))
      await user.click(screen.getByText('Navigate Away'))
      await user.click(screen.getByRole('button', { name: 'Exit without saving' }))

      expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/workflows' })
    })

    it('hides save button when no saveAndExit is provided and not on builder', async () => {
      const user = userEvent.setup()
      routerTestState.pathname = '/configuration/integrations/1/resources'
      vi.mocked(useWorkflowStore).getState = vi.fn().mockReturnValue({ isDirty: false })

      render(
        <UnsavedChangesProvider>
          <DirtyCheckConsumer dirtyCheck={() => true} />
        </UnsavedChangesProvider>
      )

      await user.click(screen.getByText('Register Dirty'))
      await user.click(screen.getByText('Navigate Away'))

      expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Exit without saving' })).toBeInTheDocument()
    })

    it('stays on page when cancel is clicked', async () => {
      const user = userEvent.setup()
      routerTestState.pathname = '/configuration/integrations/1/resources'
      vi.mocked(useWorkflowStore).getState = vi.fn().mockReturnValue({ isDirty: false })

      render(
        <UnsavedChangesProvider>
          <DirtyCheckConsumer dirtyCheck={() => true} />
        </UnsavedChangesProvider>
      )

      await user.click(screen.getByText('Register Dirty'))
      await user.click(screen.getByText('Navigate Away'))
      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(routerTestState.navigate).not.toHaveBeenCalled()
    })
  })
})

// ── TanStack router path ──────────────────────────────────────────────────────
//
// Each test uses vi.resetModules() + vi.doMock() so that the TanStack flag and
// useBlocker are controlled per-test. Dynamic imports are used inside each test
// to get fresh module instances that see the newly registered mocks.
describe('UnsavedChangesProvider (TanStack router path)', () => {
  const mockNavigate = vi.fn()
  const mockProceed = vi.fn()
  const mockReset = vi.fn()
  const mockResetAll = vi.fn()

  let mockBlockerState: { status: string; proceed?: () => void; reset?: () => void } = { status: 'idle' }

  beforeEach(() => {
    vi.clearAllMocks()
    mockBlockerState = { status: 'idle' }

    vi.resetModules()
    vi.doMock('@tanstack/react-router', () => ({
      useBlocker: vi.fn(() => {
        const [status, setStatus] = useState(mockBlockerState.status)
        return {
          ...mockBlockerState,
          status,
          proceed: mockBlockerState.proceed
            ? () => {
                mockProceed()
                setStatus('idle')
              }
            : undefined,
          reset: mockBlockerState.reset
            ? () => {
                mockReset()
                setStatus('idle')
              }
            : undefined,
        }
      }),
      useNavigate: () => mockNavigate,
      useRouterState: (opts?: { select?: (s: { location: { pathname: string } }) => unknown }) => {
        const state = { location: { pathname: '/workflow-builder/123' } }
        return opts?.select ? opts.select(state) : state
      },
    }))
    vi.doMock('../../stores/useWorkflowStore', () => ({
      useWorkflowStore: Object.assign(vi.fn().mockReturnValue({}), {
        getState: vi.fn().mockReturnValue({ isDirty: true }),
      }),
    }))
    vi.doMock('../../stores/workflowStoreActions', () => ({
      resetAll: mockResetAll,
    }))
  })

  afterEach(() => {
    vi.resetModules()
    vi.restoreAllMocks()
  })

  it('shows modal via direct check when navigating with unsaved changes', async () => {
    const user = userEvent.setup()
    const { UnsavedChangesProvider } = await import('./UnsavedChangesProvider')
    const { useUnsavedChanges: useTanStackUnsavedChanges } = await import('../../app/useUnsavedChanges')

    function TestNav() {
      const { requestNavigation } = useTanStackUnsavedChanges()
      return <button onClick={() => requestNavigation('/workflows')}>Navigate Away</button>
    }

    render(
      <UnsavedChangesProvider>
        <TestNav />
      </UnsavedChangesProvider>
    )

    await user.click(screen.getByText('Navigate Away'))

    expect(screen.getByText('Save changes before exiting the workflow builder?')).toBeInTheDocument()
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('shows modal when TanStack router blocks navigation', async () => {
    mockBlockerState = { status: 'blocked', proceed: mockProceed, reset: mockReset }

    const { UnsavedChangesProvider } = await import('./UnsavedChangesProvider')

    render(
      <UnsavedChangesProvider>
        <div />
      </UnsavedChangesProvider>
    )

    expect(await screen.findByText('Save changes before exiting the workflow builder?')).toBeInTheDocument()
  })

  it('calls proceed and clears workflow state when exiting without saving', async () => {
    const user = userEvent.setup()
    mockBlockerState = { status: 'blocked', proceed: mockProceed, reset: mockReset }

    const { UnsavedChangesProvider } = await import('./UnsavedChangesProvider')

    render(
      <UnsavedChangesProvider>
        <div />
      </UnsavedChangesProvider>
    )

    await screen.findByText('Save changes before exiting the workflow builder?')
    await user.click(screen.getByRole('button', { name: 'Exit without saving' }))

    expect(mockResetAll).toHaveBeenCalled()
    expect(mockProceed).toHaveBeenCalled()
    expect(screen.queryByText('Save changes before exiting the workflow builder?')).not.toBeInTheDocument()
  })

  it('calls proceed after a successful save', async () => {
    const user = userEvent.setup()
    mockBlockerState = { status: 'blocked', proceed: mockProceed, reset: mockReset }
    const saveHandler = vi.fn().mockResolvedValue(true)

    const { UnsavedChangesProvider } = await import('./UnsavedChangesProvider')
    const { useUnsavedChanges: useTanStackUnsavedChanges } = await import('../../app/useUnsavedChanges')

    function TestNav() {
      const { registerSaveHandler } = useTanStackUnsavedChanges()
      return <button onClick={() => registerSaveHandler(saveHandler)}>Register Handler</button>
    }

    render(
      <UnsavedChangesProvider>
        <TestNav />
      </UnsavedChangesProvider>
    )

    await screen.findByText('Save changes before exiting the workflow builder?')
    await user.click(screen.getByText('Register Handler'))
    await user.click(screen.getByRole('button', { name: 'Save workflow' }))

    await waitFor(() => {
      expect(saveHandler).toHaveBeenCalled()
      expect(mockProceed).toHaveBeenCalled()
    })
    expect(screen.queryByText('Save changes before exiting the workflow builder?')).not.toBeInTheDocument()
  })

  it('calls reset when save fails', async () => {
    const user = userEvent.setup()
    mockBlockerState = { status: 'blocked', proceed: mockProceed, reset: mockReset }
    const saveHandler = vi.fn().mockResolvedValue(false)

    const { UnsavedChangesProvider } = await import('./UnsavedChangesProvider')
    const { useUnsavedChanges: useTanStackUnsavedChanges } = await import('../../app/useUnsavedChanges')

    function TestNav() {
      const { registerSaveHandler } = useTanStackUnsavedChanges()
      return <button onClick={() => registerSaveHandler(saveHandler)}>Register Handler</button>
    }

    render(
      <UnsavedChangesProvider>
        <TestNav />
      </UnsavedChangesProvider>
    )

    await screen.findByText('Save changes before exiting the workflow builder?')
    await user.click(screen.getByText('Register Handler'))
    await user.click(screen.getByRole('button', { name: 'Save workflow' }))

    await waitFor(() => {
      expect(saveHandler).toHaveBeenCalled()
      expect(mockReset).toHaveBeenCalled()
    })
  })

  it('does not show modal when blocker status is idle', async () => {
    mockBlockerState = { status: 'idle' }

    const { UnsavedChangesProvider } = await import('./UnsavedChangesProvider')

    render(
      <UnsavedChangesProvider>
        <div>content</div>
      </UnsavedChangesProvider>
    )

    expect(screen.queryByText('Save changes before exiting the workflow builder?')).not.toBeInTheDocument()
  })

  it('calls reset when the modal is cancelled', async () => {
    const user = userEvent.setup()
    mockBlockerState = { status: 'blocked', proceed: mockProceed, reset: mockReset }

    const { UnsavedChangesProvider } = await import('./UnsavedChangesProvider')

    render(
      <UnsavedChangesProvider>
        <div />
      </UnsavedChangesProvider>
    )

    await screen.findByText('Save changes before exiting the workflow builder?')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(mockReset).toHaveBeenCalled()
    expect(screen.queryByText('Save changes before exiting the workflow builder?')).not.toBeInTheDocument()
  })
})
