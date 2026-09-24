import {
  Button,
  Content,
  ContentVariants,
  Form,
  FormGroup,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
} from '@patternfly/react-core'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'

import { SynForm } from '../../components/forms/SynForm'
import { SynFormField } from '../../components/forms/SynFormField'
import { invalidateAuthzCaches } from '../../hooks/invalidateAuthzCaches'
import { useSynForm } from '../../hooks/useSynForm'
import { useAlerts } from '../../providers/alerts'
import { detachPromise } from '../../utils/detachPromise'
import { buildAssignmentBody } from '../access-management/RoleAssignmentTypes'

import { accessClient } from './accessClient'
import { accessControlHelp } from './accessControlFieldHelp'
import { assignNewThenDeleteOldWithRollback } from './editAssignmentMutations'
import { editAssignmentSchema } from './editAssignmentSchema'
import type { EditAssignmentFormData } from './editAssignmentSchema'
import { TypeaheadSelect } from './TypeaheadSelect'
import type { PermissionRow } from './types'
import { useAllRoles } from './useAllRoles'

type EditAssignmentDialogProps = {
  row: PermissionRow
  displayName: string
  onClose: () => void
  onSuccess: () => void
}

export function EditAssignmentDialog({ row, displayName, onClose, onSuccess }: Readonly<EditAssignmentDialogProps>) {
  const queryClient = useQueryClient()
  const { showSuccess } = useAlerts()
  const [isPending, setIsPending] = useState(false)

  const isProjectScoped = row.scopeType === 'project'

  const { roles: allRoles } = useAllRoles()

  const roleOptions = useMemo(
    () =>
      allRoles.map((role) =>
        isProjectScoped ? { value: role.name, label: role.name } : { value: role.id, label: role.name }
      ),
    [allRoles, isProjectScoped]
  )

  const form = useSynForm({
    schema: editAssignmentSchema,
    defaultValues: {
      roleName: '',
    },
    onClose,
  })
  const { handleSubmit, handleError, handleClose, reset, setError } = form

  useEffect(() => {
    reset({ roleName: isProjectScoped ? row.assignmentName : '' })
  }, [row, isProjectScoped, reset])

  const { mutateAsync: deleteRoleAssignment } = accessClient.useMutation('delete', '/role_assignments/{assignment_id}')
  const { mutateAsync: deleteProjectRoleAssignment } = accessClient.useMutation(
    'delete',
    '/projects/{project_id}/role_assignments/{assignment_id}'
  )

  const { mutateAsync: createRoleAssignment } = accessClient.useMutation('post', '/role_assignments')
  const { mutateAsync: createProjectRoleAssignment } = accessClient.useMutation(
    'post',
    '/projects/{project_id}/role_assignments'
  )

  const onSubmit = async (data: EditAssignmentFormData) => {
    const newRole = data.roleName
    if (!newRole || newRole === row.assignmentName) {
      handleClose()
      return
    }

    setIsPending(true)
    try {
      if (row.sourceEndpoint === 'project-role-assignments') {
        if (!row.projectId) {
          setError('roleName', { message: 'Invalid assignment: missing project ID' })
          setIsPending(false)
          return
        }
        const pid = row.projectId
        const projectBody = buildAssignmentBody(row.principalType, row.principalId, newRole)
        await assignNewThenDeleteOldWithRollback({
          assignNew: () =>
            createProjectRoleAssignment({
              params: { path: { project_id: pid } },
              body: projectBody,
            }),
          deleteOld: () =>
            deleteProjectRoleAssignment({ params: { path: { project_id: pid, assignment_id: row.id } } }),
          revokeNew: (newAssignmentId) =>
            deleteProjectRoleAssignment({ params: { path: { project_id: pid, assignment_id: newAssignmentId } } }),
        })
      } else {
        const globalBody = buildAssignmentBody(row.principalType, row.principalId, newRole)
        await assignNewThenDeleteOldWithRollback({
          assignNew: () =>
            createRoleAssignment({
              body: globalBody,
            }),
          deleteOld: () => deleteRoleAssignment({ params: { path: { assignment_id: row.id } } }),
          revokeNew: (newAssignmentId) =>
            deleteRoleAssignment({ params: { path: { assignment_id: newAssignmentId } } }),
        })
      }

      showSuccess({ title: 'Assignment updated', description: `Updated role for ${displayName}` })
      invalidateAuthzCaches(queryClient)
      detachPromise(queryClient.invalidateQueries({ queryKey: ['role-assignments'] }))
      handleClose()
      onSuccess()
    } catch (error) {
      handleError({ title: 'Failed to update assignment' })(error)
    } finally {
      setIsPending(false)
    }
  }

  return (
    <Modal isOpen onClose={handleClose} variant="small">
      <ModalHeader title="Edit principal assignment" />
      <ModalBody>
        <Form id="edit-assignment-form" onSubmit={handleSubmit(onSubmit)}>
          <FormGroup label="Principal" fieldId="principal-display">
            <Content component={ContentVariants.p}>{displayName}</Content>
          </FormGroup>

          <FormGroup label="Scope" fieldId="scope-display" labelHelp={accessControlHelp.scope}>
            <Content component={ContentVariants.p}>{row.scopeType === 'project' ? row.scopeName : 'System'}</Content>
          </FormGroup>

          <SynForm form={form}>
            <SynFormField<EditAssignmentFormData, 'roleName'>
              name="roleName"
              label="Role"
              fieldId="role-select"
              isRequired
              labelHelp={accessControlHelp.role}
            >
              {({ field, fieldState }) => (
                <TypeaheadSelect
                  id="role-select"
                  ariaLabel="Role"
                  options={roleOptions}
                  selected={field.value}
                  onChange={field.onChange}
                  placeholder="Select a role..."
                  hasError={!!fieldState.error}
                />
              )}
            </SynFormField>
          </SynForm>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" form="edit-assignment-form" type="submit" isDisabled={isPending} isLoading={isPending}>
          Save assignment
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isPending}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
