import { Flex, FlexItem } from '@patternfly/react-core'
import type { ConditionActivity } from '@syntara/contracts'
import { type Node, type NodeProps } from '@xyflow/react'

import { SynDetailList } from '../../../../components/details/SynDetailList'
import { SynStep } from '../../../../components/steps/SynStep'
import { SynStepBody } from '../../../../components/steps/SynStepBody'
import { RegistryStepId } from '../../../../constants'
import type { ActivityStatus } from '../../execution/types'
import { semanticZoomActivityTitle } from '../semanticZoom'
import { getStepTypeColor } from '../stepTypeColors'

import { BranchHandle, BranchHandles } from './common/BranchHandle'
import { renderJson, renderOutputs } from './common/detailRenderers'
import { StandardStepHeader } from './common/StandardStepHeader'
import { StepMenuCategory, useStepMenuActions } from './hooks/useStepMenuActions'
import { renderStepIcon } from './renderStepIcon'
import { stepMetadata } from './stepMetadata'

export type ConditionNode = { type: 'condition' } & Node<ConditionActivity>

export function ConditionStepComponent(props: NodeProps<ConditionNode>) {
  const metadata = stepMetadata.condition
  const iconNode = renderStepIcon(
    metadata.icon,
    RegistryStepId.LOGIC_CONDITION,
    'canvas',
    getStepTypeColor('condition')
  )
  const menuActions = useStepMenuActions({
    nodeId: props.data.id,
    stepCategory: StepMenuCategory.CONTROL_FLOW,
  })

  // Extract execution state if present
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
      disableSource
      collapsible={false}
      executionState={executionState}
      topBarColor={getStepTypeColor('condition')}
      semanticZoomSummary={{
        title: semanticZoomActivityTitle(props.data.name, `Untitled ${metadata.label}`),
        typeLabel: metadata.label,
      }}
      semanticZoomBranchSources={[
        { id: 'true', ariaLabel: 'True branch output' },
        { id: 'false', ariaLabel: 'False branch output' },
      ]}
    >
      <ConditionStepDetails conditionActivity={props.data} icon={iconNode} menuActions={menuActions}>
        <BranchHandles>
          <BranchHandle id="true" nodeId={props.data.id} ariaLabel="True branch output">
            True
          </BranchHandle>
          <BranchHandle id="false" nodeId={props.data.id} ariaLabel="False branch output">
            False
          </BranchHandle>
        </BranchHandles>
      </ConditionStepDetails>
    </SynStep>
  )
}

export function ConditionStepDetails(props: {
  conditionActivity: ConditionActivity
  children?: React.ReactNode
  showJson?: boolean
  icon?: React.ReactNode
  menuActions?: ReturnType<typeof useStepMenuActions>
}) {
  const metadata = stepMetadata.condition

  return (
    <>
      <StandardStepHeader
        icon={props.icon}
        title={props.conditionActivity.name ?? 'Untitled Condition'}
        subtitle={metadata.label}
        expandable={metadata.expandable}
        menuActions={props.menuActions}
      />
      <Flex justifyContent={{ default: 'justifyContentFlexEnd' }} gap={{ default: 'gapNone' }}>
        <FlexItem grow={{ default: 'grow' }} style={{ minWidth: 0 }}>
          <SynStepBody>
            <SynDetailList>
              {renderOutputs(props.conditionActivity.outputs)}
              {renderJson(props.conditionActivity, props.showJson, 'Full Definition')}
            </SynDetailList>
          </SynStepBody>
        </FlexItem>
        <div style={{ paddingBottom: 'var(--pf-t--global--spacer--md)' }}>{props.children}</div>
      </Flex>
    </>
  )
}
