import type { WaitActivity } from '@syntara/contracts'
import { type Node, type NodeProps } from '@xyflow/react'
import { useShallow } from 'zustand/react/shallow'

import { SynDetailList } from '../../../../components/details/SynDetailList'
import { SynStep } from '../../../../components/steps/SynStep'
import { SynStepBody } from '../../../../components/steps/SynStepBody'
import { RegistryStepId } from '../../../../constants'
import { formatDurationLabel } from '../../../builder/utils/timeUtils'
import type { ActivityStatus } from '../../execution/types'
import { useExecutionStore } from '../../stores/useExecutionStore'
import { semanticZoomActivityTitle } from '../semanticZoom'
import { getStepTypeColor } from '../stepTypeColors'

import { renderText } from './common/detailRenderers'
import { StandardStepHeader } from './common/StandardStepHeader'
import { StepMenuCategory, useStepMenuActions } from './hooks/useStepMenuActions'
import { useWaitCountdown } from './hooks/useWaitCountdown'
import { renderStepIcon } from './renderStepIcon'
import { stepMetadata } from './stepMetadata'

export type WaitNode = { type: 'wait' } & Node<WaitActivity>

export function WaitStepComponent(props: NodeProps<WaitNode>) {
  const metadata = stepMetadata.wait
  const iconNode = renderStepIcon(metadata.icon, RegistryStepId.LOGIC_WAIT, 'canvas', getStepTypeColor('wait'))
  const menuActions = useStepMenuActions({
    nodeId: props.data.id,
    stepCategory: StepMenuCategory.CONTROL_FLOW,
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
    <SynStep
      className={metadata.className}
      nodeProps={props}
      executionState={executionState}
      topBarColor={getStepTypeColor('wait')}
      semanticZoomSummary={{
        title: semanticZoomActivityTitle(props.data.name, `Untitled ${metadata.label}`),
        typeLabel: metadata.label,
      }}
    >
      <StandardStepHeader
        icon={iconNode}
        title={props.data.name ?? 'Untitled Wait'}
        subtitle={metadata.label}
        expandable={false}
        menuActions={menuActions}
      />
      <SynStepBody>
        <SynDetailList>
          {renderText('Duration', durationLabel)}
          {isActive && renderText('⏱ Countdown', remaining ?? '')}
        </SynDetailList>
      </SynStepBody>
    </SynStep>
  )
}
