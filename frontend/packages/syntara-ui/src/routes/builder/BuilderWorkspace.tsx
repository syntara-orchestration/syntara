import { Flex, FlexItem, StackItem } from '@patternfly/react-core'

import { SynPanel } from '../../components/layout/SynPanel'
import { SynPanelStack, SynPanelStackItem } from '../../components/layout/SynPanelStack'
import { detachPromise } from '../../utils/detachPromise'
import { ApprovalSidePanel } from '../executions/ApprovalSidePanel'

import styles from './BuilderContent.module.css'
import { BuilderFlow } from './BuilderFlow'
import type { useBuilderSession } from './builderSession'
import type { useBuilderWorkspace } from './builderWorkspaceState'
import { BuilderSidePanels } from './components/BuilderSidePanels'
import { ExecutionDetailsPanelWrapper } from './components/ExecutionDetailsPanelWrapper'
import { StepEditorOverlay } from './components/StepEditorOverlay'
import { VersionHistorySidePanel } from './components/VersionHistorySidePanel'
import type { useBuilderVersionPanel } from './hooks/useBuilderVersionPanel'
import { StepEditorAutoSubmitContext, type useStepEditorAutoSubmitRef } from './hooks/useStepEditorAutoSubmit'
import { useWorkflowMetadata } from './hooks/useWorkflowMetadata'
import type { BuilderContentProps } from './types/builderContent'
import { VersionInfoCard } from './VersionInfoCard'

type Session = ReturnType<typeof useBuilderSession>
type VersionPanel = ReturnType<typeof useBuilderVersionPanel>

