import { ActivityTypeEnum, ScheduleTypeEnum, TriggerTypeEnum, type Activity } from '@syntara/contracts'
import { MarkerType } from '@xyflow/react'

import { formatScheduleSummary } from '../../../utils/triggerFormatting'
import { BUTTON_EDGE_DEFAULT_STROKE } from '../edges/buttonEdgeStrokeColor'

/**
 * In v2, triggers are { id, type, name, parameters } nodes.
 * Manual trigger type is 'manual_trigger'.
 */
export type Trigger = {
  id?: string
  type: string
  name?: string
  parameters?: Record<string, unknown>
}

export type TaskActivity = Activity

export const markerEnd = {
  type: MarkerType.ArrowClosed,
  width: 12,
  height: 12,
  color: BUTTON_EDGE_DEFAULT_STROKE,
}

export type EdgeType = {
  id: string
  type?: string
  source: string
  target: string
  sourceHandle?: string
  targetHandle?: string
  selectable?: boolean
  data?: {
    onAddNode?: (sourceNodeId: string, targetNodeId: string, edgeId: string) => void
    onButtonClick?: () => void
    isActive?: boolean
    isPending?: boolean
    executionStatus?: 'passed' | 'pending'
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    [key: string]: any
  }
  markerEnd?: typeof markerEnd
}

/**
 * Extracts all executor and approval activities from the flat activity list.
 * In v2, all activities are flat (no nested structures), so this just filters
 * by type. Also includes generic placeholder nodes (type: 'generic').
 */
export function extractTaskActivities(activities: Activity[]): Activity[] {
  const tasks: Activity[] = []
  for (const activity of activities) {
    // In v2, executor types are direct activity types
    // Also include 'generic' type for placeholder nodes (UI-only concept)
    if (
      activity.type === ActivityTypeEnum.SCRIPT ||
      activity.type === ActivityTypeEnum.HTTP_REQUEST ||
      activity.type === ActivityTypeEnum.AGENTIC ||
      activity.type === ActivityTypeEnum.AAP_JOB_TEMPLATE ||
      activity.type === ActivityTypeEnum.AAP_WORKFLOW_JOB_TEMPLATE ||
      activity.type === ActivityTypeEnum.APPROVAL ||
      activity.type === ActivityTypeEnum.INTERNAL_ACTIVITY ||
      activity.type === 'generic'
    ) {
      tasks.push(activity)
    }
  }
  return tasks
}

function getScheduledDetails(parameters: Record<string, unknown> | undefined): string {
  if (!parameters) return 'Scheduled'
  const scheduleType = parameters.schedule_type as string | undefined
  if (scheduleType === ScheduleTypeEnum.CRON) return `Cron: ${(parameters.cron as string) ?? ''}`
  if (scheduleType === ScheduleTypeEnum.INTERVAL) {
    const interval = (parameters.interval as string) ?? ''
    return formatScheduleSummary(interval) ?? `Interval: ${interval}`
  }
  return 'Scheduled'
}

function getWebhookStyleDetails(parameters: Record<string, unknown> | undefined, label: string): string {
  const path = (parameters?.webhook_path as string) ?? ''
  return path ? `${label}: /${path}` : label
}

/**
 * Extracts display name and details from a trigger based on its type and configuration.
 * Returns separate fields to avoid encoding issues with special characters in names.
 */
export function getTriggerDisplayData(trigger: Trigger): { name: string; details: string | null } {
  const name = trigger.name?.trim() || 'Trigger'
  let details: string | null = null

  switch (trigger.type) {
    case TriggerTypeEnum.MANUAL_TRIGGER:
      details = 'Manual'
      break
    case TriggerTypeEnum.SCHEDULED:
      details = getScheduledDetails(trigger.parameters)
      break
    case TriggerTypeEnum.EVENT:
      if (trigger.parameters) {
        const source = (trigger.parameters.source as string) ?? ''
        const eventType = (trigger.parameters.event_type as string) ?? ''
        details = `Event: ${source}/${eventType}`
      } else {
        details = 'Event'
      }
      break
    case TriggerTypeEnum.WEBHOOK_TRIGGER:
      details = getWebhookStyleDetails(trigger.parameters, 'Webhook')
      break
    case TriggerTypeEnum.EDA_TRIGGER:
      details = getWebhookStyleDetails(trigger.parameters, 'EDA')
      break
  }

  return { name, details }
}
