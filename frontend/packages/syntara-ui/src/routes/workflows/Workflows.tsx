import { Button } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiImportIcon } from '@patternfly/react-icons'
import type { WorkflowAPI } from '@syntara/contracts'
import { useNavigate } from '@tanstack/react-router'
import { useCallback, useMemo, useState } from 'react'

import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { SynPage, SynPageBody } from '../../components/layout/SynPage'
import { SynPageHeader } from '../../components/layout/SynPageHeader'
import { SynListPanel } from '../../components/panels/list/SynListPanel'
import { SynKebabMenu } from '../../components/SynKebabMenu'
import { SynPageTitle } from '../../components/SynPageTitle'
import { builtinProjectTooltip } from '../../hooks/permissionUtils'
import { useCursorPagination, useCursorReset } from '../../hooks/useCursorPagination'
import { useDialogState } from '../../hooks/useDialogState'
import { useProjectSelector } from '../../hooks/useProjectSelector'
import { useProjectsForGrouping } from '../../hooks/useProjectsForGrouping'
import { useAlerts } from '../../providers/alerts'
import { getErrorMessage } from '../../utils/apiErrors'
import { detachPromise } from '../../utils/detachPromise'
import { useDocLink } from '../../utils/docs/useDocLink'
import { downloadWorkflowExportById } from '../../utils/downloadWorkflowExport'

import { buildProjectRowActions } from './projectRowActions'
import { useDuplicateWorkflow } from './useDuplicateWorkflow'
import { useProjectActions } from './useProjectActions'
import { useWorkflowActions } from './useWorkflowActions'
import { useWorkflowGrouping } from './useWorkflowGrouping'
import { useWorkflowPermissions } from './useWorkflowPermissions'
import { useWorkflowProjectControls } from './useWorkflowProjectControls'
import { useWorkflowsPageToolbar } from './useWorkflowsPageToolbar'
import { useWorkflowsQuery } from './useWorkflowsQuery'
import { WorkflowDialogs } from './WorkflowDialogs'
import { transformIsEnabledFilter, workflowFilterDefinitions } from './workflowFilterDefinitions'
import { buildWorkflowRowActions } from './workflowRowActions'
import { WorkflowsListView } from './WorkflowsListView'
import { workflowDefaultSort, workflowTableColumns } from './workflowTableColumns'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

type WorkflowsPageToolbarProps = {
  headerProjectActions: ReturnType<typeof buildProjectRowActions>
  canCreate: boolean
  createTooltip: string
  showWorkflowActions: boolean
  showImportWorkflow: boolean
  onImportClick: () => void
  onCreateClick: () => void
}

function WorkflowsPageToolbar({
  headerProjectActions,
  canCreate,
  createTooltip,
  showWorkflowActions,
  showImportWorkflow,
  onImportClick,
  onCreateClick,
}: WorkflowsPageToolbarProps) {
  return (
    <>
      {showImportWorkflow && (
        <DisabledWithTooltip isDisabled={!canCreate} content={createTooltip}>
          <Button variant="secondary" icon={<RhUiImportIcon />} isAriaDisabled={!canCreate} onClick={onImportClick}>
            Import workflow
          </Button>
        </DisabledWithTooltip>
      )}
      {showWorkflowActions && (
        <DisabledWithTooltip isDisabled={!canCreate} content={createTooltip}>
          <Button variant="primary" icon={<RhUiAddIcon />} isAriaDisabled={!canCreate} onClick={onCreateClick}>
            Create workflow
          </Button>
        </DisabledWithTooltip>
      )}
      {headerProjectActions.length > 0 && <SynKebabMenu actions={headerProjectActions} aria-label="Project actions" />}
    </>
  )
}

