import { LabelGroup, Truncate } from '@patternfly/react-core'
import { Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { ExecutionsAPI } from '@syntara/contracts'
import { useCallback, useMemo, useState } from 'react'

import { AppRoute } from '../../../app/AppRoute'
import { credentialsClient } from '../../../client'
import { NxLabel } from '../../../components/labels/NxLabel'
import { SynPanelContentStack } from '../../../components/layout/SynPanelContentStack'
import { NxListPanelTable, NxListPanelView } from '../../../components/panels/list/NxListPanel'
import { NxEmptyStateNoData } from '../../../components/states/NxEmptyStateNoData'
import { DateCell } from '../../../components/table/DateCell'
import { LinkCell } from '../../../components/table/LinkCell'
import { UserTimestamp } from '../../../components/table/UserTimestamp'
import { useExpandableRowIds } from '../../../hooks/useExpandableRowIds'
import { detachPromise } from '../../../utils/detachPromise'
import { StatusLabel } from '../../builder/ExecutionStatus'
import { executionStatusDisplayLabels } from '../../builder/executionStatusConstants'

import type { CredentialWorkflowRef } from './credentialConstants'
import { expandableRowIds, hasTrimmedDescription, RELATED_RESOURCE_DASH } from './credentialRelatedTableUtils'
import { DescriptionExpandableContent } from './DescriptionExpandableContent'

type ExecutionStatus = ExecutionsAPI.components['schemas']['ExecutionStatus']

type CredentialWorkflowsTabProps = {
  credentialId: string
}

const WORKFLOW_COLUMN_COUNT = 6
const noop = () => {}

function isExecutionStatus(status: string): status is ExecutionStatus {
  return Object.hasOwn(executionStatusDisplayLabels, status)
}

function workflowHref(workflowId: string): string {
  return AppRoute.WorkflowBuilder.Edit.replace(':workflowId', workflowId)
}

function WorkflowsTable({
  workflows,
  expandedRows,
  allRowsExpanded,
  onToggleRow,
  onCollapseAll,
}: Readonly<{
  workflows: CredentialWorkflowRef[]
  expandedRows: Set<string>
  allRowsExpanded: boolean
  onToggleRow: (id: string) => void
  onCollapseAll: () => void
}>) {
  return (
    <>
      <Thead>
        <Tr>
          <Th
            expand={{
              areAllExpanded: allRowsExpanded,
              collapseAllAriaLabel: allRowsExpanded ? 'Collapse all' : 'Expand all',
              onToggle: onCollapseAll,
            }}
            aria-label="Row expansion"
          />
          <Th>Workflow name</Th>
          <Th>Created by</Th>
          <Th>Steps using credential</Th>
          <Th>Last execution</Th>
          <Th>Status</Th>
        </Tr>
      </Thead>
      {workflows.map((workflow, rowIndex) => {
        const expandable = hasTrimmedDescription(workflow.description)
        const isExpanded = expandable && expandedRows.has(workflow.id)
        return (
          <Tbody key={workflow.id} isExpanded={isExpanded}>
            <Tr isContentExpanded={isExpanded}>
              <Td
                expand={
                  expandable
                    ? {
                        rowIndex,
                        isExpanded,
                        onToggle: () => onToggleRow(workflow.id),
                      }
                    : undefined
                }
              />
              <Td dataLabel="Workflow name">
                <LinkCell href={workflowHref(workflow.id)}>
                  <Truncate content={workflow.name} />
                </LinkCell>
              </Td>
              <Td dataLabel="Created by">
                <UserTimestamp user={workflow.created_by} timestamp={workflow.created_at ?? undefined} inline />
              </Td>
              <Td dataLabel="Steps using credential">
                {workflow.node_names && workflow.node_names.length > 0 ? (
                  <LabelGroup numLabels={5}>
                    {workflow.node_names.map((nodeName) => (
                      <NxLabel key={nodeName} variant="outline">
                        {nodeName}
                      </NxLabel>
                    ))}
                  </LabelGroup>
                ) : (
                  RELATED_RESOURCE_DASH
                )}
              </Td>
              <Td dataLabel="Last execution">
                <DateCell dateString={workflow.last_execution_at} />
              </Td>
              <Td dataLabel="Status">
                {workflow.last_execution_status && isExecutionStatus(workflow.last_execution_status) ? (
                  <StatusLabel status={workflow.last_execution_status} />
                ) : (
                  RELATED_RESOURCE_DASH
                )}
              </Td>
            </Tr>
            {expandable && workflow.description ? (
              <Tr isExpanded={isExpanded}>
                <Td colSpan={WORKFLOW_COLUMN_COUNT}>
                  <DescriptionExpandableContent description={workflow.description} />
                </Td>
              </Tr>
            ) : null}
          </Tbody>
        )
      })}
    </>
  )
}

export function CredentialWorkflowsTab({ credentialId }: Readonly<CredentialWorkflowsTabProps>) {
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)

  const handlePerPageChange = useCallback((newPerPage: number) => {
    setPerPage(newPerPage)
    setPage(1)
  }, [])

  const query = credentialsClient.useQuery('get', '/credentials/{credential_id}/workflows', {
    params: { path: { credential_id: credentialId } },
  })
  const workflows = query.data?.resources ?? []
  const paginatedWorkflows = workflows.slice((page - 1) * perPage, page * perPage)
  const expandableIds = useMemo(() => expandableRowIds(paginatedWorkflows, 'workflow'), [paginatedWorkflows])
  const { expandedRows, allRowsExpanded, handleToggleRow, handleCollapseAll } = useExpandableRowIds(expandableIds)

  return (
    <SynPanelContentStack>
      <NxListPanelView
        isPending={query.isPending}
        error={query.error}
        onRetry={() => detachPromise(query.refetch())}
        errorTitle="Failed to load workflows"
        isEmpty={workflows.length === 0}
        hasActiveFilters={false}
        onClearAllFilters={noop}
        noDataState={
          <NxEmptyStateNoData
            title="No workflows using this credential"
            description="This credential is not currently referenced by any workflows. Workflows will appear here once they are configured to use this credential."
          />
        }
        body={
          <NxListPanelTable
            caption="Workflows using this credential"
            isExpandable
            footer={{
              page,
              perPage,
              total: workflows.length,
              hasNext: page * perPage < workflows.length,
              onPrev: () => setPage((p) => Math.max(1, p - 1)),
              onNext: () => setPage((p) => p + 1),
              onPerPageChange: handlePerPageChange,
            }}
          >
            <WorkflowsTable
              workflows={paginatedWorkflows}
              expandedRows={expandedRows}
              allRowsExpanded={allRowsExpanded}
              onToggleRow={handleToggleRow}
              onCollapseAll={handleCollapseAll}
            />
          </NxListPanelTable>
        }
      />
    </SynPanelContentStack>
  )
}
