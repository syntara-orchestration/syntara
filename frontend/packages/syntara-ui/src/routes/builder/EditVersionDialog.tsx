import { zodResolver } from '@hookform/resolvers/zod'
import {
  Button,
  Form,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  TextArea,
  TextInput,
} from '@patternfly/react-core'
import { useEffect } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { z } from 'zod'

const editVersionSchema = z.object({
  name: z.string().max(255).optional().or(z.literal('')),
  change_description: z.string().max(1024).optional().or(z.literal('')),
})

type EditVersionFormData = z.infer<typeof editVersionSchema>

type EditVersionDialogProps = Readonly<{
  isOpen: boolean
  isSaving: boolean
  onClose: () => void
  onSave: (publishName: string | null, changeDescription: string | null) => void
  initialName?: string | null
  initialDescription?: string | null
}>

export function EditVersionDialog({
  isOpen,
  isSaving,
  onClose,
  onSave,
  initialName,
  initialDescription,
}: EditVersionDialogProps) {
  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<EditVersionFormData>({
    resolver: zodResolver(editVersionSchema, undefined, { mode: 'sync' }),
    defaultValues: { name: '', change_description: '' },
  })

  useEffect(() => {
    if (isOpen) {
      reset({
        name: initialName ?? '',
        change_description: initialDescription ?? '',
      })
    }
  }, [isOpen, initialName, initialDescription, reset])

  const onSubmit = (data: EditVersionFormData) => {
    const name = data.name?.trim()
    const desc = data.change_description?.trim()
    onSave(name || null, desc || null)
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} variant="small">
      <ModalHeader title="Edit version name and description" />
      <ModalBody>
        <Form onSubmit={handleSubmit(onSubmit)} id="edit-version-form">
          <FormGroup label="Version name" fieldId="edit-version-name">
            <Controller
              name="name"
              control={control}
              render={({ field }) => (
                <>
                  <TextInput
                    id="edit-version-name"
                    type="text"
                    aria-label="Version name"
                    validated={errors.name ? 'error' : 'default'}
                    value={field.value ?? ''}
                    onChange={(_event, value) => field.onChange(value)}
                  />
                  {errors.name && (
                    <FormHelperText>
                      <HelperText>
                        <HelperTextItem variant="error">{errors.name.message}</HelperTextItem>
                      </HelperText>
                    </FormHelperText>
                  )}
                </>
              )}
            />
          </FormGroup>
          <FormGroup label="Description" fieldId="edit-version-description">
            <Controller
              name="change_description"
              control={control}
              render={({ field }) => (
                <TextArea
                  id="edit-version-description"
                  aria-label="Description"
                  placeholder="Describe what changed"
                  value={field.value ?? ''}
                  onChange={(_event, value) => field.onChange(value)}
                  rows={4}
                />
              )}
            />
          </FormGroup>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" type="submit" form="edit-version-form" isLoading={isSaving} isDisabled={isSaving}>
          Save version
        </Button>
        <Button variant="link" onClick={onClose} isDisabled={isSaving}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
