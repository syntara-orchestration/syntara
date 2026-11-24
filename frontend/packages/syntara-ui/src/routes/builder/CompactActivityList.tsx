import {
  Content,
  ContentVariants,
  DataList,
  DataListCell,
  DataListItem,
  DataListItemCells,
  DataListItemRow,
} from '@patternfly/react-core'
import { useCallback, useMemo, type KeyboardEvent, type MouseEvent } from 'react'

import { ExecutionTimeRange } from '../../components/table/ExecutionTimestamp'
import type { ActivityState, ActivityStatus } from '../workflows/execution/types'

import styles from './CompactActivityList.module.css'
import type { ActivityOrderItem } from './ExecutionActivityTable'
import { ActivityStatusLabel } from './ExecutionStatus'
import { getActivityStatusDisplayLabel } from './executionStatusConstants'
import { ACTIVITY_STATUS } from './utils/executionState/executionHelpers'

function activityListItemAriaLabel(displayName: string, status: ActivityStatus, nodeType?: string): string {
  return `${displayName}, ${getActivityStatusDisplayLabel(status, nodeType)}`
}

export type CompactActivityListProps = {
  activityStates: Map<string, ActivityState>
  activityOrder: ActivityOrderItem[]
  onRowClick?: (nodeId: string, nodeName: string) => void
  selectedNodeId?: string | null
}

export function CompactActivityList({
  activityStates,
  activityOrder,
  onRowClick,
  selectedNodeId,
}: Readonly<CompactActivityListProps>) {
  const displayNameById = useMemo(() => new Map(activityOrder.map(({ id, name }) => [id, name ?? id])), [activityOrder])

  const handleSelectDataListItem = useCallback(
    (_event: MouseEvent | KeyboardEvent, itemId: string) => {
      if (!onRowClick) return
      onRowClick(itemId, displayNameById.get(itemId) ?? itemId)
    },
    [displayNameById, onRowClick]
  )

  const selectionProps = onRowClick
    ? {
        onSelectDataListItem: handleSelectDataListItem,
        ...(selectedNodeId ? { selectedDataListItemId: selectedNodeId } : {}),
      }
    : {}

  return (
    <DataList
      aria-label="Activity list"
      isCompact
      gridBreakpoint="none"
      wrapModifier="breakWord"
      className={styles.list}
      {...selectionProps}
    >
      {activityOrder.map(({ id, name, type }) => {
        const state = activityStates.get(id)
        const hasTimeRange = Boolean(state?.startedAt)
        const displayName = name ?? id
        const titleId = `activity-list-item-${id}-title`
        const status = state?.status ?? ACTIVITY_STATUS.PENDING
        const rowAriaLabel = activityListItemAriaLabel(displayName, status, type)

        return (
          <DataListItem key={id} id={id} aria-labelledby={titleId} aria-label={rowAriaLabel}>
            <DataListItemRow>
              <DataListItemCells
                dataListCells={
                  <DataListCell className={styles.rowMainCell}>
                    <div className={styles.titleRow}>
                      <Content id={titleId} component={ContentVariants.p} className={styles.primaryLine}>
                        {displayName}
                      </Content>
                      <div className={styles.statusCell}>
                        <ActivityStatusLabel status={status} nodeType={type} />
                      </div>
                      {hasTimeRange && (
                        <Content component={ContentVariants.small} className={styles.subtleText}>
                          <ExecutionTimeRange startedAt={state?.startedAt} completedAt={state?.completedAt} />
                        </Content>
                      )}
                    </div>
                  </DataListCell>
                }
              />
            </DataListItemRow>
          </DataListItem>
        )
      })}
    </DataList>
  )
}
