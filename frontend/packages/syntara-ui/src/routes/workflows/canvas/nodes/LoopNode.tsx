import { Badge, Flex } from '@patternfly/react-core'
import type { LoopActivity } from '@syntara/contracts'
import { type Node, type NodeProps } from '@xyflow/react'

import { SynStep } from '../../../../components/steps/SynStep'
import type { ActivityStatus } from '../../execution/types'
import { semanticZoomActivityTitle } from '../semanticZoom'
import { getStepTypeColor } from '../stepTypeColors'

import { BranchHandle, BranchHandles } from './common/BranchHandle'
import { StandardStepHeader } from './common/StandardStepHeader'
import { useLoopIterationCount } from './hooks/useLoopIterationCount'
import { StepMenuCategory, useStepMenuActions } from './hooks/useStepMenuActions'
import styles from './LoopNode.module.css'
import { renderStepIcon } from './renderStepIcon'
import { stepMetadata } from './stepMetadata'

export type LoopNode = { type: 'loop' } & Node<LoopActivity>

export function LoopStepComponent(props: NodeProps<LoopNode>) {
  const metadata = stepMetadata.loop
  const iconNode = renderStepIcon(metadata.icon, 'logic-loop', 'canvas', getStepTypeColor('loop'))
  const menuActions = useStepMenuActions({
    nodeId: props.data.id,
    stepCategory: StepMenuCategory.CONTROL_FLOW,
  })
  const iterationCount = useLoopIterationCount(props.data.id)

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
      disableSource // Disable default source handle since we use BranchHandles instead
      enableEnd={metadata.enableEnd}
      enableStart={metadata.enableStart}
      nodeProps={props}
      executionState={executionState}
      topBarColor={getStepTypeColor('loop')}
      semanticZoomSummary={{
        title: semanticZoomActivityTitle(props.data.name, `Untitled ${metadata.label}`),
        typeLabel: metadata.label,
      }}
      semanticZoomBranchSources={[
        { id: 'done', ariaLabel: 'Done branch output' },
        { id: 'loop', ariaLabel: 'Loop branch output' },
      ]}
    >
      <StandardStepHeader
        icon={iconNode}
        title={props.data.name ?? ''}
        subtitle={metadata.label}
        menuActions={menuActions}
      />
      <Flex justifyContent={{ default: 'justifyContentFlexEnd' }} className={styles.branchHandlesWrapper}>
        <BranchHandles>
          <BranchHandle id="done" nodeId={props.data.id} ariaLabel="Done branch output">
            Done
          </BranchHandle>
          <BranchHandle
            id="loop"
            nodeId={props.data.id}
            ariaLabel="Loop branch output"
            badge={
              iterationCount != null ? (
                <Badge
                  isRead
                  screenReaderText={`${iterationCount} ${iterationCount === 1 ? 'loop iteration' : 'loop iterations'}`}
                >
                  {iterationCount}
                </Badge>
              ) : undefined
            }
          >
            Loop
          </BranchHandle>
        </BranchHandles>
      </Flex>
    </SynStep>
  )
}
