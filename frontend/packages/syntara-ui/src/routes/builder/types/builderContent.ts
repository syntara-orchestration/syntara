import type { WorkflowAPI } from '@syntara/contracts'

import type { ExecutionCopyData } from '../hooks/useExecutionCopyToEditor'

export type BuilderContentProps = Readonly<{
  workflow?: WorkflowAPI.components['schemas']['WorkflowReadWithVersion']
  isNew: boolean
  workflowId: string | null
  /** Project chosen in the new-workflow picker before the builder opened (R18). Ignored for existing workflows. */
  initialProjectId?: string
  executionCopy?: ExecutionCopyData
  initialViewVersion?: number | null
}>
