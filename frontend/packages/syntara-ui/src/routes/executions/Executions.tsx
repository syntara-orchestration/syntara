import { StackItem } from '@patternfly/react-core'
import { Thead, Tr, Th } from '@patternfly/react-table'
import type { Execution } from '@syntara/contracts'
import { useSearch } from '@tanstack/react-router'
import { useMemo, useState } from 'react'

import { executionsClient } from '../../client'
import { FilterBar } from '../../components/filters/FilterBar'
import { SynPage, SynPageBody } from '../../components/layout/SynPage'
import { SynPageHeader } from '../../components/layout/SynPageHeader'
import { SynPanel } from '../../components/layout/SynPanel'
import { SynPanelContentStack } from '../../components/layout/SynPanelContentStack'
import { SynEmptyStateFilter } from '../../components/states/SynEmptyStateFilter'
import { SynEmptyStateNoData } from '../../components/states/SynEmptyStateNoData'
import { useQueryState } from '../../components/states/useQueryState'
import { SynPageTitle } from '../../components/SynPageTitle'
import { NxScrollableTableContainer } from '../../components/table/NxScrollableTableContainer'
import { useCursorPagination, useCursorReset } from '../../hooks/useCursorPagination'
import { useProjectSelector } from '../../hooks/useProjectSelector'
import { useProjectsForGrouping } from '../../hooks/useProjectsForGrouping'
import type { FilterFieldDefinition } from '../../types/filters'
import { detachPromise } from '../../utils/detachPromise'
import { useDocLink } from '../../utils/docs/useDocLink'

import {
  getExecutionWorkflowFilterDefinition,
  getExecutionStatusFilterDefinition,
  getExecutionCreatedAtFilterDefinition,
  getExecutionVersionFilterFromExecutions,
  transformExecutionStatusFilter,
} from './executionFilters'
import { FlatExecutionsTableBody, GroupedExecutionsTableBody } from './ExecutionsTableBody'
import { executionDefaultSort, executionTableColumns } from './executionTableColumns'

function buildFilterFieldDefinitions(executions: Execution[]): FilterFieldDefinition[] {
  return [
    getExecutionWorkflowFilterDefinition(),
    getExecutionStatusFilterDefinition(),
    getExecutionVersionFilterFromExecutions(executions),
    getExecutionCreatedAtFilterDefinition(),
  ].filter((def): def is FilterFieldDefinition => def !== null)
}