export default function Workflows() {
  const workflowsDocLink = useDocLink('workflows')
  const { showAlert, showSuccess, showError } = useAlerts()
  const navigate = useNavigate()
  const setLocation = useCallback((to: string) => detachPromise(navigate({ to })), [navigate])
  const {
    selectedProject,
    selectedProjectId,
    stableProjectId,
    isAllProjects,
    projects,
    ProjectSelector,
    refetchProjects,
  } = useProjectSelector()
  const projectsForGrouping = useProjectsForGrouping(projects, isAllProjects)
  const projectsById = useMemo(() => new Map(projectsForGrouping.map((p) => [p.id, p])), [projectsForGrouping])
  // UUID — same as builder `resourceProject` so useCanI cache keys stay aligned.
  const permissions = useWorkflowPermissions({
    resourceProject: selectedProjectId ?? undefined,
  })
  const { projectPermissions, projectEditDialog, projectDeleteDialog, projectActionCallbacks } =
    useWorkflowProjectControls(projects, selectedProjectId)
  // All-projects view hides built-in workflows in the UI. Filter them out in the
  // API query so cursor pagination limit/total match what's rendered (otherwise
  // sorting can fill a page with built-ins that get stripped client-side).
  const projectExtraParams = useMemo(() => {
    if (isAllProjects) return { is_builtin: false }
    if (selectedProjectId) return { project_id: selectedProjectId }
    return undefined
  }, [isAllProjects, selectedProjectId])

  const {
    cursor,
    resetPagination,
    filters,
    hasActiveFilters,
    queryParams,
    handleFilterChange,
    handleClearAllFilters,
    getFooterProps,
    getSortParams,
  } = useCursorPagination({
    transformFilters: transformIsEnabledFilter,
    extraParams: projectExtraParams,
    defaultSort: workflowDefaultSort,
    columns: workflowTableColumns,
  })

  const runDialog = useDialogState<Workflow>()
  const deleteDialog = useDialogState<Workflow>()
  const publishDialog = useDialogState<Workflow>()
  const unpublishDialog = useDialogState<Workflow>()
  const [importDialogOpen, setImportDialogOpen] = useState(false)

  const { workflowsQuery, workflows } = useWorkflowsQuery({
    queryParams,
    isAllProjects,
    stableProjectId,
    projectSelectorReady: isAllProjects || !!stableProjectId,
  })

  const {
    handleRunWorkflow,
    handleDeleteWorkflow,
    handlePublishWorkflow,
    handleUnpublishWorkflow,
    isDeleting,
    isPublishing,
  } = useWorkflowActions({
    showSuccess,
    showError,
    onNavigate: setLocation,
    onRefetch: () => detachPromise(workflowsQuery.refetch()),
    onDeleteSettled: () => deleteDialog.close(),
    onPublishSettled: () => publishDialog.close(),
    onUnpublishSettled: () => unpublishDialog.close(),
  })

  const { sortedWorkflows, groupedWorkflows, collapsedProjects, toggleProjectCollapsed } = useWorkflowGrouping(
    workflows,
    projectsForGrouping,
    isAllProjects
  )

  useCursorReset(sortedWorkflows.length, hasActiveFilters, cursor, workflowsQuery.isFetching, resetPagination)

  const { handleDeleteProject: handleDeleteProjectBase, isDeletingProject } = useProjectActions({
    showSuccess,
    showError,
    onRefetch: () => {
      detachPromise(workflowsQuery.refetch())
      detachPromise(refetchProjects())
    },
    onDeleteSettled: () => projectDeleteDialog.close(),
  })

  const { duplicateWorkflow, isDuplicating } = useDuplicateWorkflow({
    showAlert,
    showError,
    setLocation,
    onSuccess: () => detachPromise(workflowsQuery.refetch()),
  })

  const { headerProjectActions, showWorkflowActions, showImportWorkflow, showToolbar } = useWorkflowsPageToolbar({
    isAllProjects,
    selectedProjectId,
    projects,
    sortedWorkflowsLength: sortedWorkflows.length,
    hasActiveFilters,
    projectEditDialog,
    projectDeleteDialog,
    projectPermissions,
  })

  const getRowActions = (workflow: Workflow) => {
    const isBuiltinProject = !!selectedProject?.is_builtin || !!projectsById.get(workflow.project_id)?.is_builtin
    return buildWorkflowRowActions(workflow, permissions, isBuiltinProject, {
      navigate,
      onRun: (wf) => runDialog.open(wf),
      onDuplicate: (wf) => detachPromise(duplicateWorkflow(wf)),
      onExport: (wf) => {
        if (wf.id) {
          detachPromise(
            downloadWorkflowExportById(wf.id).catch((err: unknown) => {
              showError({ title: 'Export failed', description: getErrorMessage(err) })
            })
          )
        }
      },
      onPublish: (wf) => publishDialog.open(wf),
      onUnpublish: (wf) => unpublishDialog.open(wf),
      onDelete: (wf) => deleteDialog.open(wf),
      isDuplicating,
    })
  }

  const hasQueryState = workflowsQuery.isPending || !!workflowsQuery.error
  return (
    <>
      <SynPage>
        <SynPageTitle segments={['Workflows']} />
        <SynPageHeader
          title="Workflows"
          docLink={workflowsDocLink}
          projectSelector={hasQueryState ? undefined : ProjectSelector}
          toolbar={
            !hasQueryState && showToolbar ? (
              <WorkflowsPageToolbar
                headerProjectActions={headerProjectActions}
                canCreate={permissions.canCreate && !selectedProject?.is_builtin}
                createTooltip={
                  selectedProject?.is_builtin ? builtinProjectTooltip('create a workflow') : permissions.tooltips.create
                }
                showWorkflowActions={showWorkflowActions}
                showImportWorkflow={showImportWorkflow}
                onImportClick={() => setImportDialogOpen(true)}
                onCreateClick={() => detachPromise(navigate({ to: '/workflow-builder/new' }))}
              />
            ) : undefined
          }
        />

        <SynPageBody>
          <SynListPanel>
            <WorkflowsListView
              isPending={workflowsQuery.isPending}
              error={workflowsQuery.error}
              onRetry={() => detachPromise(workflowsQuery.refetch())}
              isFetching={workflowsQuery.isFetching}
              sortedWorkflows={sortedWorkflows}
              hasActiveFilters={hasActiveFilters}
              filters={filters}
              filterFieldDefinitions={workflowFilterDefinitions}
              onFilterChange={handleFilterChange}
              onClearAllFilters={handleClearAllFilters}
              onCreateWorkflow={
                permissions.canCreate && !selectedProject?.is_builtin
                  ? () => detachPromise(navigate({ to: '/workflow-builder/new' }))
                  : undefined
              }
              footer={getFooterProps(workflowsQuery.data)}
              getSortParams={getSortParams}
              isAllProjects={isAllProjects}
              groupedWorkflows={groupedWorkflows}
              collapsedProjects={collapsedProjects}
              onToggleProject={toggleProjectCollapsed}
              getRowActions={getRowActions}
              projectActionCallbacks={projectActionCallbacks}
            />
          </SynListPanel>
        </SynPageBody>
      </SynPage>

      <WorkflowDialogs
        runDialog={runDialog}
        deleteDialog={deleteDialog}
        publishDialog={publishDialog}
        unpublishDialog={unpublishDialog}
        importDialogOpen={importDialogOpen}
        setImportDialogOpen={setImportDialogOpen}
        projectEditDialog={projectEditDialog}
        projectDeleteDialog={projectDeleteDialog}
        onRunWorkflow={handleRunWorkflow}
        onDeleteWorkflow={handleDeleteWorkflow}
        onPublishWorkflow={handlePublishWorkflow}
        onUnpublishWorkflow={handleUnpublishWorkflow}
        onDeleteProject={handleDeleteProjectBase}
        onRefetchWorkflows={() => detachPromise(workflowsQuery.refetch())}
        onRefetchProjects={() => detachPromise(refetchProjects())}
        isDeleting={isDeleting}
        isPublishing={isPublishing}
        isDeletingProject={isDeletingProject}
      />
    </>
  )
}
