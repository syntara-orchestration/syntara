import { Button, Content, Truncate } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiCodeIcon, RhUiEditFillIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { ActionsColumn, Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { IAction, ThProps } from '@patternfly/react-table'
import { useCallback, useMemo, useState } from 'react'

import { SynConfirmationDialog } from '../../components/dialogs/SynConfirmationDialog'
import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { IconLabel } from '../../components/IconLabel'
import { SynListPanelTable, SynListPanelToolbar, SynListPanelView } from '../../components/panels/list/SynListPanel'
import { SynEmptyStateNoData } from '../../components/states/SynEmptyStateNoData'
import { useCursorReset } from '../../hooks/useCursorPagination'
import { useDeleteAction } from '../../hooks/useDeleteAction'
import { useDialogState } from '../../hooks/useDialogState'
import { FilterOperatorEnum, FilterTypeEnum } from '../../types/filters'
import { detachPromise } from '../../utils/detachPromise'

import { accessClient } from './accessClient'
import { PolicyDialog } from './PolicyDialog'
import { PolicyJsonModal } from './PolicyJsonModal'
import { toPolicyRead } from './policyUtils'
import { POLICY_SCOPE_OPTIONS, transformFiltersForApi } from './scopeFilterUtils'
import { PolicyTypeLabel, ProjectLabel, ScopeLabel, StatementsCell } from './ScopeLabel'
import type { PolicyRead } from './types'
import { useAccessTabQuery } from './useAccessTabQuery'
import { usePolicyPermissions } from './usePolicyPermissions'

const BASE_FILTER_FIELD_DEFS = [
  {
    key: 'name',
    label: 'Name',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by name',
  },
  {
    key: 'description',
    label: 'Description',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by description',
  },
  {
    key: 'scope',
    label: 'Scope',
    type: FilterTypeEnum.SELECT,
    options: POLICY_SCOPE_OPTIONS,
    placeholder: 'Filter by scope',
  },
  {
    key: 'project',
    label: 'Project',
    type: FilterTypeEnum.SELECT,
    options: [],
    placeholder: 'Filter by project',
  },
  {
    key: 'type',
    label: 'Type',
    type: FilterTypeEnum.SELECT,
    options: [
      { value: 'builtin', label: 'Built-in' },
      { value: 'custom', label: 'Custom' },
    ],
    placeholder: 'Filter by type',
  },
]

const SORT_FIELDS: Record<number, string> = {
  0: 'name',
  2: 'scope',
  4: 'project_id',
  5: 'is_builtin',
}

function getPolicyRowActions(
  policy: PolicyRead,
  onViewPolicyJson: (policy: PolicyRead) => void,
  onEdit: (policy: PolicyRead) => void,
  onDelete: (policy: PolicyRead) => void,
  permissions: ReturnType<typeof usePolicyPermissions>
): IAction[] {
  const actions: IAction[] = [
    {
      title: <IconLabel icon={<RhUiCodeIcon />}>View policy definition</IconLabel>,
      onClick: () => onViewPolicyJson(policy),
    },
  ]
  if (policy.is_builtin) return actions
  return [
    ...actions,
    {
      title: <IconLabel icon={<RhUiEditFillIcon />}>Edit policy</IconLabel>,
      isAriaDisabled: !permissions.canUpdate,
      tooltipProps: permissions.canUpdate ? undefined : { content: permissions.tooltips.update },
      onClick: permissions.canUpdate ? () => onEdit(policy) : undefined,
    },
    { isSeparator: true },
    {
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete policy</IconLabel>,
      isDanger: true,
      isAriaDisabled: !permissions.canDelete,
      tooltipProps: permissions.canDelete ? undefined : { content: permissions.tooltips.delete },
      onClick: permissions.canDelete ? () => onDelete(policy) : undefined,
    },
  ]
}

function PoliciesTableBody({
  policies,
  projectNameMap,
  getSortParams,
  onViewPolicyJson,
  onEdit,
  onDelete,
  permissions,
}: Readonly<{
  policies: PolicyRead[]
  projectNameMap: Map<string, string>
  getSortParams: (columnIndex: number) => ThProps['sort']
  onViewPolicyJson: (p: PolicyRead) => void
  onEdit: (policy: PolicyRead) => void
  onDelete: (policy: PolicyRead) => void
  permissions: ReturnType<typeof usePolicyPermissions>
}>) {
  return (
    <>
      <Thead>
        <Tr>
          <Th sort={getSortParams(0)}>Name</Th>
          <Th>Description</Th>
          <Th sort={getSortParams(2)}>Scope</Th>
          <Th>Statements</Th>
          <Th sort={getSortParams(4)}>Project</Th>
          <Th sort={getSortParams(5)}>Type</Th>
          <Th screenReaderText="Actions" />
        </Tr>
      </Thead>
      <Tbody>
        {policies.map((policy) => (
          <Tr key={policy.id} data-testid={`policy-row-${policy.id}`}>
            <Td dataLabel="Name">
              <code>
                <Truncate content={policy.name} />
              </code>
            </Td>
            <Td dataLabel="Description">
              <Truncate content={policy.description ?? '-'} />
            </Td>
            <Td dataLabel="Scope">
              <ScopeLabel scope={policy.scope} />
            </Td>
            <Td dataLabel="Statements">
              <StatementsCell statements={policy.statements} />
            </Td>
            <Td dataLabel="Project">
              <ProjectLabel projectId={policy.project_id} projectNameMap={projectNameMap} />
            </Td>
            <Td dataLabel="Type">
              <PolicyTypeLabel isBuiltin={policy.is_builtin} />
            </Td>
            <Td isActionCell>
              <ActionsColumn items={getPolicyRowActions(policy, onViewPolicyJson, onEdit, onDelete, permissions)} />
            </Td>
          </Tr>
        ))}
      </Tbody>
    </>
  )
}

export function PoliciesTab() {
  const permissions = usePolicyPermissions()
  const policyJsonDialog = useDialogState<PolicyRead>()
  const editDialog = useDialogState<PolicyRead>()
  const deleteDialog = useDialogState<PolicyRead>()
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)

  const {
    cursor,
    resetPagination,
    filters,
    hasActiveFilters,
    handleFilterChange,
    handleClearAllFilters,
    getFooterProps,
    getSortParams,
    projectNameMap,
    filterFieldDefinitions,
    queryParams,
  } = useAccessTabQuery({
    baseFilterDefs: BASE_FILTER_FIELD_DEFS,
    sortFields: SORT_FIELDS,
    defaultSortField: 'name',
    transformFilters: transformFiltersForApi,
  })

  const policiesQuery = accessClient.useQuery('get', '/policies', {
    params: { query: queryParams },
  })

  const data = policiesQuery.data
  const policies = useMemo(() => (data?.resources ?? []).map(toPolicyRead), [data?.resources])
  const refetch = useCallback(() => detachPromise(policiesQuery.refetch()), [policiesQuery])
  const { mutate: deletePolicy } = accessClient.useMutation('delete', '/policies/{policy_id}')
  const handleDelete = useDeleteAction({
    deleteFn: deletePolicy,
    buildParams: (policy: PolicyRead) => ({ params: { path: { policy_id: policy.id } } }),
    entityLabel: 'policy',
    getItemName: (policy: PolicyRead) => policy.name,
    onSuccess: refetch,
    onSettled: deleteDialog.close,
  })

  useCursorReset({
    itemCount: policies.length,
    hasActiveFilters,
    cursor,
    isFetching: policiesQuery.isFetching,
    resetPagination,
  })

  const showToolbar = policies.length > 0 || hasActiveFilters
  const policyJsonItem = policyJsonDialog.item

  return (
    <>
      <SynListPanelView
        tabKey="policies"
        tabLabel="Policies"
        isPending={policiesQuery.isPending}
        isFetching={policiesQuery.isFetching}
        error={policiesQuery.error}
        onRetry={refetch}
        isEmpty={policies.length === 0}
        hasActiveFilters={hasActiveFilters}
        onClearAllFilters={handleClearAllFilters}
        noDataState={
          <SynEmptyStateNoData
            title="No policies yet"
            description="No policies are available."
            buttonText="Create policy"
            addData={permissions.canCreate ? () => setIsCreateDialogOpen(true) : undefined}
          />
        }
        toolbar={
          showToolbar ? (
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
                    onClick={permissions.canCreate ? () => setIsCreateDialogOpen(true) : undefined}
                  >
                    Create policy
                  </Button>
                </DisabledWithTooltip>
              }
            />
          ) : undefined
        }
        body={
          <>
            <Content>
              Policies define what actions are allowed or denied on resources at the system or project level. Browse the
              built-in policies to understand available permissions, then group them into roles for project scoped or
              system level assignments to users and groups.
            </Content>
            <SynListPanelTable caption="Policies" footer={getFooterProps(data)}>
              <PoliciesTableBody
                policies={policies}
                projectNameMap={projectNameMap}
                getSortParams={getSortParams}
                onViewPolicyJson={policyJsonDialog.open}
                onEdit={editDialog.open}
                onDelete={deleteDialog.open}
                permissions={permissions}
              />
            </SynListPanelTable>
          </>
        }
      />

      {policyJsonItem != null && (
        <PolicyJsonModal isOpen={policyJsonDialog.isOpen} policy={policyJsonItem} onClose={policyJsonDialog.close} />
      )}
      {isCreateDialogOpen && (
        <PolicyDialog
          projectNameMap={projectNameMap}
          onClose={() => setIsCreateDialogOpen(false)}
          onSuccess={refetch}
        />
      )}
      {editDialog.item && (
        <PolicyDialog
          policy={editDialog.item}
          projectNameMap={projectNameMap}
          onClose={editDialog.close}
          onSuccess={refetch}
        />
      )}
      <SynConfirmationDialog
        isOpen={deleteDialog.isOpen}
        onClose={deleteDialog.close}
        onConfirm={() => handleDelete(deleteDialog.item)}
        title="Delete policy?"
        confirmLabel="Delete policy"
        confirmVariant="danger"
        titleIconVariant="warning"
        destructiveAcknowledgement={{
          checkboxId: 'delete-policy-ack',
          label: 'I understand this policy will be permanently deleted.',
        }}
      >
        The policy <strong>{deleteDialog.item?.name}</strong> will be deleted. This cannot be undone.
      </SynConfirmationDialog>
    </>
  )
}
