import type { WorkflowAPI } from '@syntara/contracts'

import { workflowFetchClient } from '../../client'
import { activitiesReferenceTrigger } from '../builder/utils/triggerReferenceCheck'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

type TriggerLike = {
  id?: string
  name?: string
  type?: string
  parameters?: {
    input_schema?: Record<string, unknown>
  }
}

export type WorkflowRunTrigger = {
  triggerNodeId: string
  triggerName: string
  triggerType?: string
  inputSchema?: Record<string, unknown>
  hasTriggerReferences: boolean
}

function isTriggerLike(value: unknown): value is TriggerLike {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function extractTriggers(definition: unknown): TriggerLike[] | undefined {
  if (!definition || typeof definition !== 'object') return undefined
  const triggers = (definition as { triggers?: unknown }).triggers
  if (!Array.isArray(triggers)) return undefined
  return triggers.filter(isTriggerLike)
}

type ActivityLike = { parameters?: Record<string, unknown> }

function extractActivities(definition: unknown): ActivityLike[] {
  if (!definition || typeof definition !== 'object') return []
  const nodes = (definition as { nodes?: unknown }).nodes
  if (!Array.isArray(nodes)) return []
  return nodes.filter((n): n is ActivityLike => typeof n === 'object' && n !== null)
}

function buildRunTrigger(trigger: TriggerLike, triggers: TriggerLike[], definition: unknown): WorkflowRunTrigger {
  const activities = extractActivities(definition)
  const triggerNodeIds = triggers.flatMap((t) => (t.id ? [t.id] : []))
  const inputSchema = trigger.parameters?.input_schema
  if (!trigger.id) {
    throw new Error('Trigger is missing id')
  }
  return {
    triggerNodeId: trigger.id,
    triggerName: trigger.name ?? 'Trigger',
    triggerType: trigger.type,
    inputSchema: inputSchema && typeof inputSchema === 'object' ? inputSchema : undefined,
    hasTriggerReferences: activitiesReferenceTrigger(activities, triggerNodeIds),
  }
}

/**
 * Resolve the first trigger from the workflow's published definition for a list-page run.
 * Prefers the published version when it differs from the current draft.
 */
export async function resolveWorkflowRunTrigger(workflow: Workflow): Promise<WorkflowRunTrigger | null> {
  if (!workflow.id) return null

  const { data: detail, error } = await workflowFetchClient.GET('/workflows/{workflow_id}', {
    params: { path: { workflow_id: workflow.id } },
  })
  if (error || !detail) return null

  const publishedVersionNumber = workflow.published_version_number ?? detail.published_version_number
  const currentVersionNumber = detail.current_version
  let definition = detail.version?.workflow_definition
  let triggers = extractTriggers(definition)

  if (
    publishedVersionNumber != null &&
    currentVersionNumber != null &&
    publishedVersionNumber !== currentVersionNumber
  ) {
    const { data: publishedVersion, error: versionError } = await workflowFetchClient.GET(
      '/workflows/{workflow_id}/versions/{version}',
      {
        params: { path: { workflow_id: workflow.id, version: publishedVersionNumber } },
      }
    )
    if (!versionError && publishedVersion) {
      definition = publishedVersion.workflow_definition ?? definition
      triggers = extractTriggers(definition) ?? triggers
    }
  }

  const trigger = triggers?.[0]
  if (!trigger?.id) return null

  return buildRunTrigger(trigger, triggers ?? [], definition)
}
