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
  TextInput,
} from '@patternfly/react-core'
import { useQueryClient } from '@tanstack/react-query'
import { Controller, useForm } from 'react-hook-form'

import { invalidateAuthzCaches } from '../../hooks/invalidateAuthzCaches'
import { useFormMutationErrorHandler } from '../../hooks/useFormMutationErrorHandler'
import { useAlerts } from '../../providers/alerts'

import { accessClient } from './accessClient'
import { accessControlHelp } from './accessControlFieldHelp'
import { roleBaseSchema } from './addRoleSchema'
import type { EditRoleFormData } from './addRoleSchema'
import { PolicySelect } from './PolicySelect'
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
          <FormGroup label="Name" isRequired fieldId="role-name">
            <TextInput
              id="role-name"
              isRequired
              aria-label="Role name"
              validated={errors.name ? 'error' : 'default'}
              {...register('name')}
            />
            {errors.name ? (
              <FormHelperText>
                <HelperText>
                  <HelperTextItem variant="error">{errors.name.message}</HelperTextItem>
                </HelperText>
              </FormHelperText>
            ) : (
              <FormHelperText>
                <HelperText>
                  <HelperTextItem>Lowercase alphanumeric with hyphens (e.g. my-custom-role)</HelperTextItem>
                </HelperText>
              </FormHelperText>
            )}
          </FormGroup>

          <FormGroup label="Description" fieldId="role-description">
            <TextInput
              id="role-description"
              aria-label="Role description"
              validated={errors.description ? 'error' : 'default'}
              {...register('description')}
            />
            {errors.description && (
              <FormHelperText>
                <HelperText>
                  <HelperTextItem variant="error">{errors.description.message}</HelperTextItem>
                </HelperText>
              </FormHelperText>
            )}
          </FormGroup>

          <FormGroup label="Policies" isRequired fieldId="role-policies" labelHelp={accessControlHelp.policies}>
            <Controller
              name="policies"
              control={control}
              render={({ field }) => (
                <PolicySelect
                  selected={field.value}
                  onChange={field.onChange}
                  hasError={!!errors.policies}
                  scopeProjectId={role.project_id ?? null}
                />
              )}
            />
            {errors.policies && (
              <FormHelperText>
                <HelperText>
                  <HelperTextItem variant="error">{errors.policies.message}</HelperTextItem>
                </HelperText>
              </FormHelperText>
            )}
          </FormGroup>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" form="edit-role-form" type="submit" isLoading={isPending}>
          Save
        </Button>
        <Button variant="link" onClick={onClose}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
