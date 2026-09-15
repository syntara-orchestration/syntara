import { FlexItem } from '@patternfly/react-core'
import type { ExecutionsAPI, WorkflowAPI } from '@syntara/contracts'
import { memo } from 'react'

import type { PaginationFooterProps } from '../../../components/table/PaginationFooter'
import type { FilterConfig } from '../../../types/filters'
import { AddNodePanel } from '../AddNodePanel'
import type { BuilderAction } from '../builderReducer'
import { WorkflowHistoryCard } from '../WorkflowHistoryCard'
import { WorkflowSidepanel } from '../WorkflowSidepanel'

type Execution = ExecutionsAPI.components['schemas']['ExecutionRead']
type WorkflowWithVersion = WorkflowAPI.components['schemas']['WorkflowReadWithVersion']

type BuilderSidePanelsProps = {
  isAddNodePanelOpen: boolean
  isNodeEditorOpen: boolean
  canEdit: boolean
  sourceNodeId: string | null
  replacementNodeId: string | null
  hasNoWorkflowNodes: boolean
  dispatch: React.Dispatch<BuilderAction>
  historyCardOpen: boolean
  isNew: boolean
  executions: Execution[]
  onExecutionNavigate: (id: string) => void
  executionFilters: FilterConfig[]
  onFilterChange: (filters: FilterConfig[]) => void
  executionPaginationFooterProps: PaginationFooterProps
  detailsOpen: boolean
  workflow?: WorkflowWithVersion
  workflowName: string
  workflowDescription: string
  markDirty: () => void
  projectId?: string
}

export const BuilderSidePanels = memo(function BuilderSidePanels({
  isAddNodePanelOpen,
  isNodeEditorOpen,
  canEdit,
  sourceNodeId,
  replacementNodeId,
  hasNoWorkflowNodes,
  dispatch,
  historyCardOpen,
  isNew,
  executions,
  onExecutionNavigate,
  executionFilters,
  onFilterChange,
  executionPaginationFooterProps,
  detailsOpen,
  workflow,
  workflowName,
  workflowDescription,
  markDirty,
  projectId,
}: Readonly<BuilderSidePanelsProps>) {
  return (
    <>
      {isAddNodePanelOpen && !isNodeEditorOpen && canEdit && (
        <FlexItem style={{ flexShrink: 0, alignSelf: 'stretch' }}>
          <AddNodePanel
            onClose={() => dispatch({ type: 'CLOSE_ADD_NODE_PANEL' })}
            onSelectNode={(nodeTypeId, nodeSubtypeId) =>
              dispatch({
                type: 'OPEN_NODE_EDITOR_ADD',
                payload: { nodeTypeId, nodeSubtypeId: nodeSubtypeId ?? null },
              })
            }
            sourceNodeId={sourceNodeId}
            replacementNodeId={replacementNodeId}
            hasNoWorkflowNodes={hasNoWorkflowNodes}
            projectId={projectId}
          />
        </FlexItem>
      )}

      {!isNodeEditorOpen && historyCardOpen && !isNew && (
        <FlexItem style={{ flexShrink: 0, alignSelf: 'stretch' }}>
          <WorkflowHistoryCard
            executions={executions}
            onClose={() => dispatch({ type: 'SET_HISTORY_CARD_OPEN', payload: false })}
            onExecutionSelect={onExecutionNavigate}
            filters={executionFilters}
            onFilterChange={onFilterChange}
            paginationFooterProps={executionPaginationFooterProps}
          />
        </FlexItem>
      )}

      {!isNodeEditorOpen && detailsOpen && workflow && (
        <FlexItem style={{ flexShrink: 0, alignSelf: 'stretch' }}>
          <WorkflowSidepanel
            workflow={workflow}
            workflowName={workflowName}
            workflowDescription={workflowDescription}
            onNameChange={(name) => {
              dispatch({ type: 'SET_WORKFLOW_NAME', payload: name })
              markDirty()
            }}
            onDescriptionChange={(desc) => {
              dispatch({ type: 'SET_WORKFLOW_DESCRIPTION', payload: desc })
              markDirty()
            }}
            onClose={() => dispatch({ type: 'SET_DETAILS_OPEN', payload: false })}
          />
        </FlexItem>
      )}
    </>
  )
})
