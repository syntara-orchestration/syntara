import { Button, Form, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'
import type { Group } from '@syntara/contracts'
import { useEffect } from 'react'

import { SynForm } from '../../components/forms/SynForm'
import { SynTextAreaField } from '../../components/forms/SynTextAreaField'
import { SynTextField } from '../../components/forms/SynTextField'
import { useSynForm } from '../../hooks/useSynForm'
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

  const form = useSynForm({
    schema: groupFormSchema,
    defaultValues: { name: '', description: '' },
    onClose,
  })
  const { handleSubmit, handleError, handleClose, reset } = form

  useEffect(() => {
    if (isOpen) {
      reset({
        name: group?.name ?? initialName ?? '',
        description: group?.description ?? '',
      })
    }
  }, [isOpen, group, initialName, reset])

  const { mutate: createGroup, isPending: isCreating } = accessClient.useMutation('post', '/groups')
  const { mutate: updateGroup, isPending: isUpdating } = accessClient.useMutation('patch', '/groups/{group_id}')
  const isPending = isCreating || isUpdating

  const onSubmit = (formData: GroupFormData) => {
    const alertContext = formData.name ? `Group "${formData.name}"` : undefined

    if (isEditMode && group) {
      updateGroup(
        {
          params: { path: { group_id: group.id } },
          body: { name: formData.name, description: formData.description },
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
        { body: { name: formData.name, description: formData.description } },
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
          <SynForm form={form}>
            <SynTextField
              name="name"
              label="Group name"
              fieldId="group-name"
              isRequired
              placeholder="Enter group name"
              labelHelp={groupHelp.name}
            />
            <SynTextAreaField
              name="description"
              label="Description"
              fieldId="group-description"
              placeholder="Enter description"
              rows={3}
            />
          </SynForm>
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
