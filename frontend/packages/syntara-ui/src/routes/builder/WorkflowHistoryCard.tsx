import {
  Button,
  Content,
  ContentVariants,
  Divider,
  Flex,
  FlexItem,
  Icon,
  SimpleList,
  SimpleListGroup,
  Stack,
  StackItem,
  Title,
  TitleSizes,
  Truncate,
} from '@patternfly/react-core'
import { RhUiCloseIcon, RhUiHistoryIcon, RhUiRedoIcon } from '@patternfly/react-icons'
import type { ExecutionsAPI } from '@syntara/contracts'
import { useNavigate } from '@tanstack/react-router'
import { useMemo, useState, type ReactNode } from 'react'

import { FilterBar } from '../../components/filters/FilterBar'
import { IconLabel } from '../../components/IconLabel'
import { ApprovalPendingBadge } from '../../components/labels/ApprovalPendingBadge'
import { SynLabel } from '../../components/labels/SynLabel'
import { SynPanel } from '../../components/layout/SynPanel'
import { SynEmptyStateFilter } from '../../components/states/SynEmptyStateFilter'
import type { KebabAction } from '../../components/SynKebabMenu'
import { SynKebabMenu } from '../../components/SynKebabMenu'
import { SynLink } from '../../components/SynLink'
import { ExecutionTimestamp } from '../../components/table/ExecutionTimestamp'
import type { PaginationFooterProps } from '../../components/table/PaginationFooter'
import { PaginationFooter } from '../../components/table/PaginationFooter'
import { permissionTooltip } from '../../hooks/permissionUtils'
import { useCanI } from '../../hooks/useCanI'
import { useElapsedTime } from '../../hooks/useElapsedTime'
import type { FilterConfig, FilterFieldDefinition } from '../../types/filters'
import { formatElapsedTime } from '../../utils/dateUtils'
import { detachPromise } from '../../utils/detachPromise'
import {
  getExecutionStatusFilterDefinition,
  getExecutionVersionFilterFromExecutions,
} from '../executions/executionFilters'
import { isExecutionRetryable } from '../executions/executionRetryable'
import { useIsCurrentVersion } from '../executions/hooks/useIsCurrentVersion'
import { RetryExecutionDialog } from '../executions/RetryExecutionDialog'
import { useRetryExecution } from '../executions/useRetryExecution'
import type { ExecutionMetadata } from '../workflows/stores/useExecutionStore'

import { StatusLabel } from './ExecutionStatus'
import { formatHistoryDateTime, getDateGroupLabel } from './historyDateUtils'
import { HistoryListItemLink } from './HistoryListItemLink'
import { executionDetailHref, getClearFiltersHandler, workflowVersionHref } from './hooks/historyRowModel'
import styles from './WorkflowHistoryCard.module.css'

type Execution = ExecutionsAPI.components['schemas']['ExecutionRead']

const TRUNCATED_ID_LENGTH = 8 // First 8 chars of UUID provide sufficient uniqueness
const historyRetryTooltip = permissionTooltip('retry this execution', 'execution:run')

type ExecutionGroup = {
  label: string
  items: Execution[]
}

function groupExecutionsByDate(executions: Execution[]): ExecutionGroup[] {
  const map = new Map<string, Execution[]>()
  for (const exec of executions) {
    const label = exec.created_at ? getDateGroupLabel(exec.created_at) : 'Unknown'
    if (!map.has(label)) map.set(label, [])
    map.get(label)!.push(exec)
  }
  return Array.from(map.entries()).map(([label, items]) => ({ label, items }))
}

type ExecutionHistoryRowProps = {
  execution: Execution
  onSelect: () => void
  isSelected?: boolean
}

function HistoryRowRetryAction({ execution }: Readonly<{ execution: Execution }>) {
  const [retryDialogOpen, setRetryDialogOpen] = useState(false)
  const navigate = useNavigate()
  const truncatedId = execution.id ? execution.id.slice(0, TRUNCATED_ID_LENGTH) : null

  /* v8 ignore start -- v8 emits phantom branches from compiled hook destructuring */
  const { allowed: canRun, isChecking } = useCanI('run', 'execution', {
    resourceProject: execution.project_id,
  })
  const {
    isCurrentVersion,
    versionLabel,
    isLoading: isVersionLoading,
  } = useIsCurrentVersion(execution.workflow_id, execution.workflow_version_id, retryDialogOpen)
  const retryHook = useRetryExecution(execution.id, (newId) => {
    setRetryDialogOpen(false)
    detachPromise(navigate({ to: `/executions/${newId}` }))
  })
  /* v8 ignore stop */

  const kebabActions: KebabAction[] = [
    {
      key: 'retry',
      title: <IconLabel icon={<RhUiRedoIcon />}>Retry run</IconLabel>,
      isAriaDisabled: !canRun || isChecking,
      tooltipProps: !canRun && !isChecking ? { content: historyRetryTooltip } : undefined,
      onClick: () => setRetryDialogOpen(true),
    },
  ]

  return (
    <>
      <div onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()} role="presentation">
        <SynKebabMenu aria-label={`Actions for execution ${truncatedId ?? execution.id}`} actions={kebabActions} />
      </div>
      <RetryExecutionDialog
        isOpen={retryDialogOpen}
        onClose={() => setRetryDialogOpen(false)}
        onConfirm={retryHook.handleRetry}
        confirmLoading={retryHook.isPending || isVersionLoading}
        isCurrentVersion={isCurrentVersion}
        isVersionLoading={isVersionLoading}
        versionLabel={versionLabel}
      />
    </>
  )
}

