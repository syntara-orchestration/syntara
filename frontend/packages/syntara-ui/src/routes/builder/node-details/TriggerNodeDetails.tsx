import {
  type MissedSchedulePolicy,
  type ScheduleType,
  ScheduleTypeEnum,
  TriggerTypeEnum,
  WEBHOOK_TRIGGER_TYPES,
} from '@syntara/contracts'
import { useMemo, type ReactNode } from 'react'

import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStoreActions } from '../../../stores/useWorkflowStore'
import type { Trigger } from '../../../stores/workflowStoreTypes'
import { parseJsonSchema } from '../../../utils/jsonSafeParse'
import { isValidWebhookPath, normalizeWebhookPath } from '../../../utils/webhookPath'
import type { TriggerFormData } from '../node-forms/TriggerNodeForm'
import { TriggerNodeForm } from '../node-forms/TriggerNodeForm'

/**
 * Deep equality check for triggers to prevent marking workflow dirty when no changes are made.
 */
function triggersEqual(a: Trigger, b: Trigger): boolean {
  if (a.id !== b.id) return false
  if (a.type !== b.type) return false
  if (a.name !== b.name) return false

  // Deep compare parameters objects
  const aParams = a.parameters ?? {}
  const bParams = b.parameters ?? {}
  const aKeys = Object.keys(aParams).sort((a, b) => a.localeCompare(b))
  const bKeys = Object.keys(bParams).sort((a, b) => a.localeCompare(b))

  if (aKeys.length !== bKeys.length) return false
  if (!aKeys.every((key, i) => key === bKeys[i])) return false

  // Compare parameters values - handle nested objects (like input_schema)
  return aKeys.every((key) => {
    const aVal = aParams[key]
    const bVal = bParams[key]
    if (aVal === bVal) return true
    if (typeof aVal !== typeof bVal) return false
    if (typeof aVal === 'object' && aVal !== null && bVal !== null) {
      return JSON.stringify(aVal) === JSON.stringify(bVal)
    }
    return false
  })
}

/**
 * SECURITY: Validate ISO 8601 duration/recurring interval format.
 * Prevents injection of malformed values that could cause backend errors.
 *
 * Accepts:
 * - Simple durations: PT1H, P1D
 * - Compound durations: P1DT12H30M, PT1H30M45S
 * - Recurring intervals: R/2024-01-01T00:00:00Z/P1D, R5/2024-01-01T00:00:00Z/PT1H
 *
 * Rejects:
 * - Empty durations: P, PT
 * - Malformed recurring: R/2024-01-01T00:00:00Z/Pgarbage
 * - Non-ISO format: "every day", "1 hour"
 */
const DATETIME_PATTERN = /^\d{4}-\d{2}-\d{2}T.+$/

const ISO8601_DURATION_DIGITS = String.raw`\d+`
const iso8601OptionalDurationUnit = (unit: string) => `(${ISO8601_DURATION_DIGITS}${unit})?`
const ISO8601_DURATION_PATTERN = new RegExp(
  `^P${iso8601OptionalDurationUnit('Y')}${iso8601OptionalDurationUnit('M')}${iso8601OptionalDurationUnit('W')}${iso8601OptionalDurationUnit('D')}` +
    `(T${iso8601OptionalDurationUnit('H')}${iso8601OptionalDurationUnit('M')}(${ISO8601_DURATION_DIGITS}(\\.\\d+)?S)?)?$`
)

function hasReasonableValues(str: string): boolean {
  const numbers = str.match(/\d+/g) ?? []
  return numbers.every((n) => n.length <= 4)
}

function validateRecurringInterval(interval: string): boolean {
  const parts = interval.split('/')
  if (parts.length < 3 || parts.length > 4) return false
  const [count, startDate, duration, endDate] = parts
  if (!count.startsWith('R')) return false
  if (!DATETIME_PATTERN.test(startDate)) return false
  if (!duration.startsWith('P')) return false
  if (!hasReasonableValues(count)) return false
  if (endDate && !DATETIME_PATTERN.test(endDate)) return false
  return validateISO8601Interval(duration)
}

