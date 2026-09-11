import { Flex, FlexItem, Tooltip } from '@patternfly/react-core'
import { EdgeHandleEnum, type SwitchActivity, type SwitchConfig } from '@syntara/contracts'
import { type Node, type NodeProps } from '@xyflow/react'
import { useEffect, useRef, useState } from 'react'

import { SynDetailList } from '../../../../components/details/SynDetailList'
import { RegistryNodeId } from '../../../../constants'
import { buildSwitchCasePort } from '../../../builder/utils/switchCaseHelpers'
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
import styles from './SwitchNode.module.css'

function TruncatedPathLabel({ label }: Readonly<{ label: string }>) {
  const ref = useRef<HTMLDivElement>(null)
  const [isTruncated, setIsTruncated] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const checkTruncation = () => setIsTruncated(el.scrollHeight > el.clientHeight)
    checkTruncation()

    const observer = new ResizeObserver(checkTruncation)
    observer.observe(el)
    return () => observer.disconnect()
  }, [label])

  const content = (
    <div ref={ref} className={styles.truncatedLabel}>
      {label}
    </div>
  )

  if (isTruncated) {
    return <Tooltip content={label}>{content}</Tooltip>
  }

  return content
}

export type SwitchNode = { type: 'switch' } & Node<SwitchActivity>

export function SwitchNodeComponent(props: NodeProps<SwitchNode>) {
  const metadata = nodeMetadata.switch
  const iconNode = renderNodeIcon(metadata.icon, RegistryNodeId.LOGIC_SWITCH, 'canvas', getNodeTypeColor('switch'))
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

  const config = (props.data.parameters ?? { cases: [] }) as SwitchConfig
  const cases = config.cases ?? []

  const branchSources = [
    ...cases.map((c, i) => ({
      id: c.port || buildSwitchCasePort(i),
      ariaLabel: `${c.label || `Path ${i + 1}`} branch output`,
    })),
    { id: EdgeHandleEnum.DEFAULT, ariaLabel: 'Fallback branch output' },
  ]

  return (
    <NodeComponent
      className={metadata.className}
      nodeProps={props}
      disableSource
      executionState={executionState}
      topBarColor={getNodeTypeColor('switch')}
      semanticZoomSummary={{
        title: semanticZoomActivityTitle(props.data.name, `Untitled ${metadata.label}`),
        typeLabel: metadata.label,
      }}
      semanticZoomBranchSources={branchSources}
    >
      <SwitchNodeDetails switchActivity={props.data} icon={iconNode} menuActions={menuActions}>
        <BranchHandles>
          {cases.map((c, i) => (
            <BranchHandle
              key={c.port || buildSwitchCasePort(i)}
              id={c.port || buildSwitchCasePort(i)}
              nodeId={props.data.id}
              ariaLabel={`${c.label || `Path ${i + 1}`} branch output`}
            >
              <TruncatedPathLabel label={c.label || `Path ${i + 1}`} />
            </BranchHandle>
          ))}
          <BranchHandle id={EdgeHandleEnum.DEFAULT} nodeId={props.data.id} ariaLabel="Fallback branch output">
            Fallback
          </BranchHandle>
        </BranchHandles>
      </SwitchNodeDetails>
    </NodeComponent>
  )
}

function SwitchNodeDetails(props: {
  switchActivity: SwitchActivity
  children?: React.ReactNode
  showJson?: boolean
  icon?: React.ReactNode
  menuActions?: ReturnType<typeof useNodeMenuActions>
}) {
  const metadata = nodeMetadata.switch

  return (
    <>
      <StandardNodeHeader
        icon={props.icon}
        title={props.switchActivity.name ?? 'Untitled Switch'}
        subtitle={metadata.label}
        menuActions={props.menuActions}
      />
      <Flex justifyContent={{ default: 'justifyContentFlexEnd' }} gap={{ default: 'gapNone' }}>
        <FlexItem grow={{ default: 'grow' }} className={styles.nodeBodyWrapper}>
          <NodeBody>
            <SynDetailList>
              {renderOutputs(props.switchActivity.outputs)}
              {renderJson(props.switchActivity, props.showJson, 'Full Definition')}
            </SynDetailList>
          </NodeBody>
        </FlexItem>
        <div className={styles.branchHandlesWrapper}>{props.children}</div>
      </Flex>
    </>
  )
}
