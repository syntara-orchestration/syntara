import { Content, ContentVariants, Flex, FlexItem } from '@patternfly/react-core'
import { RhUiSettingsIcon } from '@patternfly/react-icons'
import type { TaskActivity } from '@syntara/contracts'
import { type Node, type NodeProps } from '@xyflow/react'

import { SynStep } from '../../../../components/steps/SynStep'
import { SynStepBody } from '../../../../components/steps/SynStepBody'
import { FlowNodeType } from '../../../../constants'
import { getActivityMetadata } from '../../../../stores/useWorkflowStore'
import type { ActivityStatus } from '../../execution/types'
import { semanticZoomActivityTitle } from '../semanticZoom'
import { getStepTypeColor } from '../stepTypeColors'

import { StandardStepHeader } from './common/StandardStepHeader'
import { renderStepIcon } from './renderStepIcon'

export type GenericNode = { type: typeof FlowNodeType.GENERIC } & Node<TaskActivity>

/**
 * Generic placeholder **step** on the canvas (React Flow node until configured).
 * Renders a dashed border node with a plus icon
 * When clicked, allows the user to pick which step type to convert the placeholder into
 */
export function GenericStepComponent(props: NodeProps<GenericNode>) {
  const metadata = getActivityMetadata(props.data)
  const customMessage = metadata?.__customMessage
  const displayMessage = (typeof customMessage === 'string' ? customMessage : undefined) ?? 'Select a step type'

  const showTitle = !customMessage

  const reverseHandles = typeof metadata?.__reverseHandles === 'boolean' ? metadata.__reverseHandles : undefined

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
      nodeProps={props}
      reverseHandles={reverseHandles}
      hasDashedBorder
      rootTestId="generic-flow-node"
      executionState={executionState}
      collapsible={false}
      topBarColor={getStepTypeColor(FlowNodeType.GENERIC)}
      semanticZoomSummary={{
        title: semanticZoomActivityTitle(props.data.name, displayMessage),
        typeLabel: 'Generic',
      }}
    >
      <StandardStepHeader
        icon={renderStepIcon(RhUiSettingsIcon, FlowNodeType.GENERIC, 'canvas', getStepTypeColor(FlowNodeType.GENERIC))}
        title={showTitle ? 'Click to configure' : undefined}
        expandable={false}
      />
      <SynStepBody>
        <Flex alignItems={{ default: 'alignItemsCenter' }} justifyContent={{ default: 'justifyContentCenter' }}>
          <FlexItem>
            <Content component={ContentVariants.h4} style={{ overflowWrap: 'anywhere' }}>
              {displayMessage}
            </Content>
          </FlexItem>
        </Flex>
      </SynStepBody>
    </SynStep>
  )
}
