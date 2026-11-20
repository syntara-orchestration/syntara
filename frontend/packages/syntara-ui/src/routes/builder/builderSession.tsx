import { Content, ContentVariants } from '@patternfly/react-core'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { useNodesInitialized, useReactFlow } from '@xyflow/react'
import { useCallback, useEffect, useMemo, useReducer, useRef, useState, type Dispatch } from 'react'

import { useUnsavedChanges } from '../../app/useUnsavedChanges'
import { invalidateWorkflowQueries } from '../../hooks/invalidateWorkflowQueries'
import { useSearchParams } from '../../hooks/routing/useSearchParams'
import { useCursorPagination } from '../../hooks/useCursorPagination'
import { useProjectSelector } from '../../hooks/useProjectSelector'
import { useAlerts } from '../../providers/alerts'
import { useWorkflowStore } from '../../stores/useWorkflowStore'
import { detachPromise } from '../../utils/detachPromise'
import { transformExecutionStatusFilter } from '../executions/executionFilters'
import { getStepTypePermissionMessage, useStepTypePermissions } from '../workflows/useStepTypePermissions'

import styles from './BuilderContent.module.css'
import { builderReducer, getInitialBuilderState, type BuilderAction } from './builderReducer'
import { useBuilderContentQueries } from './hooks/useBuilderContentQueries'
import { useBuilderDerivedUiFlags } from './hooks/useBuilderDerivedUiFlags'
import { useBuilderWorkflowLifecycle } from './hooks/useBuilderWorkflowLifecycle'
import { useExecutionCopyToEditor } from './hooks/useExecutionCopyToEditor'
import { useUndoRedoKeyboard } from './hooks/useUndoRedoKeyboard'
import type { BuilderContentProps } from './types/builderContent'
import { useBuilderPermissions } from './useBuilderPermissions'

function useEditorPermissions({
  workflow,
  workflowId,
  isNew,
  isBuiltin,
  builderProjectId,
  queryClient,
}: Pick<BuilderContentProps, 'workflow' | 'workflowId' | 'isNew'> & {
  isBuiltin: boolean
  builderProjectId?: string
  queryClient: ReturnType<typeof useQueryClient>
}) {
  const workflowPermissionChecks = useBuilderPermissions(isNew, isBuiltin, builderProjectId)
  const retryWorkflowPermissionContext = useCallback(() => invalidateWorkflowQueries(queryClient), [queryClient])
  const stepTypePermissions = useStepTypePermissions(workflow?.step_types, builderProjectId, {
    enabled: !isNew && Boolean(workflowId) && !isBuiltin,
    retryContext: retryWorkflowPermissionContext,
  })
  const stepTypeTooltip = getStepTypePermissionMessage(stepTypePermissions)
  const builderTooltips = useMemo(() => {
    if (stepTypePermissions.canAuthor) return workflowPermissionChecks.tooltips
    return {
      edit: stepTypeTooltip,
      save: stepTypeTooltip,
      publish: stepTypeTooltip,
      unpublish: stepTypeTooltip,
      run: workflowPermissionChecks.tooltips.run,
      delete: stepTypeTooltip,
      create: stepTypeTooltip,
    }
  }, [workflowPermissionChecks.tooltips, stepTypePermissions.canAuthor, stepTypeTooltip])
  const builderPermissions = useMemo(
    () => ({
      ...workflowPermissionChecks,
      canEdit: workflowPermissionChecks.canEdit && stepTypePermissions.canAuthor,
      canCreate: workflowPermissionChecks.canCreate && stepTypePermissions.canAuthor,
      canDelete: workflowPermissionChecks.canDelete && stepTypePermissions.canAuthor,
      isLoading: workflowPermissionChecks.isLoading || stepTypePermissions.isChecking,
      stepTypePermissionError: stepTypePermissions.isError,
      stepTypePermissionLoading: stepTypePermissions.isChecking,
      blockedStepTypes: stepTypePermissions.blockedStepTypes.map((stepType) => stepType.label),
      retryStepTypePermissions: stepTypePermissions.retry,
      tooltips: builderTooltips,
    }),
    [workflowPermissionChecks, stepTypePermissions, builderTooltips]
  )

  return { builderPermissions, workflowPermissionChecks, retryWorkflowPermissionContext, stepTypePermissions }
}

