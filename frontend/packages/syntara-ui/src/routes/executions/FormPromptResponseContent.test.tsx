import type { FormsAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { FormPromptResponseContent } from './FormPromptResponseContent'
import { useCanSubmitFormPrompt } from './hooks/useCanSubmitFormPrompt'
import { useFormPromptPermissions } from './hooks/useFormPromptPermissions'

const mockMutateAsync = vi.hoisted(() => vi.fn())
const mockFormsUseQuery = vi.hoisted(() => vi.fn())
const mockUseCanSubmitFormPrompt = vi.hoisted(() =>
  vi.fn(() => ({ canSubmit: true, isLoading: false, isError: false }))
)

vi.mock('../../client', () => ({
  formsClient: {
    useQuery: mockFormsUseQuery,
    useMutation: vi.fn(() => ({
      mutateAsync: mockMutateAsync,
      isPending: false,
    })),
  },
}))

vi.mock('./hooks/useFormPromptPermissions', () => ({
  useFormPromptPermissions: vi.fn(() => ({
    canRead: true,
    canSubmit: true,
    isChecking: false,
    isError: false,
    tooltips: { submit: 'No permission' },
  })),
}))

vi.mock('./hooks/useCanSubmitFormPrompt', () => ({
  useCanSubmitFormPrompt: mockUseCanSubmitFormPrompt,
}))

vi.mock('../../components/forms/SynDynamicForm', () => ({
  SynDynamicForm: ({
    id,
    onSubmit,
  }: {
    id?: string
    onSubmit?: (data: Record<string, unknown>) => void | Promise<void>
  }) => (
    <form
      id={id}
      aria-label="Form prompt fields"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit?.({ reason: 'approved' })?.catch(() => undefined)
      }}
    />
  ),
}))

vi.mock('../../providers/alerts', () => ({
  useAlerts: () => ({
    showSuccess: vi.fn(),
    showError: vi.fn(),
  }),
}))

vi.mock('../workflows/stores/useExecutionStore', () => ({
  useExecutionStore: (selector: (state: { activityStates: Map<string, unknown> }) => unknown) =>
    selector({ activityStates: new Map() }),
}))

type FormPromptRead = FormsAPI.components['schemas']['FormPromptRead']

const pendingPrompt: FormPromptRead = {
  id: 'fp-1',
  execution_id: 'exec-1',
  project_id: 'proj-1',
  prompt_node_id: 'collect_details',
  name: 'Collect input',
  status: 'pending',
  message: 'Please complete the form.',
  created_at: '2026-09-30T00:00:00.000Z',
  timeout_at: '2027-08-04T16:41:00.000Z',
  form_definition: { fields: [] },
  submit_label: 'Send',
}

const submittedPrompt: FormPromptRead = {
  ...pendingPrompt,
  status: 'submitted',
  response_data: { answer: 'yes' },
}

function renderContent(formPromptId = 'fp-1', executionId = 'exec-1', activityNameMap?: Map<string, string>) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <FormPromptResponseContent
        executionId={executionId}
        formPromptId={formPromptId}
        activityNameMap={activityNameMap}
      />
    </QueryClientProvider>
  )
}

