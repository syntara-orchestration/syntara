import { type Activity, TriggerTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { BUTTON_EDGE_DEFAULT_STROKE } from '../edges/buttonEdgeStrokeColor'

import type { Trigger } from './workflowToGraph'
import { extractTaskActivities, getTriggerDisplayData, markerEnd } from './workflowToGraph'

describe('workflowToGraph', () => {
  describe('markerEnd', () => {
    it('has expected marker configuration', () => {
      expect(markerEnd).toEqual({
        type: 'arrowclosed',
        width: 12,
        height: 12,
        color: BUTTON_EDGE_DEFAULT_STROKE,
      })
    })
  })

  describe('extractTaskActivities', () => {
    it('returns empty array for empty input', () => {
      expect(extractTaskActivities([])).toEqual([])
    })

    it('extracts script activities from flat array', () => {
      const activities: Activity[] = [
        { id: 'task-1', type: 'script', name: 'Task 1', parameters: { language: 'python', code: '' } },
        { id: 'task-2', type: 'script', name: 'Task 2', parameters: { language: 'python', code: '' } },
      ]
      const tasks = extractTaskActivities(activities)
      expect(tasks).toHaveLength(2)
      expect(tasks[0].id).toBe('task-1')
      expect(tasks[1].id).toBe('task-2')
    })

    it('includes executor and approval activities but skips control flow nodes', () => {
      const activities: Activity[] = [
        { id: 'task-1', type: 'script', name: 'Task 1', parameters: { language: 'python', code: '' } },
        { id: 'approval-1', type: 'approval', name: 'Approval', parameters: {} },
        { id: 'cond-1', type: 'condition', name: 'Condition', parameters: { condition: 'true' } },
        { id: 'loop-1', type: 'loop', name: 'Loop', parameters: { type: 'for_each', items: '${items}' } },
        { id: 'converge-1', type: 'converge', name: 'Converge', parameters: { strategy: 'all' } },
      ]
      const tasks = extractTaskActivities(activities)
      // Only script and approval are executor/approval types
      expect(tasks).toHaveLength(2)
      expect(tasks[0].id).toBe('task-1')
      expect(tasks[1].id).toBe('approval-1')
    })

    it('extracts http_request activities', () => {
      const activities: Activity[] = [
        {
          id: 'http-1',
          type: 'http_request',
          name: 'API Call',
          parameters: { method: 'GET', url: 'https://example.com' },
        },
      ]
      const tasks = extractTaskActivities(activities)
      expect(tasks).toHaveLength(1)
      expect(tasks[0].id).toBe('http-1')
    })

    it('extracts agentic activities', () => {
      const activities: Activity[] = [
        { id: 'agentic-1', type: 'agentic', name: 'Task Agent', parameters: { prompt: 'Do something' } },
      ]
      const tasks = extractTaskActivities(activities)
      expect(tasks).toHaveLength(1)
      expect(tasks[0].id).toBe('agentic-1')
    })

    it('extracts aap_job_template activities', () => {
      const activities: Activity[] = [
        { id: 'aap-1', type: 'aap_job_template', name: 'AAP Job', parameters: { job_template_id: 42 } },
      ]
      const tasks = extractTaskActivities(activities)
      expect(tasks).toHaveLength(1)
      expect(tasks[0].id).toBe('aap-1')
    })

    it('extracts terraform enterprise activities', () => {
      const activities: Activity[] = [
        { id: 'tfe-1', type: 'tfe_create_workspace', name: 'Create Workspace', parameters: { name: 'demo' } },
      ]
      const tasks = extractTaskActivities(activities)
      expect(tasks).toHaveLength(1)
      expect(tasks[0].id).toBe('tfe-1')
    })

    it('skips unknown activity types', () => {
      const activities = [{ id: 'unknown-1', type: 'unknown_type', name: 'Unknown', parameters: {} }] as Activity[]
      const tasks = extractTaskActivities(activities)
      expect(tasks).toHaveLength(0)
    })
  })

  describe('getTriggerDisplayData', () => {
    it('returns separate name and details for manual_trigger', () => {
      const trigger: Trigger = {
        type: TriggerTypeEnum.MANUAL_TRIGGER,
      }
      expect(getTriggerDisplayData(trigger)).toEqual({ name: 'Trigger', details: 'Manual' })
    })

    it('uses trigger name when provided', () => {
      const trigger: Trigger = {
        type: TriggerTypeEnum.MANUAL_TRIGGER,
        name: 'Start Workflow',
      }
      expect(getTriggerDisplayData(trigger)).toEqual({ name: 'Start Workflow', details: 'Manual' })
    })

    it('handles cron scheduled trigger', () => {
      const trigger: Trigger = {
        type: TriggerTypeEnum.SCHEDULED,
        parameters: {
          schedule_type: 'cron',
          cron: '0 9 * * *',
        },
      }
      expect(getTriggerDisplayData(trigger)).toEqual({ name: 'Trigger', details: 'Cron: 0 9 * * *' })
    })

    it('shows plain-language summary for ISO 8601 interval', () => {
      const trigger: Trigger = {
        type: TriggerTypeEnum.SCHEDULED,
        parameters: {
          schedule_type: 'interval',
          interval: 'R/2024-01-01T10:00:00Z/P1D',
        },
      }
      const result = getTriggerDisplayData(trigger)
      expect(result.name).toBe('Trigger')
      expect(result.details).toMatch(/^Daily at \d{1,2}:\d{2} [AP]M starting \w{3} \d{1,2}, 2024$/)
    })

    it('falls back to raw interval for non-ISO format', () => {
      const trigger: Trigger = {
        type: TriggerTypeEnum.SCHEDULED,
        parameters: {
          schedule_type: 'interval',
          interval: '1h',
        },
      }
      expect(getTriggerDisplayData(trigger)).toEqual({ name: 'Trigger', details: 'Interval: 1h' })
    })

    it('shows generic label for unknown schedule type', () => {
      const trigger: Trigger = {
        type: TriggerTypeEnum.SCHEDULED,
        parameters: {
          schedule_type: 'unknown',
        },
      }
      expect(getTriggerDisplayData(trigger)).toEqual({ name: 'Trigger', details: 'Scheduled' })
    })

    it('handles event trigger', () => {
      const trigger: Trigger = {
        type: 'event',
        parameters: {
          source: 'github',
          event_type: 'push',
        },
      }
      expect(getTriggerDisplayData(trigger)).toEqual({ name: 'Trigger', details: 'Event: github/push' })
    })

    it('handles event trigger with custom name', () => {
      const trigger: Trigger = {
        type: 'event',
        name: 'GitHub Push',
        parameters: {
          source: 'github',
          event_type: 'push',
        },
      }
      expect(getTriggerDisplayData(trigger)).toEqual({ name: 'GitHub Push', details: 'Event: github/push' })
    })

    it('returns just the name with null details for unknown trigger type', () => {
      const trigger = {
        type: 'unknown',
        name: 'Custom Trigger',
      } as Trigger
      expect(getTriggerDisplayData(trigger)).toEqual({ name: 'Custom Trigger', details: null })
    })

    it('trims whitespace from trigger name', () => {
      const trigger: Trigger = {
        type: TriggerTypeEnum.MANUAL_TRIGGER,
        name: '  Trimmed Name  ',
      }
      expect(getTriggerDisplayData(trigger)).toEqual({ name: 'Trimmed Name', details: 'Manual' })
    })

    it('falls back to "Trigger" when name is empty', () => {
      const trigger: Trigger = {
        type: TriggerTypeEnum.MANUAL_TRIGGER,
        name: '   ',
      }
      expect(getTriggerDisplayData(trigger)).toEqual({ name: 'Trigger', details: 'Manual' })
    })

    it('handles names with parentheses correctly', () => {
      const trigger: Trigger = {
        type: TriggerTypeEnum.MANUAL_TRIGGER,
        name: 'Hello(World)',
      }
      expect(getTriggerDisplayData(trigger)).toEqual({ name: 'Hello(World)', details: 'Manual' })
    })

    it('handles EDA trigger with webhook path', () => {
      const trigger: Trigger = {
        type: TriggerTypeEnum.EDA_TRIGGER,
        parameters: { webhook_path: 'my-events' },
      }
      expect(getTriggerDisplayData(trigger)).toEqual({ name: 'Trigger', details: 'EDA: /my-events' })
    })

    it('handles EDA trigger without webhook path', () => {
      const trigger: Trigger = {
        type: TriggerTypeEnum.EDA_TRIGGER,
        parameters: {},
      }
      expect(getTriggerDisplayData(trigger)).toEqual({ name: 'Trigger', details: 'EDA' })
    })

    it('handles EDA trigger with custom name', () => {
      const trigger: Trigger = {
        type: TriggerTypeEnum.EDA_TRIGGER,
        name: 'My EDA Trigger',
        parameters: { webhook_path: 'github-events' },
      }
      expect(getTriggerDisplayData(trigger)).toEqual({ name: 'My EDA Trigger', details: 'EDA: /github-events' })
    })
  })
})
