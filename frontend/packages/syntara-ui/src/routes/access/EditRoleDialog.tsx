import { zodResolver } from '@hookform/resolvers/zod'
import { Button, Form, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'
import { useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'

import { invalidateAuthzCaches } from '../../hooks/invalidateAuthzCaches'
import { useFormMutationErrorHandler } from '../../hooks/useFormMutationErrorHandler'
import { useAlerts } from '../../providers/alerts'

import { accessClient } from './accessClient'
import { roleBaseSchema } from './addRoleSchema'
import type { EditRoleFormData } from './addRoleSchema'
import { PolicySelect } from './PolicySelect'
import { RoleFormFields } from './RoleFormFields'
import type { RoleRead } from './types'

type EditRoleDialogProps = {
  role: RoleRead
  onClose: () => void
  onSuccess: () => void
}

export function EditRoleDialog({ role, onClose, onSuccess }: Readonly<EditRoleDialogProps>) {
  const queryClient = useQueryClient()
  const { showSuccess } = useAlerts()

  const {
    register,
    handleSubmit,
    control,
    setError,
    formState: { errors },
  } = useForm<EditRoleFormData>({
    resolver: zodResolver(roleBaseSchema, undefined, { mode: 'sync' }),
    defaultValues: {
      name: role.name,
      description: role.description ?? '',
      policies: role.policies,
    },
  })

  const handleError = useFormMutationErrorHandler<EditRoleFormData>(setError)
  const { mutate: updateRole, isPending } = accessClient.useMutation('put', '/roles/{role_id}')

  const onSubmit = (data: EditRoleFormData) => {
    updateRole(
      {
        params: { path: { role_id: role.id } },
        body: {
          name: data.name,
          description: data.description || undefined,
          policies: data.policies,
        },
      },
      {
        onSuccess: () => {
          showSuccess({ title: 'Role updated', description: `${data.name} has been updated.` })
          invalidateAuthzCaches(queryClient)
          onSuccess()
          onClose()
        },
        onError: handleError({ title: 'Failed to update role' }),
      }
    )
  }

  return (
    <Modal isOpen onClose={onClose} variant="medium">
      <ModalHeader title={`Edit ${role.name}`} />
      <ModalBody>
        <Form id="edit-role-form" onSubmit={handleSubmit(onSubmit)}>
          <RoleFormFields
            fieldIds={{ name: 'role-name', description: 'role-description', policies: 'role-policies' }}
            register={register}
            control={control}
            errors={errors}
            nameField="name"
            descriptionField="description"
            policiesField="policies"
            renderPolicySelect={({ selected, onChange, hasError }) => (
              <PolicySelect
                selected={selected}
                onChange={onChange}
                hasError={hasError}
                scopeProjectId={role.project_id ?? null}
              />
            )}
          />
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" form="edit-role-form" type="submit" isLoading={isPending}>
          Save role
        </Button>
        <Button variant="link" onClick={onClose}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
