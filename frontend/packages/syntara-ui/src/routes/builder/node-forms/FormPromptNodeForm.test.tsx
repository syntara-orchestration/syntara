import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'

import { FormPromptNodeForm } from './FormPromptNodeForm'
import type { FormPromptFormData } from './formPromptNodeFormSchema'
import { axeOptionsPatternFlyTabs } from './test-utils/axePatternFlyTabs'
import { renderWithHeader } from './test-utils/renderWithHeader'

const FORM_PROMPT_FORM_ID = 'form-prompt-node-form'
const defaultFormDefinition = createEmptyFormDefinition() as FormPromptFormData['form_definition']

const { mockUseApprovalDecideUsers, mockUseApprovalDecideGroups } = vi.hoisted(() => ({
  mockUseApprovalDecideUsers: vi.fn(() => ({
    users: [
      { id: 'user-1', username: 'responder1' },
      { id: 'user-2', username: 'responder2' },
    ],
    isLoading: false,
    isPermissionDenied: false,
    error: null,
    refetch: vi.fn(),
  })),
  mockUseApprovalDecideGroups: vi.fn(() => ({
    groups: [
      { id: 'group-1', name: 'operators' },
      { id: 'group-2', name: 'admins' },
    ],
    isLoading: false,
    error: null,
  })),
}))

vi.mock('./useApprovalDecideUsers', () => ({
  useApprovalDecideUsers: mockUseApprovalDecideUsers,
}))

vi.mock('./useApprovalDecideGroups', () => ({
  useApprovalDecideGroups: mockUseApprovalDecideGroups,
}))

const { mockUseWorkflowEngineDefaults } = vi.hoisted(() => ({
  mockUseWorkflowEngineDefaults: vi.fn(() => ({
    defaults: { timeoutSeconds: { form_prompt: 86400 }, continueOnFailure: false },
    isLoading: false,
  })),
}))

vi.mock('../hooks/useWorkflowEngineDefaults', () => ({
  useWorkflowEngineDefaults: mockUseWorkflowEngineDefaults,
}))

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: (selector: (state: { projectId: string | undefined }) => unknown) =>
    selector({ projectId: 'project-1' }),
}))

vi.mock('../../../components/forms/SynFormFieldBuilder', () => ({
  SynFormFieldBuilder: () => <section aria-label="Form field builder">Form field builder</section>,
}))

function renderFormPrompt(ui: ReactElement) {
  return renderWithHeader(ui, { formId: FORM_PROMPT_FORM_ID })
}

async function submitFormPromptForm(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Submit' }))
}

describe('FormPromptNodeForm', () => {
  const mockOnSubmit = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    mockUseWorkflowEngineDefaults.mockReturnValue({
      defaults: { timeoutSeconds: { form_prompt: 86400 }, continueOnFailure: false },
      isLoading: false,
    })
  })

  describe('Rendering', () => {
    it('renders Parameters and Settings tabs', () => {
      renderFormPrompt(<FormPromptNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.getByRole('tab', { name: 'Parameters' })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: 'Settings' })).toBeInTheDocument()
    })

    it('renders responder users and groups fields', () => {
      renderFormPrompt(<FormPromptNodeForm onSubmit={mockOnSubmit} projectId="project-1" />)

      expect(screen.getByText('Responder users')).toBeInTheDocument()
      expect(screen.getByText('Responder groups')).toBeInTheDocument()
    })

    it('renders message field and embedded form builder', () => {
      renderFormPrompt(<FormPromptNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.getByRole('textbox', { name: 'Message' })).toBeInTheDocument()
      expect(screen.getByRole('region', { name: 'Form field builder' })).toBeInTheDocument()
      expect(screen.getByRole('heading', { name: 'Form fields' })).toBeInTheDocument()
    })

    it('renders timeout section and fallback decision on Parameters', () => {
      renderFormPrompt(<FormPromptNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.getByRole('heading', { name: 'Timeout' })).toBeInTheDocument()
      expect(screen.getByText('Fallback decision')).toBeInTheDocument()
      expect(screen.getByText('Form submission window')).toBeInTheDocument()
    })

    it('shows Settings tab content when selected', async () => {
      const user = userEvent.setup()
      renderFormPrompt(<FormPromptNodeForm onSubmit={mockOnSubmit} />)

      await user.click(screen.getByRole('tab', { name: 'Settings' }))

      expect(screen.getByText('Expected duration (seconds)')).toBeInTheDocument()
    })

    it('shows default field values callout when continue on failure and submit path', () => {
      renderFormPrompt(
        <FormPromptNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            name: 'Form step',
            form_definition: defaultFormDefinition,
            settings: { continue_on_failure: true },
            fallback_decision: 'submit',
          }}
        />
      )

      expect(screen.getByText('Default field values')).toBeInTheDocument()
      expect(
        screen.getByText(/auto-submitted using the default values defined for each field on the Parameters tab/i)
      ).toBeInTheDocument()
    })
  })

  describe('Form submission', () => {
    it('submits trimmed parameters and derived fallback_behavior', async () => {
      const user = userEvent.setup()
      const formDefinition = defaultFormDefinition

      renderFormPrompt(
        <FormPromptNodeForm
          onSubmit={mockOnSubmit}
          projectId="project-1"
          initialData={{
            name: '  Collect input  ',
            message: '  Please respond  ',
            form_definition: formDefinition,
            responder_users: ['responder1'],
            responder_groups: ['operators'],
            response_window: 3600,
            settings: { continue_on_failure: true },
            fallback_decision: 'fallback',
            submit_label: 'Send',
            success_message: 'Thanks',
            timezone: 'America/New_York',
          }}
        />
      )

      await submitFormPromptForm(user)

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledOnce()
      })

      expect(mockOnSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Collect input',
          message: 'Please respond',
          form_definition: formDefinition,
          responder_users: ['responder1'],
          responder_groups: ['operators'],
          response_window: 3600,
          fallback_decision: 'fallback',
          fallback_behavior: 'fallback',
          submit_label: 'Send',
          success_message: 'Thanks',
          timezone: 'America/New_York',
        })
      )
    })

    it('forces submit path and fail behavior when continue on failure is off', async () => {
      const user = userEvent.setup()

      renderFormPrompt(
        <FormPromptNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            name: 'Form step',
            form_definition: defaultFormDefinition,
            settings: { continue_on_failure: false },
            fallback_decision: 'fallback',
          }}
        />
      )

      await submitFormPromptForm(user)

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledOnce()
      })

      expect(mockOnSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          fallback_decision: 'submit',
          fallback_behavior: 'fail',
        })
      )
    })
  })

  describe('Accessibility', () => {
    it('has no axe violations on Parameters tab (PatternFly Tabs happy-dom limitation)', async () => {
      const { container } = renderFormPrompt(<FormPromptNodeForm onSubmit={mockOnSubmit} projectId="project-1" />)

      const results = await axe(container, axeOptionsPatternFlyTabs)
      expect(results).toHaveNoViolations()
    })
  })
})
