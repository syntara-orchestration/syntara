import type { WaitActivity } from '@syntara/contracts'
import { type Node, type NodeProps } from '@xyflow/react'
import { useShallow } from 'zustand/react/shallow'

import { SynDetailList } from '../../../../components/details/SynDetailList'
import { RegistryNodeId } from '../../../../constants'
import { formatDurationLabel } from '../../../builder/utils/timeUtils'
import type { ActivityStatus } from '../../execution/types'
import { useExecutionStore } from '../../stores/useExecutionStore'
import { getNodeTypeColor } from '../nodeTypeColors'
import { semanticZoomActivityTitle } from '../semanticZoom'

import { renderText } from './common/detailRenderers'
import { NodeBody } from './common/NodeBody'
import { NodeComponent } from './common/NodeComponent'
import { StandardNodeHeader } from './common/StandardNodeHeader'
import { MenuNodeType, useNodeMenuActions } from './hooks/useNodeMenuActions'
import { useWaitCountdown } from './hooks/useWaitCountdown'
import { nodeMetadata } from './nodeMetadata'
import { renderNodeIcon } from './renderNodeIcon'

export type WaitNode = { type: 'wait' } & Node<WaitActivity>

export function WaitNodeComponent(props: NodeProps<WaitNode>) {
  const metadata = nodeMetadata.wait
  const iconNode = renderNodeIcon(metadata.icon, RegistryNodeId.LOGIC_WAIT, 'canvas', getNodeTypeColor('wait'))
  const menuActions = useNodeMenuActions({
    nodeId: props.data.id,
    nodeType: MenuNodeType.CONTROL_FLOW,
  })

  const executionState = (props.data as Record<string, unknown>).__executionState as
    | {
        status: ActivityStatus
        started_at?: string
        completed_at?: string
        error_details?: string
        retry_count?: number
      }
    | undefined

  const { liveStatus, liveStartedAt } = useExecutionStore(
    useShallow((state) => {
      const a = state.activityStates.get(props.data.id)
      return { liveStatus: a?.status, liveStartedAt: a?.startedAt }
    })
  )
  const countdownStatus = liveStatus ?? executionState?.status
  const countdownStartedAt = liveStartedAt ?? executionState?.started_at

  const totalSeconds = (props.data.parameters as { duration?: number } | undefined)?.duration ?? 0
  const durationLabel = totalSeconds > 0 ? formatDurationLabel(totalSeconds) : 'Not configured'

  const { isActive, remaining } = useWaitCountdown(countdownStatus, countdownStartedAt, totalSeconds)

  return (
    <NodeComponent
      className={metadata.className}
      nodeProps={props}
      executionState={executionState}
      topBarColor={getNodeTypeColor('wait')}
      semanticZoomSummary={{
        title: semanticZoomActivityTitle(props.data.name, `Untitled ${metadata.label}`),
        typeLabel: metadata.label,
      }}
    >
      <StandardNodeHeader
        icon={iconNode}
        title={props.data.name ?? 'Untitled Wait'}
        subtitle={metadata.label}
        expandable={false}
        menuActions={menuActions}
      />
      <NodeBody>
        <SynDetailList>
          {renderText('Duration', durationLabel)}
          {isActive && renderText('⏱ Countdown', remaining ?? '')}
        </SynDetailList>
      </NodeBody>
    </NodeComponent>
  )
}
