import { Content, Modal, ModalBody, ModalHeader } from '@patternfly/react-core'
import type { FormDefinition } from '@syntara/contracts'
import { useMemo } from 'react'

import { SynDynamicForm } from '../../../components/forms/SynDynamicForm'
import { safeParseFormDefinition } from '../../../forms'

type FormPromptPreviewModalProps = Readonly<{
  isOpen: boolean
  onClose: () => void
  formDefinition: FormDefinition
  message?: string | null
}>

export function FormPromptPreviewModal({ isOpen, onClose, formDefinition, message }: FormPromptPreviewModalProps) {
  const parsed = useMemo(() => safeParseFormDefinition(formDefinition), [formDefinition])

  return (
    <Modal variant="medium" isOpen={isOpen} onClose={onClose} aria-labelledby="form-prompt-preview-title">
      <ModalHeader title="Preview form" labelId="form-prompt-preview-title" />
      <ModalBody>
        {!parsed.success ? (
          <Content component="p">Fix form field validation errors before previewing.</Content>
        ) : (
          <SynDynamicForm
            definition={parsed.data}
            description={message?.trim() || undefined}
            hideSubmitButton
            isReadOnly
            onSubmit={() => undefined}
          />
        )}
      </ModalBody>
    </Modal>
  )
}
