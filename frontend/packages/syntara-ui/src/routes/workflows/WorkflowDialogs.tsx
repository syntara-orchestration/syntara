import type { WorkflowAPI } from '@syntara/contracts'

import { SynConfirmationDialog } from '../../components/dialogs/SynConfirmationDialog'
import type { DialogState } from '../../hooks/useDialogState'
import type { ProjectRead } from '../access/types'
import { ProjectFormModal } from '../access-management/ProjectFormModal'
import { ProjectDeleteDialog } from '../access-management/projects/ProjectDeleteDialog'
import { PublishWorkflowDialog } from '../builder/PublishWorkflowDialog'

import { ImportWorkflowDialog } from './ImportWorkflowDialog'
import { WorkflowDeleteDialog } from './WorkflowDeleteDialog'
import { WorkflowListRunFlow } from './WorkflowListRunFlow'

type Workflow = WorkflowAPI.components['schemas']['WorkflowRead']

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
  return (
    <>
      <WorkflowListRunFlow runDialog={runDialog} onRunWorkflow={onRunWorkflow} />

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
        confirmLabel="Unpublish workflow"
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

      <ProjectDeleteDialog
        projectName={projectDeleteDialog.item?.name}
        isOpen={projectDeleteDialog.isOpen}
        onClose={projectDeleteDialog.close}
        onConfirm={() => {
          if (projectDeleteDialog.item) {
            onDeleteProject(projectDeleteDialog.item)
          }
        }}
        confirmLoading={isDeletingProject}
      />
    </>
  )
}