function useExecutionVersionFilter(
  resources:
    NonNullable<ReturnType<typeof useBuilderContentQueries>['executionsQuery']['data']>['resources'] | undefined,
  handleExecutionFilterChange: ReturnType<typeof useCursorPagination>['handleFilterChange'],
  dispatch: Dispatch<BuilderAction>
) {
  const executionsByVersion = useMemo(() => {
    const map = new Map<number, string>()
    for (const e of resources ?? []) {
      const versionNum = e.workflow_version
      const versionId = e.workflow_version_id
      if (versionNum != null && versionId && !map.has(versionNum)) {
        map.set(versionNum, versionId)
      }
    }
    return map
  }, [resources])

  const handleOpenRunHistory = useCallback(
    (versionNumber: number) => {
      const versionId = executionsByVersion.get(versionNumber)
      if (versionId) {
        handleExecutionFilterChange([{ key: 'workflow_version_id', value: versionId, operator: 'eq' }])
      }
      dispatch({ type: 'SET_HISTORY_CARD_OPEN', payload: true })
    },
    [dispatch, executionsByVersion, handleExecutionFilterChange]
  )

  return { executionsByVersion, handleOpenRunHistory }
}

export function useBuilderSession({
  workflow,
  isNew,
  workflowId,
  initialProjectId,
  executionCopy,
  initialViewVersion,
}: BuilderContentProps) {
  const navigate = useNavigate()
  const setLocation = useCallback(
    (to: string) => {
      detachPromise(navigate({ to }))
    },
    [navigate]
  )
  const [searchParams, setSearchParams] = useSearchParams()
  const { showSuccess } = useAlerts()
  const [saveAttemptedWithoutProject, setSaveAttemptedWithoutProject] = useState(false)
  // A new workflow arrives with the project chosen in BuilderNew's picker (R18), and an
  // existing one keeps its project, so the toolbar only shows the project. The selector
  // remains as a fallback for a new workflow opened without a project.
  const fixedProjectId = isNew ? initialProjectId : (workflow?.project_id ?? undefined)
  const { selectedProject, selectedProjectName, stableProjectId, ProjectSelector } = useProjectSelector({
    requireProject: isNew,
    initialProjectId: fixedProjectId,
    hasValidationError: saveAttemptedWithoutProject,
    onProjectSelect: () => setSaveAttemptedWithoutProject(false),
    isDisabled: !isNew || !!fixedProjectId,
    clearSelectionOnMount: isNew && !fixedProjectId,
  })
  const projectDisplay =
    !isNew || fixedProjectId ? (
      <Content component={ContentVariants.p} className={styles.projectDisplay}>
        Project: {selectedProjectName ?? '…'}
      </Content>
    ) : (
      ProjectSelector
    )

  const queryClient = useQueryClient()
  const reactFlowInstance = useReactFlow()
  const nodesInitialized = useNodesInitialized()
  const store = useWorkflowStore()
  const { currentWorkflow } = store
  const unsavedChanges = useUnsavedChanges()
  const { requestNavigation } = unsavedChanges
  const handleExecutionNavigate = useCallback(
    (id: string) => requestNavigation(`/executions/${id}`),
    [requestNavigation]
  )

  const executionExtraParams = useMemo(() => ({ workflow_id: workflowId ?? '' }), [workflowId])
  const {
    filters: executionFilters,
    queryParams: executionsQueryParams,
    handleFilterChange: handleExecutionFilterChange,
    handleClearAllFilters: clearExecutionFilters,
    getFooterProps: getExecutionPaginationFooterProps,
  } = useCursorPagination({
    limit: 20,
    transformFilters: transformExecutionStatusFilter,
    extraParams: executionExtraParams,
    defaultSort: { field: 'created_at', direction: 'desc' as const },
  })
  const [state, dispatch] = useReducer(builderReducer, getInitialBuilderState())
  const expandAllEvents = useMemo(
    () => ({ expandAllEvent: new EventTarget(), collapseAllEvent: new EventTarget() }),
    []
  )
  const { hasNoWorkflowSteps, isAddStepPanelOpen, isStepEditorOpen } = useBuilderDerivedUiFlags(
    currentWorkflow,
    state.addStepPanelOpen,
    state.stepEditorMode
  )

  useEffect(() => () => useWorkflowStore.temporal.getState().clear(), [])
  const { executionsQuery, mostRecentExecutionQuery, workflowsListQuery } = useBuilderContentQueries({
    workflowId,
    isNew,
    executionsQueryParams,
    mostRecentExecutionId: state.mostRecentExecutionId,
    mostRecentRunPanelOpen: state.mostRecentRunPanelOpen,
  })

  useBuilderWorkflowLifecycle({
    workflowId,
    isNew,
    workflow,
    workflowName: state.workflowName,
    initialViewVersion,
    workflowsListResources: workflowsListQuery.data?.resources,
    workflowsListDataUndefined: workflowsListQuery.data === undefined,
    workflowsListIsPending: workflowsListQuery.isPending,
    workflowsListError: workflowsListQuery.error,
    dispatch,
    setWorkflow: store.setWorkflow,
    setStoredEdges: store.setEdges,
    loadWorkflowWithEdges: store.loadWorkflowWithEdges,
  })
  useExecutionCopyToEditor({ executionCopy, dispatch, markDirty: store.markDirty, showSuccess })

  const initialViewVersionRef = useRef(initialViewVersion)
  useEffect(() => {
    if (initialViewVersionRef.current === initialViewVersion) return
    initialViewVersionRef.current = initialViewVersion
    if (initialViewVersion != null) {
      dispatch({ type: 'SET_VIEWING_VERSION', payload: initialViewVersion })
      dispatch({ type: 'SET_VERSION_HISTORY_OPEN', payload: true })
      dispatch({ type: 'SET_HISTORY_CARD_OPEN', payload: false })
      queueMicrotask(() => {
        clearExecutionFilters()
      })
    }
  }, [initialViewVersion, dispatch, clearExecutionFilters])
  const isBuiltin = currentWorkflow?.is_builtin === true
  const builderProjectId = workflow?.project_id ?? selectedProject?.id ?? stableProjectId
  const permissions = useEditorPermissions({ workflow, workflowId, isNew, isBuiltin, builderProjectId, queryClient })
  const { builderPermissions } = permissions
  useUndoRedoKeyboard({
    disabled: isStepEditorOpen || state.viewingVersion !== null || !builderPermissions.canEdit,
  })

  const versionFilter = useExecutionVersionFilter(
    executionsQuery.data?.resources,
    handleExecutionFilterChange,
    dispatch
  )
  const executionPaginationFooterProps = useMemo(
    () => getExecutionPaginationFooterProps(executionsQuery.data),
    [getExecutionPaginationFooterProps, executionsQuery.data]
  )

  return {
    state,
    dispatch,
    store,
    unsavedChanges,
    setLocation,
    searchParams,
    setSearchParams,
    queryClient,
    reactFlowInstance,
    nodesInitialized,
    stableProjectId,
    builderProjectId,
    projectDisplay,
    isBuiltin,
    setSaveAttemptedWithoutProject,
    hasNoWorkflowSteps,
    isAddStepPanelOpen,
    isStepEditorOpen,
    expandAllEvents,
    executionsQuery,
    mostRecentExecutionQuery,
    workflowsListQuery,
    executionFilters,
    handleExecutionFilterChange,
    clearExecutionFilters,
    handleExecutionNavigate,
    executionPaginationFooterProps,
    ...permissions,
    ...versionFilter,
  }
}
