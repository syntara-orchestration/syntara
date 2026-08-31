import { List, ListItem, Stack, StackItem } from '@patternfly/react-core'
import type { WorkflowAPI } from '@syntara/contracts'
import { useCallback, useState } from 'react'

import { SynConfirmationDialog } from '../../components/dialogs/SynConfirmationDialog'
import type { DialogState } from '../../hooks/useDialogState'
import { useAlerts } from '../../providers/alerts'
import { detachPromise } from '../../utils/detachPromise'
import type { ProjectRead } from '../access/types'
import { ProjectFormModal } from '../access-management/ProjectFormModal'
import { RunWorkflowModal } from '../builder/components/RunWorkflowModal'
import { PublishWorkflowDialog } from '../builder/PublishWorkflowDialog'
import { hasNonEmptyInputSchema } from '../builder/utils/triggerReferenceCheck'

import { ImportWorkflowDialog } from './ImportWorkflowDialog'
import { resolveWorkflowRunTrigger, type WorkflowRunTrigger } from './resolveWorkflowRunTrigger'
import { WorkflowDeleteDialog } from './WorkflowDeleteDialog'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

type PendingRunInput = {
  workflow: Workflow
  trigger: WorkflowRunTrigger
}

/**
 * Props for WorkflowDialogs component
 */
type WorkflowDialogsProps = {
  /** Dialog state for workflow run confirmation */
  runDialog: DialogState<Workflow>
  /** Dialog state for workflow deletion confirmation */
  deleteDialog: DialogState<Workflow>
  /** Dialog state for workflow publish modal */
  publishDialog: DialogState<Workflow>
  /** Dialog state for workflow unpublish confirmation */
  unpublishDialog: DialogState<Workflow>
  /** Controls visibility of the import workflow dialog */
  importDialogOpen: boolean
  /** Callback to toggle import dialog visibility */
  setImportDialogOpen: (open: boolean) => void
  /** Dialog state for project edit modal */
  projectEditDialog: DialogState<ProjectRead>
  /** Dialog state for project deletion confirmation */
  projectDeleteDialog: DialogState<ProjectRead>
  /** Handler to execute a workflow with optional trigger inputs */
  onRunWorkflow: (workflow: Workflow, inputData?: Record<string, unknown>, triggerNodeId?: string) => void
  /** Handler to delete a workflow - dialog closes in onSettled callback */
  onDeleteWorkflow: (workflow: Workflow) => void
  /** Handler to publish a workflow - dialog closes in onSettled callback */
  onPublishWorkflow: (workflow: Workflow, publishName?: string, description?: string) => void
  /** Handler to unpublish a workflow - dialog closes in onSettled callback */
  onUnpublishWorkflow: (workflow: Workflow) => void
  /** Handler to delete a project - dialog closes in onSettled callback */
  onDeleteProject: (project: ProjectRead) => void
  /** Callback to refetch workflows list after import success */
  onRefetchWorkflows: () => void
  /** Callback to refetch projects list after project edit success */
  onRefetchProjects: () => void
  /** Loading state for workflow deletion mutation */
  isDeleting: boolean
  /** Loading state for workflow publish mutation */
  isPublishing: boolean
  /** Loading state for project deletion mutation */
  isDeletingProject: boolean
}