export function BuilderWorkspace({
  workflow,
  workflowId,
  isNew,
  session,
  workspace,
  versionPanel,
  autoSubmitRef,
}: Pick<BuilderContentProps, 'workflow' | 'workflowId' | 'isNew'> & {
  session: Session
  workspace: ReturnType<typeof useBuilderWorkspace>
  versionPanel: VersionPanel
  autoSubmitRef: ReturnType<typeof useStepEditorAutoSubmitRef>
}) {
  const {
    builderPermissions,
    builderProjectId,
    stepTypePermissions,
    workflowPermissionChecks,
    dispatch,
    setLocation,
    executionsQuery,
    handleExecutionNavigate,
    executionFilters,
    handleExecutionFilterChange,
    executionPaginationFooterProps,
    isStepEditorOpen,
    isAddStepPanelOpen,
    hasNoWorkflowSteps,
  } = session
  const { markDirty } = session.store
  const {
    selectedNode,
    sourceNodeId,
    sourceHandle,
    edgeIdToReplace,
    copiedRunActivityIds,
    mostRecentExecutionId,
    historyCardOpen,
    detailsOpen,
    workflowName,
    workflowDescription,
    stepEditorMode,
    stepEditorStepTypeId,
    stepEditorStepSubtypeId,
    replacementNodeId,
    confirmDialogOpen,
    newNodeDesiredPosition,
    validationErrors,
  } = session.state
  const workflowMetadata = useWorkflowMetadata(workflow)
  return (
    <StackItem isFilled className={styles.filledMinHeight}>
      <Flex
        alignItems={{ default: 'alignItemsStretch' }}
        flexWrap={{ default: 'nowrap' }}
        gap={{ default: 'gapSm' }}
        className={styles.canvasFlex}
      >
        <FlexItem
          className={styles.canvasFlexItem}
          style={{ pointerEvents: isStepEditorOpen && !versionPanel.isViewingVersion ? 'none' : 'auto' }}
        >
          <SynPanelStack>
            {workspace.showCanvas && (
              <SynPanelStackItem isFilled>
                <SynPanel hasNoPadding isFullHeight className={styles.canvasPanel}>
                  <VersionInfoCard
                    title={versionPanel.viewedVersionName}
                    date={versionPanel.viewedVersionDate}
                    description={versionPanel.viewedVersionDescription}
                    publishedAt={versionPanel.viewedVersionPublishedAt}
                    unpublishedAt={versionPanel.viewedVersionUnpublishedAt}
                  />
                  <BuilderFlow
                    workflowId={workflowId}
                    readOnly={versionPanel.isViewingVersion || !stepTypePermissions.canAuthor}
                    canEdit={workflowPermissionChecks.canEdit}
                    panelOpen={isAddStepPanelOpen || !!selectedNode}
                    activeEdgeButtonNodeId={isAddStepPanelOpen ? sourceNodeId : null}
                    activeEdgeButtonHandle={isAddStepPanelOpen ? sourceHandle : null}
                    activeEdgeId={isAddStepPanelOpen ? edgeIdToReplace : null}
                    executionStatus={workspace.canvasExecutionStatus}
                    copiedRunActivityIds={copiedRunActivityIds}
                    disableDeleteKey={isStepEditorOpen}
                    disableSpacePanning={isStepEditorOpen || confirmDialogOpen}
                    onNodeClick={workspace.wrappedHandleNodeClick}
                    onAddNodeFromEdge={workspace.handleAddNodeFromEdge}
                    onNodesDeleted={workspace.handleNodesDeleted}
                    newNodeDesiredPosition={newNodeDesiredPosition}
                    onClearDesiredPosition={workspace.handleClearDesiredPosition}
                    validationErrors={validationErrors}
                  />
                </SynPanel>
              </SynPanelStackItem>
            )}
            {workspace.showMostRecentRunPanelInEditor && mostRecentExecutionId && (
              <ExecutionDetailsPanelWrapper
                executionId={mostRecentExecutionId}
                workflowDefinition={workflow?.version?.workflow_definition}
                selectedNodeId={workspace.mostRecentSelectedNodeId}
                selectedNodeName={workspace.mostRecentSelectedNodeName}
                onNodeSelect={workspace.handleMostRecentNodeSelect}
                panelHeight={workspace.mostRecentPanelHeight}
                onResize={workspace.handleMostRecentResize}
                isTerminalStatus={workspace.isTerminalStatus}
                onClosePanel={workspace.handleCloseMostRecentRunPanel}
                isPanelExpanded={workspace.isPanelExpanded}
                panelExpandControl={workspace.panelExpandControl}
              />
            )}
          </SynPanelStack>
        </FlexItem>
        <BuilderSidePanels
          isAddStepPanelOpen={isAddStepPanelOpen}
          isStepEditorOpen={isStepEditorOpen}
          canEdit={builderPermissions.canEdit}
          sourceNodeId={sourceNodeId}
          replacementNodeId={replacementNodeId}
          hasNoWorkflowSteps={hasNoWorkflowSteps}
          projectId={builderProjectId}
          dispatch={dispatch}
          historyCardOpen={historyCardOpen}
          isNew={isNew}
          executions={executionsQuery.data?.resources ?? []}
          onExecutionNavigate={handleExecutionNavigate}
          executionFilters={executionFilters}
          onFilterChange={handleExecutionFilterChange}
          executionPaginationFooterProps={executionPaginationFooterProps}
          detailsOpen={detailsOpen}
          workflow={workflow}
          workflowName={workflowName}
          workflowDescription={workflowDescription}
          markDirty={markDirty}
        />

        {!isStepEditorOpen && workspace.approvalViewOpen && workspace.pendingApproval && (
          <FlexItem className={styles.approvalPanelSlot}>
            <ApprovalSidePanel
              approval={workspace.pendingApproval}
              message={workspace.approvalMessage}
              onClose={workspace.handleApprovalClose}
              onDecisionSubmitted={workspace.handleApprovalDismiss}
              onNavigate={setLocation}
            />
          </FlexItem>
        )}

        <VersionHistorySidePanel
          sidePanel={versionPanel.versionSidePanel}
          isStepEditorOpen={isStepEditorOpen}
          projectId={builderProjectId}
          editPermission={{
            canEdit: builderPermissions.canEdit,
            tooltip: builderPermissions.tooltips.edit,
            canCreate: builderPermissions.canCreate,
            createTooltip: builderPermissions.tooltips.create,
          }}
        />

        <StepEditorAutoSubmitContext.Provider value={autoSubmitRef}>
          <StepEditorOverlay
            isOpen={isStepEditorOpen}
            mode={stepEditorMode}
            selectedNode={selectedNode}
            stepTypeId={stepEditorStepTypeId}
            stepSubtypeId={stepEditorStepSubtypeId}
            sourceNodeId={sourceNodeId}
            replacementNodeId={replacementNodeId}
            executionId={mostRecentExecutionId}
            workflowId={workflowId}
            onConnect={workspace.handleConnectFromPanel}
            onClose={workspace.handleCloseStepEditor}
            onNavigateToStep={workspace.handleNavigateToStep}
            onAddStep={workspace.handleAddStepFromPanel}
            projectId={builderProjectId}
            workflowMetadata={workflowMetadata}
            onRunStep={selectedNode ? () => detachPromise(workspace.handleRunStep(selectedNode.id)) : undefined}
            readOnly={!builderPermissions.canEdit}
          />
        </StepEditorAutoSubmitContext.Provider>
      </Flex>
    </StackItem>
  )
}
