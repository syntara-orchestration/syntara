import {
  Button,
  Content,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  Radio,
  Stack,
  StackItem,
} from '@patternfly/react-core'
import { useState } from 'react'

type ImportChoice = 'new' | 'current'

type ImportConfirmationDialogProps = Readonly<{
  isOpen: boolean
  onClose: () => void
  onImportCurrent: () => void
  onImportNew: () => void
  workflowName: string
  isDirty: boolean
  isPending: boolean
}>

export function ImportConfirmationDialog({
  isOpen,
  onClose,
  onImportCurrent,
  onImportNew,
  workflowName,
  isDirty,
  isPending,
}: ImportConfirmationDialogProps) {
  const [choice, setChoice] = useState<ImportChoice>('new')

  if (!isOpen && choice !== 'new') {
    setChoice('new')
  }

  const handleConfirm = () => {
    if (choice === 'new') {
      onImportNew()
    } else {
      onImportCurrent()
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      variant="small"
      aria-labelledby="import-confirmation-title"
      aria-describedby="import-confirmation-body"
    >
      <ModalHeader title="Import workflow?" labelId="import-confirmation-title" />
      <ModalBody id="import-confirmation-body">
        <Stack hasGutter>
          <StackItem>
            <Content component="p">
              {workflowName ? (
                <>
                  Choose how to import <strong>{workflowName}</strong>:
                </>
              ) : (
                'Choose how to import:'
              )}
            </Content>
          </StackItem>
          <StackItem>
            <Radio
              id="import-choice-new"
              name="import-choice"
              label="Import as new workflow"
              description="Creates a separate workflow from the imported file."
              isChecked={choice === 'new'}
              onChange={() => setChoice('new')}
            />
          </StackItem>
          <StackItem>
            <Radio
              id="import-choice-current"
              name="import-choice"
              label="Import into current workflow"
              description="Overwrites the canvas with the imported definition."
              isChecked={choice === 'current'}
              onChange={() => setChoice('current')}
            />
          </StackItem>
          {isDirty && (
            <StackItem>
              <Content component="p">
                <strong>Note:</strong> You have unsaved changes that will be lost.
              </Content>
            </StackItem>
          )}
        </Stack>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" onClick={handleConfirm} isDisabled={isPending} isLoading={isPending}>
          Import workflow
        </Button>
        <Button variant="link" onClick={onClose} isDisabled={isPending}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
