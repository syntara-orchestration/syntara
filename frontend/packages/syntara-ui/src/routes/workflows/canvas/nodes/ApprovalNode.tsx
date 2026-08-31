import { Flex, FlexItem } from '@patternfly/react-core'
import { ActivityTypeEnum, type ApprovalActivity as ApprovalNodeType } from '@syntara/contracts'
import { type Node, type NodeProps } from '@xyflow/react'

import { SynDetailList } from '../../../../components/details/SynDetailList'
import type { ActivityStatus } from '../../execution/types'
import { getNodeTypeColor } from '../nodeTypeColors'
import { semanticZoomActivityTitle } from '../semanticZoom'

import { BranchHandle, BranchHandles } from './common/BranchHandle'
import { renderText } from './common/detailRenderers'
import { NodeBody } from './common/NodeBody'
import { NodeComponent } from './common/NodeComponent'
import { StandardNodeHeader } from './common/StandardNodeHeader'
import { MenuNodeType, useNodeMenuActions } from './hooks/useNodeMenuActions'
import { nodeMetadata } from './nodeMetadata'
import { renderNodeIcon } from './renderNodeIcon'

export type ApprovalNode = { type: 'approval' } & Node<ApprovalNodeType>

export function ApprovalNodeComponent(props: NodeProps<ApprovalNode>) {
  const metadata = nodeMetadata.approval
  const menuActions = useNodeMenuActions({
    nodeId: props.data.id,
    nodeType: MenuNodeType.ACTIVITY,
    disabled: props.data.settings?.disabled ?? false,
  })

  const iconNode = renderNodeIcon(metadata.icon, 'approval', 'canvas', getNodeTypeColor(ActivityTypeEnum.APPROVAL))
  const taskExecutor = metadata.label

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

  const showExecutionBadge =
    ((props.data as Record<string, unknown>).metadata as { __showExecutionBadge?: boolean } | undefined)
      ?.__showExecutionBadge === true

  // In v2, approval parameters have approver_timeout at parameters level (no approvers list)
  const approvalConfig = (props.data.parameters ?? {}) as { approver_timeout?: number }

  return (
    <NodeComponent
      className={metadata.className}
      nodeProps={props}
      disableSource
      collapsible={false}
      executionState={executionState}
      showExecutionBadge={showExecutionBadge}
      topBarColor={getNodeTypeColor('approval')}
      semanticZoomSummary={{
        title: semanticZoomActivityTitle(props.data.name, `Untitled ${taskExecutor}`),
        typeLabel: taskExecutor,
      }}
      semanticZoomBranchSources={[
        { id: 'approved', ariaLabel: 'Approved branch output' },
        { id: 'rejected', ariaLabel: 'Rejected branch output' },
      ]}
    >
      <>
        <StandardNodeHeader
          icon={iconNode}
          title={props.data.name ?? 'Untitled Approval'}
          subtitle={taskExecutor}
          expandable={metadata.expandable}
          menuActions={menuActions}
        />
        <Flex justifyContent={{ default: 'justifyContentFlexEnd' }} gap={{ default: 'gapNone' }}>
          <FlexItem grow={{ default: 'grow' }} style={{ minWidth: 0 }}>
            <NodeBody>
              {approvalConfig.approver_timeout != null && (
                <SynDetailList>{renderText('Timeout', `${approvalConfig.approver_timeout}s`)}</SynDetailList>
              )}
            </NodeBody>
          </FlexItem>
          <div style={{ paddingBottom: 'var(--pf-t--global--spacer--md)' }}>
            <BranchHandles>
              <BranchHandle id="approved" nodeId={props.data.id} ariaLabel="Approved branch output">
                Approved
              </BranchHandle>
              <BranchHandle id="rejected" nodeId={props.data.id} ariaLabel="Rejected branch output">
                Rejected
              </BranchHandle>
            </BranchHandles>
          </div>
        </Flex>
      </>
    </NodeComponent>
  )
}
