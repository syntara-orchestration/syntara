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
import type { Group } from '@syntara/contracts'
import { useEffect } from 'react'
import { Controller, useForm } from 'react-hook-form'

import { useFormMutationErrorHandler } from '../../hooks/useFormMutationErrorHandler'
import { useAlerts } from '../../providers/alerts'
import { accessClient } from '../access/accessClient'

import { groupHelp } from './groupFieldHelp'
import { groupFormSchema, type GroupFormData } from './groupFormSchema'

export type GroupFormModalProps = {
  /** Group to edit, or null/undefined to create a new group */
  group?: Group | null
  /** Pre-fill the group name when creating (e.g. from an IdP group value) */
  initialName?: string
  /** Whether the modal is open */
  isOpen: boolean
  /** Callback when the modal is closed (cancel or after success) */
  onClose: () => void
  /** Callback after a successful create/update to refresh the list */
  onSuccess: () => void
}

export function GroupFormModal({ group, initialName, isOpen, onClose, onSuccess }: Readonly<GroupFormModalProps>) {
  const isEditMode = Boolean(group)
  const title = isEditMode && group ? `Edit ${group.name}` : 'Create group'

  const { showAlert } = useAlerts()

  const { control, handleSubmit, setError, reset } = useForm<GroupFormData>({
    resolver: zodResolver(groupFormSchema, undefined, { mode: 'sync' }),
    defaultValues: {
      name: group?.name ?? '',
      description: group?.description ?? '',
    },
  })

  useEffect(() => {
    if (isOpen) {
      reset({
        name: group?.name ?? initialName ?? '',
        description: group?.description ?? '',
      })
    }
  }, [isOpen, group, initialName, reset])

  const handleError = useFormMutationErrorHandler<GroupFormData>(setError)

  const { mutate: createGroup, isPending: isCreating } = accessClient.useMutation('post', '/groups')

  const { mutate: updateGroup, isPending: isUpdating } = accessClient.useMutation('patch', '/groups/{group_id}')

  const isPending = isCreating || isUpdating

  const handleClose = () => {
    reset()
    onClose()
  }

  const onSubmit = (formData: GroupFormData) => {
    const alertContext = formData.name ? `Group "${formData.name}"` : undefined

    if (isEditMode && group) {
      updateGroup(
        {
          params: { path: { group_id: group.id } },
          body: {
            name: formData.name,
            description: formData.description,
          },
        },
        {
          onSuccess: () => {
            showAlert({
              title: 'Group updated',
              description: `Group "${formData.name}" has been updated successfully.`,
              variant: 'success',
              autoDismiss: true,
            })
            handleClose()
            onSuccess()
          },
          onError: handleError({ title: 'Failed to update group', context: alertContext }),
        }
      )
    } else {
      createGroup(
        {
          body: {
            name: formData.name,
            description: formData.description,
          },
        },
        {
          onSuccess: () => {
            showAlert({
              title: 'Group created',
              description: `Group "${formData.name}" has been created successfully.`,
              variant: 'success',
              autoDismiss: true,
            })
            handleClose()
            onSuccess()
          },
          onError: handleError({ title: 'Failed to create group', context: alertContext }),
        }
      )
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="medium">
      <ModalHeader title={title} />
      <ModalBody>
        <Form id="group-form" onSubmit={handleSubmit(onSubmit)}>
          <Controller
            name="name"
            control={control}
            render={({ field, fieldState }) => (
              <FormGroup label="Group name" fieldId="group-name" isRequired labelHelp={groupHelp.name}>
                <TextInput
                  id="group-name"
                  aria-label="Group name"
                  placeholder="Enter group name"
                  validated={fieldState.error ? 'error' : 'default'}
                  value={field.value ?? ''}
                  onChange={field.onChange}
                  onBlur={field.onBlur}
                  name={field.name}
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
          <Controller
            name="description"
            control={control}
            render={({ field, fieldState }) => (
              <FormGroup label="Description" fieldId="group-description">
                <TextArea
                  id="group-description"
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
          form="group-form"
          isDisabled={isPending}
          isLoading={isPending}
          icon={isEditMode ? undefined : <RhUiAddIcon />}
        >
          {isEditMode ? 'Save' : 'Create group'}
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isPending}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
