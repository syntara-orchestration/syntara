import { Modal, ModalBody } from '@patternfly/react-core'
import { useMemo } from 'react'

import { useBlurOnOpen } from '../../../hooks/useBlurOnOpen'
import type { WorkflowRunTrigger } from '../resolveWorkflowRunTrigger'
import { RunWorkflowTriggerDropdownList } from '../RunWorkflowTriggerDropdownList'

import styles from './WorkflowFormTriggerSelectDialog.module.css'

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

  const options = useMemo(
    () =>
      triggers.map((trigger, index) => ({
        id: trigger.triggerNodeId,
        label: trigger.triggerName || `Trigger ${index + 1}`,
      })),
    [triggers]
  )

  return (
    <Modal isOpen={isOpen} onClose={onClose} variant="small" aria-label="Run workflow">
      <ModalBody className={styles.menuPanel}>
        <RunWorkflowTriggerDropdownList
          options={options}
          onSelect={(option) => {
            const trigger = triggers.find((candidate) => candidate.triggerNodeId === option.id)
            if (trigger) {
              onSelect(trigger)
            }
          }}
        />
      </ModalBody>
    </Modal>
  )
}