export function WorkflowDialogs({
  runDialog,
  deleteDialog,
  publishDialog,
  unpublishDialog,
  importDialogOpen,
  setImportDialogOpen,
  projectEditDialog,
  projectDeleteDialog,
  onRunWorkflow,
  onDeleteWorkflow,
  onPublishWorkflow,
  onUnpublishWorkflow,
  onDeleteProject,
  onRefetchWorkflows,
  onRefetchProjects,
  isDeleting,
  isPublishing,
  isDeletingProject,
}: WorkflowDialogsProps) {
  const { showError } = useAlerts()
  const [isResolvingRun, setIsResolvingRun] = useState(false)
  const [pendingRunInput, setPendingRunInput] = useState<PendingRunInput | null>(null)

  const closeRunInput = useCallback(() => {
    setPendingRunInput(null)
  }, [])

  const closeRunDialog = runDialog.close
  const workflowToRun = runDialog.item

  const handleConfirmRun = useCallback(() => {
    if (!workflowToRun) return

    setIsResolvingRun(true)
    detachPromise(
      resolveWorkflowRunTrigger(workflowToRun)
        .then((trigger) => {
          if (!trigger) {
            showError({ title: 'Cannot run workflow', description: 'Workflow has no triggers configured' })
            closeRunDialog()
            return
          }

          if (!trigger.hasTriggerReferences && !hasNonEmptyInputSchema(trigger.inputSchema)) {
            onRunWorkflow(workflowToRun, {}, trigger.triggerNodeId)
            closeRunDialog()
            return
          }

          setPendingRunInput({ workflow: workflowToRun, trigger })
          closeRunDialog()
        })
        .catch((error: unknown) => {
          showError({
            title: 'Cannot run workflow',
            description: error instanceof Error ? error.message : 'Failed to load workflow trigger details',
          })
          closeRunDialog()
        })
        .finally(() => {
          setIsResolvingRun(false)
        })
    )
  }, [closeRunDialog, onRunWorkflow, showError, workflowToRun])

  const handleRunWithInputs = useCallback(
    (inputData: Record<string, unknown>, triggerNodeId?: string) => {
      if (!pendingRunInput) return
      onRunWorkflow(pendingRunInput.workflow, inputData, triggerNodeId ?? pendingRunInput.trigger.triggerNodeId)
      setPendingRunInput(null)
    },
    [onRunWorkflow, pendingRunInput]
  )

  return (
    <>
      <SynConfirmationDialog
        isOpen={runDialog.isOpen}
        onClose={runDialog.close}
        onConfirm={handleConfirmRun}
        title={`Run ${runDialog.item?.name}?`}
        confirmLabel="Run now"
        confirmLoading={isResolvingRun}
      >
        You are about to manually run this workflow. This action will start the workflow immediately, bypassing its
        normal trigger conditions.
      </SynConfirmationDialog>

      <RunWorkflowModal
        key={pendingRunInput ? `open-${pendingRunInput.trigger.triggerNodeId}` : 'closed'}
        isOpen={pendingRunInput != null}
        onClose={closeRunInput}
        onConfirm={handleRunWithInputs}
        workflowName={pendingRunInput?.workflow.name ?? ''}
        triggerName={pendingRunInput?.trigger.triggerName ?? 'Trigger'}
        triggerNodeId={pendingRunInput?.trigger.triggerNodeId}
        inputSchema={pendingRunInput?.trigger.inputSchema}
        workflowId={pendingRunInput?.workflow.id}
      />

      <WorkflowDeleteDialog
        isOpen={deleteDialog.isOpen}
        workflowName={deleteDialog.item?.name ?? ''}
        onClose={deleteDialog.close}
        onConfirm={() => {
          if (deleteDialog.item) {
            onDeleteWorkflow(deleteDialog.item)
          }
          // Dialog closes in onSettled callback passed to useWorkflowActions
        }}
        confirmLoading={isDeleting}
      />

      <ImportWorkflowDialog
        isOpen={importDialogOpen}
        onClose={() => setImportDialogOpen(false)}
        onSuccess={onRefetchWorkflows}
      />

      <PublishWorkflowDialog
        isOpen={publishDialog.isOpen}
        isPublishing={isPublishing}
        onClose={publishDialog.close}
        onPublish={(publishName, description) => {
          if (publishDialog.item) {
            onPublishWorkflow(publishDialog.item, publishName, description)
          }
        }}
      />

      <SynConfirmationDialog
        isOpen={unpublishDialog.isOpen}
        onClose={unpublishDialog.close}
        onConfirm={() => {
          if (unpublishDialog.item) {
            onUnpublishWorkflow(unpublishDialog.item)
          }
          // Dialog closes in onSettled callback passed to useWorkflowActions
        }}
        title="Unpublish workflow?"
        confirmLabel="Unpublish"
        confirmVariant="danger"
        titleIconVariant="warning"
      >
        The workflow <strong>{unpublishDialog.item?.name}</strong> will be unpublished. It will no longer be available
        for execution until published again.
      </SynConfirmationDialog>

      <ProjectFormModal
        project={projectEditDialog.item}
        isOpen={projectEditDialog.isOpen}
        onClose={projectEditDialog.close}
        onSuccess={() => {
          onRefetchWorkflows()
          onRefetchProjects()
        }}
      />

      <SynConfirmationDialog
        isOpen={projectDeleteDialog.isOpen}
        onClose={projectDeleteDialog.close}
        onConfirm={() => {
          if (projectDeleteDialog.item) {
            onDeleteProject(projectDeleteDialog.item)
          }
          // Dialog closes in onSettled callback passed to useProjectActions
        }}
        title="Delete project?"
        confirmLabel="Delete"
        confirmVariant="danger"
        titleIconVariant="warning"
        confirmLoading={isDeletingProject}
        destructiveAcknowledgement={{
          checkboxId: 'delete-project-ack',
          label:
            'I understand this project, its workflows, and role assignments will be permanently deleted or removed.',
        }}
      >
        <Stack hasGutter>
          <StackItem>
            The project <strong>{projectDeleteDialog.item?.name}</strong> will be deleted. This cannot be undone.
          </StackItem>
          <StackItem>
            <List>
              <ListItem>All workflows in this project will be permanently deleted.</ListItem>
              <ListItem>All project role assignments will be removed.</ListItem>
              <ListItem>
                Uploaded files are kept after the project is deleted. There is no in-product list or delete flow for
                them yet.
              </ListItem>
            </List>
          </StackItem>
        </Stack>
      </SynConfirmationDialog>
    </>
  )
}