export function ExecutionHistoryRow({ execution, onSelect, isSelected }: ExecutionHistoryRowProps) {
  const isRunning = execution.status === 'running'
  const startedAtValue = execution.created_at ?? null
  const { elapsedMs } = useElapsedTime(startedAtValue, execution.completed_at, isRunning)
  const elapsedLabel = elapsedMs !== undefined ? `Elapsed time: ${formatElapsedTime(elapsedMs)}` : 'Elapsed time: -'
  const truncatedId = execution.id ? execution.id.slice(0, TRUNCATED_ID_LENGTH) : null
  const isTestRun = (execution as { execution_metadata?: ExecutionMetadata }).execution_metadata?.mode === 'test'
  const retryable = isExecutionRetryable(execution.status, execution.mode)
  const executionHref = executionDetailHref(execution.id)
  const runIdLabel = truncatedId ? `Run ID: ${truncatedId}` : null
  const versionHref =
    execution.workflow_version != null && execution.workflow_id
      ? workflowVersionHref(execution.workflow_id, execution.workflow_version)
      : null
  const dateLabel = execution.created_at
    ? `Execution from ${formatHistoryDateTime(execution.created_at)}`
    : `Execution ${truncatedId ?? execution.id}`
  const rowLabel = runIdLabel ? `${dateLabel}, ${runIdLabel}` : dateLabel

  /* v8 ignore start -- phantom branches from compiled JSX props/ternaries in history row layout */
  return (
    // eslint-disable-next-line syntara/prefer-pf-list-components -- SimpleListItem renders a <button> wrapper, causing invalid nested interactive elements (https://github.com/patternfly/patternfly-react/issues/11368)
    <li className={`pf-v6-c-simple-list__item ${styles.historyRowItem}`}>
      <HistoryListItemLink
        to={executionHref}
        isSelected={isSelected}
        onSelect={onSelect}
        data-item-id={execution.id}
        aria-label={rowLabel}
        overlay
        className={styles.historyRowOverlay}
      />
      <Stack className={styles.historyRowStack}>
        <FlexItem className={styles.historyRowTitle}>
          {execution.created_at && (
            <Content component={ContentVariants.p} className={styles.historyRowDatetime}>
              <ExecutionTimestamp dateString={execution.created_at} />
            </Content>
          )}
        </FlexItem>
        <Stack className={styles.historyMetaStack}>
          <Content component={ContentVariants.small} className={styles.historyRowMeta}>
            {elapsedLabel}
          </Content>
          {runIdLabel && (
            <Content component={ContentVariants.small} className={styles.historyRowMeta}>
              {runIdLabel}
            </Content>
          )}
          {versionHref && (
            <Content component={ContentVariants.small} className={styles.historyRowMeta}>
              {'Version: '}
              <SynLink to={versionHref} className={styles.historyRowRaised}>
                {execution.workflow_version_name ? (
                  <Truncate content={execution.workflow_version_name} />
                ) : (
                  <ExecutionTimestamp dateString={execution.workflow_version_created_at} />
                )}
              </SynLink>
            </Content>
          )}
          {execution.retried_from_execution_id && (
            <Content component={ContentVariants.small} className={`${styles.historyRowMeta} ${styles.retriedFrom}`}>
              {`Retried from: ${execution.retried_from_execution_id.slice(0, TRUNCATED_ID_LENGTH)}`}
            </Content>
          )}
        </Stack>
        <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }} flexWrap={{ default: 'wrap' }}>
          {execution.status && <StatusLabel status={execution.status} />}
          <ApprovalPendingBadge approvalPending={execution.approval_pending} />
          {isTestRun && <SynLabel color="purple">Test run</SynLabel>}
        </Flex>
      </Stack>
      {retryable && (
        <div className={styles.historyRowKebab}>
          <HistoryRowRetryAction execution={execution} />
        </div>
      )}
    </li>
  )
  /* v8 ignore stop */
}

