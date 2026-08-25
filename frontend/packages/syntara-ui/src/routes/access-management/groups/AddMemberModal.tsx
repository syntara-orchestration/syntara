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
} from '@patternfly/react-core'
import { useMemo } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { z } from 'zod'

import { useFormMutationErrorHandler } from '../../../hooks/useFormMutationErrorHandler'
import { useAlerts } from '../../../providers/alerts'
import { accessClient } from '../../access/accessClient'
import { TypeaheadSelect } from '../../access/TypeaheadSelect'
import { useAllUsers } from '../../access/useAllUsers'
import { userDisplayName } from '../users/userDisplayName'

const addMemberSchema = z.object({
  userId: z.string().min(1, 'User is required'),
})

type AddMemberFormData = z.infer<typeof addMemberSchema>

type AddMemberModalProps = {
  groupId: string
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
  existingMemberIds: string[]
}

export function AddMemberModal({
  groupId,
  isOpen,
  onClose,
  onSuccess,
  existingMemberIds,
}: Readonly<AddMemberModalProps>) {
  const { showSuccess } = useAlerts()

  const { handleSubmit, control, reset, setError } = useForm<AddMemberFormData>({
    resolver: zodResolver(addMemberSchema, undefined, { mode: 'sync' }),
    defaultValues: { userId: '' },
  })

  const handleError = useFormMutationErrorHandler<AddMemberFormData>(setError)

  const { users: allUsers } = useAllUsers()

  const availableUsers = useMemo(() => {
    return allUsers
      .filter((u) => !existingMemberIds.includes(u.id))
      .map((u) => {
        const displayName = userDisplayName(u)
        return {
          value: u.id,
          label: u.username,
          description: displayName === u.username ? undefined : displayName,
        }
      })
  }, [allUsers, existingMemberIds])

  const { mutate: addMember, isPending } = accessClient.useMutation('post', '/groups/{group_id}/members')

  const handleClose = () => {
    reset()
    onClose()
  }

  const onSubmit = (data: AddMemberFormData) => {
    const user = availableUsers.find((u) => u.value === data.userId)
    addMember(
      {
        params: { path: { group_id: groupId } },
        body: { user_id: data.userId },
      },
      {
        onSuccess: () => {
          showSuccess({
            title: 'Member added',
            description: `User "${user?.label ?? data.userId}" has been added to the group.`,
          })
          handleClose()
          onSuccess()
        },
        onError: handleError({ title: 'Failed to add member' }),
      }
    )
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="medium">
      <ModalHeader title="Add member" />
      <ModalBody>
        <Form id="add-member-form" onSubmit={handleSubmit(onSubmit)}>
          <FormGroup label="User" fieldId="add-member-user" isRequired>
            <Controller
              name="userId"
              control={control}
              render={({ field, fieldState }) => (
                <>
                  <TypeaheadSelect
                    id="add-member-user"
                    ariaLabel="Select a user"
                    options={availableUsers}
                    selected={field.value}
                    onChange={field.onChange}
                    placeholder="Search for a user..."
                    hasError={!!fieldState.error}
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
        <Button variant="primary" type="submit" form="add-member-form" isDisabled={isPending} isLoading={isPending}>
          Add
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isPending}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
