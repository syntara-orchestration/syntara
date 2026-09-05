import { zodResolver } from '@hookform/resolvers/zod'
import {
  Button,
  Content,
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
import { format } from 'date-fns'
import { useEffect } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { z } from 'zod'

const publishWorkflowSchema = z.object({
  name: z.string().min(1, 'Version name is required').max(255),
  description: z.string().max(1000, 'Description must be 1000 characters or fewer').optional().or(z.literal('')),
})

type PublishWorkflowFormData = z.infer<typeof publishWorkflowSchema>

function getDefaultVersionName(): string {
  return format(new Date(), 'PPp')
}

type PublishWorkflowDialogProps = Readonly<{
  isOpen: boolean
  isPublishing: boolean
  onClose: () => void
  onPublish: (publishName?: string, description?: string) => void
}>

export function PublishWorkflowDialog({ isOpen, isPublishing, onClose, onPublish }: PublishWorkflowDialogProps) {
  const { control, handleSubmit, reset } = useForm<PublishWorkflowFormData>({
    resolver: zodResolver(publishWorkflowSchema, undefined, { mode: 'sync' }),
    defaultValues: { name: '', description: '' },
  })

  useEffect(() => {
    if (isOpen) {
      reset({ name: getDefaultVersionName(), description: '' })
    }
  }, [isOpen, reset])

  const onSubmit = (data: PublishWorkflowFormData) => {
    const name = data.name.trim()
    const desc = data.description?.trim()
    onPublish(name || undefined, desc || undefined)
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} variant="small" aria-label="Publish workflow">
      <ModalHeader title="Publish workflow?" />
      <ModalBody>
        <Content component="p" style={{ marginBottom: 'var(--pf-t--global--spacer--md)' }}>
          This will override any previously published workflow and your trigger step will now be able to trigger
          workflow runs. These triggered runs will happen in the background and can be viewed in run history. The
          previously published workflow can be viewed in version history.
        </Content>
        <Form onSubmit={handleSubmit(onSubmit)} id="publish-workflow-form">
          <FormGroup label="Version name" isRequired fieldId="publish-name">
            <Controller
              name="name"
              control={control}
              render={({ field, fieldState }) => (
                <>
                  <TextInput
                    id="publish-name"
                    type="text"
                    aria-label="Version name"
                    isRequired
                    validated={fieldState.error ? 'error' : 'default'}
                    value={field.value ?? ''}
                    onChange={(_event, value) => field.onChange(value)}
                  />
                  {fieldState.error && (
                    <FormHelperText>
                      <HelperText>
                        <HelperTextItem variant="error">{fieldState.error.message}</HelperTextItem>
                      </HelperText>
                    </FormHelperText>
                  )}
                </>
              )}
            />
          </FormGroup>
          <FormGroup label="Description" fieldId="publish-description">
            <Controller
              name="description"
              control={control}
              render={({ field, fieldState }) => (
                <>
                  <TextArea
                    id="publish-description"
                    aria-label="Description"
                    placeholder="Describe what changed"
                    validated={fieldState.error ? 'error' : 'default'}
                    value={field.value ?? ''}
                    onChange={(_event, value) => field.onChange(value)}
                    rows={4}
                  />
                  {fieldState.error && (
                    <FormHelperText>
                      <HelperText>
                        <HelperTextItem variant="error">{fieldState.error.message}</HelperTextItem>
                      </HelperText>
                    </FormHelperText>
                  )}
                </>
              )}
            />
          </FormGroup>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          type="submit"
          form="publish-workflow-form"
          isLoading={isPublishing}
          isDisabled={isPublishing}
        >
          Publish workflow
        </Button>
        <Button variant="link" onClick={onClose} isDisabled={isPublishing}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
