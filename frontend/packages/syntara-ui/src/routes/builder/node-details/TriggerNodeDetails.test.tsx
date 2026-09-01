import { TriggerTypeEnum } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import type { Trigger } from '../../../stores/workflowStoreTypes'
import { expectStringContaining } from '../../../test/test-helpers'
import * as TriggerNodeFormModule from '../node-forms/TriggerNodeForm'

import { TriggerNodeDetails } from './TriggerNodeDetails'

// Mock the workflow store
const mockUpdateTrigger = vi.fn()
vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: vi.fn((selector?: (store: { updateTrigger: typeof mockUpdateTrigger }) => unknown) => {
    const store = {
      updateTrigger: mockUpdateTrigger,
    }
    return selector ? selector(store) : store
  }),
  useWorkflowStoreActions: vi.fn(() => ({
    updateTrigger: mockUpdateTrigger,
  })),
  createManualTrigger: vi.fn((_requiresApproval?: boolean, name?: string) => ({
    id: 'manual_trigger',
    type: TriggerTypeEnum.MANUAL_TRIGGER,
    name: name ?? 'Manual Trigger',
    parameters: {},
  })),
  createScheduledTrigger: vi.fn(
    (scheduleType: 'interval' | 'cron', options?: { interval?: string }, name?: string) => ({
      id: 'scheduled_trigger',
      type: TriggerTypeEnum.SCHEDULED,
      name: name ?? 'Scheduled Trigger',
      parameters: {
        schedule_type: scheduleType,
        ...(scheduleType === 'interval' && { interval: options?.interval ?? '' }),
      },
    })
  ),
}))

vi.mock('../utils/nodeNaming', () => ({
  getNodeDisplayNameForEdit: (baseName: string, requestedName?: string, currentName?: string) =>
    requestedName ?? currentName ?? baseName,
}))

// Mock the alerts hook
const mockShowError = vi.fn()
vi.mock('../../../providers/alerts', () => ({
  useAlerts: vi.fn(() => ({
    showSuccess: vi.fn(),
    showError: mockShowError,
  })),
}))

// Mock TriggerNodeForm
vi.mock('../node-forms/TriggerNodeForm', () => ({
  TriggerNodeForm: ({
    initialData,
    onSubmit,
    onCancel,
    submitButtonText,
  }: {
    initialData?: Record<string, unknown>
    onSubmit: (data: Record<string, unknown>) => void
    onCancel: () => void
    submitButtonText?: string
  }) => (
    <div data-testid="trigger-node-form">
      <div data-testid="initial-data">{JSON.stringify(initialData)}</div>
      <button type="button" onClick={() => onSubmit(initialData ?? {})} data-testid="submit-button">
        {submitButtonText ?? 'Add step'}
      </button>
      <button type="button" onClick={onCancel} data-testid="cancel-button">
        Cancel
      </button>
    </div>
  ),
}))

