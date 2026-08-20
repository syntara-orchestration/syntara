import { Th, Thead, Tr, type ThProps } from '@patternfly/react-table'
import type { WorkflowAPI } from '@syntara/contracts'

import { NxListPanelTable, NxListPanelToolbar, NxListPanelView } from '../../components/panels/list/NxListPanel'
import { SynEmptyStateNoData } from '../../components/states/SynEmptyStateNoData'
import type { TableFooterProps } from '../../components/table/SynScrollableTableContainer'
import type { FilterConfig, FilterFieldDefinition } from '../../types/filters'
import type { ProjectRead } from '../access/types'

import type { ProjectRowActionCallbacks } from './projectRowActions'
import { FlatWorkflowsTableBody, GroupedWorkflowsTableBody, type RowAction } from './WorkflowsTableBody'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

type GroupedWorkflows = Map<string, { project: ProjectRead | null; workflows: Workflow[] }>

export type WorkflowsListViewProps = Readonly<{
  isPending: boolean
  error: unknown
  onRetry: () => void
  isFetching?: boolean
  sortedWorkflows: Workflow[]
  hasActiveFilters: boolean
  filterFieldDefinitions: FilterFieldDefinition[]
  filters: FilterConfig[]
  onFilterChange: (filters: FilterConfig[]) => void
  onClearAllFilters: () => void
  onCreateWorkflow?: () => void
  footer?: TableFooterProps
  getSortParams: (columnField: string) => ThProps['sort']
  isAllProjects: boolean
  groupedWorkflows: GroupedWorkflows | null
  collapsedProjects: Set<string>
  onToggleProject: (projectId: string) => void
  getRowActions: (workflow: Workflow) => RowAction[]
  projectActionCallbacks?: ProjectRowActionCallbacks
}>

export function WorkflowsListView({
  isPending,
  error,
  onRetry,
  isFetching,
  sortedWorkflows,
  hasActiveFilters,
  filterFieldDefinitions,
  filters,
  onFilterChange,
  onClearAllFilters,
  onCreateWorkflow,
  footer,
  getSortParams,
  isAllProjects,
  groupedWorkflows,
  collapsedProjects,
  onToggleProject,
  getRowActions,
  projectActionCallbacks,
}: WorkflowsListViewProps) {
  const isEmpty = sortedWorkflows.length === 0

  return (
    <NxListPanelView
      isPending={isPending}
      isFetching={isFetching}
      error={error}
      errorTitle="Error loading workflows"
      onRetry={onRetry}
      isEmpty={isEmpty}
      hasActiveFilters={hasActiveFilters}
      onClearAllFilters={onClearAllFilters}
      noDataState={
        <SynEmptyStateNoData
          title="No workflows yet"
          description="Create your first workflow to get started."
          buttonText="Create workflow"
          addData={onCreateWorkflow}
        />
      }
      toolbar={
        !isEmpty || hasActiveFilters ? (
          <NxListPanelToolbar
            filters={filters}
            filterDefinitions={filterFieldDefinitions}
            onFilterChange={onFilterChange}
            clearAllFilters={onClearAllFilters}
          />
        ) : undefined
      }
      body={
        <NxListPanelTable caption="Workflows table" footer={footer}>
          <Thead>
            <Tr>
              <Th sort={getSortParams('name')}>Name</Th>
              <Th sort={getSortParams('created_at')}>Created at</Th>
              <Th sort={getSortParams('updated_at')}>Updated at</Th>
              <Th sort={getSortParams('is_enabled')}>State</Th>
              <Th screenReaderText="Actions" />
            </Tr>
          </Thead>
          {isAllProjects && groupedWorkflows ? (
            <GroupedWorkflowsTableBody
              groupedWorkflows={groupedWorkflows}
              collapsedProjects={collapsedProjects}
              onToggleProject={onToggleProject}
              getRowActions={getRowActions}
              projectActionCallbacks={projectActionCallbacks}
            />
          ) : (
            <FlatWorkflowsTableBody workflows={sortedWorkflows} getRowActions={getRowActions} />
          )}
        </NxListPanelTable>
      }
    />
  )
}
