import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'

import { executionsClient } from '../../client'
import { useCanI } from '../../hooks/useCanI'

import { CancelExecutionButton } from './CancelExecutionButton'

const mockMutate = vi.fn()
const mockShowSuccess = vi.fn()
const mockShowError = vi.fn()

vi.mock('../../client', () => ({
  executionsClient: {
    useMutation: vi.fn(() => ({
      mutate: mockMutate,
      isPending: false,
    })),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../hooks/useCanI', () => ({
  useCanI: vi.fn(() => ({ allowed: true, isChecking: false, isError: false })),
}))

vi.mock('../../providers/alerts/AlertContext', () => ({
  useAlerts: () => ({
    showSuccess: mockShowSuccess,
    showError: mockShowError,
  }),
}))

function renderButton(executionId = 'exec-123', projectId = 'project-1') {
  const queryClient = new QueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <CancelExecutionButton executionId={executionId} projectId={projectId} />
    </QueryClientProvider>
  )
}

describe('CancelExecutionButton', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(executionsClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    } as never)
  })

  it('renders an enabled cancel button', () => {
    renderButton()
    const button = screen.getByRole('button', { name: 'Cancel run' })
    expect(button).toBeInTheDocument()
    expect(button).toBeEnabled()
  })

  it('calls handleCancel which invokes mutate on click', async () => {
    mockMutate.mockImplementation((_params: unknown, callbacks: { onSuccess: () => void }) => {
      callbacks.onSuccess()
    })
    const user = userEvent.setup()
    renderButton('exec-999')

    await user.click(screen.getByRole('button', { name: 'Cancel run' }))

    expect(mockMutate).toHaveBeenCalledWith(
      { params: { path: { execution_id: 'exec-999' } } },
      expect.objectContaining({
        onSuccess: expect.any(Function) as unknown,
        onError: expect.any(Function) as unknown,
      })
    )
  })

  it('disables button and shows spinner while mutation is pending', () => {
    vi.mocked(executionsClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: true,
    } as never)

    renderButton()

    const button = screen.getByRole('button', { name: /Cancel/ })
    expect(button).toHaveAttribute('aria-disabled', 'true')
  })

  it('passes resourceProject to useCanI when projectId is provided', () => {
    renderButton('exec-123', 'proj-42')

    expect(useCanI).toHaveBeenCalledWith('run', 'execution', { resourceProject: 'proj-42' })
  })

  it('is aria-disabled when user lacks execution:run permission', () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })

    renderButton()

    const button = screen.getByRole('button', { name: 'Cancel run' })
    expect(button).toHaveAttribute('aria-disabled', 'true')
  })

  it('is aria-disabled while permission check is in flight without showing permission tooltip', () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: true, isError: false })

    renderButton()

    const button = screen.getByRole('button', { name: 'Cancel run' })
    expect(button).toHaveAttribute('aria-disabled', 'true')
    expect(screen.queryByText(/you need a role with the execution:run policy/i)).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = renderButton()
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
