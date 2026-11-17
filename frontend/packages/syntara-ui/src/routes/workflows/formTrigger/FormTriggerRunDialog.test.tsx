import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { parseFormDefinition } from '../../../forms'
import { AlertProvider } from '../../../providers/alerts'
import { ColorSchemeProvider } from '../../../providers/theme/ColorSchemeProvider'

import { FormTriggerRunDialog } from './FormTriggerRunDialog'

const mockNavigate = vi.fn()
const mockPost = vi.hoisted(() => vi.fn())
const mockShowSuccess = vi.hoisted(() => vi.fn())

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

vi.mock('../../../client', () => ({
  executionsFetchClient: {
    POST: mockPost,
  },
}))

vi.mock('../../../providers/alerts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../providers/alerts')>()
  return {
    ...actual,
    useAlerts: () => ({
      showSuccess: mockShowSuccess,
      showError: vi.fn(),
      showWarning: vi.fn(),
      showInfo: vi.fn(),
      showAlert: vi.fn(),
      dismissAlert: vi.fn(),
      clearAllAlerts: vi.fn(),
    }),
  }
})

const formTrigger = {
  definition: parseFormDefinition({
    fields: [{ type: 'text', value_name: 'reason', label: 'Reason', required: true }],
  }),
  message: 'Enter details',
  submitLabel: 'Send request',
  successMessage: 'Request received.',
}

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

function renderDialog(overrides: Partial<ComponentProps<typeof FormTriggerRunDialog>> = {}) {
  const props: ComponentProps<typeof FormTriggerRunDialog> = {
    isOpen: true,
    onClose: vi.fn(),
    workflowId: 'wf-1',
    workflowName: 'Demo workflow',
    triggerNodeId: 'form-1',
    triggerName: 'Intake',
    formTrigger,
    usePublished: true,
    canRun: true,
    runTooltip: 'You need execution:run',
    ...overrides,
  }
  return render(
    <QueryClientProvider client={queryClient}>
      <ColorSchemeProvider>
        <AlertProvider>
          <FormTriggerRunDialog {...props} />
        </AlertProvider>
      </ColorSchemeProvider>
    </QueryClientProvider>
  )
}

describe('FormTriggerRunDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockPost.mockResolvedValue({ data: { id: 'exec-1' }, error: undefined })
  })

  it('has no accessibility violations when open', async () => {
    const { container } = renderDialog()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('renders the form message and custom submit label', () => {
    renderDialog()
    expect(screen.getByText('Enter details')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Reason' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send request' })).toBeInTheDocument()
  })

  it('shows inline client validation errors for required fields', async () => {
    const user = userEvent.setup()
    renderDialog()

    await user.click(screen.getByRole('button', { name: 'Send request' }))

    expect(await screen.findByText(/required/i)).toBeInTheDocument()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('submits via POST /executions, shows a toast, closes, and navigates to the execution', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    renderDialog({ onClose })

    await user.type(screen.getByRole('textbox', { name: 'Reason' }), 'ok')
    await user.click(screen.getByRole('button', { name: 'Send request' }))

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/executions', {
        body: {
          workflow_id: 'wf-1',
          trigger_node_id: 'form-1',
          input_data: { reason: 'ok' },
          use_published: true,
        },
      })
    })
    expect(mockShowSuccess).toHaveBeenCalledWith({
      title: 'Submission successful',
      description: 'Request received.',
    })
    expect(onClose).toHaveBeenCalled()
    expect(mockNavigate).toHaveBeenCalledWith({
      to: '/executions/$executionId',
      params: { executionId: 'exec-1' },
      search: { history: 'closed' },
    })
  })

  it('disables submit and fields when user lacks execution:run', () => {
    renderDialog({ canRun: false, runTooltip: 'Need execution:run' })
    expect(screen.getByRole('button', { name: 'Send request' })).toBeDisabled()
    expect(screen.getByRole('textbox', { name: 'Reason' })).toBeDisabled()
  })

  it('shows the permission tooltip on disabled fields when user lacks execution:run', async () => {
    const user = userEvent.setup()
    renderDialog({ canRun: false, runTooltip: 'Need execution:run' })

    await user.hover(screen.getByRole('textbox', { name: 'Reason' }))

    expect(await screen.findByText('Need execution:run')).toBeInTheDocument()
  })

  it('shows loading on submit while permissions are checked', () => {
    renderDialog({ isCheckingPermissions: true })
    const submitButton = screen.getByRole('button', { name: /send request/i })
    expect(submitButton).toHaveClass('pf-m-in-progress')
    expect(submitButton).toBeDisabled()
  })

  it('maps server validation errors onto form fields', async () => {
    mockPost.mockResolvedValue({
      data: undefined,
      error: {
        code: 'FORM_VALIDATION_ERROR',
        detail: 'Form validation failed: reason: This field is required',
      },
    })
    const user = userEvent.setup()
    renderDialog()

    await user.type(screen.getByRole('textbox', { name: 'Reason' }), 'ok')
    await user.click(screen.getByRole('button', { name: 'Send request' }))

    await waitFor(() => expect(mockPost).toHaveBeenCalled())
    expect(await screen.findByText('This field is required')).toBeInTheDocument()
  })

  it('shows a submission failed alert for non-field API errors', async () => {
    mockPost.mockResolvedValue({
      data: undefined,
      error: { detail: 'Workflow is not published' },
    })
    const user = userEvent.setup()
    renderDialog()

    await user.type(screen.getByRole('textbox', { name: 'Reason' }), 'ok')
    await user.click(screen.getByRole('button', { name: 'Send request' }))

    expect(
      await screen.findByText('Unable to submit this form. Try again or contact your administrator.')
    ).toBeInTheDocument()
  })

  it('shows loading on the submit button while the request is in flight', async () => {
    let resolvePost: (value: unknown) => void = () => undefined
    mockPost.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePost = resolve
        })
    )
    const user = userEvent.setup()
    renderDialog()

    await user.type(screen.getByRole('textbox', { name: 'Reason' }), 'ok')
    await user.click(screen.getByRole('button', { name: 'Send request' }))

    expect(await screen.findByRole('progressbar')).toBeInTheDocument()

    resolvePost({ data: { id: 'exec-1' }, error: undefined })
    await waitFor(() => expect(screen.queryByRole('progressbar')).not.toBeInTheDocument())
  })
})
