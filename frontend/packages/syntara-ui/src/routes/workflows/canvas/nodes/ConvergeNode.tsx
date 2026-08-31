import { Flex } from '@patternfly/react-core'
import { ActivityTypeEnum, type ConvergeActivity } from '@syntara/contracts'
import { type Node, type NodeProps } from '@xyflow/react'

import { SynDetail } from '../../../../components/details/SynDetail'
import { SynDetailList } from '../../../../components/details/SynDetailList'
import { RegistryNodeId } from '../../../../constants'
import type { ActivityStatus } from '../../execution/types'
import { getNodeTypeColor } from '../nodeTypeColors'
import { semanticZoomActivityTitle } from '../semanticZoom'

import { NodeBody } from './common/NodeBody'
import { NodeComponent } from './common/NodeComponent'
import { StandardNodeHeader } from './common/StandardNodeHeader'
import { MenuNodeType, useNodeMenuActions } from './hooks/useNodeMenuActions'
import { nodeMetadata } from './nodeMetadata'
import { renderNodeIcon } from './renderNodeIcon'

function getStrategyLabel(strategy?: 'all' | 'any', nRequired?: number): string {
  if (strategy !== 'any') return 'All'
  return nRequired != null && nRequired > 0 ? `Any ${nRequired}` : 'Any'
}

export type ConvergeNode = { type: 'converge' } & Node<ConvergeActivity>

export function ConvergeNodeComponent(props: NodeProps<ConvergeNode>) {
  const metadata = nodeMetadata.converge
  const iconNode = renderNodeIcon(
    metadata.icon,
    RegistryNodeId.LOGIC_CONVERGE,
    'canvas',
    getNodeTypeColor(ActivityTypeEnum.CONVERGE)
  )
  const menuActions = useNodeMenuActions({
    nodeId: props.data.id,
    nodeType: MenuNodeType.CONTROL_FLOW,
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
    <NodeComponent
      className={metadata.className}
      nodeProps={props}
      executionState={executionState}
      topBarColor={getNodeTypeColor('converge')}
      rootTestId="converge-node"
      semanticZoomSummary={{
        title: semanticZoomActivityTitle(props.data.name, `Untitled ${metadata.label}`),
        typeLabel: metadata.label,
      }}
    >
      <StandardNodeHeader
        icon={iconNode}
        title={props.data.name}
        subtitle={metadata.label}
        expandable
        menuActions={menuActions}
      />
      <Flex justifyContent={{ default: 'justifyContentFlexStart' }} style={{ overflow: 'hidden' }}>
        <NodeBody>
          <SynDetailList data-testid="converge-node-details">
            <SynDetail label="Type">{strategyLabel}</SynDetail>
          </SynDetailList>
        </NodeBody>
      </Flex>
    </NodeComponent>
  )
}