export default function Executions() {
  const executionsDocLink = useDocLink('executions')
  const { selectedProject, isAllProjects, projects, ProjectSelector } = useProjectSelector()
  const projectsForGrouping = useProjectsForGrouping(projects, isAllProjects)
  const searchParams: { workflow_id?: string } = useSearch({ strict: false })
  const workflowIdFilter = searchParams.workflow_id

  // Initialize default filter from URL parameter (backwards compatibility)
  const defaultFilters = useMemo(
    () => (workflowIdFilter ? [{ key: 'workflow_id', value: workflowIdFilter }] : []),
    [workflowIdFilter]
  )

  const selectedProjectId = selectedProject?.id ?? null
  const projectExtraParams = useMemo(
    () => (selectedProjectId ? { project_id: selectedProjectId } : undefined),
    [selectedProjectId]
  )

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
    defaultFilters,
    extraParams: projectExtraParams,
    defaultSort: executionDefaultSort,
    columns: executionTableColumns,
    transformFilters: transformExecutionStatusFilter,
  })

  const executionsQuery = executionsClient.useQuery('get', '/executions', {
    params: {
      query: queryParams,
    },
  })

  const executions = useMemo(() => (executionsQuery.data?.resources ?? []) as Execution[], [executionsQuery.data])

  useCursorReset(executions.length, hasActiveFilters, cursor, executionsQuery.isFetching, resetPagination)

  const filterFieldDefinitions = useMemo(() => buildFilterFieldDefinitions(executions), [executions])

  const builtinProjectIds = useMemo(
    () => new Set(projectsForGrouping.filter((p) => p.is_builtin).map((p) => p.id)),
    [projectsForGrouping]
  )

  const visibleExecutions = useMemo(() => {
    if (!isAllProjects) return executions
    return executions.filter((e) => {
      const pid = e.project_id ?? 'unknown'
      return !builtinProjectIds.has(pid)
    })
  }, [executions, isAllProjects, builtinProjectIds])

  // Group executions by project when viewing all projects
  const [collapsedProjects, setCollapsedProjects] = useState<Set<string>>(new Set())

  const groupedExecutions = useMemo(() => {
    if (!isAllProjects) return null
    const groups = new Map<string, { project: (typeof projectsForGrouping)[number] | null; executions: Execution[] }>()
    for (const execution of visibleExecutions) {
      const projectId = execution.project_id ?? 'unknown'
      if (builtinProjectIds.has(projectId)) continue
      if (!groups.has(projectId)) {
        groups.set(projectId, {
          project: projectsForGrouping.find((p) => p.id === projectId) ?? null,
          executions: [],
        })
      }
      groups.get(projectId)!.executions.push(execution)
    }
    return groups
  }, [visibleExecutions, projectsForGrouping, isAllProjects, builtinProjectIds])

  const toggleProjectCollapsed = (projectId: string) => {
    setCollapsedProjects((prev) => {
      const next = new Set(prev)
      if (next.has(projectId)) {
        next.delete(projectId)
      } else {
        next.add(projectId)
      }
      return next
    })
  }

  const queryState = useQueryState(executionsQuery, {
    title: 'Error loading executions',
    onRetry: () => detachPromise(executionsQuery.refetch()),
  })
  if (queryState) {
    return (
      <SynPage>
        <SynPageTitle segments={['Workflow Runs']} />
        <SynPageHeader title="Workflow Runs" docLink={executionsDocLink} projectSelector={ProjectSelector} />
        <SynPageBody>
          <SynPanel isFullHeight>{queryState}</SynPanel>
        </SynPageBody>
      </SynPage>
    )
  }

  return (
    <SynPage>
      <SynPageTitle segments={['Workflow Runs']} />
      <SynPageHeader title="Workflow Runs" docLink={executionsDocLink} projectSelector={ProjectSelector} />
      <SynPageBody>
        <SynPanel isFullHeight>
          {visibleExecutions.length === 0 && !hasActiveFilters ? (
            <SynPageBody isCentered>
              <SynEmptyStateNoData title="No executions found" description="No executions found." />
            </SynPageBody>
          ) : (
            <SynPanelContentStack variant="inset">
              <StackItem>
                <FilterBar
                  fieldDefinitions={filterFieldDefinitions}
                  filters={filters}
                  onFilterChange={handleFilterChange}
                  showClearAll={true}
                />
              </StackItem>

              {visibleExecutions.length === 0 ? (
                <SynPageBody isCentered>
                  <SynEmptyStateFilter clearAllFilters={handleClearAllFilters} />
                </SynPageBody>
              ) : (
                <NxScrollableTableContainer caption="Executions table" footer={getFooterProps(executionsQuery.data)}>
                  <Thead>
                    <Tr>
                      <Th modifier="nowrap">Run ID</Th>
                      <Th modifier="nowrap" sort={getSortParams('workflow_id')}>
                        Workflow name
                      </Th>
                      <Th sort={getSortParams('status')}>Status</Th>
                      <Th modifier="nowrap">Version</Th>
                      <Th sort={getSortParams('created_at')}>Created at</Th>
                      <Th sort={getSortParams('completed_at')}>Completed at</Th>
                      <Th screenReaderText="Actions" />
                    </Tr>
                  </Thead>
                  {isAllProjects && groupedExecutions ? (
                    <GroupedExecutionsTableBody
                      groupedExecutions={groupedExecutions}
                      collapsedProjects={collapsedProjects}
                      onToggleProject={toggleProjectCollapsed}
                    />
                  ) : (
                    <FlatExecutionsTableBody executions={visibleExecutions} />
                  )}
                </NxScrollableTableContainer>
              )}
            </SynPanelContentStack>
          )}
        </SynPanel>
      </SynPageBody>
    </SynPage>
  )
}
