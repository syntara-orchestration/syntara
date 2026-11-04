import { Alert, Content, Modal, ModalBody, ModalHeader, Stack, StackItem } from '@patternfly/react-core'
import type { FormDefinition } from '@syntara/contracts'
import { useMemo } from 'react'

import { SynDynamicForm } from '../../../components/forms/SynDynamicForm'
import { safeParseFormDefinition } from '../../../forms'
import {
  formDefinitionHasUnresolvedDynamicOptions,
  FORM_PROMPT_PREVIEW_DYNAMIC_OPTIONS_ALERT_BODY,
  FORM_PROMPT_PREVIEW_DYNAMIC_OPTIONS_ALERT_TITLE,
} from '../../../forms/formPromptDynamicOptions'

type FormPromptPreviewModalProps = Readonly<{
  isOpen: boolean
  onClose: () => void
  formDefinition: FormDefinition
  message?: string | null
}>

export function FormPromptPreviewModal({ isOpen, onClose, formDefinition, message }: FormPromptPreviewModalProps) {
  const parsed = useMemo(() => safeParseFormDefinition(formDefinition), [formDefinition])
  const showDynamicOptionsNotice = parsed.success && formDefinitionHasUnresolvedDynamicOptions(parsed.data)

  return (
    <Modal variant="medium" isOpen={isOpen} onClose={onClose} aria-labelledby="form-prompt-preview-title">
      <ModalHeader title="Preview form" labelId="form-prompt-preview-title" />
      <ModalBody>
        {!parsed.success ? (
          <Content component="p">Fix form field validation errors before previewing.</Content>
        ) : (
          <Stack hasGutter>
            {showDynamicOptionsNotice ? (
              <StackItem>
                <Alert variant="info" isInline title={FORM_PROMPT_PREVIEW_DYNAMIC_OPTIONS_ALERT_TITLE}>
                  {FORM_PROMPT_PREVIEW_DYNAMIC_OPTIONS_ALERT_BODY}
                </Alert>
              </StackItem>
            ) : null}
            <StackItem>
              <SynDynamicForm
                definition={parsed.data}
                description={message?.trim() || undefined}
                hideSubmitButton
                isReadOnly
                onSubmit={() => undefined}
              />
            </StackItem>
          </Stack>
        )}
      </ModalBody>
    </Modal>
  )
}
