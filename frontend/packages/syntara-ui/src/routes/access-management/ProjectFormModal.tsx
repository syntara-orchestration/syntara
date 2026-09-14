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
import { RhUiAddIcon, RhUiErrorIcon } from '@patternfly/react-icons'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { Controller, useForm } from 'react-hook-form'

import { useFormMutationErrorHandler } from '../../hooks/useFormMutationErrorHandler'
import { useAlerts } from '../../providers/alerts'
import { detachPromise } from '../../utils/detachPromise'
import { accessClient } from '../access/accessClient'
import type { ProjectRead } from '../access/types'

import { HintOrError } from './authentication/identity-providers/formFieldHelpers'
import { projectHelp } from './projectFieldHelp'
import {
  PROJECT_NAME_HINT,
  PROJECT_NAME_PLACEHOLDER,
  projectFormSchema,
  type ProjectFormData,
} from './projectFormSchema'

export type ProjectFormModalProps = {
  /** Project to edit, or null/undefined to create a new project */
  project?: ProjectRead | null
  /** Whether the modal is open */
  isOpen: boolean
  /** Callback when the modal is closed (cancel or after success) */
  onClose: () => void
  /** Callback after a successful create/update to refresh the list */
  onSuccess: () => void
  /** Optional callback with the newly created project (create-mode only) */
  onCreated?: (project: ProjectRead) => void
}

export function ProjectFormModal({ project, isOpen, onClose, onSuccess, onCreated }: Readonly<ProjectFormModalProps>) {
  const isEditMode = Boolean(project)
  const title = isEditMode && project ? `Edit ${project.name}` : 'Create project'

  const queryClient = useQueryClient()
  const { showAlert } = useAlerts()

  const invalidateAllProjects = () => {
    detachPromise(queryClient.invalidateQueries({ queryKey: ['all-projects'] }))
  }

  const { control, handleSubmit, setError, reset } = useForm<ProjectFormData>({
    resolver: zodResolver(projectFormSchema, undefined, { mode: 'sync' }),
    defaultValues: {
      name: project?.name ?? '',
      description: project?.description ?? '',
    },
  })

  useEffect(() => {
    if (isOpen) {
      reset({
        name: project?.name ?? '',
        description: project?.description ?? '',
      })
    }
  }, [isOpen, project, reset])

  const handleError = useFormMutationErrorHandler<ProjectFormData>(setError)

  const { mutate: createProject, isPending: isCreating } = accessClient.useMutation('post', '/projects')

  const { mutate: updateProject, isPending: isUpdating } = accessClient.useMutation('patch', '/projects/{project_id}')

  const isPending = isCreating || isUpdating

  const handleClose = () => {
    reset()
    onClose()
  }

  const onSubmit = (formData: ProjectFormData) => {
    const alertContext = formData.name ? `Project "${formData.name}"` : undefined

    if (isEditMode && project) {
      updateProject(
        {
          params: { path: { project_id: project.id ?? '' } },
          body: {
            name: formData.name,
            description: formData.description ?? undefined,
          },
        },
        {
          onSuccess: () => {
            showAlert({
              title: 'Project updated',
              description: `Project "${formData.name}" has been updated successfully.`,
              variant: 'success',
              autoDismiss: true,
            })
            invalidateAllProjects()
            handleClose()
            onSuccess()
          },
          onError: handleError({ title: 'Failed to update project', context: alertContext }),
        }
      )
    } else {
      createProject(
        {
          body: {
            name: formData.name,
            description: formData.description ?? undefined,
          },
        },
        {
          onSuccess: (created) => {
            showAlert({
              title: 'Project created',
              description: `Project "${formData.name}" has been created successfully.`,
              variant: 'success',
              autoDismiss: true,
            })
            invalidateAllProjects()
            handleClose()
            onSuccess()
            onCreated?.(created)
          },
          onError: handleError({ title: 'Failed to create project', context: alertContext }),
        }
      )
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="medium">
      <ModalHeader title={title} />
      <ModalBody>
        <Form id="project-form" onSubmit={handleSubmit(onSubmit)}>
          <Controller
            name="name"
            control={control}
            render={({ field, fieldState }) => (
              <FormGroup label="Project name" fieldId="project-name" isRequired labelHelp={projectHelp.name}>
                <TextInput
                  id="project-name"
                  aria-label="Project name"
                  placeholder={PROJECT_NAME_PLACEHOLDER}
                  validated={fieldState.error ? 'error' : 'default'}
                  value={field.value ?? ''}
                  onChange={field.onChange}
                  onBlur={field.onBlur}
                  name={field.name}
                />
                <HintOrError error={fieldState.error} hint={PROJECT_NAME_HINT} />
              </FormGroup>
            )}
          />
          <Controller
            name="description"
            control={control}
            render={({ field, fieldState }) => (
              <FormGroup label="Description" fieldId="project-description">
                <TextArea
                  id="project-description"
                  aria-label="Description"
                  placeholder="Enter description"
                  validated={fieldState.error ? 'error' : 'default'}
                  value={field.value ?? ''}
                  onChange={field.onChange}
                  onBlur={field.onBlur}
                  name={field.name}
                  rows={3}
                />
                {fieldState.error && (
                  <FormHelperText>
                    <HelperText>
                      <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                        {fieldState.error.message}
                      </HelperTextItem>
                    </HelperText>
                  </FormHelperText>
                )}
              </FormGroup>
            )}
          />
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          type="submit"
          form="project-form"
          isDisabled={isPending}
          isLoading={isPending}
          icon={isEditMode ? undefined : <RhUiAddIcon />}
          iconPosition={isEditMode ? undefined : 'start'}
        >
          {isEditMode ? 'Save' : 'Create project'}
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isPending}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
