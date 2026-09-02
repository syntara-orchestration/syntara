import { useNavigate } from '@tanstack/react-router'
import { useMemo } from 'react'

import { AppRoute } from '../../../app/AppRoute'
import { useCursorPagination, useCursorReset } from '../../../hooks/useCursorPagination'
import { detachPromise } from '../../../utils/detachPromise'
import { useWorkflowPermissions } from '../../workflows/useWorkflowPermissions'
import { useWorkflowsQuery } from '../../workflows/useWorkflowsQuery'
import { transformIsEnabledFilter, workflowFilterDefinitions } from '../../workflows/workflowFilterDefinitions'
import { WorkflowsListView } from '../../workflows/WorkflowsListView'
import type { RowAction } from '../../workflows/WorkflowsTableBody'
import { workflowDefaultSort, workflowTableColumns } from '../../workflows/workflowTableColumns'

const EMPTY_ROW_ACTIONS: RowAction[] = []
const EMPTY_COLLAPSED_PROJECTS = new Set<string>()
function noopToggleProject() {
  return
}

function noRowActions(): RowAction[] {
  return EMPTY_ROW_ACTIONS
}

type ProjectWorkflowsTabProps = {
  projectId: string
  isBuiltin?: boolean
}

export function ProjectWorkflowsTab({ projectId, isBuiltin = false }: Readonly<ProjectWorkflowsTabProps>) {
  const navigate = useNavigate()
  const permissions = useWorkflowPermissions({ resourceProject: projectId })
  const extraParams = useMemo(() => ({ project_id: projectId }), [projectId])

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
    extraParams,
    defaultSort: workflowDefaultSort,
    columns: workflowTableColumns,
  })

  const { workflowsQuery, workflows } = useWorkflowsQuery({
    queryParams,
    isAllProjects: false,
    stableProjectId: projectId,
    projectSelectorReady: Boolean(projectId),
  })

  useCursorReset(workflows.length, hasActiveFilters, cursor, workflowsQuery.isFetching, resetPagination)

  const canCreate = permissions.canCreate && !isBuiltin

  return (
    <WorkflowsListView
      tabKey="workflows"
      tabLabel="Workflows"
      isPending={workflowsQuery.isPending}
      error={workflowsQuery.error}
      onRetry={() => detachPromise(workflowsQuery.refetch())}
      isFetching={workflowsQuery.isFetching}
      sortedWorkflows={workflows}
      hasActiveFilters={hasActiveFilters}
      filters={filters}
      filterFieldDefinitions={workflowFilterDefinitions}
      onFilterChange={handleFilterChange}
      onClearAllFilters={handleClearAllFilters}
      onCreateWorkflow={canCreate ? () => detachPromise(navigate({ to: AppRoute.WorkflowBuilder.New })) : undefined}
      footer={getFooterProps(workflowsQuery.data)}
      getSortParams={getSortParams}
      isAllProjects={false}
      groupedWorkflows={null}
      collapsedProjects={EMPTY_COLLAPSED_PROJECTS}
      onToggleProject={noopToggleProject}
      getRowActions={noRowActions}
    />
  )
}
