import { TriggerTypeEnum } from '@syntara/contracts'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { submitForm } from '../../../test/submit-form'
import { isValidWebhookPath } from '../../../utils/webhookPath'

import { renderWithHeader } from './test-utils/renderWithHeader'
import { TriggerNodeForm } from './TriggerNodeForm'

// Mock ExpandableCodeEditor (moved to ../components/ after refactor)
vi.mock('../components/ExpandableCodeEditor', () => ({
  ExpandableCodeEditor: ({
    code,
    onCodeChange,
    ariaLabel,
  }: {
    code: string
    onCodeChange: (value: string) => void
    ariaLabel?: string
  }) => (
    <textarea
      data-testid="json-schema-editor"
      aria-label={ariaLabel}
      value={code}
      onChange={(e) => onCodeChange(e.target.value)}
    />
  ),
}))

// Mock backendUrl
vi.mock('../../../utils/backendUrl', () => ({
  WEBHOOK_BASE_URL: 'https://example.com/api/v1/webhooks',
  backendOrigin: 'https://example.com',
}))

// Mock ServiceAccountSelect to avoid async state updates from useQuery/useCanI
vi.mock('./ServiceAccountSelect', () => ({
  ServiceAccountSelect: () => null,
}))

// Mock ScheduleBuilderFields
vi.mock('../../../components/forms/ScheduleBuilderFields', () => ({
  ScheduleBuilderFields: ({
    value,
    onChange,
    errorMessage,
  }: {
    value: string
    onChange: (value: string) => void
    required?: boolean
    errorMessage?: string
  }) => (
    <div data-testid="schedule-builder-fields">
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        data-testid="interval-input"
        placeholder="Enter interval"
      />
      {errorMessage && <span data-testid="interval-error">{errorMessage}</span>}
    </div>
  ),
}))

async function submitTriggerForm() {
  await submitForm()
}

