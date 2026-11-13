import { SynPanelStackItem } from '../../../components/layout/SynPanelStack'
import { ResizableDivider } from '../../../components/ResizableDivider'
import type { RunDetailsPanelExpandControl } from '../../executions/RunDetailsPanelExpandButton'
import { ExecutionDetailsPanel } from '../ExecutionDetailsPanel'

type ExecutionDetailsPanelWrapperProps = {
  executionId: string
  workflowDefinition: Parameters<typeof ExecutionDetailsPanel>[0]['workflowDefinition']
  selectedNodeId: string | null
  selectedNodeName: string | null
  onNodeSelect: (nodeId: string, nodeName: string) => void
  panelHeight: number
  onResize: (newHeight: number) => void
  isTerminalStatus: boolean
  onClosePanel?: () => void
  isPanelExpanded: boolean
  panelExpandControl?: RunDetailsPanelExpandControl
}

export function ExecutionDetailsPanelWrapper(props: ExecutionDetailsPanelWrapperProps) {
  const {
    executionId,
    workflowDefinition,
    selectedNodeId,
    selectedNodeName,
    onNodeSelect,
    panelHeight,
    onResize,
    isTerminalStatus,
    onClosePanel,
    isPanelExpanded,
    panelExpandControl,
  } = props

  return (
    <>
      {!isPanelExpanded && <ResizableDivider onResize={onResize} />}
      <SynPanelStackItem
        isFilled={isPanelExpanded}
        style={isPanelExpanded ? { minHeight: 0 } : { height: `${String(panelHeight)}px` }}
      >
        <ExecutionDetailsPanel
          executionId={executionId}
          workflowDefinition={workflowDefinition}
          selectedNodeId={selectedNodeId}
          selectedNodeName={selectedNodeName}
          onNodeSelect={onNodeSelect}
          headerLabel="Most recent run details"
          onClosePanel={isTerminalStatus ? onClosePanel : undefined}
          panelExpandControl={panelExpandControl}
        />
      </SynPanelStackItem>
    </>
  )
}
