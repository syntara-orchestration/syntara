import { Button, Form, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'

import { SynForm } from '../../../components/forms/SynForm'
import { SynFormField } from '../../../components/forms/SynFormField'
import { SynTextField } from '../../../components/forms/SynTextField'
import { useSynForm } from '../../../hooks/useSynForm'
import { useAlerts } from '../../../providers/alerts'
import { accessClient } from '../../access/accessClient'
import { accessControlHelp } from '../../access/accessControlFieldHelp'

import { addProjectRoleSchema, PROJECT_ROLE_NAME_HINT } from './addProjectRoleSchema'
import type { AddProjectRoleFormData } from './addProjectRoleSchema'
import { ProjectPolicySelect } from './ProjectPolicySelect'

type AddProjectRoleDialogProps = {
  projectId: string
  onClose: () => void
  onSuccess: () => void
}

export function AddProjectRoleDialog({ projectId, onClose, onSuccess }: Readonly<AddProjectRoleDialogProps>) {
  const { showSuccess } = useAlerts()

  const form = useSynForm({
    schema: addProjectRoleSchema,
    defaultValues: {
      name: '',
      description: '',
      policies: [],
    },
    onClose,
  })
  const { handleSubmit, handleError, handleClose } = form

  const { mutate: createRole, isPending } = accessClient.useMutation('post', '/projects/{project_id}/roles')

  const onSubmit = (data: AddProjectRoleFormData) => {
    createRole(
      {
        params: { path: { project_id: projectId } },
        body: {
          name: data.name,
          description: data.description || undefined,
          policies: data.policies,
        },
      },
      {
        onSuccess: () => {
          showSuccess({ title: 'Role added', description: 'Role created successfully' })
          handleClose()
          onSuccess()
        },
        onError: handleError({ title: 'Failed to add role' }),
      }
    )
  }

  return (
    <Modal isOpen onClose={handleClose} variant="medium">
      <ModalHeader title="Add Project Role" />
      <ModalBody>
        <Form id="add-project-role-form" onSubmit={handleSubmit(onSubmit)}>
          <SynForm form={form}>
            <SynTextField
              name="name"
              label="Role name"
              fieldId="project-role-name"
              isRequired
              hint={PROJECT_ROLE_NAME_HINT}
            />
            <SynTextField name="description" label="Role description" fieldId="project-role-description" />
            <SynFormField<AddProjectRoleFormData, 'policies'>
              name="policies"
              label="Policies"
              fieldId="project-role-policies"
              isRequired
              labelHelp={accessControlHelp.policies}
            >
              {({ field, fieldState }) => (
                <ProjectPolicySelect
                  projectId={projectId}
                  selected={field.value}
                  onChange={field.onChange}
                  hasError={!!fieldState.error}
                />
              )}
            </SynFormField>
          </SynForm>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          form="add-project-role-form"
          type="submit"
          isDisabled={isPending}
          isLoading={isPending}
        >
          Add
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isPending}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
