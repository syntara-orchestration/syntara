import type { WorkflowAPI } from '@syntara/contracts'
import type { Query, QueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'

import type { AlertMessage } from '../../../providers/alerts'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'
import { extractVersionConflictInfo, getErrorMessage, isWorkflowVersionConflictError } from '../../../utils/apiErrors'
import type { ValidationError } from '../builderReducer'
import { extractValidationErrors, extractValidationErrorsFromUnknown } from '../useWorkflowVerification'
import { buildWorkflowDefinition } from '../utils/workflowDefinitionBuilder'
import { DEFAULT_WORKFLOW_NAME, getNextDefaultWorkflowName } from '../utils/workflowNaming'
import type { ConflictInfo } from '../VersionConflictDialog'

type CleanedNode = { id: string; parameters?: Record<string, unknown> }

function getCleanedNodes(data: SaveResponseData | undefined): CleanedNode[] | undefined {
  if (!data || !('version' in data) || !data.version?.workflow_definition) return undefined
  const nodes = data.version.workflow_definition.nodes as CleanedNode[] | undefined
  return nodes
}

function syncToolSelectionsFromResponse(responseData: SaveResponseData | undefined): void {
  const cleanedNodes = getCleanedNodes(responseData)
  if (!cleanedNodes) return

  const store = useWorkflowStore.getState()
  const activities = store.currentWorkflow?.workflow.activities
  if (!activities) return

  let updated = false
  for (const activity of activities) {
    const activityParams = (activity as { parameters?: Record<string, unknown> }).parameters
    if (!activityParams || !('tool_selections' in activityParams)) continue

    const node = cleanedNodes.find((n) => n.id === activity.id)
    if (!node?.parameters) continue

    const nodeToolSelections = node.parameters.tool_selections as string[] | undefined
    const nodeStrategy = node.parameters.tool_selection_strategy as string | undefined

    if (
      JSON.stringify(activityParams.tool_selections) !== JSON.stringify(nodeToolSelections) ||
      activityParams.tool_selection_strategy !== nodeStrategy
    ) {
      const newParams: Record<string, unknown> = { ...activityParams, tool_selection_strategy: nodeStrategy }
      if (nodeToolSelections !== undefined) {
        newParams.tool_selections = nodeToolSelections
      } else {
        delete newParams.tool_selections
      }
      store.updateActivity(activity.id, { parameters: newParams } as Partial<typeof activity>)
      updated = true
    }
  }
  if (updated) store.markClean()
}

function formatSaveFailureDescription(error: unknown, action: string): string {
  const findings = extractValidationErrorsFromUnknown(error)
  if (findings && findings.length > 0) {
    const findingText = findings.map((f) => f.message).join('\n• ')
    return `Failed to ${action} workflow:\n• ${findingText}`
  }
  return `Failed to ${action} workflow: ${getErrorMessage(error)}`
}

function reportSaveError(
  error: unknown,
  action: 'update' | 'create',
  showError: (options: AlertMessage) => void,
  onValidationFindings?: (errors: ValidationError[]) => void
): void {
  const findings = extractValidationErrorsFromUnknown(error)
  showError({
    title: `Failed to ${action} workflow`,
    description: formatSaveFailureDescription(error, action),
  })
  if (findings && findings.length > 0) {
    onValidationFindings?.(findings)
  }
}

function buildSavePayloads(opts: {
  nameToSave: string
  workflowDescription: string
  workflowDef: Record<string, unknown>
  selectedProjectId: string
  expectedVersion: number | null | undefined
}) {
  const { nameToSave, workflowDescription, workflowDef, selectedProjectId, expectedVersion } = opts
  const createPayload: CreateWorkflowBodyExtended = {
    name: nameToSave,
    description: workflowDescription,
    workflow_definition: workflowDef as unknown as CreateWorkflowBody['workflow_definition'],
    project_id: selectedProjectId,
  }
  const patchPayload: PatchWorkflowBody = {
    name: nameToSave,
    description: workflowDescription,
    workflow_definition: workflowDef as unknown as PatchWorkflowBody['workflow_definition'],
    ...(expectedVersion != null ? { expected_version: expectedVersion } : {}),
  }
  return { createPayload, patchPayload }
}

type WorkflowCreateResponse = WorkflowAPI.components['schemas']['WorkflowRead']
type WorkflowUpdateResponse = WorkflowAPI.components['schemas']['WorkflowReadWithVersion']
type SaveResponseData = WorkflowCreateResponse | WorkflowUpdateResponse

function reportSaveValidationIssues(
  data: SaveResponseData | undefined,
  onValidationFindings?: (errors: ValidationError[]) => void,
  onSaveWithValidationIssues?: () => void
): void {
  const inlineFindings = extractValidationErrors({
    validation_result: data?.validation_result as Record<string, unknown> | undefined,
  })
  if (inlineFindings && inlineFindings.length > 0) {
    onValidationFindings?.(inlineFindings)
    return
  }
  onSaveWithValidationIssues?.()
}

type CreateWorkflowBody = WorkflowAPI.paths['/workflows']['post']['requestBody']['content']['application/json']
/**
 * Create payload extensions the backend accepts; OpenAPI `CreateWorkflowRequest` may omit fields.
 * Keep create as one round-trip (labels + project) — avoid POST-then-PATCH partial failure.
 */
type CreateWorkflowBodyExtended = CreateWorkflowBody & {
  labels?: Record<string, string>
}
type PatchWorkflowBody =
  WorkflowAPI.paths['/workflows/{workflow_id}']['patch']['requestBody']['content']['application/json']

function isWorkflowQuery(query: Query): boolean {
  return (
    query.queryKey[0] === 'get' && typeof query.queryKey[1] === 'string' && query.queryKey[1].startsWith('/workflows')
  )
}

export type UseBuilderSaveWorkflowParams = {
  currentWorkflow: WorkflowDefinition | null
  workflowName: string
  workflowDescription: string
  workflowId: string | null
  isNew: boolean
  /** When creating a workflow, scopes the resource to this project (access control). */
  selectedProject: { id: string } | null
  workflowsListResources: { name: string }[] | undefined
  queryClient: QueryClient
  setLocation: (to: string) => void
  showSuccess: (options: AlertMessage) => void
  showWarning: (options: AlertMessage) => void
  showError: (options: AlertMessage) => void
  /** Called when saving on create path without a project (UI can highlight the project selector). */
  onMissingProjectForCreate?: () => void
  markClean: () => void
  expectedVersion: number | null
  onConflict?: (info: ConflictInfo) => void
  onVersionUpdated?: (newVersion: number) => void
  /** Called after a successful save when the response indicates validation issues. */
  onSaveWithValidationIssues?: () => void
  /**
   * Called when the API returns structured validation findings — either inline on a
   * successful save (`validation_result`) or on a validation problem error body.
   * Used to populate the validation banner with node-level messages.
   */
  onValidationFindings?: (errors: ValidationError[]) => void
  createWorkflow: (
    args: { body: CreateWorkflowBodyExtended },
    opts?: {
      onSuccess?: (data: WorkflowCreateResponse) => void | Promise<void>
      onError?: (error: unknown) => void
    }
  ) => void
  updateWorkflow: (
    args: {
      params: { path: { workflow_id: string } }
      body: PatchWorkflowBody
    },
    opts?: {
      onSuccess?: (data: WorkflowUpdateResponse) => void | Promise<void>
      onError?: (error: unknown) => void
    }
  ) => void
}

function promisifyCreate(
  createWorkflow: UseBuilderSaveWorkflowParams['createWorkflow'],
  payload: CreateWorkflowBodyExtended
): Promise<{ data?: WorkflowCreateResponse; error?: unknown }> {
  return new Promise((resolve) => {
    createWorkflow(
      { body: payload },
      {
        onSuccess: (data) => resolve({ data }),
        onError: (error) => resolve({ error }),
      }
    )
  })
}

function promisifyUpdate(
  updateWorkflow: UseBuilderSaveWorkflowParams['updateWorkflow'],
  workflowId: string,
  payload: PatchWorkflowBody
): Promise<{ data?: WorkflowUpdateResponse; error?: unknown }> {
  return new Promise((resolve) => {
    updateWorkflow(
      { params: { path: { workflow_id: workflowId } }, body: payload },
      {
        onSuccess: (data) => resolve({ data }),
        onError: (error) => resolve({ error }),
      }
    )
  })
}

async function completeSave(
  queryClient: QueryClient,
  markClean: () => void,
  navigateToId: string | undefined,
  setLocation: (to: string) => void
): Promise<void> {
  markClean()
  await queryClient.invalidateQueries({ predicate: isWorkflowQuery })
  if (navigateToId) {
    setLocation(`/workflow-builder/${navigateToId}`)
  }
}

async function processSaveResult(
  saveResult: { data?: SaveResponseData; error?: unknown },
  ctx: {
    willPatchExisting: boolean
    isNew: boolean
    nameToSave: string
    showError: (options: AlertMessage) => void
    showSuccess: (options: AlertMessage) => void
    showWarning: (options: AlertMessage) => void
    markClean: () => void
    queryClient: QueryClient
    setLocation: (to: string) => void
    onVersionUpdated?: (newVersion: number) => void
    onSaveWithValidationIssues?: () => void
    onValidationFindings?: (errors: ValidationError[]) => void
    blockOnWarnings?: boolean
  }
): Promise<boolean> {
  if (saveResult.error) {
    reportSaveError(
      saveResult.error,
      ctx.willPatchExisting ? 'update' : 'create',
      ctx.showError,
      ctx.onValidationFindings
    )
    return false
  }

  const hasIssues = saveResult.data?.has_validation_issues === true
  const verb = ctx.isNew ? 'created' : 'saved'
  if (hasIssues) {
    ctx.showWarning({ title: `Workflow ${verb} with warnings`, description: `${ctx.nameToSave} has been saved.` })
    reportSaveValidationIssues(saveResult.data, ctx.onValidationFindings, ctx.onSaveWithValidationIssues)
    syncToolSelectionsFromResponse(saveResult.data)
  } else {
    ctx.showSuccess({ title: `Workflow ${verb}`, description: `${ctx.nameToSave} has been saved.` })
  }

  await completeSave(ctx.queryClient, ctx.markClean, ctx.isNew ? saveResult.data?.id : undefined, ctx.setLocation)
  const newVersion = saveResult.data?.current_version
  if (ctx.willPatchExisting && newVersion != null) ctx.onVersionUpdated?.(newVersion)
  if (!hasIssues) ctx.onValidationFindings?.([])
  if (hasIssues && ctx.blockOnWarnings) return false
  return true
}

export function useBuilderSaveWorkflow(
  params: UseBuilderSaveWorkflowParams
): (options?: { expectedVersionOverride?: number; blockOnWarnings?: boolean }) => Promise<boolean> {
  const {
    currentWorkflow,
    workflowName,
    workflowDescription,
    workflowId,
    isNew,
    selectedProject,
    workflowsListResources,
    queryClient,
    setLocation,
    showSuccess,
    showWarning,
    showError,
    onMissingProjectForCreate,
    markClean,
    expectedVersion,
    onConflict,
    onVersionUpdated,
    onSaveWithValidationIssues,
    onValidationFindings,
    createWorkflow,
    updateWorkflow,
  } = params

  const getWorkflowDefinition = useCallback(() => {
    const { edges, nodePositions, currentWorkflow: freshWorkflow } = useWorkflowStore.getState()
    const activities = freshWorkflow?.workflow.activities ?? []
    const triggers = freshWorkflow?.triggers ?? []

    return buildWorkflowDefinition(workflowName, workflowDescription, activities, triggers, {
      edges,
      nodePositions,
    })
  }, [workflowName, workflowDescription])

  return useCallback(
    async (options?: { expectedVersionOverride?: number; blockOnWarnings?: boolean }): Promise<boolean> => {
      const effectiveExpectedVersion = options?.expectedVersionOverride ?? expectedVersion
      const willPatchExisting = Boolean(workflowId && !isNew)
      if (!currentWorkflow) {
        showError({ title: 'Failed to save workflow', description: 'No workflow to save' })
        return false
      }
      if (!willPatchExisting && !selectedProject?.id) {
        showError({ title: 'Project required', description: 'Select a project to save this workflow.' })
        if (onMissingProjectForCreate) onMissingProjectForCreate()
        return false
      }

      const nameToSave =
        isNew && workflowName === DEFAULT_WORKFLOW_NAME && workflowsListResources
          ? getNextDefaultWorkflowName(workflowsListResources)
          : workflowName

      const workflowDef = getWorkflowDefinition()
      workflowDef.name = nameToSave
      const { createPayload, patchPayload } = buildSavePayloads({
        nameToSave,
        workflowDescription,
        workflowDef,
        selectedProjectId: selectedProject?.id ?? '',
        expectedVersion: effectiveExpectedVersion,
      })

      const saveResult = willPatchExisting
        ? // eslint-disable-next-line @typescript-eslint/no-non-null-assertion -- safe: willPatchExisting = Boolean(workflowId && !isNew) ensures workflowId is non-null when this branch executes
          await promisifyUpdate(updateWorkflow, workflowId!, patchPayload)
        : await promisifyCreate(createWorkflow, createPayload)

      // Check for version conflict
      if (saveResult.error && isWorkflowVersionConflictError(saveResult.error) && onConflict) {
        onConflict(extractVersionConflictInfo(saveResult.error))
        return false
      }

      return processSaveResult(saveResult, {
        willPatchExisting,
        isNew,
        nameToSave,
        showError,
        showSuccess,
        showWarning,
        markClean,
        queryClient,
        setLocation,
        onVersionUpdated,
        onSaveWithValidationIssues,
        onValidationFindings,
        blockOnWarnings: options?.blockOnWarnings,
      })
    },
    [
      currentWorkflow,
      workflowName,
      workflowDescription,
      getWorkflowDefinition,
      workflowId,
      isNew,
      selectedProject,
      workflowsListResources,
      updateWorkflow,
      createWorkflow,
      showSuccess,
      showWarning,
      showError,
      onMissingProjectForCreate,
      expectedVersion,
      onConflict,
      onVersionUpdated,
      onSaveWithValidationIssues,
      onValidationFindings,
      setLocation,
      queryClient,
      markClean,
    ]
  )
}
