import { Content, ContentVariants } from '@patternfly/react-core'
import { RhUiExternalLinkIcon } from '@patternfly/react-icons'
import { Thead, Th, Tbody, Td, Tr } from '@patternfly/react-table'
import type React from 'react'
import { Fragment, useMemo } from 'react'

import { ExecutionTimestamp } from '../../components/table/ExecutionTimestamp'
import { SynScrollableTableContainer } from '../../components/table/SynScrollableTableContainer'
import { extractAAPJobUrl, isAAPNodeType } from '../../utils/aapJobUrl'
import { formatElapsedTime } from '../../utils/dateUtils'
import type { ActivityState } from '../workflows/execution/types'
import { parseCompositeKey } from '../workflows/execution/utils/activityState'

import { ActivityStatusLabel } from './ExecutionStatus'
import { ACTIVITY_STATUS } from './utils/executionState/executionHelpers'

function parseTimeMs(value: string | null | undefined): number | null {
  if (value == null) return null
  const ms = Date.parse(value)
  return Number.isNaN(ms) ? null : ms
}

function computeActivityDurationMs(state: ActivityState | undefined, now: number): number | null {
  if (!state) return null
  const startedAtMs = parseTimeMs(state.startedAt)
  if (startedAtMs === null) return null
  const completedAtMs = parseTimeMs(state.completedAt)
  if (completedAtMs !== null) return Math.max(0, completedAtMs - startedAtMs)
  const isActive = state.status === ACTIVITY_STATUS.RUNNING || state.status === ACTIVITY_STATUS.RETRYING
  return isActive ? Math.max(0, now - startedAtMs) : null
}

export type ActivityOrderItem = {
  id: string
  name?: string
  type?: string
}

type ExecutionActivityTableProps = {
  activityStates: Map<string, ActivityState>
  activityOrder: ActivityOrderItem[]
  /** Current timestamp (ms) used to compute elapsed time for running activities. */
  now: number
  /** Execution-level error — activity errors matching this are suppressed to avoid duplication. */
  executionError?: string | null
  /** Callback when a row is clicked to select a node. */
  onRowClick?: (nodeId: string, nodeName: string) => void
  /** Currently selected node ID for row highlighting. */
  selectedNodeId?: string | null
}

const DASH = (
  <Content
    component={ContentVariants.small}
    style={{ color: 'var(--pf-t--global--color--text--secondary)', margin: 0 }}
  >
    —
  </Content>
)

const ERROR_STYLE: React.CSSProperties = {
  color: 'var(--pf-t--global--color--status--danger--default)',
  fontSize: 'var(--pf-t--global--font--size--sm)',
  padding: 'var(--pf-t--global--spacer--xs) 0',
  margin: 0,
}

const AAP_LINK_STYLE: React.CSSProperties = {
  textDecoration: 'underline dotted',
  textUnderlineOffset: '3px',
  whiteSpace: 'nowrap',
}

function AAPJobLink({ url }: Readonly<{ url: string }>) {
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" style={AAP_LINK_STYLE}>
      View job in AAP <RhUiExternalLinkIcon />
    </a>
  )
}

function ActivityRow({
  id,
  name,
  type,
  state,
  now,
  executionError,
  onRowClick,
  isSelected,
  hasAAPColumn,
}: Readonly<{
  id: string
  name?: string
  type?: string
  state?: ActivityState
  now: number
  executionError?: string | null
  onRowClick?: (nodeId: string, nodeName: string) => void
  isSelected?: boolean
  hasAAPColumn: boolean
}>) {
  const elapsedMs = computeActivityDurationMs(state, now) ?? undefined
  const displayName = name ?? id
  const jobUrl = isAAPNodeType(type) ? extractAAPJobUrl(state?.outputData) : null
  const columnCount = hasAAPColumn ? 6 : 5

  return (
    <Fragment>
      <Tr
        style={{ cursor: 'pointer' }}
        onRowClick={onRowClick ? () => onRowClick(id, displayName) : undefined}
        isRowSelected={isSelected}
      >
        <Td dataLabel="Name">{displayName}</Td>
        <Td dataLabel="Started">{state?.startedAt ? <ExecutionTimestamp dateString={state.startedAt} /> : DASH}</Td>
        <Td dataLabel="Ended">{state?.completedAt ? <ExecutionTimestamp dateString={state.completedAt} /> : DASH}</Td>
        <Td dataLabel="Elapsed time">{elapsedMs === undefined ? DASH : formatElapsedTime(elapsedMs)}</Td>
        <Td dataLabel="Status" modifier="nowrap">
          <ActivityStatusLabel status={state?.status ?? 'pending'} nodeType={type} />
        </Td>
        {hasAAPColumn && <Td dataLabel="AAP Job">{jobUrl ? <AAPJobLink url={jobUrl} /> : null}</Td>}
      </Tr>
      {state?.errorDetails && state.errorDetails !== executionError && (
        <Tr>
          <Td colSpan={columnCount} style={{ paddingTop: 0 }}>
            <Content component={ContentVariants.small} style={ERROR_STYLE}>
              {state.errorDetails}
            </Content>
          </Td>
        </Tr>
      )}
    </Fragment>
  )
}

export function ExecutionActivityTable({
  activityStates,
  activityOrder,
  now,
  executionError,
  onRowClick,
  selectedNodeId,
}: ExecutionActivityTableProps) {
  const hasAAPColumn = useMemo(() => activityOrder.some((a) => isAAPNodeType(a.type)), [activityOrder])

  return (
    <SynScrollableTableContainer caption="Activity states" useFixedLayout={false} variant="compact">
      <Thead>
        <Tr>
          <Th modifier="nowrap">Name</Th>
          <Th modifier="nowrap">Started</Th>
          <Th modifier="nowrap">Ended</Th>
          <Th modifier="nowrap">Elapsed time</Th>
          <Th modifier="nowrap">Status</Th>
          {hasAAPColumn && <Th aria-label="AAP job link" />}
        </Tr>
      </Thead>
      <Tbody>
        {activityOrder.map(({ id, name, type }) => (
          <ActivityRow
            key={id}
            id={id}
            name={name}
            type={type}
            state={activityStates.get(id)}
            now={now}
            executionError={executionError}
            onRowClick={onRowClick}
            isSelected={parseCompositeKey(id).baseId === selectedNodeId}
            hasAAPColumn={hasAAPColumn}
          />
        ))}
      </Tbody>
    </SynScrollableTableContainer>
  )
}