describe('TriggerNodeDetails Component', () => {
  const mockOnClose = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    vi.restoreAllMocks()
  })

  describe('Manual Trigger', () => {
    it('renders TriggerNodeForm with manual trigger data', () => {
      const trigger = {
        id: 'manual_trigger',
        type: TriggerTypeEnum.MANUAL_TRIGGER,
        name: 'Trigger',
        parameters: {},
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      expect(screen.getByTestId('trigger-node-form')).toBeInTheDocument()
      expect(screen.getByTestId('initial-data')).toHaveTextContent(
        JSON.stringify({
          name: 'Trigger',
          triggerType: TriggerTypeEnum.MANUAL_TRIGGER,
        })
      )
    })
  })

  describe('Manual Trigger with input_schema', () => {
    it('reads input_schema object from config and passes as JSON string', () => {
      const trigger = {
        id: 'manual_trigger',
        type: TriggerTypeEnum.MANUAL_TRIGGER,
        name: 'Trigger',
        parameters: {
          input_schema: {
            type: 'object',
            properties: { name: { type: 'string' } },
          },
        },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      const initialData = JSON.parse(screen.getByTestId('initial-data').textContent ?? '{}') as Record<string, unknown>
      expect(initialData.inputSchema).toBe(
        JSON.stringify({ type: 'object', properties: { name: { type: 'string' } } }, null, 2)
      )
    })

    it('reads input_schema string from config as-is', () => {
      const schemaStr = '{"type":"object","properties":{"x":{"type":"number"}}}'
      const trigger = {
        id: 'manual_trigger',
        type: TriggerTypeEnum.MANUAL_TRIGGER,
        name: 'Trigger',
        parameters: { input_schema: schemaStr },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      const initialData = JSON.parse(screen.getByTestId('initial-data').textContent ?? '{}') as Record<string, unknown>
      expect(initialData.inputSchema).toBe(schemaStr)
    })

    it('writes parsed input_schema to config on submit', async () => {
      const user = userEvent.setup()
      const schemaJson = '{"type":"object","properties":{"name":{"type":"string"}}}'

      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-with-schema"
          onClick={() => {
            onSubmit({
              name: 'Trigger',
              triggerType: TriggerTypeEnum.MANUAL_TRIGGER,
              inputSchema: schemaJson,
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      const trigger = { id: 'manual_trigger', type: TriggerTypeEnum.MANUAL_TRIGGER, name: 'Trigger', parameters: {} }
      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      await user.click(screen.getByTestId('submit-with-schema'))

      expect(mockUpdateTrigger).toHaveBeenCalledWith(0, {
        id: 'manual_trigger',
        type: TriggerTypeEnum.MANUAL_TRIGGER,
        name: 'Trigger',
        parameters: { input_schema: JSON.parse(schemaJson) as Record<string, unknown> },
      })

      formSpy.mockRestore()
    })

    it('omits input_schema from config when empty', async () => {
      const user = userEvent.setup()

      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-empty-schema"
          onClick={() => {
            onSubmit({
              name: 'Trigger',
              triggerType: TriggerTypeEnum.MANUAL_TRIGGER,
              inputSchema: '',
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      const trigger = {
        id: 'manual_trigger',
        type: TriggerTypeEnum.MANUAL_TRIGGER,
        name: 'Trigger',
        parameters: { input_schema: { type: 'object' } },
      }
      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      await user.click(screen.getByTestId('submit-empty-schema'))

      expect(mockUpdateTrigger).toHaveBeenCalledWith(0, {
        id: 'manual_trigger',
        type: TriggerTypeEnum.MANUAL_TRIGGER,
        name: 'Trigger',
        parameters: {},
      })
    })

    it('silently drops invalid JSON in inputSchema (Zod catches at form level)', async () => {
      const user = userEvent.setup()

      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-bad-schema"
          onClick={() => {
            onSubmit({
              name: 'Trigger',
              triggerType: TriggerTypeEnum.MANUAL_TRIGGER,
              inputSchema: 'not valid json',
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      const trigger = {
        id: 'manual_trigger',
        type: TriggerTypeEnum.MANUAL_TRIGGER,
        name: 'Trigger',
        parameters: { input_schema: { type: 'object' } },
      }
      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      await user.click(screen.getByTestId('submit-bad-schema'))

      // parseJsonSchema silently returns undefined for invalid JSON,
      // so the trigger is saved with empty config (no input_schema key).
      // Zod validation at the form level prevents this path in normal usage.
      expect(mockUpdateTrigger).toHaveBeenCalledWith(0, {
        id: 'manual_trigger',
        type: TriggerTypeEnum.MANUAL_TRIGGER,
        name: 'Trigger',
        parameters: {},
      })
      expect(mockOnClose).toHaveBeenCalledTimes(1)
    })
  })

  describe('Scheduled Trigger - Interval', () => {
    it('renders TriggerNodeForm with interval scheduled trigger data', () => {
      const trigger = {
        id: 'scheduled_trigger',
        type: TriggerTypeEnum.SCHEDULED,
        name: 'Trigger',
        parameters: {
          schedule_type: 'interval',
          interval: 'R/2024-01-01T10:00:00Z/P1D',
        },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      expect(screen.getByTestId('initial-data')).toHaveTextContent(
        JSON.stringify({
          name: 'Trigger',
          triggerType: TriggerTypeEnum.SCHEDULED,
          scheduleType: 'interval',
          interval: 'R/2024-01-01T10:00:00Z/P1D',
        })
      )
    })

    it('includes timezone and missedSchedulePolicy when present', () => {
      const trigger = {
        id: 'scheduled_trigger',
        type: TriggerTypeEnum.SCHEDULED,
        name: 'TZ Trigger',
        parameters: {
          schedule_type: 'interval',
          interval: 'PT1H',
          timezone: 'America/New_York',
          missed_schedule_policy: 'skip',
        },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      const initialDataText = screen.getByTestId('initial-data').textContent ?? '{}'
      expect(initialDataText).toContain('"timezone":"America/New_York"')
      expect(initialDataText).toContain('"missedSchedulePolicy":"skip"')
    })

    it('submits scheduled trigger with timezone and missedSchedulePolicy', async () => {
      const user = userEvent.setup()
      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-tz"
          onClick={() => {
            onSubmit({
              name: 'TZ Trigger',
              triggerType: TriggerTypeEnum.SCHEDULED,
              scheduleType: 'interval',
              interval: 'PT2H',
              timezone: 'UTC',
              missedSchedulePolicy: 'skip',
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      const trigger = {
        id: 'sched-tz',
        type: TriggerTypeEnum.SCHEDULED,
        name: 'Old',
        parameters: { schedule_type: 'interval', interval: 'PT1H' },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)
      await user.click(screen.getByTestId('submit-tz'))

      expect(mockUpdateTrigger).toHaveBeenCalledWith(0, {
        id: 'sched-tz',
        type: TriggerTypeEnum.SCHEDULED,
        name: 'TZ Trigger',
        parameters: {
          schedule_type: 'interval',
          interval: 'PT2H',
          timezone: 'UTC',
          missed_schedule_policy: 'skip',
        },
      })

      formSpy.mockRestore()
    })
  })

  describe('Scheduled Trigger - Cron', () => {
    it('renders TriggerNodeForm with cron scheduled trigger data', () => {
      const trigger = {
        id: 'scheduled_trigger',
        type: TriggerTypeEnum.SCHEDULED,
        name: 'Daily Job',
        parameters: {
          schedule_type: 'cron',
          cron: '0 9 * * 1-5',
        },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      expect(screen.getByTestId('initial-data')).toHaveTextContent(
        JSON.stringify({
          name: 'Daily Job',
          triggerType: TriggerTypeEnum.SCHEDULED,
          scheduleType: 'cron',
          cron: '0 9 * * 1-5',
        })
      )
    })

    it('calls updateTrigger with cron scheduled trigger on form submission', async () => {
      const user = userEvent.setup()
      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-cron"
          onClick={() => {
            onSubmit({
              name: 'Cron Trigger',
              triggerType: TriggerTypeEnum.SCHEDULED,
              scheduleType: 'cron',
              cron: '*/5 * * * *',
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      const trigger = {
        id: 'scheduled_trigger',
        type: TriggerTypeEnum.SCHEDULED,
        name: 'Trigger',
        parameters: { schedule_type: 'interval', interval: 'PT1H' },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={2} onClose={mockOnClose} />)

      await user.click(screen.getByTestId('submit-cron'))

      expect(mockUpdateTrigger).toHaveBeenCalledWith(2, {
        id: 'scheduled_trigger',
        type: TriggerTypeEnum.SCHEDULED,
        name: 'Cron Trigger',
        parameters: {
          schedule_type: 'cron',
          cron: '*/5 * * * *',
        },
      })
      expect(mockOnClose).toHaveBeenCalledTimes(1)
    })
  })

  describe('Error Handling', () => {
    it('handles invalid trigger type gracefully', () => {
      const trigger = {
        id: 'manual_trigger',
        type: TriggerTypeEnum.MANUAL_TRIGGER,
        name: 'Trigger',
        parameters: {},
      }

      // This test just verifies the component renders without errors
      // The actual error handling for invalid trigger types would be tested
      // through integration tests with actual form submissions
      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      expect(screen.getByTestId('trigger-node-form')).toBeInTheDocument()
    })

    it('rejects invalid ISO 8601 interval format', async () => {
      const user = userEvent.setup()
      // Spy on the module export
      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-invalid"
          onClick={() => {
            onSubmit({
              name: 'Test',
              triggerType: TriggerTypeEnum.SCHEDULED,
              scheduleType: 'interval',
              interval: 'invalid-format', // Invalid format
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      const trigger = {
        id: 'scheduled_trigger',
        type: TriggerTypeEnum.SCHEDULED,
        name: 'Trigger',
        parameters: { schedule_type: 'interval', interval: 'PT1H' },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      await user.click(screen.getByTestId('submit-invalid'))

      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Update failed',
        description: expectStringContaining('Invalid interval format'),
      })
      expect(mockOnClose).not.toHaveBeenCalled()

      formSpy.mockRestore()
    })

    it('rejects empty ISO 8601 duration (P or PT)', async () => {
      const user = userEvent.setup()
      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-empty-duration"
          onClick={() => {
            onSubmit({
              name: 'Test',
              triggerType: TriggerTypeEnum.SCHEDULED,
              scheduleType: 'interval',
              interval: 'PT', // Empty duration
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      const trigger = {
        id: 'scheduled_trigger',
        type: TriggerTypeEnum.SCHEDULED,
        name: 'Trigger',
        parameters: { schedule_type: 'interval', interval: 'PT1H' },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      await user.click(screen.getByTestId('submit-empty-duration'))

      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Update failed',
        description: expectStringContaining('Invalid interval format'),
      })
      expect(mockOnClose).not.toHaveBeenCalled()

      formSpy.mockRestore()
    })

    it('accepts valid simple ISO 8601 duration', async () => {
      const user = userEvent.setup()
      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-valid-duration"
          onClick={() => {
            onSubmit({
              name: 'Test',
              triggerType: TriggerTypeEnum.SCHEDULED,
              scheduleType: 'interval',
              interval: 'PT1H', // Valid simple duration
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      const trigger = {
        id: 'scheduled_trigger',
        type: TriggerTypeEnum.SCHEDULED,
        name: 'Trigger',
        parameters: { schedule_type: 'interval', interval: 'PT30M' },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      await user.click(screen.getByTestId('submit-valid-duration'))

      expect(mockShowError).not.toHaveBeenCalled()
      expect(mockOnClose).toHaveBeenCalled()

      formSpy.mockRestore()
    })

    it('accepts valid compound ISO 8601 duration', async () => {
      const user = userEvent.setup()
      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-compound-duration"
          onClick={() => {
            onSubmit({
              name: 'Test',
              triggerType: TriggerTypeEnum.SCHEDULED,
              scheduleType: 'interval',
              interval: 'P1DT12H30M', // Valid compound duration (1 day, 12 hours, 30 minutes)
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      const trigger = {
        id: 'scheduled_trigger',
        type: TriggerTypeEnum.SCHEDULED,
        name: 'Trigger',
        parameters: { schedule_type: 'interval', interval: 'PT1H' },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      await user.click(screen.getByTestId('submit-compound-duration'))

      expect(mockShowError).not.toHaveBeenCalled()
      expect(mockOnClose).toHaveBeenCalled()

      formSpy.mockRestore()
    })

    it('rejects malformed recurring interval with invalid duration', async () => {
      const user = userEvent.setup()
      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-malformed-recurring"
          onClick={() => {
            onSubmit({
              name: 'Test',
              triggerType: TriggerTypeEnum.SCHEDULED,
              scheduleType: 'interval',
              interval: 'R/2024-01-01T00:00:00Z/Pgarbage', // Malformed: invalid duration part
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      const trigger = {
        id: 'scheduled_trigger',
        type: TriggerTypeEnum.SCHEDULED,
        name: 'Trigger',
        parameters: { schedule_type: 'interval', interval: 'PT1H' },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      await user.click(screen.getByTestId('submit-malformed-recurring'))

      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Update failed',
        description: expectStringContaining('Invalid interval format'),
      })
      expect(mockOnClose).not.toHaveBeenCalled()

      formSpy.mockRestore()
    })

    it('rejects recurring interval with empty duration', async () => {
      const user = userEvent.setup()
      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-empty-recurring-duration"
          onClick={() => {
            onSubmit({
              name: 'Test',
              triggerType: TriggerTypeEnum.SCHEDULED,
              scheduleType: 'interval',
              interval: 'R/2024-01-01T00:00:00Z/P', // Empty duration part
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      const trigger = {
        id: 'scheduled_trigger',
        type: TriggerTypeEnum.SCHEDULED,
        name: 'Trigger',
        parameters: { schedule_type: 'interval', interval: 'PT1H' },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      await user.click(screen.getByTestId('submit-empty-recurring-duration'))

      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Update failed',
        description: expectStringContaining('Invalid interval format'),
      })
      expect(mockOnClose).not.toHaveBeenCalled()

      formSpy.mockRestore()
    })

    it('accepts valid recurring interval with compound duration', async () => {
      const user = userEvent.setup()
      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-valid-recurring"
          onClick={() => {
            onSubmit({
              name: 'Test',
              triggerType: TriggerTypeEnum.SCHEDULED,
              scheduleType: 'interval',
              interval: 'R/2024-01-01T00:00:00Z/P1DT12H', // Valid recurring with compound duration
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      const trigger = {
        id: 'scheduled_trigger',
        type: TriggerTypeEnum.SCHEDULED,
        name: 'Trigger',
        parameters: { schedule_type: 'interval', interval: 'PT1H' },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      await user.click(screen.getByTestId('submit-valid-recurring'))

      expect(mockShowError).not.toHaveBeenCalled()
      expect(mockOnClose).toHaveBeenCalled()

      formSpy.mockRestore()
    })

    it('accepts valid recurring ISO 8601 interval', async () => {
      const user = userEvent.setup()
      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-valid-recurring"
          onClick={() => {
            onSubmit({
              name: 'Test',
              triggerType: TriggerTypeEnum.SCHEDULED,
              scheduleType: 'interval',
              interval: 'R/2024-01-01T10:00:00Z/P1D', // Valid recurring interval
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      const trigger = {
        id: 'scheduled_trigger',
        type: TriggerTypeEnum.SCHEDULED,
        name: 'Trigger',
        parameters: { schedule_type: 'interval', interval: 'PT1H' },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      await user.click(screen.getByTestId('submit-valid-recurring'))

      expect(mockShowError).not.toHaveBeenCalled()
      expect(mockOnClose).toHaveBeenCalled()

      formSpy.mockRestore()
    })

    it('accepts recurring interval with end date', async () => {
      const user = userEvent.setup()
      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-with-end-date"
          onClick={() => {
            onSubmit({
              name: 'Test',
              triggerType: TriggerTypeEnum.SCHEDULED,
              scheduleType: 'interval',
              interval: 'R/2024-01-01T10:00:00Z/P1D/2024-12-31T23:59:59+00:00',
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      const trigger = {
        id: 'scheduled_trigger',
        type: TriggerTypeEnum.SCHEDULED,
        name: 'Trigger',
        parameters: { schedule_type: 'interval', interval: 'PT1H' },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      await user.click(screen.getByTestId('submit-with-end-date'))

      expect(mockShowError).not.toHaveBeenCalled()
      expect(mockOnClose).toHaveBeenCalled()

      formSpy.mockRestore()
    })
  })

  describe('Submit Button', () => {
    it('renders form with initial data', () => {
      const trigger = {
        id: 'manual_trigger',
        type: TriggerTypeEnum.MANUAL_TRIGGER,
        name: 'Trigger',
        parameters: {},
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      expect(screen.getByTestId('trigger-node-form')).toBeInTheDocument()
    })
  })

  describe('Default Fallback', () => {
    it('falls back to manual trigger for unsupported trigger types', () => {
      // Create an event trigger (which is not yet fully implemented)
      const trigger = {
        id: 'event_trigger',
        type: 'event' as const,
        name: 'Trigger',
        parameters: {},
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      expect(screen.getByTestId('initial-data')).toHaveTextContent(
        JSON.stringify({
          name: 'Trigger',
          triggerType: TriggerTypeEnum.MANUAL_TRIGGER,
        })
      )
    })

    it('does not call updateTrigger when submitting without changes (manual trigger)', async () => {
      const user = userEvent.setup()
      const trigger: Trigger = {
        id: 'manual_trigger',
        type: TriggerTypeEnum.MANUAL_TRIGGER,
        name: 'My Trigger',
        parameters: { input_schema: { type: 'object', properties: { name: { type: 'string' } } } },
      }

      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-unchanged"
          onClick={() => {
            // Submit with the same data as the initial trigger
            onSubmit({
              name: 'My Trigger',
              triggerType: TriggerTypeEnum.MANUAL_TRIGGER,
              inputSchema: JSON.stringify({ type: 'object', properties: { name: { type: 'string' } } }),
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      const submitButton = screen.getByTestId('submit-unchanged')
      await user.click(submitButton)

      // updateTrigger should NOT be called because nothing changed
      expect(mockUpdateTrigger).not.toHaveBeenCalled()
      expect(mockOnClose).toHaveBeenCalled()

      formSpy.mockRestore()
    })

    it('does not call updateTrigger when submitting without changes (scheduled trigger)', async () => {
      const user = userEvent.setup()
      const trigger: Trigger = {
        id: 'scheduled_trigger',
        type: TriggerTypeEnum.SCHEDULED,
        name: 'Scheduled Task',
        parameters: { schedule_type: 'interval', interval: 'PT1H' },
      }

      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-unchanged-scheduled"
          onClick={() => {
            // Submit with the same data as the initial trigger
            onSubmit({
              name: 'Scheduled Task',
              triggerType: TriggerTypeEnum.SCHEDULED,
              scheduleType: 'interval',
              interval: 'PT1H',
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      const submitButton = screen.getByTestId('submit-unchanged-scheduled')
      await user.click(submitButton)

      // updateTrigger should NOT be called because nothing changed
      expect(mockUpdateTrigger).not.toHaveBeenCalled()
      expect(mockOnClose).toHaveBeenCalled()

      formSpy.mockRestore()
    })

    it('calls updateTrigger when trigger data actually changes', async () => {
      const user = userEvent.setup()
      const trigger: Trigger = {
        id: 'manual_trigger',
        type: TriggerTypeEnum.MANUAL_TRIGGER,
        name: 'Old Name',
        parameters: {},
      }

      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-changed"
          onClick={() => {
            // Submit with different data
            onSubmit({
              name: 'New Name',
              triggerType: TriggerTypeEnum.MANUAL_TRIGGER,
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      const submitButton = screen.getByTestId('submit-changed')
      await user.click(submitButton)

      // updateTrigger SHOULD be called because the name changed
      expect(mockUpdateTrigger).toHaveBeenCalledWith(0, {
        id: 'manual_trigger',
        type: TriggerTypeEnum.MANUAL_TRIGGER,
        name: 'New Name',
        parameters: {},
      })
      expect(mockOnClose).toHaveBeenCalled()

      formSpy.mockRestore()
    })
  })

  describe('Webhook Trigger', () => {
    it('renders TriggerNodeForm with webhook trigger data', () => {
      const trigger = {
        id: 'wh-1',
        type: TriggerTypeEnum.WEBHOOK_TRIGGER,
        name: 'My Webhook',
        parameters: {
          webhook_path: 'jira-updates',
          input_schema: { type: 'object', properties: { name: { type: 'string' } } },
        },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      expect(screen.getByTestId('trigger-node-form')).toBeInTheDocument()
      const initialDataText = screen.getByTestId('initial-data').textContent ?? '{}'
      expect(initialDataText).toContain('"triggerType":"webhook_trigger"')
      expect(initialDataText).toContain('"webhookPath":"jira-updates"')
      expect(initialDataText).toContain('object')
      expect(initialDataText).toContain('inputSchema')
    })

    it('calls updateTrigger with webhook trigger on form submission', async () => {
      const user = userEvent.setup()

      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-webhook"
          onClick={() => {
            onSubmit({
              name: 'My Webhook',
              triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER,
              webhookPath: 'github-push',
              inputSchema: '{"type": "object"}',
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      const trigger = {
        id: 'wh-1',
        type: TriggerTypeEnum.WEBHOOK_TRIGGER,
        name: 'My Webhook',
        parameters: { webhook_path: 'old-path' },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      await user.click(screen.getByTestId('submit-webhook'))

      expect(mockUpdateTrigger).toHaveBeenCalledWith(0, {
        id: 'wh-1',
        type: TriggerTypeEnum.WEBHOOK_TRIGGER,
        name: 'My Webhook',
        parameters: {
          webhook_path: 'github-push',
          input_schema: { type: 'object' },
        },
      })
      expect(mockOnClose).toHaveBeenCalledTimes(1)

      formSpy.mockRestore()
    })

    it('shows error when webhook path is missing on submit', async () => {
      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-no-path"
          onClick={() => {
            onSubmit({
              name: 'Test',
              triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER,
              webhookPath: '',
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      const trigger = {
        id: 'wh-2',
        type: TriggerTypeEnum.WEBHOOK_TRIGGER,
        name: 'Test',
        parameters: { webhook_path: 'old' },
      }

      const user = userEvent.setup()
      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      await user.click(screen.getByRole('button', { name: 'Submit' }))

      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Update failed',
        description: 'Webhook path is required and must be a valid slug',
      })
      expect(mockOnClose).not.toHaveBeenCalled()

      formSpy.mockRestore()
    })

    it('loads webhook trigger with authorizedServiceAccountIds', () => {
      const trigger = {
        id: 'wh-auth',
        type: TriggerTypeEnum.WEBHOOK_TRIGGER,
        name: 'Auth Webhook',
        parameters: {
          webhook_path: 'auth-path',
          authorized_service_account_ids: ['sa-1', 'sa-2'],
        },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      const initialDataText = screen.getByTestId('initial-data').textContent ?? '{}'
      expect(initialDataText).toContain('"authorizedServiceAccountIds"')
      expect(initialDataText).toContain('sa-1')
      expect(initialDataText).toContain('sa-2')
    })

    it('submits webhook trigger with authorizedServiceAccountIds', async () => {
      const user = userEvent.setup()
      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-webhook-auth"
          onClick={() => {
            onSubmit({
              name: 'Auth Webhook',
              triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER,
              webhookPath: 'auth-path',
              authorizedServiceAccountIds: ['sa-1'],
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      const trigger = {
        id: 'wh-auth',
        type: TriggerTypeEnum.WEBHOOK_TRIGGER,
        name: 'Auth Webhook',
        parameters: { webhook_path: 'old-path' },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)
      await user.click(screen.getByTestId('submit-webhook-auth'))

      expect(mockUpdateTrigger).toHaveBeenCalledWith(0, {
        id: 'wh-auth',
        type: TriggerTypeEnum.WEBHOOK_TRIGGER,
        name: 'Auth Webhook',
        parameters: {
          webhook_path: 'auth-path',
          authorized_service_account_ids: ['sa-1'],
        },
      })

      formSpy.mockRestore()
    })

    it('shows error for invalid input schema on webhook submit', async () => {
      const user = userEvent.setup()
      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-bad-json"
          onClick={() => {
            onSubmit({
              name: 'Test',
              triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER,
              webhookPath: 'valid-path',
              inputSchema: 'not json at all { broken',
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      const trigger = {
        id: 'wh-bad',
        type: TriggerTypeEnum.WEBHOOK_TRIGGER,
        name: 'Test',
        parameters: { webhook_path: 'old' },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)
      await user.click(screen.getByTestId('submit-bad-json'))

      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Update failed',
        description: expectStringContaining('Invalid JSON schema'),
      })

      formSpy.mockRestore()
    })

    it('loads webhook trigger without input_schema gracefully', () => {
      const trigger = {
        id: 'wh-3',
        type: TriggerTypeEnum.WEBHOOK_TRIGGER,
        name: 'Simple Webhook',
        parameters: {
          webhook_path: 'simple',
        },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      const initialDataText = screen.getByTestId('initial-data').textContent ?? '{}'
      expect(initialDataText).toContain('"triggerType":"webhook_trigger"')
      expect(initialDataText).toContain('"webhookPath":"simple"')
      // inputSchema is undefined when no input_schema in config, so it's omitted from JSON serialization
      expect(initialDataText).not.toContain('"inputSchema"')
    })

    it('has no accessibility violations', async () => {
      const trigger = {
        id: 'wh-4',
        type: TriggerTypeEnum.WEBHOOK_TRIGGER,
        name: 'Accessible Webhook',
        parameters: { webhook_path: 'test-path' },
      }

      const { container } = render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('EDA Trigger', () => {
    it('renders TriggerNodeForm with EDA trigger data', () => {
      const trigger = {
        id: 'eda-1',
        type: TriggerTypeEnum.EDA_TRIGGER,
        name: 'My EDA Trigger',
        parameters: {
          webhook_path: 'eda-events',
          input_schema: { type: 'object', properties: { event: { type: 'string' } } },
        },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      expect(screen.getByTestId('trigger-node-form')).toBeInTheDocument()
      const initialDataText = screen.getByTestId('initial-data').textContent ?? '{}'
      expect(initialDataText).toContain('"triggerType":"eda_trigger"')
      expect(initialDataText).toContain('"webhookPath":"eda-events"')
      expect(initialDataText).toContain('inputSchema')
    })

    it('calls updateTrigger with EDA trigger on form submission', async () => {
      const user = userEvent.setup()
      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-eda"
          onClick={() => {
            onSubmit({
              name: 'My EDA Trigger',
              triggerType: TriggerTypeEnum.EDA_TRIGGER,
              webhookPath: 'github-events',
              inputSchema: '{"type": "object"}',
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      const trigger = {
        id: 'eda-1',
        type: TriggerTypeEnum.EDA_TRIGGER,
        name: 'My EDA Trigger',
        parameters: { webhook_path: 'old-path' },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)
      await user.click(screen.getByTestId('submit-eda'))

      expect(mockUpdateTrigger).toHaveBeenCalledWith(0, {
        id: 'eda-1',
        type: TriggerTypeEnum.EDA_TRIGGER,
        name: 'My EDA Trigger',
        parameters: {
          webhook_path: 'github-events',
          input_schema: { type: 'object' },
        },
      })
      expect(mockOnClose).toHaveBeenCalledTimes(1)
      formSpy.mockRestore()
    })

    it('shows error when webhook path is missing on submit', async () => {
      const formSpy = vi.spyOn(TriggerNodeFormModule, 'TriggerNodeForm')
      formSpy.mockImplementation(({ onSubmit }) => (
        <button
          data-testid="submit-no-path"
          onClick={() => {
            onSubmit({
              name: 'Test',
              triggerType: TriggerTypeEnum.EDA_TRIGGER,
              webhookPath: '',
            })
          }}
          type="button"
        >
          Submit
        </button>
      ))

      const trigger = {
        id: 'eda-2',
        type: TriggerTypeEnum.EDA_TRIGGER,
        name: 'Test',
        parameters: { webhook_path: 'old' },
      }

      const user = userEvent.setup()
      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)
      await user.click(screen.getByRole('button', { name: 'Submit' }))

      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Update failed',
        description: 'Webhook path is required and must be a valid slug',
      })
      expect(mockOnClose).not.toHaveBeenCalled()
      formSpy.mockRestore()
    })

    it('loads EDA trigger without input_schema gracefully', () => {
      const trigger = {
        id: 'eda-3',
        type: TriggerTypeEnum.EDA_TRIGGER,
        name: 'Simple EDA',
        parameters: {
          webhook_path: 'simple',
        },
      }

      render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)

      const initialDataText = screen.getByTestId('initial-data').textContent ?? '{}'
      expect(initialDataText).toContain('"triggerType":"eda_trigger"')
      expect(initialDataText).toContain('"webhookPath":"simple"')
      expect(initialDataText).not.toContain('"inputSchema"')
    })

    it('has no accessibility violations', async () => {
      const trigger = {
        id: 'eda-4',
        type: TriggerTypeEnum.EDA_TRIGGER,
        name: 'Accessible EDA',
        parameters: { webhook_path: 'test-path' },
      }

      const { container } = render(<TriggerNodeDetails trigger={trigger} triggerIndex={0} onClose={mockOnClose} />)
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
