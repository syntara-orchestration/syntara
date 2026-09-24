import { useQueryClient } from '@tanstack/react-query'

import { useSynForm } from '../../hooks/useSynForm'
import { useAlerts } from '../../providers/alerts'
import { detachPromise } from '../../utils/detachPromise'
import { buildAssignmentBody, RolePrincipalType } from '../access-management/RoleAssignmentTypes'

import { accessClient } from './accessClient'
import type { AssignRoleFormBodyProps } from './AssignRoleFormBody'
import { assignRoleSchema } from './assignRoleSchema'
import type { AssignRoleFormData } from './assignRoleSchema'
import { assignmentAddedDescription } from './assignRoleSuccessMessage'
import { roleAssignmentsQueryKey } from './useAlreadyAssignedRoles'
import { useAssignRoleFormQueries } from './useAssignRoleFormQueries'

type UseAssignRoleDialogOptions = {
  onClose: () => void
  onSuccess: () => void
}

export function useAssignRoleDialog({ onClose, onSuccess }: UseAssignRoleDialogOptions) {
  const queryClient = useQueryClient()
  const { showSuccess } = useAlerts()

  const form = useSynForm({
    schema: assignRoleSchema,
    defaultValues: {
      principalType: RolePrincipalType.USER,
      scope: 'project',
      projectId: '',
      userId: '',
      groupId: '',
      serviceAccountId: '',
      roleName: '',
    },
    onClose,
  })
  const { handleSubmit, handleError, handleClose, control, setValue } = form

  const queries = useAssignRoleFormQueries(control)

  const { mutate: createRoleAssignment, isPending: isPendingSystem } = accessClient.useMutation(
    'post',
    '/role_assignments'
  )
  const { mutate: createProjectRoleAssignment, isPending: isPendingProject } = accessClient.useMutation(
    'post',
    '/projects/{project_id}/role_assignments'
  )
  const isPending = isPendingSystem || isPendingProject

  const onPrincipalTypeChange = (value: RolePrincipalType) => {
    setValue('userId', '')
    setValue('groupId', '')
    setValue('serviceAccountId', '')
    if (value === RolePrincipalType.SERVICE_ACCOUNT) {
      setValue('scope', 'project')
      setValue('roleName', '')
    }
  }

  const onScopeChange = (value: string) => {
    setValue('roleName', '')
    if (value !== 'project') {
      setValue('projectId', '')
    }
  }

  const onProjectChange = () => {
    setValue('roleName', '')
  }

  const onSubmit = (data: AssignRoleFormData) => {
    const principalIdByType: Record<RolePrincipalType, string> = {
      [RolePrincipalType.USER]: data.userId,
      [RolePrincipalType.GROUP]: data.groupId,
      [RolePrincipalType.SERVICE_ACCOUNT]: data.serviceAccountId,
    }
    const principalId = principalIdByType[data.principalType]
    const body = buildAssignmentBody(data.principalType, principalId, data.roleName)
    const onMutationSuccess = () => {
      detachPromise(
        queryClient.invalidateQueries({
          queryKey: roleAssignmentsQueryKey(data.principalType, principalId),
        })
      )
      showSuccess({
        title: 'Assignment added',
        description: assignmentAddedDescription(
          data,
          queries.userOptions,
          queries.groupOptions,
          queries.serviceAccountOptions
        ),
      })
      handleClose()
      onSuccess()
    }
    const onMutationError = handleError({ title: 'Failed to add assignment' })

    if (data.scope === 'project') {
      createProjectRoleAssignment(
        { params: { path: { project_id: data.projectId } }, body },
        { onSuccess: onMutationSuccess, onError: onMutationError }
      )
    } else {
      createRoleAssignment({ body }, { onSuccess: onMutationSuccess, onError: onMutationError })
    }
  }

  const formBodyProps: AssignRoleFormBodyProps = {
    form,
    principalType: queries.principalType,
    isProjectScoped: queries.isProjectScoped,
    projectOptions: queries.projectOptions,
    userOptions: queries.userOptions,
    groupOptions: queries.groupOptions,
    serviceAccountOptions: queries.serviceAccountOptions,
    roleOptions: queries.roleOptions,
    roleDisabled: queries.isProjectScoped && !queries.selectedProjectId,
    isProjectsLoading: queries.isProjectsLoading,
    onUserSearchChange: queries.setUserSearchTerm,
    hasMoreUsers: !!queries.usersQuery.data?.next,
    isUsersLoading: queries.usersQuery.isFetching,
    onGroupSearchChange: queries.setGroupSearchTerm,
    hasMoreGroups: !!queries.groupsQuery.data?.next,
    isGroupsLoading: queries.groupsQuery.isFetching,
    onServiceAccountSearchChange: queries.setSaSearchTerm,
    hasMoreServiceAccounts: !!queries.serviceAccountsQuery.data?.next,
    isServiceAccountsLoading: queries.serviceAccountsQuery.isFetching,
    onRoleSearchChange: queries.setRoleSearchTerm,
    hasMoreRoles: !!queries.activeRolesQuery.data?.next,
    isRolesLoading: queries.activeRolesQuery.isFetching || queries.isAssignmentsLoading,
    isAssignmentsError: queries.isAssignmentsError,
    onPrincipalTypeChange,
    onScopeChange,
    onProjectChange,
  }

  return { handleSubmit, onSubmit, handleClose, isPending, formBodyProps }
}
