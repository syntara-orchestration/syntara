import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'

import { FormPromptNodeForm } from './FormPromptNodeForm'
import { FORM_PROMPT_FALLBACK_ENABLE_LINK, FORM_PROMPT_FALLBACK_ENABLED_HELPER } from './shared/nodeFieldHelpText'
import { axeOptionsPatternFlyTabs } from './test-utils/axePatternFlyTabs'
import { renderWithHeader } from './test-utils/renderWithHeader'

const FORM_PROMPT_FORM_ID = 'form-prompt-node-form'
const defaultFormDefinition = createEmptyFormDefinition()

const { mockWorkflowProjectId } = vi.hoisted(() => {
  const mockWorkflowProjectId: { current: string | undefined } = { current: 'project-1' }
  return { mockWorkflowProjectId }
})

const { mockUseFormPromptSubmitUsers, mockUseApprovalDecideGroups } = vi.hoisted(() => ({
  mockUseFormPromptSubmitUsers: vi.fn(() => ({
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

vi.mock('./useFormPromptSubmitUsers', () => ({
  useFormPromptSubmitUsers: mockUseFormPromptSubmitUsers,
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
    selector({ projectId: mockWorkflowProjectId.current }),
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
    mockWorkflowProjectId.current = 'project-1'
    mockUseFormPromptSubmitUsers.mockReturnValue({
      users: [
        { id: 'user-1', username: 'responder1' },
        { id: 'user-2', username: 'responder2' },
      ],
      isLoading: false,
      isPermissionDenied: false,
      error: null,
      refetch: vi.fn(),
    })
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

    it('enables continue on failure from the fallback guidance link', async () => {
      const user = userEvent.setup()
      renderFormPrompt(<FormPromptNodeForm onSubmit={mockOnSubmit} />)

      await user.click(screen.getByRole('button', { name: FORM_PROMPT_FALLBACK_ENABLE_LINK }))

      expect(screen.getByText(FORM_PROMPT_FALLBACK_ENABLED_HELPER)).toBeInTheDocument()
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

    it('shows warning alert when user lacks who_can permission', () => {
      mockUseFormPromptSubmitUsers.mockReturnValue({
        users: [],
        isLoading: false,
        isPermissionDenied: true,
        error: null,
        refetch: vi.fn(),
      })

      renderFormPrompt(<FormPromptNodeForm onSubmit={mockOnSubmit} projectId="some-project" />)

      expect(screen.getByText('Dropdown unavailable')).toBeInTheDocument()
      expect(
        screen.getByText("You don't have permission to list responder users. You can still enter usernames manually.")
      ).toBeInTheDocument()
    })

    it('shows project-required info alert when no project is selected', () => {
      mockWorkflowProjectId.current = undefined
      renderFormPrompt(<FormPromptNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.getByText('Project required')).toBeInTheDocument()
      expect(
        screen.getByText('Select a project to load responder users, or enter usernames manually.')
      ).toBeInTheDocument()
    })

    it('forwards projectId prop to useFormPromptSubmitUsers', () => {
      renderFormPrompt(<FormPromptNodeForm onSubmit={mockOnSubmit} projectId="test-project-123" />)

      expect(mockUseFormPromptSubmitUsers).toHaveBeenCalledWith('test-project-123')
    })
  })

  describe('Form submission', () => {
    it('submits trimmed parameters and fallback_decision', async () => {
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
          submit_label: 'Send',
          success_message: 'Thanks',
          timezone: 'America/New_York',
        })
      )
    })

    it('forces submit fallback_decision when continue on failure is off', async () => {
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

    it('has no accessibility violations in no-project state', async () => {
      mockWorkflowProjectId.current = undefined
      const { container } = renderFormPrompt(<FormPromptNodeForm onSubmit={mockOnSubmit} />)
      expect(await screen.findByText('Project required')).toBeInTheDocument()
      const results = await axe(container, axeOptionsPatternFlyTabs)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations when who_can permission is denied', async () => {
      mockUseFormPromptSubmitUsers.mockReturnValue({
        users: [],
        isLoading: false,
        isPermissionDenied: true,
        error: null,
        refetch: vi.fn(),
      })

      const { container } = renderFormPrompt(<FormPromptNodeForm onSubmit={mockOnSubmit} projectId="some-project" />)
      expect(await screen.findByText('Dropdown unavailable')).toBeInTheDocument()
      const results = await axe(container, axeOptionsPatternFlyTabs)
      expect(results).toHaveNoViolations()
    })
  })
})