function validateISO8601Interval(interval: string): boolean {
  if (interval.startsWith('R')) {
    return validateRecurringInterval(interval)
  }

  if (!ISO8601_DURATION_PATTERN.test(interval)) return false

  // Must have at least one component (not just P or PT)
  if (interval === 'P' || interval === 'PT') return false

  // SECURITY: Validate reasonable numeric values (max 8 digits per component)
  if (!hasReasonableValues(interval)) return false

  return true
}

function serializeInputSchema(rawSchema: unknown): string | undefined {
  if (typeof rawSchema === 'string') return rawSchema
  if (rawSchema && typeof rawSchema === 'object') return JSON.stringify(rawSchema, null, 2)
  return undefined
}

function buildScheduledTrigger(data: TriggerFormData, triggerId: string, name: string): Trigger {
  const scheduleType = (data.scheduleType ?? ScheduleTypeEnum.INTERVAL) as ScheduleType
  const scheduleValueMap: Record<string, string | undefined> = { interval: data.interval, cron: data.cron }
  const scheduleValue = scheduleValueMap[scheduleType]

  if (scheduleType === ScheduleTypeEnum.INTERVAL && scheduleValue && !validateISO8601Interval(scheduleValue)) {
    throw new Error(
      `Invalid interval format: "${scheduleValue}". Expected ISO 8601 duration (e.g., PT1H, P1DT12H, PT1H30M) or recurring interval (e.g., R/2024-01-01T10:00:00Z/P1D).`
    )
  }

  return {
    id: triggerId,
    type: TriggerTypeEnum.SCHEDULED,
    name: name ?? 'Scheduled Trigger',
    parameters: {
      schedule_type: scheduleType,
      ...(scheduleValue && { [scheduleType]: scheduleValue }),
      ...(data.timezone && { timezone: data.timezone }),
      ...(data.missedSchedulePolicy && { missed_schedule_policy: data.missedSchedulePolicy }),
    },
  }
}

function buildWebhookStyleTrigger(
  data: TriggerFormData,
  triggerId: string,
  name: string,
  type: typeof TriggerTypeEnum.WEBHOOK_TRIGGER | typeof TriggerTypeEnum.EDA_TRIGGER
): Trigger {
  const webhookPath = normalizeWebhookPath(data.webhookPath ?? '')
  if (!webhookPath || !isValidWebhookPath(webhookPath)) {
    throw new Error('Webhook path is required and must be a valid slug')
  }
  const inputSchema = parseJsonSchema(data.inputSchema)
  if (data.inputSchema?.trim() && !inputSchema) {
    throw new Error('Invalid JSON schema — check syntax')
  }
  return {
    id: triggerId,
    type,
    name,
    parameters: {
      webhook_path: webhookPath,
      ...(inputSchema && { input_schema: inputSchema }),
      ...(data.authorizedServiceAccountIds?.length && {
        authorized_service_account_ids: data.authorizedServiceAccountIds,
      }),
    },
  }
}

function buildUpdatedTrigger(data: TriggerFormData, trigger: Trigger, name: string | undefined): Trigger {
  if (data.triggerType === TriggerTypeEnum.MANUAL_TRIGGER) {
    const inputSchema = parseJsonSchema(data.inputSchema)
    return {
      id: trigger.id ?? 'manual_trigger',
      type: TriggerTypeEnum.MANUAL_TRIGGER,
      name: name ?? 'Manual Trigger',
      parameters: {
        ...(inputSchema && { input_schema: inputSchema }),
      },
    }
  }
  if (data.triggerType === TriggerTypeEnum.SCHEDULED) {
    return buildScheduledTrigger(data, trigger.id ?? 'scheduled_trigger', name ?? 'Scheduled Trigger')
  }
  if (data.triggerType === TriggerTypeEnum.WEBHOOK_TRIGGER) {
    return buildWebhookStyleTrigger(
      data,
      trigger.id ?? 'webhook_trigger',
      name ?? 'Webhook Trigger',
      TriggerTypeEnum.WEBHOOK_TRIGGER
    )
  }
  if (data.triggerType === TriggerTypeEnum.EDA_TRIGGER) {
    return buildWebhookStyleTrigger(
      data,
      trigger.id ?? 'eda_trigger',
      name ?? 'EDA Trigger',
      TriggerTypeEnum.EDA_TRIGGER
    )
  }
  throw new Error('Invalid trigger type')
}

