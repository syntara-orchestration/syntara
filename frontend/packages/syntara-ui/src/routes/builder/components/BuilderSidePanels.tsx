import { FlexItem } from '@patternfly/react-core'
import type { ExecutionsAPI, WorkflowAPI } from '@syntara/contracts'
import { memo } from 'react'

import type { PaginationFooterProps } from '../../../components/table/PaginationFooter'
import type { FilterConfig } from '../../../types/filters'
import { AddStepPanel } from '../AddStepPanel'
import type { BuilderAction } from '../builderReducer'
import { WorkflowHistoryCard } from '../WorkflowHistoryCard'
import { WorkflowSidepanel } from '../WorkflowSidepanel'

type Execution = ExecutionsAPI.components['schemas']['ExecutionRead']
type WorkflowWithVersion = WorkflowAPI.components['schemas']['WorkflowReadWithVersion']

type BuilderSidePanelsProps = {
  isAddStepPanelOpen: boolean
  isStepEditorOpen: boolean
  canEdit: boolean
  sourceNodeId: string | null
  replacementNodeId: string | null
  hasNoWorkflowSteps: boolean
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
}

export const BuilderSidePanels = memo(function BuilderSidePanels({
  isAddStepPanelOpen,
  isStepEditorOpen,
  canEdit,
  sourceNodeId,
  replacementNodeId,
  hasNoWorkflowSteps,
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
}: Readonly<BuilderSidePanelsProps>) {
  return (
    <>
      {isAddStepPanelOpen && !isStepEditorOpen && canEdit && (
        <FlexItem style={{ flexShrink: 0, alignSelf: 'stretch' }}>
          <AddStepPanel
            onClose={() => dispatch({ type: 'CLOSE_ADD_NODE_PANEL' })}
            onSelectStep={(stepTypeId, stepSubtypeId) =>
              dispatch({
                type: 'OPEN_NODE_EDITOR_ADD',
                payload: { stepTypeId, stepSubtypeId: stepSubtypeId ?? null },
              })
            }
            sourceNodeId={sourceNodeId}
            replacementNodeId={replacementNodeId}
            hasNoWorkflowSteps={hasNoWorkflowSteps}
          />
        </FlexItem>
      )}

      {!isStepEditorOpen && historyCardOpen && !isNew && (
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

      {!isStepEditorOpen && detailsOpen && workflow && (
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
