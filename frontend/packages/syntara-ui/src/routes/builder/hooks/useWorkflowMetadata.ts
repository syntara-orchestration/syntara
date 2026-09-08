import type { WorkflowAPI } from '@syntara/contracts'
import { useMemo } from 'react'

import type { WorkflowMetadata } from '../types/workflowMetadata'

type UserReference = WorkflowAPI.components['schemas']['UserReference']

type WorkflowLike = {
  name?: string
  id?: string
  current_version?: number
  version?: { version?: number }
  published_version_id?: string | null
  created_by?: unknown
}

function isUserReference(value: unknown): value is UserReference {
  if (typeof value !== 'object' || value === null) return false
  const { id, name } = value as { id?: unknown; name?: unknown }
  return typeof id === 'string' && typeof name === 'string'
}

function resolveAuthor(createdBy: unknown): string {
  if (typeof createdBy === 'string') return createdBy
  if (isUserReference(createdBy) && createdBy.name.length > 0) return createdBy.name
  return 'Unknown'
}

export function useWorkflowMetadata(workflow: WorkflowLike | undefined): WorkflowMetadata | undefined {
  return useMemo(() => {
    if (!workflow?.name && !workflow?.id) return undefined
    return {
      name: workflow.name ?? '',
      id: workflow.id ?? '',
      version: workflow.current_version ?? workflow.version?.version ?? 0,
      published: workflow.published_version_id != null,
      author: resolveAuthor(workflow.created_by),
    }
  }, [workflow])
}
