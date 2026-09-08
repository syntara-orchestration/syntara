import { Button, Content, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'
import { useCallback, useState } from 'react'

import { useBlurOnOpen } from '../../hooks/useBlurOnOpen'

type SaveBeforeViewDialogProps = Readonly<{
  isOpen: boolean
  onSave: () => Promise<boolean>
  onViewWithoutSaving: () => void
  onCancel: () => void
  title?: string
  bodyText?: string
  buttonLabel?: string
}>

export function SaveBeforeViewDialog({
  isOpen,
  onSave,
  onViewWithoutSaving,
  onCancel,
  title = 'Save changes before viewing this version?',
  bodyText = 'Viewing workflow versions will exit the editor view and will permanently delete all recent unsaved progress on your workflow. Please save your work before leaving.',
  buttonLabel = 'View version without saving',
}: SaveBeforeViewDialogProps) {
  useBlurOnOpen(isOpen)
  const [isSaving, setIsSaving] = useState(false)

  const handleSave = useCallback(async () => {
    setIsSaving(true)
    try {
      await onSave()
    } finally {
      setIsSaving(false)
    }
  }, [onSave])

  return (
    <Modal isOpen={isOpen} onClose={onCancel} variant="small">
      <ModalHeader title={title} />
      <ModalBody>
        <Content>{bodyText}</Content>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" onClick={handleSave} isLoading={isSaving} isDisabled={isSaving}>
          Save workflow
        </Button>
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
