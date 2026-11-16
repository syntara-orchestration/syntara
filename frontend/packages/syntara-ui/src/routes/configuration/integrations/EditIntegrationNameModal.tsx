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
} from '@patternfly/react-core'
import { useEffect } from 'react'
import { useWatch } from 'react-hook-form'

import { SynForm } from '../../../components/forms/SynForm'
import { SynTextField } from '../../../components/forms/SynTextField'
import { useSynForm } from '../../../hooks/useSynForm'

import type { EditIntegrationNameFormData } from './editIntegrationNameSchema'
import { editIntegrationNameSchema } from './editIntegrationNameSchema'
import { integrationHelp } from './integrationFieldHelp'

type EditIntegrationNameModalProps = Readonly<{
  isOpen: boolean
  isSaving: boolean
  initialName: string
  onClose: () => void
  onSave: (name: string) => void
}>

export function EditIntegrationNameModal({
  isOpen,
  isSaving,
  initialName,
  onClose,
  onSave,
}: EditIntegrationNameModalProps) {
  const form = useSynForm({
    schema: editIntegrationNameSchema,
    defaultValues: { name: '' },
    onClose,
  })
  const {
    control,
    handleSubmit,
    handleClose,
    reset,
    formState: { isDirty },
  } = form

  const nameValue = useWatch({ control, name: 'name' })

  useEffect(() => {
    if (isOpen) {
      reset({ name: initialName })
    }
  }, [isOpen, initialName, reset])

  function onSubmit(data: EditIntegrationNameFormData) {
    onSave(data.name)
  }

  const canSave = isDirty && nameValue.trim().length > 0 && !isSaving

  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="small">
      <ModalHeader title="Edit integration name" />
      <ModalBody>
        <Stack hasGutter>
          <StackItem>
            <Content component={ContentVariants.p}>
              You can only edit the server name / ID. All other settings are read-only.
            </Content>
          </StackItem>
          <StackItem>
            <Form id="edit-integration-name-form" onSubmit={handleSubmit(onSubmit)}>
              <SynForm form={form}>
                <SynTextField
                  name="name"
                  label="Server name / ID"
                  fieldId="edit-integration-name"
                  isRequired
                  labelHelp={integrationHelp.serverName}
                />
              </SynForm>
            </Form>
          </StackItem>
        </Stack>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          type="submit"
          form="edit-integration-name-form"
          isLoading={isSaving}
          isDisabled={!canSave}
        >
          Save name
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isSaving}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