describe('TriggerNodeForm Component', () => {
  const mockOnSubmit = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Manual Trigger', () => {
    it('renders manual trigger form by default', () => {
      renderWithHeader(<TriggerNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.queryByLabelText('Trigger type')).not.toBeInTheDocument()
      expect(screen.queryByLabelText('Requires Approval')).not.toBeInTheDocument()
    })

    it('renders with initial manual trigger data', () => {
      const initialData = {
        triggerType: 'manual',
      }

      renderWithHeader(<TriggerNodeForm onSubmit={mockOnSubmit} initialData={initialData} />)

      expect(screen.queryByLabelText('Trigger type')).not.toBeInTheDocument()
    })
  })

  describe('Manual Trigger — inputSchema validation', () => {
    it('rejects invalid JSON in input schema', async () => {
      renderWithHeader(
        <TriggerNodeForm
          onSubmit={mockOnSubmit}
          initialData={{ triggerType: TriggerTypeEnum.MANUAL_TRIGGER, inputSchema: 'not valid json' }}
        />
      )

      await submitTriggerForm()

      await waitFor(() => {
        expect(screen.getByText('Invalid JSON — check syntax')).toBeInTheDocument()
      })
      expect(mockOnSubmit).not.toHaveBeenCalled()
    })

    it('rejects input schema that is not a JSON object', async () => {
      renderWithHeader(
        <TriggerNodeForm
          onSubmit={mockOnSubmit}
          initialData={{ triggerType: TriggerTypeEnum.MANUAL_TRIGGER, inputSchema: '"just a string"' }}
        />
      )

      await submitTriggerForm()

      await waitFor(() => {
        expect(screen.getByText('Input schema must be a JSON object')).toBeInTheDocument()
      })
      expect(mockOnSubmit).not.toHaveBeenCalled()
    })

    it('submits successfully with valid JSON object in input schema', async () => {
      renderWithHeader(
        <TriggerNodeForm
          onSubmit={mockOnSubmit}
          initialData={{ triggerType: TriggerTypeEnum.MANUAL_TRIGGER, inputSchema: '{"type": "object"}' }}
        />
      )

      await submitTriggerForm()

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            triggerType: TriggerTypeEnum.MANUAL_TRIGGER,
            inputSchema: '{"type": "object"}',
          })
        )
      })
    })

    it('submits successfully with empty input schema', async () => {
      renderWithHeader(
        <TriggerNodeForm onSubmit={mockOnSubmit} initialData={{ triggerType: TriggerTypeEnum.MANUAL_TRIGGER }} />
      )

      await submitTriggerForm()

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled()
      })
    })
  })

  describe('Scheduled Trigger', () => {
    it('shows schedule options when scheduled trigger is selected', () => {
      renderWithHeader(
        <TriggerNodeForm onSubmit={mockOnSubmit} initialData={{ triggerType: TriggerTypeEnum.SCHEDULED }} />
      )

      const toggle = screen.getByRole('button', { name: 'Schedule expression' })
      expect(toggle).toBeInTheDocument()
      expect(toggle).toHaveTextContent('Visual schedule builder')
    })

    it('shows interval picker for interval schedule type', () => {
      renderWithHeader(
        <TriggerNodeForm
          onSubmit={mockOnSubmit}
          initialData={{ triggerType: TriggerTypeEnum.SCHEDULED, scheduleType: 'interval' }}
        />
      )

      expect(screen.getByTestId('schedule-builder-fields')).toBeInTheDocument()
    })

    it('toggles cron input when schedule type changes', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <TriggerNodeForm
          onSubmit={mockOnSubmit}
          initialData={{ triggerType: TriggerTypeEnum.SCHEDULED, scheduleType: 'interval' }}
        />
      )

      expect(screen.queryByLabelText('Cron expression')).not.toBeInTheDocument()

      const toggle = screen.getByRole('button', { name: 'Schedule expression' })
      await user.click(toggle)
      await user.click(screen.getByRole('option', { name: 'Custom cron expression' }))

      expect(screen.getByLabelText('Cron expression')).toBeInTheDocument()
      expect(screen.queryByTestId('schedule-builder-fields')).not.toBeInTheDocument()

      await user.click(toggle)
      await user.click(screen.getByRole('option', { name: 'Visual schedule builder' }))
      expect(screen.queryByLabelText('Cron expression')).not.toBeInTheDocument()

      await user.click(toggle)
      await user.click(screen.getByRole('option', { name: 'Custom cron expression' }))

      expect(screen.getByLabelText('Cron expression')).toBeInTheDocument()
    })

    it('shows cron input for cron schedule type', () => {
      renderWithHeader(
        <TriggerNodeForm
          onSubmit={mockOnSubmit}
          initialData={{ triggerType: TriggerTypeEnum.SCHEDULED, scheduleType: 'cron' }}
        />
      )

      expect(screen.getByLabelText('Cron expression')).toBeInTheDocument()
      expect(screen.queryByTestId('schedule-builder-fields')).not.toBeInTheDocument()
    })

    it('shows cron input with initial value', () => {
      renderWithHeader(
        <TriggerNodeForm
          onSubmit={mockOnSubmit}
          initialData={{ triggerType: TriggerTypeEnum.SCHEDULED, scheduleType: 'cron', cron: '0 9 * * *' }}
        />
      )

      expect(screen.getByLabelText('Cron expression')).toHaveValue('0 9 * * *')
    })

    it('has no accessibility violations for cron schedule type', async () => {
      const { container } = renderWithHeader(
        <TriggerNodeForm
          onSubmit={mockOnSubmit}
          initialData={{ triggerType: TriggerTypeEnum.SCHEDULED, scheduleType: 'cron', cron: '0 9 * * *' }}
        />
      )
      // Exclude aria-valid-attr-value: PF6 Tabs renders aria-controls pointing to
      // a panel ID that may not exist in the DOM when only the active tab is rendered
      const results = await axe(container, { rules: { 'aria-valid-attr-value': { enabled: false } } })
      expect(results).toHaveNoViolations()
    })

    it('renders with initial scheduled trigger data', () => {
      const initialData = {
        triggerType: TriggerTypeEnum.SCHEDULED,
        scheduleType: 'interval',
        interval: 'R/2024-01-01T10:00:00Z/P1D',
      }

      renderWithHeader(<TriggerNodeForm onSubmit={mockOnSubmit} initialData={initialData} />)

      expect(screen.getByRole('button', { name: 'Schedule expression' })).toHaveTextContent('Visual schedule builder')
      expect(screen.getByTestId('interval-input')).toHaveValue('R/2024-01-01T10:00:00Z/P1D')
    })

    it('seeds a default interval so save can submit without waiting for the builder effect', async () => {
      renderWithHeader(
        <TriggerNodeForm onSubmit={mockOnSubmit} initialData={{ triggerType: TriggerTypeEnum.SCHEDULED }} />
      )

      const intervalValue = screen.getByTestId('interval-input').getAttribute('value') ?? ''
      expect(intervalValue.startsWith('R')).toBe(true)

      await submitTriggerForm()

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            triggerType: TriggerTypeEnum.SCHEDULED,
            scheduleType: 'interval',
            interval: intervalValue,
          })
        )
      })
    })

    it('blocks submit when cron expression is empty', async () => {
      renderWithHeader(
        <TriggerNodeForm
          onSubmit={mockOnSubmit}
          initialData={{ triggerType: TriggerTypeEnum.SCHEDULED, scheduleType: 'cron' }}
        />
      )

      await submitTriggerForm()

      await waitFor(() => {
        expect(screen.getByText('Cron expression is required')).toBeInTheDocument()
      })
      expect(mockOnSubmit).not.toHaveBeenCalled()
    })
  })

  describe('Form State', () => {
    it('does not show approval checkbox when scheduled trigger is selected', () => {
      renderWithHeader(
        <TriggerNodeForm onSubmit={mockOnSubmit} initialData={{ triggerType: TriggerTypeEnum.SCHEDULED }} />
      )

      expect(screen.queryByLabelText('Requires Approval')).not.toBeInTheDocument()
    })
  })

  describe('Webhook Trigger', () => {
    it('shows webhook path field when webhook trigger is selected', () => {
      renderWithHeader(
        <TriggerNodeForm onSubmit={mockOnSubmit} initialData={{ triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER }} />
      )

      expect(screen.getByLabelText('Webhook path')).toBeInTheDocument()
    })

    it('auto-generates a valid webhook path for new triggers', () => {
      renderWithHeader(
        <TriggerNodeForm onSubmit={mockOnSubmit} initialData={{ triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER }} />
      )

      const pathInput = screen.getByLabelText('Webhook path')
      const value = (pathInput as HTMLInputElement).value
      expect(value).toBeTruthy()
      expect(isValidWebhookPath(value)).toBe(true)
    })

    it('does not auto-generate a path when one is already provided', () => {
      renderWithHeader(
        <TriggerNodeForm
          onSubmit={mockOnSubmit}
          initialData={{ triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER, webhookPath: 'my-custom-path' }}
        />
      )

      expect(screen.getByLabelText('Webhook path')).toHaveValue('my-custom-path')
    })

    it('shows URL display with base URL', () => {
      renderWithHeader(
        <TriggerNodeForm onSubmit={mockOnSubmit} initialData={{ triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER }} />
      )

      expect(screen.getByLabelText('Webhook URL')).toBeInTheDocument()
    })

    it('shows JSON schema editor when switching to advanced mode', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <TriggerNodeForm onSubmit={mockOnSubmit} initialData={{ triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER }} />
      )

      expect(screen.queryByRole('textbox', { name: 'JSON schema validation editor' })).not.toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'Advanced' }))
      expect(screen.getByRole('textbox', { name: 'JSON schema validation editor' })).toBeInTheDocument()
    })

    it('submits webhook trigger with normalized path', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <TriggerNodeForm onSubmit={mockOnSubmit} initialData={{ triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER }} />
      )

      const pathInput = screen.getByLabelText('Webhook path')
      await user.clear(pathInput)
      await user.type(pathInput, '/Jira-Updates')
      await submitTriggerForm()

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER,
            webhookPath: 'jira-updates',
          })
        )
      })
    })

    it('submits form with empty webhook path (permissive schema)', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <TriggerNodeForm onSubmit={mockOnSubmit} initialData={{ triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER }} />
      )

      await user.clear(screen.getByLabelText('Webhook path'))
      await submitTriggerForm()

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled()
      })
    })

    it('rejects invalid webhook path characters', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <TriggerNodeForm onSubmit={mockOnSubmit} initialData={{ triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER }} />
      )

      const pathInput = screen.getByLabelText('Webhook path')
      await user.clear(pathInput)
      await user.type(pathInput, 'invalid path!@#')
      await submitTriggerForm()

      await waitFor(() => {
        expect(
          screen.getByText(
            'Path must start and end with a letter or number, and contain only lowercase letters, numbers, hyphens, and underscores'
          )
        ).toBeInTheDocument()
      })
      expect(mockOnSubmit).not.toHaveBeenCalled()
    })

    it('does not show schedule fields when webhook trigger is selected', () => {
      renderWithHeader(
        <TriggerNodeForm onSubmit={mockOnSubmit} initialData={{ triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER }} />
      )

      expect(screen.queryByLabelText('Schedule expression')).not.toBeInTheDocument()
      expect(screen.queryByTestId('schedule-builder-fields')).not.toBeInTheDocument()
    })

    it('renders with initial webhook trigger data', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <TriggerNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER,
            webhookPath: 'existing-path',
            inputSchema: '{"type": "object"}',
          }}
        />
      )

      expect(screen.getByLabelText('Webhook path')).toHaveValue('existing-path')
      await user.click(screen.getByRole('button', { name: 'Advanced' }))
      expect(screen.getByRole('textbox', { name: 'JSON schema validation editor' })).toHaveValue('{"type": "object"}')
    })

    it('has no accessibility violations', async () => {
      const { container } = renderWithHeader(
        <TriggerNodeForm onSubmit={mockOnSubmit} initialData={{ triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER }} />
      )
      // Exclude aria-valid-attr-value: PF6 Tabs renders aria-controls pointing to
      // a panel ID that may not exist in the DOM when only the active tab is rendered
      const results = await axe(container, { rules: { 'aria-valid-attr-value': { enabled: false } } })
      expect(results).toHaveNoViolations()
    })
  })

  describe('EDA Trigger', () => {
    it('shows webhook path field when EDA trigger is selected', () => {
      renderWithHeader(
        <TriggerNodeForm onSubmit={mockOnSubmit} initialData={{ triggerType: TriggerTypeEnum.EDA_TRIGGER }} />
      )

      expect(screen.getByLabelText('Webhook path')).toBeInTheDocument()
      expect(screen.queryByLabelText('Schedule expression')).not.toBeInTheDocument()
    })

    it('shows EDA webhook activation alert', () => {
      renderWithHeader(
        <TriggerNodeForm onSubmit={mockOnSubmit} initialData={{ triggerType: TriggerTypeEnum.EDA_TRIGGER }} />
      )

      expect(screen.getByText('EDA activation')).toBeInTheDocument()
    })

    it('auto-generates a valid webhook path for new EDA triggers', () => {
      renderWithHeader(
        <TriggerNodeForm onSubmit={mockOnSubmit} initialData={{ triggerType: TriggerTypeEnum.EDA_TRIGGER }} />
      )

      const pathInput = screen.getByLabelText('Webhook path')
      const value = (pathInput as HTMLInputElement).value
      expect(value).toBeTruthy()
      expect(isValidWebhookPath(value)).toBe(true)
    })

    it('submits EDA trigger with normalized path', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <TriggerNodeForm onSubmit={mockOnSubmit} initialData={{ triggerType: TriggerTypeEnum.EDA_TRIGGER }} />
      )

      const pathInput = screen.getByLabelText('Webhook path')
      await user.clear(pathInput)
      await user.type(pathInput, '/EDA-Events')
      await submitTriggerForm()

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            triggerType: TriggerTypeEnum.EDA_TRIGGER,
            webhookPath: 'eda-events',
          })
        )
      })
    })

    it('submits form with empty webhook path (permissive schema)', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <TriggerNodeForm onSubmit={mockOnSubmit} initialData={{ triggerType: TriggerTypeEnum.EDA_TRIGGER }} />
      )

      await user.clear(screen.getByLabelText('Webhook path'))
      await submitTriggerForm()

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled()
      })
    })

    it('renders with initial EDA trigger data', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <TriggerNodeForm
          onSubmit={mockOnSubmit}
          initialData={{
            triggerType: TriggerTypeEnum.EDA_TRIGGER,
            webhookPath: 'existing-eda-path',
            inputSchema: '{"type": "object"}',
          }}
        />
      )

      expect(screen.getByLabelText('Webhook path')).toHaveValue('existing-eda-path')
      await user.click(screen.getByRole('button', { name: 'Advanced' }))
      expect(screen.getByRole('textbox', { name: 'JSON schema validation editor' })).toHaveValue('{"type": "object"}')
    })

    it('has no accessibility violations', async () => {
      const { container } = renderWithHeader(
        <TriggerNodeForm onSubmit={mockOnSubmit} initialData={{ triggerType: TriggerTypeEnum.EDA_TRIGGER }} />
      )
      // Exclude aria-valid-attr-value: PF6 Tabs renders aria-controls pointing to
      // a panel ID that may not exist in the DOM when only the active tab is rendered
      const results = await axe(container, { rules: { 'aria-valid-attr-value': { enabled: false } } })
      expect(results).toHaveNoViolations()
    })
  })
})
