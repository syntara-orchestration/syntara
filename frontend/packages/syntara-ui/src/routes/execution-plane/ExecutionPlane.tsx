import { Truncate } from '@patternfly/react-core'
import { Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { ExecutionPlaneAPI } from '@syntara/contracts'
import { useMemo } from 'react'

import { executionPlaneClient } from '../../client'
import { SynLabel } from '../../components/labels/SynLabel'
import { SynPage, SynPageBody } from '../../components/layout/SynPage'
import { SynPageHeader } from '../../components/layout/SynPageHeader'
import {
  SynListPanel,
  SynListPanelTable,
  SynListPanelToolbar,
  SynListPanelView,
} from '../../components/panels/list/SynListPanel'
import { SynPageTitle } from '../../components/SynPageTitle'
import { useCanI } from '../../hooks/useCanI'
import { useCursorPagination, useCursorReset } from '../../hooks/useCursorPagination'
import type { FilterFieldDefinition } from '../../types/filters'
import { detachPromise } from '../../utils/detachPromise'
import { useDocLink } from '../../utils/docs/useDocLink'

import { ExecutionPlaneEmptyState } from './ExecutionPlaneEmptyState'
import { getExecutionTargetNameFilterDefinition } from './executionPlaneFilters'
import { ExecutionTargetStatusLabel } from './ExecutionTargetStatusLabel'
import { RoutingLabelsCell } from './RoutingLabelsCell'

type ExecutionTarget = ExecutionPlaneAPI.components['schemas']['ExecutionTargetFacadeRead']

function ExecutionPlaneTableContent({ rows }: Readonly<{ rows: ExecutionTarget[] }>) {
  return (
    <>
      <Thead>
        <Tr>
          <Th width={20}>Name</Th>
          <Th width={20}>Cluster</Th>
          <Th width={15}>Status</Th>
          <Th width={30}>Routing labels</Th>
          <Th width={15}>State</Th>
        </Tr>
      </Thead>
      <Tbody>
        {rows.map((target) => (
          <Tr key={target.id}>
            <Td dataLabel="Name">
              <Truncate content={target.name} />
            </Td>
            <Td dataLabel="Cluster">
              <Truncate content={target.cluster_id} />
            </Td>
            <Td dataLabel="Status">
              <ExecutionTargetStatusLabel status={target.status} message={target.status_message} />
            </Td>
            <Td dataLabel="Routing labels">
              <RoutingLabelsCell labels={target.labels} />
            </Td>
            <Td dataLabel="State">
              <SynLabel variant="outline" status={target.enabled ? 'success' : 'custom'}>
                {target.enabled ? 'Enabled' : 'Disabled'}
              </SynLabel>
            </Td>
          </Tr>
        ))}
      </Tbody>
    </>
  )
}

export default function ExecutionPlane() {
  const docLink = useDocLink('executionPlane')
  const { allowed: canConfigure } = useCanI('create', 'integration')

  const {
    cursor,
    resetPagination,
    filters,
    hasActiveFilters,
    queryParams,
    handleFilterChange,
    handleClearAllFilters,
    getFooterProps,
  } = useCursorPagination()

  const filterFieldDefinitions = useMemo<FilterFieldDefinition[]>(() => [getExecutionTargetNameFilterDefinition()], [])

  const query = executionPlaneClient.useQuery(
    'get',
    '/api/execution_plane/v1/execution_targets',
    {
      params: { query: queryParams },
    },
    {
      refetchInterval: 30_000,
    }
  )

  const results = query.data?.resources ?? []

  useCursorReset({
    itemCount: results.length,
    hasActiveFilters,
    cursor,
    isFetching: query.isFetching,
    resetPagination,
  })

  const isEmpty = results.length === 0

  return (
    <SynPage>
      <SynPageTitle segments={['Execution Plane']} />
      <SynPageHeader title="Execution Plane" docLink={docLink} />

      <SynPageBody>
        <SynListPanel>
          <SynListPanelView
            isPending={query.isPending}
            error={query.error}
            onRetry={() => detachPromise(query.refetch())}
            errorTitle="Error loading execution targets"
            isEmpty={isEmpty}
            hasActiveFilters={hasActiveFilters}
            onClearAllFilters={handleClearAllFilters}
            noDataState={<ExecutionPlaneEmptyState canConfigure={canConfigure} />}
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
              <SynListPanelTable caption="Execution targets" footer={getFooterProps(query.data)} useFixedLayout={false}>
                <ExecutionPlaneTableContent rows={results} />
              </SynListPanelTable>
            }
          />
        </SynListPanel>
      </SynPageBody>
    </SynPage>
  )
}
