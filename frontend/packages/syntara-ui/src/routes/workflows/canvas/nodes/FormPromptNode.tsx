import { Flex, FlexItem } from '@patternfly/react-core'
import { ActivityTypeEnum, EdgeHandleEnum, type Activity } from '@syntara/contracts'
import { type Node, type NodeProps } from '@xyflow/react'

import { SynDetailList } from '../../../../components/details/SynDetailList'
import { NodeBody } from '../../../../components/nodes/NodeBody'
import { NodeComponent } from '../../../../components/nodes/NodeComponent'
import { FlowNodeType } from '../../../../constants'
import type { ActivityStatus } from '../../execution/types'
import { getNodeTypeColor } from '../nodeTypeColors'
import { semanticZoomActivityTitle } from '../semanticZoom'

import { BranchHandle, BranchHandles } from './common/BranchHandle'
import { renderText } from './common/detailRenderers'
import { StandardNodeHeader } from './common/StandardNodeHeader'
import { MenuNodeType, useNodeMenuActions } from './hooks/useNodeMenuActions'
import { nodeMetadata } from './nodeMetadata'
import { renderNodeIcon } from './renderNodeIcon'

export type FormPromptNode = { type: 'form_prompt' } & Node<Activity>

export function FormPromptNodeComponent(props: NodeProps<FormPromptNode>) {
  const metadata = nodeMetadata.form_prompt
  const menuActions = useNodeMenuActions({
    nodeId: props.data.id,
    nodeType: MenuNodeType.ACTIVITY,
    disabled: props.data.settings?.disabled ?? false,
  })

  const iconNode = renderNodeIcon(
    metadata.icon,
    'form_prompt',
    'canvas',
    getNodeTypeColor(ActivityTypeEnum.FORM_PROMPT)
  )
  const taskExecutor = metadata.label

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

  const parameters = (props.data.parameters ?? {}) as {
    form_definition?: { fields?: unknown[] }
  }
  const fieldCount = parameters.form_definition?.fields?.length ?? 0

  return (
    <NodeComponent
      className={metadata.className}
      nodeProps={props}
      disableSource
      collapsible={false}
      executionState={executionState}
      showExecutionBadge={showExecutionBadge}
      topBarColor={getNodeTypeColor(FlowNodeType.FORM_PROMPT)}
      semanticZoomSummary={{
        title: semanticZoomActivityTitle(props.data.name, `Untitled ${taskExecutor}`),
        typeLabel: taskExecutor,
      }}
      semanticZoomBranchSources={[
        { id: EdgeHandleEnum.SUBMITTED, ariaLabel: 'Submitted branch output' },
        { id: EdgeHandleEnum.FALLBACK, ariaLabel: 'Fallback branch output' },
      ]}
    >
      <>
        <StandardNodeHeader
          icon={iconNode}
          title={props.data.name ?? 'Untitled Form'}
          subtitle={taskExecutor}
          expandable={metadata.expandable}
          menuActions={menuActions}
        />
        <Flex justifyContent={{ default: 'justifyContentFlexEnd' }} gap={{ default: 'gapNone' }}>
          <FlexItem grow={{ default: 'grow' }} style={{ minWidth: 0 }}>
            <NodeBody>
              <SynDetailList>{renderText('Fields', String(fieldCount))}</SynDetailList>
            </NodeBody>
          </FlexItem>
          <div style={{ paddingBottom: 'var(--pf-t--global--spacer--md)' }}>
            <BranchHandles>
              <BranchHandle id={EdgeHandleEnum.SUBMITTED} nodeId={props.data.id} ariaLabel="Submitted branch output">
                Submitted
              </BranchHandle>
              <BranchHandle id={EdgeHandleEnum.FALLBACK} nodeId={props.data.id} ariaLabel="Fallback branch output">
                Fallback
              </BranchHandle>
            </BranchHandles>
          </div>
        </Flex>
      </>
    </NodeComponent>
  )
}
