import { Content, ContentVariants, Flex, FlexItem, Truncate } from '@patternfly/react-core'
import { RhUiBanIcon, RhUiRedoIcon } from '@patternfly/react-icons'
import { Tbody, Td, Tr } from '@patternfly/react-table'
import type { ExecutionsAPI } from '@syntara/contracts'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import { AppRoute } from '../../app/AppRoute'
import { IconLabel } from '../../components/IconLabel'
import { ApprovalPendingBadge } from '../../components/labels/ApprovalPendingBadge'
import type { KebabAction } from '../../components/NxKebabMenu'
import { NxKebabMenu } from '../../components/NxKebabMenu'
import { ProjectGroupHeaderRow } from '../../components/ProjectGroupHeaderRow'
import { DateCell } from '../../components/table/DateCell'
import { ExecutionTimestamp } from '../../components/table/ExecutionTimestamp'
import { LinkCell } from '../../components/table/LinkCell'
import { permissionTooltip } from '../../hooks/permissionUtils'
import { useCanI } from '../../hooks/useCanI'
import { detachPromise } from '../../utils/detachPromise'
import type { ProjectRead } from '../access/types'
import { StatusLabel } from '../builder/ExecutionStatus'
import { useExecutionWebSocket } from '../workflows/hooks/useExecutionWebSocket'

import { isExecutionCancellable } from './executionCancellable'
import { isExecutionRetryable } from './executionRetryable'
import { ExecutionRunIdCell } from './ExecutionRunIdCell'
import { useIsCurrentVersion } from './hooks/useIsCurrentVersion'
import { RetryExecutionDialog } from './RetryExecutionDialog'
import { useCancelExecution } from './useCancelExecution'
import { useRetryExecution } from './useRetryExecution'

type ExecutionStatus = ExecutionsAPI.components['schemas']['ExecutionStatus']

type Execution = {
  id: string
  workflow_id?: string
  workflow_name?: string | null
  workflow_version_id?: string
  workflow_version?: number | null
  workflow_version_name?: string | null
  workflow_version_created_at?: string | null
  status?: ExecutionStatus
  approval_pending?: boolean
  mode?: string
  completed_at?: string | null
  created_at?: string
  updated_at?: string
}

type ExecutionRowProps = {
  execution: Execution
}

const retryTooltip = permissionTooltip('retry this execution', 'execution:run')
const cancelTooltip = permissionTooltip('cancel this execution', 'execution:run')

function ExecutionRowActions({
  execution,
  cancellable,
  retryable,
}: Readonly<{ execution: Execution; cancellable: boolean; retryable: boolean }>) {
  const [retryDialogOpen, setRetryDialogOpen] = useState(false)
  const [cancelRequested, setCancelRequested] = useState(false)
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  /* v8 ignore start -- v8 emits phantom branches from compiled hook destructuring */
  const { allowed: canRun, isChecking } = useCanI('run', 'execution')
  const {
    isCurrentVersion,
    versionLabel: dialogVersionLabel,
    isLoading: isVersionLoading,
  } = useIsCurrentVersion(execution.workflow_id, execution.workflow_version_id, retryDialogOpen)
  const retry = useRetryExecution(execution.id, (newId) => {
    setRetryDialogOpen(false)
    detachPromise(navigate({ to: AppRoute.Executions.Execution.replace(':executionId', newId) }))
  })
  const cancel = useCancelExecution(execution.id)
  /* v8 ignore stop */

  useExecutionWebSocket(execution.id, {
    enabled: cancellable && cancelRequested,
    onExecutionComplete: () => {
      detachPromise(
        Promise.all([
          queryClient.invalidateQueries({ queryKey: ['get', '/executions/{execution_id}'] }),
          queryClient.invalidateQueries({ queryKey: ['get', '/executions'] }),
        ])
      )
    },
  })

  const kebabActions: KebabAction[] = []

  if (retryable) {
    kebabActions.push({
      key: 'retry',
      title: <IconLabel icon={<RhUiRedoIcon />}>Retry run</IconLabel>,
      isAriaDisabled: !canRun || isChecking,
      tooltipProps: !canRun && !isChecking ? { content: retryTooltip } : undefined,
      onClick: () => setRetryDialogOpen(true),
    })
  }

  if (cancellable) {
    const cancelInFlight = cancel.isPending || cancelRequested
    const cancelDisabled = !canRun || isChecking || cancelInFlight
    let cancelActionTooltip: KebabAction['tooltipProps']
    if (cancelInFlight) {
      cancelActionTooltip = { content: 'Cancellation in progress…' }
    } else if (!canRun && !isChecking) {
      cancelActionTooltip = { content: cancelTooltip }
    }

    kebabActions.push({
      key: 'cancel',
      title: <IconLabel icon={<RhUiBanIcon />}>Cancel run</IconLabel>,
      isDanger: true,
      isAriaDisabled: cancelDisabled,
      tooltipProps: cancelActionTooltip,
      onClick: () => {
        cancel.handleCancel()
        setCancelRequested(true)
      },
    })
  }

  return (
    <>
      <NxKebabMenu aria-label={`Actions for execution ${execution.id}`} actions={kebabActions} />
      {retryDialogOpen && (
        <RetryExecutionDialog
          isOpen={retryDialogOpen}
          onClose={() => setRetryDialogOpen(false)}
          onConfirm={retry.handleRetry}
          confirmLoading={retry.isPending || isVersionLoading}
          isCurrentVersion={isCurrentVersion}
          isVersionLoading={isVersionLoading}
          versionLabel={dialogVersionLabel}
        />
      )}
    </>
  )
}

