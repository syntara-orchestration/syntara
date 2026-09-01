import { useMemo } from 'react'

import { userReferenceName } from '../../../utils/userReference'
import type { WorkflowMetadata } from '../types/workflowMetadata'

type WorkflowLike = {
  name?: string
  id?: string
  current_version?: number
  version?: { version?: number }
  published_version_id?: string | null
  created_by?: unknown
}

export function useWorkflowMetadata(workflow: WorkflowLike | undefined): WorkflowMetadata | undefined {
  return useMemo(() => {
    if (!workflow?.name && !workflow?.id) return undefined
    return {
      name: workflow.name ?? '',
      id: workflow.id ?? '',
      version: workflow.current_version ?? workflow.version?.version ?? 0,
      published: workflow.published_version_id != null,
      author: userReferenceName(workflow.created_by) ?? 'Unknown',
    }
  }, [workflow])
}
