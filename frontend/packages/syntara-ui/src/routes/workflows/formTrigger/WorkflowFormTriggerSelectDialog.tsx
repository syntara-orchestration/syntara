import { Button, Modal, ModalBody, ModalFooter, ModalHeader, Stack, StackItem } from '@patternfly/react-core'

import { useBlurOnOpen } from '../../../hooks/useBlurOnOpen'
import type { WorkflowRunTrigger } from '../resolveWorkflowRunTrigger'

const CHOOSE_FORM_STEP_TITLE_ID = 'choose-form-step-title'

type WorkflowFormTriggerSelectDialogProps = Readonly<{
  isOpen: boolean
  triggers: WorkflowRunTrigger[]
  onClose: () => void
  onSelect: (trigger: WorkflowRunTrigger) => void
}>

export function WorkflowFormTriggerSelectDialog({
  isOpen,
  triggers,
  onClose,
  onSelect,
}: WorkflowFormTriggerSelectDialogProps) {
  useBlurOnOpen(isOpen)

  return (
    <Modal isOpen={isOpen} onClose={onClose} variant="medium" aria-labelledby={CHOOSE_FORM_STEP_TITLE_ID}>
      <ModalHeader
        title="Choose form step"
        labelId={CHOOSE_FORM_STEP_TITLE_ID}
        description="Select which form step starts this run."
      />
      <ModalBody>
        <Stack hasGutter>
          {triggers.map((trigger, index) => (
            <StackItem key={trigger.triggerNodeId}>
              <Button variant="secondary" onClick={() => onSelect(trigger)} isBlock>
                {trigger.triggerName || `Trigger ${index + 1}`}
              </Button>
            </StackItem>
          ))}
        </Stack>
      </ModalBody>
      <ModalFooter>
        <Button variant="link" onClick={onClose}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
