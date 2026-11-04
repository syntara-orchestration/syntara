import type { FormsAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { FormFieldTypeEnum } from '../../forms'
import { FORM_PROMPT_UNRESOLVED_DYNAMIC_OPTIONS_ALERT_TITLE } from '../../forms/formPromptDynamicOptions'

import { FormPromptResponseContent } from './FormPromptResponseContent'
import { useCanSubmitFormPrompt } from './hooks/useCanSubmitFormPrompt'

const mockFormsUseQuery = vi.hoisted(() => vi.fn())

vi.mock('../../client', () => ({
  formsClient: {
    useQuery: mockFormsUseQuery,
    useMutation: vi.fn(() => ({
      mutateAsync: vi.fn(),
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
  useCanSubmitFormPrompt: vi.fn(() => ({
    canSubmit: true,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  })),
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

function renderContent(prompt: FormPromptRead) {
  mockFormsUseQuery.mockReturnValue({
    data: prompt,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  })

  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <FormPromptResponseContent executionId={prompt.execution_id} formPromptId={prompt.id ?? 'fp-1'} />
    </QueryClientProvider>
  )
}

describe('FormPromptResponseContent dynamic options', () => {
  beforeEach(() => {
    vi.mocked(useCanSubmitFormPrompt).mockReturnValue({
      canSubmit: true,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    })
  })

  it('renders workflow-resolved dropdown options without a client resolver', async () => {
    const user = userEvent.setup()
    const prompt: FormPromptRead = {
      id: 'fp-dynamic-resolved',
      execution_id: 'exec-1',
      project_id: 'proj-1',
      prompt_node_id: 'pick_env',
      name: 'Pick environment',
      status: 'pending',
      message: 'Choose an environment.',
      created_at: '2026-09-30T00:00:00.000Z',
      timeout_at: '2027-08-04T16:41:00.000Z',
      form_definition: {
        fields: [
          {
            type: FormFieldTypeEnum.DROPDOWN,
            value_name: 'environment',
            label: 'Environment',
            required: true,
            options: {
              source: 'dynamic_resolved',
              values: [
                { display_label: 'Development', value: 'dev' },
                { display_label: 'Production', value: 'prod' },
              ],
            },
          },
        ],
      },
      submit_label: 'Submit',
    }

    renderContent(prompt)

    await user.click(screen.getByRole('button', { name: 'Environment' }))
    expect(await screen.findByRole('option', { name: 'Production' })).toBeInTheDocument()
  })

  it('warns when the prompt still has unresolved dynamic option expressions', async () => {
    const prompt: FormPromptRead = {
      id: 'fp-dynamic-unresolved',
      execution_id: 'exec-1',
      project_id: 'proj-1',
      prompt_node_id: 'pick_env',
      name: 'Pick environment',
      status: 'pending',
      created_at: '2026-09-30T00:00:00.000Z',
      timeout_at: '2027-08-04T16:41:00.000Z',
      form_definition: {
        fields: [
          {
            type: FormFieldTypeEnum.DROPDOWN,
            value_name: 'environment',
            label: 'Environment',
            options: {
              source: 'dynamic',
              expression: '${trigger.envs}',
              label_key: 'name',
              value_key: 'id',
            },
          },
        ],
      },
    }

    const { container } = renderContent(prompt)

    await waitFor(() => {
      expect(screen.getByText(FORM_PROMPT_UNRESOLVED_DYNAMIC_OPTIONS_ALERT_TITLE)).toBeInTheDocument()
    })
    expect(await axe(container)).toHaveNoViolations()
  })
})
