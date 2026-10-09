import { Flex } from '@patternfly/react-core'
import { ActivityTypeEnum, type ConvergeActivity } from '@syntara/contracts'
import { type Node, type NodeProps } from '@xyflow/react'

import { SynDetail } from '../../../../components/details/SynDetail'
import { SynDetailList } from '../../../../components/details/SynDetailList'
import { SynStep } from '../../../../components/steps/SynStep'
import { SynStepBody } from '../../../../components/steps/SynStepBody'
import { RegistryStepId } from '../../../../constants'
import type { ActivityStatus } from '../../execution/types'
import { semanticZoomActivityTitle } from '../semanticZoom'
import { getStepTypeColor } from '../stepTypeColors'

import { StandardStepHeader } from './common/StandardStepHeader'
import { StepMenuCategory, useStepMenuActions } from './hooks/useStepMenuActions'
import { renderStepIcon } from './renderStepIcon'
import { stepMetadata } from './stepMetadata'

function getStrategyLabel(strategy?: 'all' | 'any', nRequired?: number): string {
  if (strategy !== 'any') return 'All'
  return nRequired != null && nRequired > 0 ? `Any ${nRequired}` : 'Any'
}

export type ConvergeNode = { type: 'converge' } & Node<ConvergeActivity>

export function ConvergeStepComponent(props: NodeProps<ConvergeNode>) {
  const metadata = stepMetadata.converge
  const iconNode = renderStepIcon(
    metadata.icon,
    RegistryStepId.LOGIC_CONVERGE,
    'canvas',
    getStepTypeColor(ActivityTypeEnum.CONVERGE)
  )
  const menuActions = useStepMenuActions({
    nodeId: props.data.id,
    stepCategory: StepMenuCategory.CONTROL_FLOW,
  })
  const config = (props.data.parameters ?? {}) as { strategy?: 'all' | 'any'; n_required?: number }
  const strategyLabel = getStrategyLabel(config.strategy, config.n_required)

  const executionState = (props.data as Record<string, unknown>).__executionState as
    | {
        status: ActivityStatus
        started_at?: string
        completed_at?: string
        error_details?: string
        retry_count?: number
      }
    | undefined

  return (
    <SynStep
      className={metadata.className}
      nodeProps={props}
      executionState={executionState}
      topBarColor={getStepTypeColor('converge')}
      rootTestId="converge-node"
      semanticZoomSummary={{
        title: semanticZoomActivityTitle(props.data.name, `Untitled ${metadata.label}`),
        typeLabel: metadata.label,
      }}
    >
      <StandardStepHeader
        icon={iconNode}
        title={props.data.name}
        subtitle={metadata.label}
        expandable
        menuActions={menuActions}
      />
      <Flex justifyContent={{ default: 'justifyContentFlexStart' }} style={{ overflow: 'hidden' }}>
        <SynStepBody>
          <SynDetailList data-testid="converge-step-details">
            <SynDetail label="Type">{strategyLabel}</SynDetail>
          </SynDetailList>
        </SynStepBody>
      </Flex>
    </SynStep>
  )
}