type TriggerNodeDetailsProps = Readonly<{
  trigger: Trigger
  triggerIndex: number
  onClose: () => void
  onHeaderContentChange?: (content: ReactNode | null) => void
}>

export function TriggerNodeDetails({ trigger, triggerIndex, onClose, onHeaderContentChange }: TriggerNodeDetailsProps) {
  const { showError } = useAlerts()
  // Use action accessor - component won't re-render when store state changes
  const { updateTrigger } = useWorkflowStoreActions()

  // Extract initial data from trigger — memoized to avoid new object refs on re-render
  const initialData = useMemo((): TriggerFormData => {
    if (trigger.type === TriggerTypeEnum.MANUAL_TRIGGER) {
      return {
        name: trigger.name,
        triggerType: TriggerTypeEnum.MANUAL_TRIGGER,
        inputSchema: serializeInputSchema(trigger.parameters?.input_schema),
      }
    }

    if (trigger.type === TriggerTypeEnum.SCHEDULED) {
      const scheduleType = (trigger.parameters?.schedule_type as string) ?? ScheduleTypeEnum.INTERVAL
      const timezone = trigger.parameters?.timezone as string | undefined
      const missedSchedulePolicy = trigger.parameters?.missed_schedule_policy as MissedSchedulePolicy | undefined

      if (scheduleType === ScheduleTypeEnum.INTERVAL) {
        return {
          name: trigger.name,
          triggerType: TriggerTypeEnum.SCHEDULED,
          scheduleType: ScheduleTypeEnum.INTERVAL,
          interval: trigger.parameters?.interval as string | undefined,
          timezone,
          missedSchedulePolicy,
        }
      }

      if (scheduleType === ScheduleTypeEnum.CRON) {
        return {
          name: trigger.name,
          triggerType: TriggerTypeEnum.SCHEDULED,
          scheduleType: ScheduleTypeEnum.CRON,
          cron: trigger.parameters?.cron as string | undefined,
          timezone,
          missedSchedulePolicy,
        }
      }
    }

    if (WEBHOOK_TRIGGER_TYPES.has(trigger.type)) {
      return {
        name: trigger.name,
        triggerType: trigger.type,
        webhookPath: (trigger.parameters?.webhook_path as string) ?? '',
        inputSchema: serializeInputSchema(trigger.parameters?.input_schema),
        authorizedServiceAccountIds: (trigger.parameters?.authorized_service_account_ids as string[] | undefined) ?? [],
      }
    }

    // Default fallback
    return {
      name: trigger.name,
      triggerType: TriggerTypeEnum.MANUAL_TRIGGER,
    }
  }, [trigger])

  const handleSubmit = (data: TriggerFormData) => {
    try {
      const name = data.name?.trim() || trigger.name
      const updatedTrigger = buildUpdatedTrigger(data, trigger, name)

      // Only update if the trigger actually changed
      if (!triggersEqual(trigger, updatedTrigger)) {
        updateTrigger(triggerIndex, updatedTrigger)
      }
      onClose()
    } catch (error) {
      showError({
        title: 'Update failed',
        description: error instanceof Error ? error.message : 'Failed to update trigger',
      })
    }
  }

  return (
    <TriggerNodeForm initialData={initialData} onSubmit={handleSubmit} onHeaderContentChange={onHeaderContentChange} />
  )
}