function ExecutionRow({ execution }: Readonly<ExecutionRowProps>) {
  const retryable = isExecutionRetryable(execution.status, execution.mode)
  const cancellable = isExecutionCancellable(execution.status)
  const hasActions = retryable || cancellable

  return (
    <Tr>
      {/* v8 ignore start -- phantom branches from React Compiler on Run ID cell JSX */}
      <Td dataLabel="Run ID">
        <ExecutionRunIdCell executionId={execution.id} />
      </Td>
      {/* v8 ignore stop */}
      <Td dataLabel="Workflow name">
        {execution.workflow_id ? (
          <LinkCell href={`/workflow-builder/${execution.workflow_id}`}>
            <Truncate content={execution.workflow_name ?? execution.workflow_id} />
          </LinkCell>
        ) : (
          '—'
        )}
      </Td>
      <Td dataLabel="Status">
        <Flex gap={{ default: 'gapSm' }} alignItems={{ default: 'alignItemsCenter' }}>
          {execution.status && (
            <FlexItem>
              <StatusLabel status={execution.status} />
            </FlexItem>
          )}
          {execution.approval_pending && (
            <FlexItem>
              <ApprovalPendingBadge approvalPending={execution.approval_pending} />
            </FlexItem>
          )}
        </Flex>
      </Td>
      <Td dataLabel="Version">
        {execution.workflow_version != null && execution.workflow_id ? (
          <LinkCell href={`/workflow-builder/${execution.workflow_id}?version=${String(execution.workflow_version)}`}>
            {execution.workflow_version_name ? (
              <Truncate content={execution.workflow_version_name} />
            ) : (
              <ExecutionTimestamp dateString={execution.workflow_version_created_at} />
            )}
          </LinkCell>
        ) : (
          '—'
        )}
      </Td>
      <Td dataLabel="Created at">
        <DateCell dateString={execution.created_at} />
      </Td>
      <Td dataLabel="Completed at">
        {execution.completed_at ? (
          <DateCell dateString={execution.completed_at} />
        ) : (
          <Content
            component={ContentVariants.small}
            style={{ color: 'var(--pf-t--global--color--text--secondary)', margin: 0 }}
          >
            —
          </Content>
        )}
      </Td>
      <Td isActionCell>
        {hasActions && <ExecutionRowActions execution={execution} cancellable={cancellable} retryable={retryable} />}
      </Td>
    </Tr>
  )
}

type ProjectGroup = {
  project: ProjectRead | null
  executions: Execution[]
}

type GroupedExecutionsTableBodyProps = {
  groupedExecutions: Map<string, ProjectGroup>
  collapsedProjects: Set<string>
  onToggleProject: (projectId: string) => void
}

export function GroupedExecutionsTableBody({
  groupedExecutions,
  collapsedProjects,
  onToggleProject,
}: Readonly<GroupedExecutionsTableBodyProps>) {
  return (
    <>
      {[...groupedExecutions.entries()].map(([projectId, { project, executions }]) => (
        <Tbody key={projectId}>
          <ProjectGroupHeaderRow
            projectId={projectId}
            projectName={project?.name}
            isCollapsed={collapsedProjects.has(projectId)}
            colSpan={7}
            onToggle={() => onToggleProject(projectId)}
          />
          {!collapsedProjects.has(projectId) &&
            executions.map((execution) => <ExecutionRow key={execution.id} execution={execution} />)}
        </Tbody>
      ))}
    </>
  )
}

type FlatExecutionsTableBodyProps = {
  executions: Execution[]
}

export function FlatExecutionsTableBody({ executions }: Readonly<FlatExecutionsTableBodyProps>) {
  return (
    <Tbody>
      {executions.map((execution) => (
        <ExecutionRow key={execution.id} execution={execution} />
      ))}
    </Tbody>
  )
}
