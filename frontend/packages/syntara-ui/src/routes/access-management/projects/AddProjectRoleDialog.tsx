import { Button, Form, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'

import { SynForm } from '../../../components/forms/SynForm'
import { useSynForm } from '../../../hooks/useSynForm'
import { useAlerts } from '../../../providers/alerts'
import { accessClient } from '../../access/accessClient'
import { ProjectRoleSynFormFields } from '../../access/RoleFormFields'

import { addProjectRoleSchema } from './addProjectRoleSchema'
import type { AddProjectRoleFormData } from './addProjectRoleSchema'

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
            <ProjectRoleSynFormFields
              projectId={projectId}
              fieldIds={{
                name: 'project-role-name',
                description: 'project-role-description',
                policies: 'project-role-policies',
              }}
            />
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
          icon={<RhUiAddIcon />}
        >
          Add role
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isPending}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
