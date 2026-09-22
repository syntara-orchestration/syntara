import { Flex, FlexItem } from '@patternfly/react-core'
import { ActivityTypeEnum, EdgeHandleEnum, type PermissionCheckActivity } from '@syntara/contracts'
import { type Node, type NodeProps } from '@xyflow/react'

import { SynDetailList } from '../../../../components/details/SynDetailList'
import { NodeBody } from '../../../../components/nodes/NodeBody'
import { NodeComponent } from '../../../../components/nodes/NodeComponent'
import { RegistryNodeId } from '../../../../constants'
import type { ActivityStatus } from '../../execution/types'
import { getNodeTypeColor } from '../nodeTypeColors'
import { semanticZoomActivityTitle } from '../semanticZoom'

import { BranchHandle, BranchHandles } from './common/BranchHandle'
import { renderJson, renderOutputs } from './common/detailRenderers'
import { StandardNodeHeader } from './common/StandardNodeHeader'
import { MenuNodeType, useNodeMenuActions } from './hooks/useNodeMenuActions'
import { nodeMetadata } from './nodeMetadata'
import { renderNodeIcon } from './renderNodeIcon'

export type PermissionCheckNode = { type: 'permission_check' } & Node<PermissionCheckActivity>

export function PermissionCheckNodeComponent(props: NodeProps<PermissionCheckNode>) {
  const metadata = nodeMetadata.permission_check
  const iconNode = renderNodeIcon(
    metadata.icon,
    RegistryNodeId.LOGIC_PERMISSION_CHECK,
    'canvas',
    getNodeTypeColor(ActivityTypeEnum.PERMISSION_CHECK)
  )
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

  return (
    <NodeComponent
      className={metadata.className}
      nodeProps={props}
      disableSource
      collapsible={false}
      executionState={executionState}
      topBarColor={getNodeTypeColor(ActivityTypeEnum.PERMISSION_CHECK)}
      semanticZoomSummary={{
        title: semanticZoomActivityTitle(props.data.name, `Untitled ${metadata.label}`),
        typeLabel: metadata.label,
      }}
      semanticZoomBranchSources={[
        { id: EdgeHandleEnum.ALLOWED, ariaLabel: 'Allowed branch output' },
        { id: EdgeHandleEnum.DENIED, ariaLabel: 'Denied branch output' },
      ]}
    >
      <PermissionCheckNodeDetails permissionCheckActivity={props.data} icon={iconNode} menuActions={menuActions}>
        <BranchHandles>
          <BranchHandle id={EdgeHandleEnum.ALLOWED} nodeId={props.data.id} ariaLabel="Allowed branch output">
            Allowed
          </BranchHandle>
          <BranchHandle id={EdgeHandleEnum.DENIED} nodeId={props.data.id} ariaLabel="Denied branch output">
            Denied
          </BranchHandle>
        </BranchHandles>
      </PermissionCheckNodeDetails>
    </NodeComponent>
  )
}

export function PermissionCheckNodeDetails(props: {
  permissionCheckActivity: PermissionCheckActivity
  children?: React.ReactNode
  showJson?: boolean
  icon?: React.ReactNode
  menuActions?: ReturnType<typeof useNodeMenuActions>
}) {
  const metadata = nodeMetadata.permission_check

  return (
    <>
      <StandardNodeHeader
        icon={props.icon}
        title={props.permissionCheckActivity.name ?? 'Untitled permission check'}
        subtitle={metadata.label}
        expandable={metadata.expandable}
        menuActions={props.menuActions}
      />
      <Flex justifyContent={{ default: 'justifyContentFlexEnd' }} gap={{ default: 'gapNone' }}>
        <FlexItem grow={{ default: 'grow' }} style={{ minWidth: 0 }}>
          <NodeBody>
            <SynDetailList>
              {renderOutputs(props.permissionCheckActivity.outputs)}
              {renderJson(props.permissionCheckActivity, props.showJson, 'Full Definition')}
            </SynDetailList>
          </NodeBody>
        </FlexItem>
        <div style={{ paddingBottom: 'var(--pf-t--global--spacer--md)' }}>{props.children}</div>
      </Flex>
    </>
  )
}
