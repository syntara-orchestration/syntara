import { useMemo } from 'react'

import { useExecutionStore } from '../../workflows/stores/useExecutionStore'
import { resolveExecutionStatus } from '../builderFlowConfig'
import { useIsExecutionView } from '../ExecutionViewContext'

const TERMINAL_EXECUTION_STATUSES = new Set(['completed', 'completed_with_errors', 'failed', 'cancelled'])

type UseBuilderFlowExecutionContextParams = {
  executionStatus?: string | null
  readOnlyProp?: boolean
  canEdit: boolean
}

export function useBuilderFlowExecutionContext({
  executionStatus,
  readOnlyProp,
  canEdit,
}: UseBuilderFlowExecutionContextParams) {
  const isExecutionView = useIsExecutionView()
  const executionMetadata = useExecutionStore((state) => state.executionMetadata)
  const preResolvedNodes = useMemo(
    () => new Set(Object.keys(executionMetadata?.pre_resolved_nodes ?? {})),
    [executionMetadata]
  )
  const storeExecutionStatus = useExecutionStore((state) => state.visualization?.status)
  const effectiveExecutionStatus = resolveExecutionStatus(executionStatus, storeExecutionStatus)
  const isActiveExecution =
    effectiveExecutionStatus !== null && !TERMINAL_EXECUTION_STATUSES.has(effectiveExecutionStatus)
  const isReadOnly = isExecutionView || isActiveExecution || readOnlyProp || !canEdit
  const buttonEdgeExecutionStatus = isActiveExecution ? effectiveExecutionStatus : null

  return {
    isExecutionView,
    effectiveExecutionStatus,
    isActiveExecution,
    isReadOnly,
    buttonEdgeExecutionStatus,
    preResolvedNodes,
  }
}
