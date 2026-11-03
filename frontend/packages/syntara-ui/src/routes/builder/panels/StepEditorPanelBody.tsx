import { Flex, FlexItem, Panel, PanelMain, PanelMainBody } from '@patternfly/react-core'
import type { Node } from '@xyflow/react'
import type { ReactNode } from 'react'

import { ResizableColumnDivider } from '../../../components/ResizableColumnDivider'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { WorkflowMetadata } from '../types/workflowMetadata'

import { useAdjacentSteps } from './hooks/useAdjacentSteps'
import { useResizablePanels } from './hooks/useResizablePanels'
import { InputPanel } from './InputPanel'
import { OutputPanel } from './OutputPanel'
import { RightSidePill } from './RightSidePill'
import styles from './StepEditorPanelBody.module.css'
import { StepPanelNavigationArrow } from './StepPanelNavigationArrow'

type StepEditorPanelBodyProps = {
  showInputPanel: boolean
  showNavigation: boolean
  nodeId?: string
  node?: Node<NodeType['data']>
  sourceNodeId?: string | null
  inputData: Record<string, Record<string, unknown>> | null
  outputData: Record<string, unknown> | null
  parametersContent: ReactNode
  onNavigateToStep?: (nodeId: string) => void
  onAddStep?: (handle?: string) => void
  workflowMetadata?: WorkflowMetadata
}

export function StepEditorPanelBody({
  showInputPanel,
  showNavigation,
  nodeId,
  node,
  sourceNodeId,
  inputData,
  outputData,
  parametersContent,
  onNavigateToStep,
  onAddStep,
  workflowMetadata,
}: Readonly<StepEditorPanelBodyProps>) {
  const { upstream, downstream } = useAdjacentSteps(showNavigation ? nodeId : undefined)
  const showPreviousArrow = showNavigation && upstream.length > 0 && onNavigateToStep != null
  const showNextArrow = showNavigation && downstream.length > 0 && onNavigateToStep != null
  const showAddStepPill = onAddStep != null

  const panelCount: 2 | 3 = showInputPanel ? 3 : 2
  const { widths, handleResize, handleResizeEnd, containerRef } = useResizablePanels({
    panelCount,
    workflowId: workflowMetadata?.id,
    nodeId,
  })

  const paramsIndex = showInputPanel ? 1 : 0
  const outputIndex = showInputPanel ? 2 : 1
  const safeNodeId = nodeId ?? ''

  return (
    <Flex
      alignItems={{ default: 'alignItemsStretch' }}
      flexWrap={{ default: 'nowrap' }}
      gap={{ default: 'gapNone' }}
      className={styles.outerFlex}
    >
      {showPreviousArrow && (
        <FlexItem className={styles.navArrow}>
          <StepPanelNavigationArrow direction="previous" steps={upstream} onNavigate={onNavigateToStep} />
        </FlexItem>
      )}
      <FlexItem flex={{ default: 'flex_1' }} className={styles.contentFlex}>
        <div
          ref={containerRef}
          style={{
            display: 'flex',
            alignItems: 'stretch',
            height: '100%',
            minWidth: 0,
            paddingLeft: showPreviousArrow ? undefined : 'var(--pf-t--global--spacer--sm)',
            paddingRight: showNextArrow ? undefined : 'var(--pf-t--global--spacer--sm)',
          }}
        >
          {showInputPanel && (
            <>
              <div className={styles.panelSlot} style={{ flexBasis: `${widths[0]}%` }}>
                <InputPanel
                  nodeId={safeNodeId}
                  executionData={inputData}
                  sourceNodeId={sourceNodeId}
                  workflowMetadata={workflowMetadata}
                />
              </div>
              <ResizableColumnDivider
                onResize={handleResize.bind(null, 0)}
                onResizeEnd={handleResizeEnd}
                currentValue={Math.round(widths[0])}
                aria-label="Resize input and parameters panels"
              />
            </>
          )}
          <div className={styles.paramsSlot} style={{ flexBasis: `${widths[paramsIndex]}%` }}>
            <Panel variant="raised" className={styles.panel}>
              <PanelMain className={styles.panelMain}>
                <PanelMainBody className={styles.panelBody}>{parametersContent}</PanelMainBody>
              </PanelMain>
            </Panel>
          </div>
          <ResizableColumnDivider
            onResize={handleResize.bind(null, showInputPanel ? 1 : 0)}
            onResizeEnd={handleResizeEnd}
            currentValue={Math.round(widths[paramsIndex])}
            aria-label="Resize parameters and output panels"
          />
          <div className={styles.panelSlot} style={{ flexBasis: `${widths[outputIndex]}%` }}>
            <OutputPanel outputData={outputData} nodeId={safeNodeId} />
          </div>
        </div>
      </FlexItem>
      {(showNextArrow || showAddStepPill) && (
        <FlexItem className={styles.navArrow}>
          <Flex direction={{ default: 'column' }} gap={{ default: 'gapNone' }}>
            {showNextArrow && (
              <FlexItem>
                <StepPanelNavigationArrow direction="next" steps={downstream} onNavigate={onNavigateToStep} />
              </FlexItem>
            )}
            {showAddStepPill && (
              <FlexItem>
                <RightSidePill node={node} onAddStep={onAddStep} />
              </FlexItem>
            )}
          </Flex>
        </FlexItem>
      )}
    </Flex>
  )
}
