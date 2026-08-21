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
import { Controller, useForm } from 'react-hook-form'

import { useFormMutationErrorHandler } from '../../../hooks/useFormMutationErrorHandler'
import { useAlerts } from '../../../providers/alerts'
import { accessClient } from '../../access/accessClient'
import { accessControlHelp } from '../../access/accessControlFieldHelp'
import type { ProjectRoleRead } from '../../access/types'

import { addProjectRoleSchema } from './addProjectRoleSchema'
import type { AddProjectRoleFormData } from './addProjectRoleSchema'
import { ProjectPolicySelect } from './ProjectPolicySelect'

type EditProjectRoleDialogProps = {
  projectId: string
  role: ProjectRoleRead
  onClose: () => void
  onSuccess: () => void
}

export function EditProjectRoleDialog({ projectId, role, onClose, onSuccess }: Readonly<EditProjectRoleDialogProps>) {
  const { showSuccess } = useAlerts()

  const {
    register,
    handleSubmit,
    control,
    setError,
    formState: { errors },
  } = useForm<AddProjectRoleFormData>({
    resolver: zodResolver(addProjectRoleSchema, undefined, { mode: 'sync' }),
    defaultValues: {
      name: role.name,
      description: role.description ?? '',
      policies: role.policies ?? [],
    },
  })

  const handleError = useFormMutationErrorHandler<AddProjectRoleFormData>(setError)
  const { mutate: updateRole, isPending } = accessClient.useMutation('put', '/projects/{project_id}/roles/{role_id}')

  const onSubmit = (data: AddProjectRoleFormData) => {
    updateRole(
      {
        params: { path: { project_id: projectId, role_id: role.id } },
        body: {
          name: data.name,
          description: data.description || undefined,
          policies: data.policies,
        },
      },
      {
        onSuccess: () => {
          showSuccess({ title: 'Role updated', description: 'Role updated successfully' })
          onSuccess()
          onClose()
        },
        onError: handleError({ title: 'Failed to update role' }),
      }
    )
  }

  return (
    <Modal isOpen onClose={onClose} variant="medium">
      <ModalHeader title="Edit Project Role" />
      <ModalBody>
        <Form id="edit-project-role-form" onSubmit={handleSubmit(onSubmit)}>
          <FormGroup label="Name" isRequired fieldId="project-role-name">
            <TextInput
              id="project-role-name"
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

          <FormGroup label="Description" fieldId="project-role-description">
            <TextInput
              id="project-role-description"
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

          <FormGroup label="Policies" isRequired fieldId="project-role-policies" labelHelp={accessControlHelp.policies}>
            <Controller
              name="policies"
              control={control}
              render={({ field }) => (
                <ProjectPolicySelect
                  projectId={projectId}
                  selected={field.value}
                  onChange={field.onChange}
                  hasError={!!errors.policies}
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
        <Button variant="primary" form="edit-project-role-form" type="submit" isLoading={isPending}>
          Save role
        </Button>
        <Button variant="link" onClick={onClose}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
