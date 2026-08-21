import { Label, Truncate } from '@patternfly/react-core'
import { RhUiEditFillIcon, RhUiLockIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { ActionsColumn, Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { IAction, ThProps } from '@patternfly/react-table'
import { useState } from 'react'

import { NxConfirmationDialog } from '../../../components/dialogs/NxConfirmationDialog'
import { IconLabel } from '../../../components/IconLabel'
import {
  NxListPanel,
  NxListPanelTable,
  NxListPanelToolbar,
  NxListPanelView,
} from '../../../components/panels/list/NxListPanel'
import { SynEmptyStateNoData } from '../../../components/states/SynEmptyStateNoData'
import { useDialogState } from '../../../hooks/useDialogState'
import { useAlerts } from '../../../providers/alerts'
import { getErrorMessage } from '../../../utils/apiErrors'
import { detachPromise } from '../../../utils/detachPromise'
import { accessClient } from '../../access/accessClient'
import { builtinFilterDefinitions } from '../../access/builtinFilterDefinitions'
import type { ProjectPolicyRead } from '../../access/types'
import { useBuiltinListState } from '../../access/useBuiltinListState'

import { EditProjectPolicyDialog } from './EditProjectPolicyDialog'

const sortFieldByColumn: Record<number, string> = {
  0: 'name',
  2: 'is_builtin',
}

function isProjectOwned(policy: ProjectPolicyRead): boolean {
  return policy.project_id != null && !policy.is_builtin
}

function ProjectPoliciesTable({
  policies,
  getSortParams,
  onEdit,
  onDelete,
}: Readonly<{
  policies: ProjectPolicyRead[]
  getSortParams: (columnIndex: number) => ThProps['sort']
  onEdit: (policy: ProjectPolicyRead) => void
  onDelete: (policy: ProjectPolicyRead) => void
}>) {
  const getPolicyActions = (policy: ProjectPolicyRead): IAction[] => [
    {
      title: <IconLabel icon={<RhUiEditFillIcon />}>Edit policy</IconLabel>,
      onClick: () => onEdit(policy),
    },
    { isSeparator: true },
    {
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete policy</IconLabel>,
      onClick: () => onDelete(policy),
    },
  ]

  return (
    <>
      <Thead>
        <Tr>
          <Th sort={getSortParams(0)}>Name</Th>
          <Th>Description</Th>
          <Th sort={getSortParams(2)} modifier="nowrap">
            Type
          </Th>
          <Th screenReaderText="Actions" />
        </Tr>
      </Thead>
      <Tbody>
        {policies.map((policy) => (
          <Tr key={policy.id}>
            <Td dataLabel="Name">
              <code>
                <Truncate content={policy.name} />
              </code>
            </Td>
            <Td dataLabel="Description">
              <Truncate content={policy.description ?? '-'} />
            </Td>
            <Td dataLabel="Type">
              {policy.is_builtin ? (
                <Label color="grey" icon={<RhUiLockIcon />} isCompact>
                  Built-in
                </Label>
              ) : (
                <Label color="blue" isCompact>
                  Custom
                </Label>
              )}
            </Td>
            <Td isActionCell>{isProjectOwned(policy) && <ActionsColumn items={getPolicyActions(policy)} />}</Td>
          </Tr>
        ))}
      </Tbody>
    </>
  )
}

export function ProjectPoliciesTab({ projectId }: Readonly<{ projectId: string }>) {
  const {
    filters,
    hasActiveFilters,
    handleFilterChange,
    clearAllFilters,
    getSortParams,
    queryParams,
    page,
    perPage,
    handlePerPageChange,
    goToPrevPage,
    goToNextPage,
  } = useBuiltinListState(sortFieldByColumn)
  const [policyToEdit, setPolicyToEdit] = useState<ProjectPolicyRead | null>(null)
  const deleteDialog = useDialogState<ProjectPolicyRead>()
  const { showSuccess, showError } = useAlerts()

  const policiesQuery = accessClient.useQuery('get', '/projects/{project_id}/policies', {
    params: {
      path: { project_id: projectId },
      query: queryParams,
    },
  })

  const policies = policiesQuery.data?.resources ?? []

  const { mutate: deletePolicy } = accessClient.useMutation('delete', '/projects/{project_id}/policies/{policy_id}')

  const handlePoliciesChanged = () => {
    detachPromise(policiesQuery.refetch())
  }

  const handleDelete = (policy: ProjectPolicyRead | null) => {
    if (!policy) return
    deletePolicy(
      { params: { path: { project_id: projectId, policy_id: policy.id } } },
      {
        onSuccess: () => {
          showSuccess({ title: 'Policy deleted', description: `Deleted policy "${policy.name}"` })
          handlePoliciesChanged()
        },
        onError: (error) => {
          showError({ title: 'Failed to delete policy', description: getErrorMessage(error) })
        },
        onSettled: () => deleteDialog.close(),
      }
    )
  }

  return (
    <>
      <NxListPanel>
        <NxListPanelView
          isPending={policiesQuery.isPending}
          isFetching={policiesQuery.isFetching}
          error={policiesQuery.error}
          onRetry={() => detachPromise(policiesQuery.refetch())}
          isEmpty={policies.length === 0}
          hasActiveFilters={hasActiveFilters}
          onClearAllFilters={clearAllFilters}
          noDataState={
            <SynEmptyStateNoData title="No policies yet" description="No policies are available for this project." />
          }
          toolbar={
            <NxListPanelToolbar
              filters={filters}
              filterDefinitions={builtinFilterDefinitions}
              onFilterChange={handleFilterChange}
              clearAllFilters={clearAllFilters}
            />
          }
          body={
            <NxListPanelTable
              caption="Project policies"
              footer={{
                page,
                perPage,
                total: policiesQuery.data?.total ?? null,
                hasNext: !!policiesQuery.data?.next,
                onPrev: goToPrevPage,
                onNext: () => goToNextPage(policiesQuery.data?.next ?? null),
                onPerPageChange: handlePerPageChange,
              }}
            >
              <ProjectPoliciesTable
                policies={policies}
                getSortParams={getSortParams}
                onEdit={setPolicyToEdit}
                onDelete={deleteDialog.open}
              />
            </NxListPanelTable>
          }
        />
      </NxListPanel>

      {policyToEdit && (
        <EditProjectPolicyDialog
          projectId={projectId}
          policy={policyToEdit}
          onClose={() => setPolicyToEdit(null)}
          onSuccess={handlePoliciesChanged}
        />
      )}

      <NxConfirmationDialog
        isOpen={deleteDialog.isOpen}
        onClose={deleteDialog.close}
        onConfirm={() => handleDelete(deleteDialog.item)}
        title="Delete policy?"
        confirmLabel="Delete"
        confirmVariant="danger"
        titleIconVariant="warning"
        destructiveAcknowledgement={{
          checkboxId: 'delete-policy-ack',
          label: 'I understand this policy will be permanently deleted.',
        }}
      >
        The policy <strong>{deleteDialog.item?.name}</strong> will be deleted. Any roles using this policy will lose its
        permissions. This cannot be undone.
      </NxConfirmationDialog>
    </>
  )
}
