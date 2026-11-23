import {
  Button,
  Content,
  ContentVariants,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  Spinner,
  Stack,
  StackItem,
} from '@patternfly/react-core'
import type { ExecutionPlaneAPI } from '@syntara/contracts'
import type { ReactNode } from 'react'

import { SynConfirmationDialog } from '../../components/dialogs/SynConfirmationDialog'
import { useBlurOnOpen } from '../../hooks/useBlurOnOpen'
import type { DialogState } from '../../hooks/useDialogState'

import type { useExecutionTargetActions } from './useExecutionTargetActions'
import { useExecutionTargetUsage } from './useExecutionTargetUsage'

type ExecutionTarget = ExecutionPlaneAPI.components['schemas']['ExecutionTargetRead']

type ExecutionTargetDialogsProps = Readonly<{
  deleteDialog: ReturnType<typeof useExecutionTargetActions>['deleteDialog']
  onDelete: () => void
  disableDialog: DialogState<ExecutionTarget>
  onDisable: () => void
}>

type UsageState = Readonly<{
  activeWorkloadCount: number
  isLoadingUsage: boolean
  usageFetchError: boolean
}>

function activeWorkloadLabel(count: number): string {
  return count === 1 ? '1 active workload' : `${String(count)} active workloads`
}

function ActiveWorkloadsNotice({
  count,
  continuation,
}: Readonly<{
  count: number
  continuation: string
}>) {
  if (count <= 0) return null

  return (
    <Content component={ContentVariants.p}>
      <strong>{activeWorkloadLabel(count)}</strong> {count === 1 ? 'is' : 'are'} running on this target. {continuation}
    </Content>
  )
}

function UsageLoadingNotice() {
  return (
    <Content component={ContentVariants.p}>
      <Spinner size="md" aria-label="Checking active workloads" /> Checking for active workloads on this target…
    </Content>
  )
}

function UsageFetchErrorNotice() {
  return <Content component={ContentVariants.p}>Unable to load active workload information for this target.</Content>
}

function ConfirmationBody({
  usage,
  children,
  continuation,
}: Readonly<{
  usage: UsageState
  children: ReactNode
  continuation: string
}>) {
  let usageDetails: ReactNode = null
  if (usage.isLoadingUsage) {
    usageDetails = <UsageLoadingNotice />
  } else if (usage.usageFetchError) {
    usageDetails = <UsageFetchErrorNotice />
  } else if (usage.activeWorkloadCount > 0) {
    usageDetails = <ActiveWorkloadsNotice count={usage.activeWorkloadCount} continuation={continuation} />
  }

  return (
    <Stack hasGutter>
      <StackItem>{children}</StackItem>
      {usageDetails ? <StackItem>{usageDetails}</StackItem> : null}
    </Stack>
  )
}

function resolveUsageTargetId(
  deleteDialog: DialogState<ExecutionTarget>,
  disableDialog: DialogState<ExecutionTarget>
): string | null {
  // Default targets cannot be deleted — skip the usage check for that informational dialog.
  if (deleteDialog.isOpen && !deleteDialog.item?.is_default) {
    return deleteDialog.item?.id ?? null
  }
  if (disableDialog.isOpen) {
    return disableDialog.item?.id ?? null
  }
  return null
}

function deleteContinuation(count: number): string {
  if (count === 1) {
    return 'The target will be deleted after that workload completes.'
  }
  return 'The target will be deleted after those workloads complete.'
}

function disableContinuation(count: number): string {
  if (count === 1) {
    return 'That workload will continue to completion.'
  }
  return 'Those workloads will continue to completion.'
}

const CANNOT_DELETE_DEFAULT_TITLE_ID = 'cannot-delete-default-execution-target-title'
const CANNOT_DELETE_DEFAULT_BODY_ID = 'cannot-delete-default-execution-target-body'

function CannotDeleteDefaultExecutionTargetModal({
  isOpen,
  onClose,
  targetName,
}: Readonly<{
  isOpen: boolean
  onClose: () => void
  targetName: string
}>) {
  useBlurOnOpen(isOpen)

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      variant="small"
      aria-labelledby={CANNOT_DELETE_DEFAULT_TITLE_ID}
      aria-describedby={CANNOT_DELETE_DEFAULT_BODY_ID}
    >
      <ModalHeader
        title="Cannot delete default execution target"
        titleIconVariant="warning"
        labelId={CANNOT_DELETE_DEFAULT_TITLE_ID}
      />
      <ModalBody id={CANNOT_DELETE_DEFAULT_BODY_ID}>
        <Content component={ContentVariants.p}>
          Set another execution target as default before deleting <strong>{targetName}</strong>. Edit another target and
          mark it as the default, then try again.
        </Content>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" onClick={onClose}>
          Close
        </Button>
      </ModalFooter>
    </Modal>
  )
}

export function ExecutionTargetDialogs({
  deleteDialog,
  onDelete,
  disableDialog,
  onDisable,
}: ExecutionTargetDialogsProps) {
  const usageTargetId = resolveUsageTargetId(deleteDialog, disableDialog)
  const usage = useExecutionTargetUsage(usageTargetId)
  const isDeletingDefault = Boolean(deleteDialog.item?.is_default)
  const isDeleteConfirmOpen = deleteDialog.isOpen && !isDeletingDefault
  const isCannotDeleteDefaultOpen = deleteDialog.isOpen && isDeletingDefault
  const defaultTargetName = deleteDialog.item?.name ?? 'this execution target'

  return (
    <>
      <SynConfirmationDialog
        isOpen={disableDialog.isOpen}
        onClose={disableDialog.close}
        onConfirm={onDisable}
        title="Disable execution target?"
        confirmLabel="Disable"
        confirmVariant="primary"
        confirmLoading={usage.isLoadingUsage}
      >
        <ConfirmationBody usage={usage} continuation={disableContinuation(usage.activeWorkloadCount)}>
          <Content component={ContentVariants.p}>
            The execution target <strong>{disableDialog.item?.name}</strong> will be disabled. Workflows that have not
            started and require affinity to this target will fail. You can re-enable it at any time.
          </Content>
        </ConfirmationBody>
      </SynConfirmationDialog>

      <SynConfirmationDialog
        isOpen={isDeleteConfirmOpen}
        onClose={deleteDialog.close}
        onConfirm={onDelete}
        title="Delete execution target?"
        confirmLabel="Delete"
        confirmVariant="danger"
        titleIconVariant="warning"
        confirmLoading={usage.isLoadingUsage}
        destructiveAcknowledgement={{
          checkboxId: 'delete-execution-target-ack',
          label: 'I understand this execution target will be permanently deleted.',
        }}
      >
        <ConfirmationBody usage={usage} continuation={deleteContinuation(usage.activeWorkloadCount)}>
          <Content component={ContentVariants.p}>
            The execution target <strong>{deleteDialog.item?.name}</strong> will be permanently deleted. This cannot be
            undone.
          </Content>
        </ConfirmationBody>
      </SynConfirmationDialog>

      <CannotDeleteDefaultExecutionTargetModal
        isOpen={isCannotDeleteDefaultOpen}
        onClose={deleteDialog.close}
        targetName={defaultTargetName}
      />
    </>
  )
}
