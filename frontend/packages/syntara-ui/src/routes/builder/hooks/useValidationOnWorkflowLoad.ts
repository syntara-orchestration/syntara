import type { WorkflowAPI } from '@syntara/contracts'
import { useEffect, useRef } from 'react'

type WorkflowWithVersion = WorkflowAPI.components['schemas']['WorkflowReadWithVersion']

/**
 * Re-runs backend verification when a workflow is opened with `has_validation_issues`
 * so the banner reflects the current definition (see verify-test-workflow.md).
 */
export function useValidationOnWorkflowLoad(options: {
  isNew: boolean
  workflow: WorkflowWithVersion | undefined
  storeReady: boolean
  handleVerifySilent: () => void
}): void {
  const { isNew, workflow, storeReady, handleVerifySilent } = options
  const refreshedKeyRef = useRef<string | null>(null)

  useEffect(() => {
    if (isNew || !workflow?.id || !storeReady) return

    const version = workflow.current_version ?? workflow.version?.version
    const key = `${workflow.id}:${String(version ?? 'unknown')}`

    if (workflow.has_validation_issues !== true) {
      refreshedKeyRef.current = key
      return
    }

    if (refreshedKeyRef.current === key) return
    refreshedKeyRef.current = key
    handleVerifySilent()
  }, [
    isNew,
    workflow?.id,
    workflow?.current_version,
    workflow?.version?.version,
    workflow?.has_validation_issues,
    storeReady,
    handleVerifySilent,
  ])
}