type WorkflowHistoryCardProps = {
  executions: Execution[]
  onClose: () => void
  onExecutionSelect: (executionId: string) => void
  selectedExecutionId?: string | null
  filters?: FilterConfig[]
  onFilterChange?: (filters: FilterConfig[]) => void
  paginationFooterProps?: PaginationFooterProps
}

export function WorkflowHistoryCard(props: WorkflowHistoryCardProps) {
  const {
    executions,
    onClose,
    onExecutionSelect,
    selectedExecutionId,
    filters = [],
    onFilterChange,
    paginationFooterProps,
  } = props

  const historyFilterFields = useMemo(
    (): FilterFieldDefinition[] => [
      getExecutionStatusFilterDefinition(),
      getExecutionVersionFilterFromExecutions(executions),
    ],
    [executions]
  )

  const groups = useMemo(() => groupExecutionsByDate(executions), [executions])

  let executionListBody: ReactNode
  if (executions.length === 0 && filters.length > 0) {
    executionListBody = <SynEmptyStateFilter clearAllFilters={getClearFiltersHandler(onFilterChange)} />
  } else if (executions.length === 0) {
    executionListBody = (
      <Content component={ContentVariants.p} className={styles.emptyStateText}>
        No execution history available
      </Content>
    )
  } else {
    executionListBody = (
      <SimpleList isControlled={false} aria-label="Run history list" className={styles.simpleList}>
        {groups.map(({ label, items }) => (
          <SimpleListGroup
            key={label}
            title={
              <Content component={ContentVariants.small} className={styles.groupTitle}>
                {label}
              </Content>
            }
          >
            {items.flatMap((execution) => [
              <ExecutionHistoryRow
                key={execution.id}
                execution={execution}
                onSelect={() => onExecutionSelect(execution.id)}
                isSelected={selectedExecutionId === execution.id}
              />,
              <Divider key={`${execution.id}-divider`} component="li" />,
            ])}
          </SimpleListGroup>
        ))}
      </SimpleList>
    )
  }

  return (
    <SynPanel
      hasNoPadding
      isFullHeight
      style={{
        width: '20rem',
        flexShrink: 0,
      }}
    >
      <Stack
        style={{
          height: '100%',
          flex: 1,
          minHeight: 0,
          minWidth: 0,
          maxHeight: '100%',
          overflow: 'hidden',
          width: '100%',
        }}
      >
        <StackItem
          style={{
            flexShrink: 0,
            padding: 'var(--pf-t--global--spacer--lg) var(--pf-t--global--spacer--md) var(--pf-t--global--spacer--md)',
          }}
        >
          <Flex
            justifyContent={{ default: 'justifyContentSpaceBetween' }}
            alignItems={{ default: 'alignItemsFlexStart' }}
          >
            <FlexItem>
              <Stack hasGutter>
                <Flex gap={{ default: 'gapSm' }} alignItems={{ default: 'alignItemsCenter' }}>
                  <Icon>
                    <RhUiHistoryIcon />
                  </Icon>
                  <Title headingLevel="h2" size={TitleSizes.md}>
                    Run history
                  </Title>
                </Flex>
                <Content component={ContentVariants.small}>View past runs of this workflow.</Content>
              </Stack>
            </FlexItem>
            <FlexItem>
              <Button variant="plain" onClick={onClose} aria-label="Close run history">
                <Icon>
                  <RhUiCloseIcon />
                </Icon>
              </Button>
            </FlexItem>
          </Flex>
        </StackItem>

        {onFilterChange && (
          <StackItem style={{ flexShrink: 0, minWidth: 0, overflow: 'hidden' }}>
            <FilterBar
              fieldDefinitions={historyFilterFields}
              filters={filters}
              onFilterChange={onFilterChange}
              isCompact
            />
          </StackItem>
        )}

        <div
          style={{
            position: 'relative',
            flex: '1 1 auto',
            minHeight: 0,
            overflow: 'hidden',
            borderRadius: 'var(--pf-t--global--border--radius--medium)',
          }}
        >
          <div
            style={{
              minHeight: 0,
              height: '100%',
              overflow: 'auto',
              width: '100%',
              position: 'relative',
            }}
          >
            {executionListBody}
          </div>
        </div>

        {paginationFooterProps && (
          <StackItem
            style={{
              flex: '0 0 auto',
              width: '100%',
              borderTop:
                'var(--pf-t--global--border--width--divider--default) solid var(--pf-t--global--border--color--default)',
              paddingBottom: 'var(--pf-t--global--spacer--sm)',
            }}
          >
            <PaginationFooter {...paginationFooterProps} />
          </StackItem>
        )}
      </Stack>
    </SynPanel>
  )
}
