import { Content, ContentVariants, Flex, FlexItem } from '@patternfly/react-core'
import { RhUiSettingsIcon } from '@patternfly/react-icons'
import type { TaskActivity } from '@syntara/contracts'
import { type Node, type NodeProps } from '@xyflow/react'

import { FlowNodeType } from '../../../../constants'
import { getActivityMetadata } from '../../../../stores/useWorkflowStore'
import type { ActivityStatus } from '../../execution/types'
import { getNodeTypeColor } from '../nodeTypeColors'
import { semanticZoomActivityTitle } from '../semanticZoom'

import { NodeBody } from './common/NodeBody'
import { NodeComponent } from './common/NodeComponent'
import { StandardNodeHeader } from './common/StandardNodeHeader'
import { renderNodeIcon } from './renderNodeIcon'

export type GenericNode = { type: typeof FlowNodeType.GENERIC } & Node<TaskActivity>

/**
 * Generic placeholder **step** on the canvas (React Flow node until configured).
 * Renders a dashed border node with a plus icon
 * When clicked, allows the user to pick which step type to convert the placeholder into
 */
export function GenericNodeComponent(props: NodeProps<GenericNode>) {
  const metadata = getActivityMetadata(props.data)
  const customMessage = metadata?.__customMessage
  const displayMessage = (typeof customMessage === 'string' ? customMessage : undefined) ?? 'Select a node type'

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
    <NodeComponent
      nodeProps={props}
      reverseHandles={reverseHandles}
      hasDashedBorder
      rootTestId="generic-flow-node"
      executionState={executionState}
      collapsible={false}
      topBarColor={getNodeTypeColor(FlowNodeType.GENERIC)}
      semanticZoomSummary={{
        title: semanticZoomActivityTitle(props.data.name, displayMessage),
        typeLabel: 'Generic',
      }}
    >
      <StandardNodeHeader
        icon={renderNodeIcon(RhUiSettingsIcon, FlowNodeType.GENERIC, 'canvas', getNodeTypeColor(FlowNodeType.GENERIC))}
        title={showTitle ? 'Click to configure' : undefined}
        expandable={false}
      />
      <NodeBody>
        <Flex alignItems={{ default: 'alignItemsCenter' }} justifyContent={{ default: 'justifyContentCenter' }}>
          <FlexItem>
            <Content component={ContentVariants.h4} style={{ overflowWrap: 'anywhere' }}>
              {displayMessage}
            </Content>
          </FlexItem>
        </Flex>
      </NodeBody>
    </NodeComponent>
  )
}
