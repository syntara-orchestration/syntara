import { Button, Content, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'
import { useCallback, useState } from 'react'

import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { useBlurOnOpen } from '../../hooks/useBlurOnOpen'

type SaveBeforeViewDialogProps = Readonly<{
  isOpen: boolean
  onSave: () => Promise<boolean>
  onViewWithoutSaving: () => void
  onCancel: () => void
  canSave?: boolean
  saveTooltip?: string
  title?: string
  bodyText?: string
  buttonLabel?: string
}>

export function SaveBeforeViewDialog({
  isOpen,
  onSave,
  onViewWithoutSaving,
  onCancel,
  canSave = true,
  saveTooltip = 'You do not have permission to save this workflow.',
  title = 'Save changes before viewing this version?',
  bodyText = 'Viewing workflow versions will exit the editor view and will permanently delete all recent unsaved progress on your workflow. Please save your work before leaving.',
  buttonLabel = 'View version without saving',
}: SaveBeforeViewDialogProps) {
  useBlurOnOpen(isOpen)
  const [isSaving, setIsSaving] = useState(false)

  const handleSave = useCallback(async () => {
    if (!canSave || isSaving) return
    setIsSaving(true)
    try {
      await onSave()
    } finally {
      setIsSaving(false)
    }
  }, [canSave, isSaving, onSave])

  return (
    <Modal isOpen={isOpen} onClose={onCancel} variant="small">
      <ModalHeader title={title} />
      <ModalBody>
        <Content>{bodyText}</Content>
      </ModalBody>
      <ModalFooter>
        <DisabledWithTooltip isDisabled={!canSave} content={saveTooltip}>
          <Button
            variant="primary"
            onClick={canSave ? handleSave : undefined}
            isLoading={isSaving}
            isDisabled={isSaving}
            isAriaDisabled={!canSave}
          >
            Save workflow
          </Button>
        </DisabledWithTooltip>
        <Button variant="secondary" onClick={onViewWithoutSaving} isDisabled={isSaving}>
          {buttonLabel}
        </Button>
        <Button variant="link" onClick={onCancel} isDisabled={isSaving}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
