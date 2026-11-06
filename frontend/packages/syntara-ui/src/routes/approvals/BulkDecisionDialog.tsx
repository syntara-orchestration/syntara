import {
  Button,
  Content,
  ContentVariants,
  Form,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  Stack,
  StackItem,
  type ButtonProps,
} from '@patternfly/react-core'
import { RhUiDislikeIcon, RhUiLikeIcon } from '@patternfly/react-icons'
import type { ReactElement } from 'react'
import { useEffect } from 'react'

import { SynForm } from '../../components/forms/SynForm'
import { SynTextAreaField } from '../../components/forms/SynTextAreaField'
import { useSynForm } from '../../hooks/useSynForm'
import { APPROVAL_NOTES_MAX_LENGTH } from '../executions/approvalDecisionSchema'

import { bulkApprovalNoteSchema, type BulkApprovalNoteFormData } from './approvalNoteSchema'

type BulkDecision = 'approve' | 'reject'

type BulkDecisionConfig = {
  actionVerb: 'approve' | 'reject'
  formId: string
  labelId: string
  noteFieldId: string
  noteLabel: string
  notePlaceholder: string
  buttonVariant: ButtonProps['variant']
  buttonIcon: ReactElement
  titleIconVariant?: 'warning'
}

const BULK_DECISION_CONFIG: Record<BulkDecision, BulkDecisionConfig> = {
  approve: {
    actionVerb: 'approve',
    formId: 'bulk-approve-form',
    labelId: 'bulk-approve-title',
    noteFieldId: 'approval-note',
    noteLabel: 'Approval note',
    notePlaceholder: 'Optional note for these approvals',
    buttonVariant: 'primary',
    buttonIcon: <RhUiLikeIcon />,
  },
  reject: {
    actionVerb: 'reject',
    formId: 'bulk-reject-form',
    labelId: 'bulk-reject-title',
    noteFieldId: 'rejection-note',
    noteLabel: 'Rejection note',
    notePlaceholder: 'Optional note for these rejections',
    buttonVariant: 'danger',
    buttonIcon: <RhUiDislikeIcon />,
    titleIconVariant: 'warning',
  },
}

function formatApprovalStepPhrase(count: number): string {
  return count === 1 ? 'approval step' : 'approval steps'
}

export type BulkDecisionDialogBaseProps = {
  isOpen: boolean
  onClose: () => void
  onConfirm: (note: string | null) => void
  approvalCount: number
  isLoading?: boolean
}

type BulkDecisionDialogProps = BulkDecisionDialogBaseProps & {
  decision: BulkDecision
}

function BulkDecisionDialog({
  decision,
  isOpen,
  onClose,
  onConfirm,
  approvalCount,
  isLoading = false,
}: Readonly<BulkDecisionDialogProps>) {
  const config = BULK_DECISION_CONFIG[decision]
  const decisionLabel = decision === 'approve' ? 'Approve' : 'Reject'
  const stepPhrase = formatApprovalStepPhrase(approvalCount)

  const form = useSynForm({
    schema: bulkApprovalNoteSchema,
    defaultValues: { note: '' },
    onClose,
  })
  const { handleSubmit, handleClose, reset } = form

  useEffect(() => {
    if (isOpen) {
      reset({ note: '' })
    }
  }, [isOpen, reset])

  const onSubmit = (data: BulkApprovalNoteFormData) => {
    onConfirm(data.note.trim() || null)
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      variant="medium"
      aria-labelledby={config.labelId}
      key={isOpen ? 'open' : 'closed'}
    >
      <ModalHeader
        title={`${decisionLabel} ${approvalCount} ${stepPhrase}`}
        labelId={config.labelId}
        titleIconVariant={config.titleIconVariant}
      />
      <ModalBody>
        <Stack hasGutter>
          <StackItem>
            <Content component={ContentVariants.p}>
              You are about to {config.actionVerb} {approvalCount} {stepPhrase}.
            </Content>
          </StackItem>

          <StackItem>
            <Form id={config.formId} onSubmit={handleSubmit(onSubmit)}>
              <SynForm form={form}>
                <SynTextAreaField
                  name="note"
                  label={config.noteLabel}
                  fieldId={config.noteFieldId}
                  placeholder={config.notePlaceholder}
                  rows={3}
                  maxLength={APPROVAL_NOTES_MAX_LENGTH}
                />
              </SynForm>
            </Form>
          </StackItem>
        </Stack>
      </ModalBody>
      <ModalFooter>
        <Button
          icon={config.buttonIcon}
          variant={config.buttonVariant}
          onClick={handleSubmit(onSubmit)}
          isLoading={isLoading}
          isDisabled={isLoading}
        >
          {decisionLabel}
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isLoading}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}

export function BulkApproveDialog(props: Readonly<BulkDecisionDialogBaseProps>) {
  return <BulkDecisionDialog decision="approve" {...props} />
}

export function BulkRejectDialog(props: Readonly<BulkDecisionDialogBaseProps>) {
  return <BulkDecisionDialog decision="reject" {...props} />
}
