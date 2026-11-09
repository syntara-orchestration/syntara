import { Button, Content, StackItem, Switch, Truncate } from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'
import { Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { ThProps } from '@patternfly/react-table'
import type { ExecutionPlaneAPI } from '@syntara/contracts'
import { useNavigate } from '@tanstack/react-router'
import { useCallback, useMemo } from 'react'

import { AppRoute } from '../../app/AppRoute'
import { executionPlaneClient } from '../../client'
import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { SynPage, SynPageBody } from '../../components/layout/SynPage'
import { SynPageHeader } from '../../components/layout/SynPageHeader'
import {
  SynListPanel,
  SynListPanelTable,
  SynListPanelToolbar,
  SynListPanelView,
} from '../../components/panels/list/SynListPanel'
import { SynKebabMenu } from '../../components/SynKebabMenu'
import { SynPageTitle } from '../../components/SynPageTitle'
import { LinkCell } from '../../components/table/LinkCell'
import { useCursorPagination, useCursorReset } from '../../hooks/useCursorPagination'
import type { FilterFieldDefinition } from '../../types/filters'
import { detachPromise } from '../../utils/detachPromise'
import { useDocLink } from '../../utils/docs/useDocLink'

import { ExecutionPlaneEmptyState } from './ExecutionPlaneEmptyState'
import { getExecutionPlaneFilterDefinitions } from './executionPlaneFilters'
import { executionPlaneDefaultSort, executionPlaneTableColumns } from './executionPlaneTableColumns'
import { buildExecutionTargetDeleteAction } from './executionTargetDeleteAction'
import { ExecutionTargetDialogs } from './ExecutionTargetDialogs'
import { buildExecutionTargetEditAction } from './executionTargetEditAction'
import { ExecutionTargetStatusLabel } from './ExecutionTargetStatusLabel'
import { getNodeSelectors } from './getNodeSelectors'
import { NodeSelectorsCell } from './NodeSelectorsCell'
import { useExecutionTargetActions } from './useExecutionTargetActions'
import { useExecutionTargetEnabledToggle } from './useExecutionTargetEnabledToggle'
import { useExecutionTargetPermissions } from './useExecutionTargetPermissions'

type ExecutionTarget = ExecutionPlaneAPI.components['schemas']['ExecutionTargetRead']

function ExecutionPlaneTableContent({
  rows,
  getSortParams,
  deleteDialog,
  handleToggleEnabled,
  isPatchPending,
  permissions,
  onEdit,
}: Readonly<{
  rows: ExecutionTarget[]
  getSortParams: (columnField: string) => ThProps['sort']
  deleteDialog: { open: (item: ExecutionTarget) => void }
  handleToggleEnabled: (target: ExecutionTarget) => void
  isPatchPending: boolean
  permissions: ReturnType<typeof useExecutionTargetPermissions>
  onEdit: (target: ExecutionTarget) => void
}>) {
  const permissionBlocked = permissions.isLoading || !permissions.canUpdate
  const toggleBlocked = permissionBlocked || isPatchPending

  return (
    <>
      <Thead>
        <Tr>
          <Th width={20} sort={getSortParams('name')}>
            Name
          </Th>
          <Th width={20} sort={getSortParams('cluster_id')}>
            OpenShift Cluster
          </Th>
          <Th width={15} sort={getSortParams('status')}>
            Status
          </Th>
          <Th width={25}>OpenShift node selector</Th>
          <Th width={10} sort={getSortParams('enabled')}>
            State
          </Th>
          <Th width={10} screenReaderText="Actions" />
        </Tr>
      </Thead>
      <Tbody>
        {rows.map((target) => (
          <Tr key={target.id}>
            <Td dataLabel="Name">
              <LinkCell href={AppRoute.ExecutionPlane.Detail.replace(':executionTargetId', target.id)}>
                <Truncate content={target.name} />
              </LinkCell>
            </Td>
            <Td dataLabel="OpenShift Cluster">
              <Truncate content={target.cluster_id} />
            </Td>
            <Td dataLabel="Status">
              <ExecutionTargetStatusLabel status={target.status} message={target.status_message} />
            </Td>
            <Td dataLabel="OpenShift node selector">
              <NodeSelectorsCell selectors={getNodeSelectors(target.placement)} />
            </Td>
            <Td dataLabel="State">
              <DisabledWithTooltip isDisabled={permissionBlocked} content={permissions.tooltips.enable}>
                <Switch
                  id={`toggle-${target.id}`}
                  label={target.enabled ? 'Enabled' : 'Disabled'}
                  isChecked={target.enabled}
                  onChange={toggleBlocked ? () => undefined : () => handleToggleEnabled(target)}
                  aria-disabled={toggleBlocked || undefined}
                  aria-label={`Toggle ${target.name}`}
                />
              </DisabledWithTooltip>
            </Td>
            <Td isActionCell>
              <SynKebabMenu
                actions={[
                  buildExecutionTargetEditAction(target, permissions, onEdit),
                  buildExecutionTargetDeleteAction(target, deleteDialog, permissions),
                ]}
                aria-label={`Actions for ${target.name}`}
              />
            </Td>
          </Tr>
        ))}
      </Tbody>
    </>
  )
}

export default function ExecutionPlane() {
  const navigate = useNavigate()
  const docLink = useDocLink('executionPlane')
  const permissions = useExecutionTargetPermissions()

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
    defaultSort: executionPlaneDefaultSort,
    columns: executionPlaneTableColumns,
  })

  const filterFieldDefinitions = useMemo<FilterFieldDefinition[]>(() => getExecutionPlaneFilterDefinitions(), [])

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

  const onMutationSuccess = useCallback(() => query.refetch(), [query])

  const { deleteDialog, handleDelete } = useExecutionTargetActions({
    onSuccess: () => detachPromise(onMutationSuccess()),
  })

  const results = query.data?.resources ?? []

  const { targets, disableDialog, handleToggleEnabled, handleDisable, isPatchPending } =
    useExecutionTargetEnabledToggle({
      targets: results,
      onSuccess: onMutationSuccess,
    })

  useCursorReset({
    itemCount: results.length,
    hasActiveFilters,
    cursor,
    isFetching: query.isFetching,
    resetPagination,
  })

  const isEmpty = results.length === 0

  const handleConfigure = permissions.canCreate
    ? () => detachPromise(navigate({ to: AppRoute.ExecutionPlane.Create }))
    : undefined

  const handleEdit = (target: ExecutionTarget) => {
    detachPromise(navigate({ to: AppRoute.ExecutionPlane.Edit.replace(':executionTargetId', target.id) }))
  }

  return (
    <SynPage>
      <SynPageTitle segments={['Execution Plane']} />
      <SynPageHeader title="Execution Plane" docLink={docLink} />

      <SynPageBody>
        <SynListPanel>
          <StackItem>
            <Content>
              Configure execution plane workers, groups, and connectivity for on-cluster workload execution.
            </Content>
          </StackItem>
          <SynListPanelView
            isPending={query.isPending}
            error={query.error}
            onRetry={() => detachPromise(query.refetch())}
            errorTitle="Error loading execution targets"
            isEmpty={isEmpty}
            hasActiveFilters={hasActiveFilters}
            onClearAllFilters={handleClearAllFilters}
            noDataState={<ExecutionPlaneEmptyState canConfigure={permissions.canCreate} />}
            toolbar={
              !isEmpty || hasActiveFilters ? (
                <SynListPanelToolbar
                  filters={filters}
                  filterDefinitions={filterFieldDefinitions}
                  onFilterChange={handleFilterChange}
                  clearAllFilters={handleClearAllFilters}
                  actions={
                    <DisabledWithTooltip isDisabled={!permissions.canCreate} content={permissions.tooltips.create}>
                      <Button
                        variant="primary"
                        icon={<RhUiAddIcon />}
                        isAriaDisabled={!permissions.canCreate}
                        onClick={handleConfigure}
                      >
                        Configure execution target
                      </Button>
                    </DisabledWithTooltip>
                  }
                />
              ) : undefined
            }
            body={
              <SynListPanelTable caption="Execution targets" footer={getFooterProps(query.data)} useFixedLayout={false}>
                <ExecutionPlaneTableContent
                  rows={targets}
                  getSortParams={getSortParams}
                  deleteDialog={deleteDialog}
                  handleToggleEnabled={handleToggleEnabled}
                  isPatchPending={isPatchPending}
                  permissions={permissions}
                  onEdit={handleEdit}
                />
              </SynListPanelTable>
            }
          />
        </SynListPanel>
      </SynPageBody>

      <ExecutionTargetDialogs
        deleteDialog={deleteDialog}
        onDelete={handleDelete}
        disableDialog={disableDialog}
        onDisable={handleDisable}
      />
    </SynPage>
  )
}
