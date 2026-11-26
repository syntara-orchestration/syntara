import type { WorkflowAPI } from '@syntara/contracts'

import type { ExecutionCopyData } from '../hooks/useExecutionCopyToEditor'

export type BuilderContentProps = Readonly<{
  workflow?: WorkflowAPI.components['schemas']['WorkflowReadWithVersion']
  isNew: boolean
  workflowId: string | null
  executionCopy?: ExecutionCopyData
  /** URL has fromExecution/linkExecution while execution payload may still be in flight. */
  pendingCopyNavigation?: boolean
  copyNavigationExecutionId?: string | null
  initialViewVersion?: number | null
}>
