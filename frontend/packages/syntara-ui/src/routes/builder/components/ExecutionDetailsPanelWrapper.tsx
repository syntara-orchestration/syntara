import { SynPanelStackItem } from '../../../components/layout/SynPanelStack'
import { ResizableDivider } from '../../../components/ResizableDivider'
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
  } = props

  return (
    <>
      <ResizableDivider onResize={onResize} />
      <SynPanelStackItem style={{ height: `${String(panelHeight)}px` }}>
        <ExecutionDetailsPanel
          executionId={executionId}
          workflowDefinition={workflowDefinition}
          selectedNodeId={selectedNodeId}
          selectedNodeName={selectedNodeName}
          onNodeSelect={onNodeSelect}
          headerLabel="Most recent run details"
          onClosePanel={isTerminalStatus ? onClosePanel : undefined}
        />
      </SynPanelStackItem>
    </>
  )
}