describe('FormPromptResponseContent', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseCanSubmitFormPrompt.mockReturnValue({ canSubmit: true, isLoading: false, isError: false })
  })

  it('shows loading spinner while prompt is loading', () => {
    mockFormsUseQuery.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })

    renderContent()
    expect(screen.getByRole('progressbar', { name: 'Loading form prompt' })).toBeInTheDocument()
  })

  it('renders pending form with message and submit control', () => {
    mockFormsUseQuery.mockReturnValue({
      data: pendingPrompt,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })

    renderContent()

    expect(screen.getByText('Prompt step')).toBeInTheDocument()
    expect(screen.getByText('collect_details')).toBeInTheDocument()
    expect(screen.getByText('Waiting')).toBeInTheDocument()
    expect(screen.getByText(/\d+[smhd]/)).toBeInTheDocument()
    expect(screen.getByText('Please complete the form.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument()
  })

  it('renders submitted response read-only', () => {
    mockFormsUseQuery.mockReturnValue({
      data: submittedPrompt,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })

    renderContent()

    expect(screen.getByText('Submitted response')).toBeInTheDocument()
    expect(screen.getByText('yes')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Send' })).not.toBeInTheDocument()
  })

  it('shows access denied when user lacks read permission', () => {
    mockFormsUseQuery.mockReturnValue({
      data: pendingPrompt,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })

    vi.mocked(useFormPromptPermissions).mockReturnValue({
      canRead: false,
      canSubmit: false,
      isChecking: false,
      isError: false,
      tooltips: { submit: 'No permission' },
    })

    renderContent()

    expect(screen.getByRole('heading', { name: 'Access denied', level: 2 })).toBeInTheDocument()
  })

  it('uses activity name map for prompt step label', () => {
    mockFormsUseQuery.mockReturnValue({
      data: pendingPrompt,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })

    renderContent('fp-1', 'exec-1', new Map([['collect_details', 'Collect customer details']]))

    expect(screen.getByText('Collect customer details')).toBeInTheDocument()
  })

  it('shows closed alert for non-pending non-submitted statuses', () => {
    mockFormsUseQuery.mockReturnValue({
      data: { ...pendingPrompt, status: 'expired' },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })

    renderContent()

    expect(screen.getByText('Form prompt closed')).toBeInTheDocument()
    expect(screen.getByText(/expired/)).toBeInTheDocument()
  })

  it('renders non-string submitted values as JSON', () => {
    mockFormsUseQuery.mockReturnValue({
      data: {
        ...submittedPrompt,
        response_data: { count: 3 },
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })

    renderContent()

    expect(screen.getByText(/count/)).toBeInTheDocument()
    expect(screen.getByText(/3/)).toBeInTheDocument()
  })

  it('shows permissions checking spinner', () => {
    mockFormsUseQuery.mockReturnValue({
      data: pendingPrompt,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })
    vi.mocked(useFormPromptPermissions).mockReturnValue({
      canRead: true,
      canSubmit: true,
      isChecking: true,
      isError: false,
      tooltips: { submit: 'No permission' },
    })

    renderContent()

    expect(screen.getByRole('progressbar', { name: 'Checking permissions' })).toBeInTheDocument()
  })

  it('hides submit footer when user is not a configured responder', () => {
    mockFormsUseQuery.mockReturnValue({
      data: pendingPrompt,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })
    mockUseCanSubmitFormPrompt.mockReturnValue({ canSubmit: false, isLoading: false, isError: false })

    renderContent()

    expect(screen.queryByRole('button', { name: 'Send' })).not.toBeInTheDocument()
    expect(useCanSubmitFormPrompt).toHaveBeenCalled()
  })

  it('keeps loading when prompt execution id mismatches route execution id', () => {
    mockFormsUseQuery.mockReturnValue({
      data: { ...pendingPrompt, execution_id: 'other-exec' },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })

    renderContent('fp-1', 'exec-1')

    expect(screen.getByText('This form prompt belongs to a different workflow run.')).toBeInTheDocument()
  })

  it('submits form data and shows success feedback', async () => {
    const user = userEvent.setup()
    const onSubmitted = vi.fn()
    const refetch = vi.fn().mockResolvedValue(undefined)
    mockMutateAsync.mockResolvedValue({})
    mockFormsUseQuery.mockReturnValue({
      data: pendingPrompt,
      isLoading: false,
      isError: false,
      error: null,
      refetch,
    })

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <FormPromptResponseContent executionId="exec-1" formPromptId="fp-1" onSubmitted={onSubmitted} />
      </QueryClientProvider>
    )

    await user.click(screen.getByRole('button', { name: 'Send' }))

    expect(mockMutateAsync).toHaveBeenCalledWith({
      params: { path: { form_prompt_id: 'fp-1' } },
      body: { response_data: { reason: 'approved' } },
    })
    expect(onSubmitted).toHaveBeenCalled()
  })

  it('has no accessibility violations for pending prompt', async () => {
    mockFormsUseQuery.mockReturnValue({
      data: pendingPrompt,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })

    const { container } = renderContent()
    expect(await axe(container)).toHaveNoViolations()
  })
})
