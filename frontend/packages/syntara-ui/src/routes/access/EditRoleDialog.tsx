import { Button, Form, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'
import { useQueryClient } from '@tanstack/react-query'

import { SynForm } from '../../components/forms/SynForm'
import { SynFormField } from '../../components/forms/SynFormField'
import { SynTextField } from '../../components/forms/SynTextField'
import { invalidateAuthzCaches } from '../../hooks/invalidateAuthzCaches'
import { useSynForm } from '../../hooks/useSynForm'
import { useAlerts } from '../../providers/alerts'

import { accessClient } from './accessClient'
import { accessControlHelp } from './accessControlFieldHelp'
import { ROLE_NAME_HINT, roleBaseSchema } from './addRoleSchema'
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

  const form = useSynForm({
    schema: roleBaseSchema,
    defaultValues: {
      name: role.name,
      description: role.description ?? '',
      policies: role.policies ?? [],
    },
    values: {
      name: role.name,
      description: role.description ?? '',
      policies: role.policies ?? [],
    },
    onClose,
  })
  const { handleSubmit, handleError, handleClose } = form

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
          handleClose()
          onSuccess()
        },
        onError: handleError({ title: 'Failed to update role' }),
      }
    )
  }

  return (
    <Modal isOpen onClose={handleClose} variant="medium">
      <ModalHeader title={`Edit ${role.name}`} />
      <ModalBody>
        <Form id="edit-role-form" onSubmit={handleSubmit(onSubmit)}>
          <SynForm form={form}>
            <SynTextField name="name" label="Name" fieldId="role-name" isRequired hint={ROLE_NAME_HINT} />
            <SynTextField name="description" label="Description" fieldId="role-description" />
            <SynFormField<EditRoleFormData, 'policies'>
              name="policies"
              label="Policies"
              fieldId="role-policies"
              isRequired
              labelHelp={accessControlHelp.policies}
            >
              {({ field, fieldState }) => (
                <PolicySelect
                  selected={field.value}
                  onChange={field.onChange}
                  hasError={!!fieldState.error}
                  scopeProjectId={role.project_id ?? null}
                />
              )}
            </SynFormField>
          </SynForm>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" form="edit-role-form" type="submit" isDisabled={isPending} isLoading={isPending}>
          Save role
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isPending}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
