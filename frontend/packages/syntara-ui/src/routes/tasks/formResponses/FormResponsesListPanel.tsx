import { useMemo, useReducer, useState } from 'react'

import { SynListPanelToolbar, SynListPanelView } from '../../../components/panels/list/SynListPanel'
import { SynEmptyStateNoData } from '../../../components/states/SynEmptyStateNoData'
import { useCursorPagination, useCursorReset } from '../../../hooks/useCursorPagination'
import { useProjectSelector } from '../../../hooks/useProjectSelector'
import { useProjectsForGrouping } from '../../../hooks/useProjectsForGrouping'
import { detachPromise } from '../../../utils/detachPromise'

import { getFormResponseNameFilterDefinition, getFormResponseStatusFilterDefinition } from './formResponseFilters'
import { FormResponsesContent } from './FormResponsesContent'
import { formResponsesReducer } from './formResponsesReducer'
import { formResponseDefaultSort, formResponseTableColumns } from './formResponseTableColumns'
import { useFormResponsesData } from './useFormResponsesData'

export type FormResponsesListPanelProps = {
  tabKey?: string
  tabLabel?: string
}

export function FormResponsesListPanel({ tabKey, tabLabel }: Readonly<FormResponsesListPanelProps> = {}) {
  const { selectedProjectId, stableProjectId, isAllProjects, projects } = useProjectSelector()
  const projectsForGrouping = useProjectsForGrouping(projects, isAllProjects)
  const [{ expandedRows }, dispatch] = useReducer(formResponsesReducer, { expandedRows: new Set<string>() })

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
    extraParams: projectExtraParams,
    defaultSort: formResponseDefaultSort,
    columns: formResponseTableColumns,
  })

  const filterFieldDefinitions = useMemo(
    () => [getFormResponseNameFilterDefinition(), getFormResponseStatusFilterDefinition()],
    []
  )

  const projectSelectorReady = isAllProjects || !!stableProjectId
  const { formPromptsQuery, enrichedRows, groupedRows, sortedRows } = useFormResponsesData({
    projectSelectorReady,
    isAllProjects,
    stableProjectId,
    queryParams,
    projects: projectsForGrouping,
  })

  const [collapsedProjects, setCollapsedProjects] = useState<Set<string>>(new Set())
  const toggleProjectCollapsed = (id: string) =>
    setCollapsedProjects((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  useCursorReset({
    itemCount: enrichedRows.length,
    hasActiveFilters,
    cursor,
    isFetching: formPromptsQuery.isFetching,
    resetPagination,
  })

  const toggleRow = (rowId: string) => dispatch({ type: 'TOGGLE_ROW', payload: rowId })
  const expandableIds = sortedRows.map((row) => row.id)
  const hasExpandableRows = expandableIds.length > 0
  const allRowsExpanded = hasExpandableRows && expandableIds.every((id) => expandedRows.has(id))
  const collapseAllAriaLabel = allRowsExpanded ? 'Collapse all' : 'Expand all'

  const onCollapseAll = (_event: unknown, _rowIndex: number, isOpen: boolean) => {
    dispatch({
      type: 'SET_EXPANDED_ROWS',
      payload: isOpen ? new Set(expandableIds) : new Set<string>(),
    })
  }

  const isEmpty = sortedRows.length === 0
  const isPending = formPromptsQuery.isPending

  return (
    <SynListPanelView
      tabKey={tabKey}
      tabLabel={tabLabel}
      isPending={isPending}
      isFetching={formPromptsQuery.isFetching}
      error={formPromptsQuery.error}
      errorTitle="Error loading form responses"
      onRetry={() => detachPromise(formPromptsQuery.refetch())}
      isEmpty={isEmpty}
      hasActiveFilters={hasActiveFilters}
      onClearAllFilters={handleClearAllFilters}
      noDataState={
        <SynEmptyStateNoData
          title="No form responses yet"
          description="No form prompts are currently pending or available."
        />
      }
      toolbar={
        !isEmpty || hasActiveFilters ? (
          <SynListPanelToolbar
            filters={filters}
            filterDefinitions={filterFieldDefinitions}
            onFilterChange={handleFilterChange}
            clearAllFilters={handleClearAllFilters}
          />
        ) : undefined
      }
      body={
        <FormResponsesContent
          sortedRows={sortedRows}
          expandedRows={expandedRows}
          onToggleRow={toggleRow}
          getSortParams={getSortParams}
          allRowsExpanded={allRowsExpanded}
          collapseAllAriaLabel={collapseAllAriaLabel}
          onCollapseAll={onCollapseAll}
          isAllProjects={isAllProjects}
          groupedRows={groupedRows}
          collapsedProjects={collapsedProjects}
          onToggleProject={toggleProjectCollapsed}
          footerProps={getFooterProps(formPromptsQuery.data)}
        />
      }
    />
  )
}
