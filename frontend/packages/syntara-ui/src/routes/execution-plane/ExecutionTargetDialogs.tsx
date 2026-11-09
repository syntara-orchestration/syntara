import { Content, ContentVariants, List, ListItem, Stack, StackItem } from '@patternfly/react-core'
import type { ExecutionPlaneAPI } from '@syntara/contracts'

import { SynConfirmationDialog } from '../../components/dialogs/SynConfirmationDialog'
import type { DialogState } from '../../hooks/useDialogState'

import type { useExecutionTargetActions } from './useExecutionTargetActions'

type ExecutionTarget = ExecutionPlaneAPI.components['schemas']['ExecutionTargetRead']

type ExecutionTargetDialogsProps = Readonly<{
  deleteDialog: ReturnType<typeof useExecutionTargetActions>['deleteDialog']
  onDelete: () => void
  disableDialog: DialogState<ExecutionTarget>
  onDisable: () => void
}>

export function ExecutionTargetDialogs({
  deleteDialog,
  onDelete,
  disableDialog,
  onDisable,
}: ExecutionTargetDialogsProps) {
  return (
    <>
      <SynConfirmationDialog
        isOpen={disableDialog.isOpen}
        onClose={disableDialog.close}
        onConfirm={onDisable}
        title="Disable execution target?"
        confirmLabel="Disable"
        confirmVariant="primary"
      >
        <Stack hasGutter>
          <StackItem>
            <Content component={ContentVariants.p}>
              You are about to disable the following execution target: <strong>{disableDialog.item?.name}</strong>
            </Content>
          </StackItem>
          <StackItem>
            <Content component={ContentVariants.p}>This will immediately:</Content>
            <List>
              <ListItem>Workflows already running on this target will continue to completion.</ListItem>
              <ListItem>Workflows that have not started and require affinity to this target will fail.</ListItem>
              <ListItem>Workflows routed by labels will shift to other available capacity.</ListItem>
            </List>
          </StackItem>
          <StackItem>
            <Content component={ContentVariants.p}>You can re-enable this execution target at any time.</Content>
          </StackItem>
        </Stack>
      </SynConfirmationDialog>

      <SynConfirmationDialog
        isOpen={deleteDialog.isOpen}
        onClose={deleteDialog.close}
        onConfirm={onDelete}
        title="Delete execution target?"
        confirmLabel="Delete"
        confirmVariant="danger"
        titleIconVariant="warning"
        destructiveAcknowledgement={{
          checkboxId: 'delete-execution-target-ack',
          label: 'I understand this execution target will be permanently deleted.',
        }}
      >
        <Content component={ContentVariants.p}>
          The execution target <strong>{deleteDialog.item?.name}</strong> will be deleted. This cannot be undone.
        </Content>
      </SynConfirmationDialog>
    </>
  )
}
