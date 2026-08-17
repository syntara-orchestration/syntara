import { Content, ContentVariants, Stack, StackItem } from '@patternfly/react-core'
import { Table, Tbody, Td, Tr } from '@patternfly/react-table'

import { ExecutionTimeRange } from '../../components/table/ExecutionTimestamp'
import type { ActivityState } from '../workflows/execution/types'
import { parseCompositeKey } from '../workflows/execution/utils/activityState'

import styles from './CompactActivityList.module.css'
import type { ActivityOrderItem } from './ExecutionActivityTable'
import { ActivityStatusLabel } from './ExecutionStatus'
import { ACTIVITY_STATUS } from './utils/executionState/executionHelpers'

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
  return (
    <Table aria-label="Activity list" isPlain variant="compact" className={styles.table}>
      <Tbody>
        {activityOrder.map(({ id, name, type }) => {
          const state = activityStates.get(id)
          const hasTimeRange = Boolean(state?.startedAt)
          const { baseId } = parseCompositeKey(id)
          const displayName = name ?? id
          const isSelected = baseId === selectedNodeId

          return (
            <Tr
              key={id}
              className={styles.clickableRow}
              onRowClick={onRowClick ? () => onRowClick(id, displayName) : undefined}
              isRowSelected={isSelected}
            >
              <Td dataLabel="Name" className={styles.nameCell}>
                <Stack>
                  <StackItem>{displayName}</StackItem>
                  {hasTimeRange && (
                    <StackItem>
                      <Content component={ContentVariants.small} className={styles.subtleText}>
                        <ExecutionTimeRange startedAt={state?.startedAt} completedAt={state?.completedAt} />
                      </Content>
                    </StackItem>
                  )}
                </Stack>
              </Td>
              <Td dataLabel="Status" modifier="nowrap" className={styles.statusCell}>
                <ActivityStatusLabel status={state?.status ?? ACTIVITY_STATUS.PENDING} nodeType={type} />
              </Td>
            </Tr>
          )
        })}
      </Tbody>
    </Table>
  )
}
