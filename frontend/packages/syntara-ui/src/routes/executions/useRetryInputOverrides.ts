import { useCallback, useMemo, useState } from 'react'

import { useCanI } from '../../hooks/useCanI'
import type { WorkflowDefShape } from '../builder/ExecutionDetailsPanel'

import {
  getRetryInputOverrideTargets,
  type ExecutionActivity,
  type RetryInputOverridesState,
} from './retryInputOverrides'

type UseRetryInputOverridesOptions = Readonly<{
  enabled: boolean
  executionProjectId?: string
  workflowDefinition?: WorkflowDefShape | null
  activityNameMap: ReadonlyMap<string, string>
  activities: ExecutionActivity[]
}>

export function useRetryInputOverrides({
  enabled,
  executionProjectId,
  workflowDefinition,
  activityNameMap,
  activities,
}: UseRetryInputOverridesOptions) {
  const [pointIds, setPointIds] = useState<string[]>([])
  const [savedOverrides, setSavedOverrides] = useState<Record<string, Record<string, unknown>>>({})
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [editingTargetIds, setEditingTargetIds] = useState<Set<string>>(new Set())
  const { allowed: canEdit } = useCanI('update', 'workflow', {
    resourceProject: executionProjectId,
    enabled: enabled && Boolean(executionProjectId),
  })

  const targets = useMemo(
    () => getRetryInputOverrideTargets(pointIds, workflowDefinition, activityNameMap, activities),
    [pointIds, workflowDefinition, activityNameMap, activities]
  )

  const onEdit = useCallback(
    (targetId: string) => {
      setDrafts((current) => ({ ...current, [targetId]: JSON.stringify(savedOverrides[targetId] ?? {}, null, 2) }))
      setErrors((current) => removeEntry(current, targetId))
      setEditingTargetIds((current) => new Set(current).add(targetId))
    },
    [savedOverrides]
  )

  const onCancel = useCallback((targetId: string) => {
    setDrafts((current) => removeEntry(current, targetId))
    setErrors((current) => removeEntry(current, targetId))
    setEditingTargetIds((current) => {
      const next = new Set(current)
      next.delete(targetId)
      return next
    })
  }, [])

  const onSave = useCallback(
    (targetId: string, overrides: Record<string, unknown> | undefined) => {
      setSavedOverrides((current) => {
        if (!overrides || Object.keys(overrides).length === 0) return removeEntry(current, targetId)
        return { ...current, [targetId]: overrides }
      })
      onCancel(targetId)
    },
    [onCancel]
  )

  const onDraftChange = useCallback(
    (targetId: string, value: string, _parsed: Record<string, unknown> | undefined, error: string | undefined) => {
      setDrafts((current) => ({ ...current, [targetId]: value }))
      setErrors((current) => (error ? { ...current, [targetId]: error } : removeEntry(current, targetId)))
    },
    []
  )

  const reset = useCallback(() => {
    setPointIds([])
    setSavedOverrides({})
    setDrafts({})
    setErrors({})
    setEditingTargetIds(new Set())
  }, [])

  const state: RetryInputOverridesState = {
    targets,
    canEdit,
    isDisabled: false,
    savedOverrides,
    drafts,
    errors,
    editingTargetIds,
    onEdit,
    onCancel,
    onSave,
    onDraftChange,
  }

  return {
    pointIds,
    setPointIds,
    savedOverrides,
    hasUnsavedInputOverrides: editingTargetIds.size > 0,
    state,
    reset,
  }
}

function removeEntry<T>(record: Readonly<Record<string, T>>, targetId: string): Record<string, T> {
  const next = { ...record }
  delete next[targetId]
  return next
}
