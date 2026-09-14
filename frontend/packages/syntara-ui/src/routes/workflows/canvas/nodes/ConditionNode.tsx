import { Flex, FlexItem } from '@patternfly/react-core'
import type { ConditionActivity } from '@syntara/contracts'
import { type Node, type NodeProps } from '@xyflow/react'

import { SynDetailList } from '../../../../components/details/SynDetailList'
import { RegistryNodeId } from '../../../../constants'
import type { ActivityStatus } from '../../execution/types'
import { getNodeTypeColor } from '../nodeTypeColors'
import { semanticZoomActivityTitle } from '../semanticZoom'

import { BranchHandle, BranchHandles } from './common/BranchHandle'
import { renderJson, renderOutputs } from './common/detailRenderers'
import { NodeBody } from './common/NodeBody'
import { NodeComponent } from './common/NodeComponent'
import { StandardNodeHeader } from './common/StandardNodeHeader'
import { MenuNodeType, useNodeMenuActions } from './hooks/useNodeMenuActions'
import { nodeMetadata } from './nodeMetadata'
import { renderNodeIcon } from './renderNodeIcon'

export type ConditionNode = { type: 'condition' } & Node<ConditionActivity>

export function ConditionNodeComponent(props: NodeProps<ConditionNode>) {
  const metadata = nodeMetadata.condition
  const iconNode = renderNodeIcon(
    metadata.icon,
    RegistryNodeId.LOGIC_CONDITION,
    'canvas',
    getNodeTypeColor('condition')
  )
  const menuActions = useNodeMenuActions({
    nodeId: props.data.id,
    nodeType: MenuNodeType.CONTROL_FLOW,
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
    <NodeComponent
      className={metadata.className}
      nodeProps={props}
      disableSource
      collapsible={false}
      executionState={executionState}
      topBarColor={getNodeTypeColor('condition')}
      semanticZoomSummary={{
        title: semanticZoomActivityTitle(props.data.name, `Untitled ${metadata.label}`),
        typeLabel: metadata.label,
      }}
      semanticZoomBranchSources={[
        { id: 'true', ariaLabel: 'True branch output' },
        { id: 'false', ariaLabel: 'False branch output' },
      ]}
    >
      <ConditionNodeDetails conditionActivity={props.data} icon={iconNode} menuActions={menuActions}>
        <BranchHandles>
          <BranchHandle id="true" nodeId={props.data.id} ariaLabel="True branch output">
            True
          </BranchHandle>
          <BranchHandle id="false" nodeId={props.data.id} ariaLabel="False branch output">
            False
          </BranchHandle>
        </BranchHandles>
      </ConditionNodeDetails>
    </NodeComponent>
  )
}

export function ConditionNodeDetails(props: {
  conditionActivity: ConditionActivity
  children?: React.ReactNode
  showJson?: boolean
  icon?: React.ReactNode
  menuActions?: ReturnType<typeof useNodeMenuActions>
}) {
  const metadata = nodeMetadata.condition

  return (
    <>
      <StandardNodeHeader
        icon={props.icon}
        title={props.conditionActivity.name ?? 'Untitled Condition'}
        subtitle={metadata.label}
        expandable={metadata.expandable}
        menuActions={props.menuActions}
      />
      <Flex justifyContent={{ default: 'justifyContentFlexEnd' }} gap={{ default: 'gapNone' }}>
        <FlexItem grow={{ default: 'grow' }} style={{ minWidth: 0 }}>
          <NodeBody>
            <SynDetailList>
              {renderOutputs(props.conditionActivity.outputs)}
              {renderJson(props.conditionActivity, props.showJson, 'Full Definition')}
            </SynDetailList>
          </NodeBody>
        </FlexItem>
        <div style={{ paddingBottom: 'var(--pf-t--global--spacer--md)' }}>{props.children}</div>
      </Flex>
    </>
  )
}
