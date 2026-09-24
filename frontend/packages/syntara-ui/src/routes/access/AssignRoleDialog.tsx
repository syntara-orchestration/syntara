import {
  Button,
  Form,
  MenuToggle,
  type MenuToggleElement,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  SelectList,
  SelectOption,
} from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'
import { useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useWatch } from 'react-hook-form'

import { FormFieldWarning } from '../../components/FormFieldError'
import { SynForm } from '../../components/forms/SynForm'
import { SynFormField } from '../../components/forms/SynFormField'
import { SynSelect } from '../../components/SynSelect'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import type { UseSynFormReturn } from '../../hooks/useSynForm'
import { useSynForm } from '../../hooks/useSynForm'
import { useAlerts } from '../../providers/alerts'
import { detachPromise } from '../../utils/detachPromise'
import { buildAssignmentBody, RolePrincipalType } from '../access-management/RoleAssignmentTypes'

import { accessClient } from './accessClient'
import { accessControlHelp } from './accessControlFieldHelp'
import { assignRoleSchema } from './assignRoleSchema'
import type { AssignRoleFormData } from './assignRoleSchema'
import { PrincipalField } from './PrincipalField'
import { PrincipalTypeSelect } from './PrincipalTypeSelect'
import { TypeaheadSelect } from './TypeaheadSelect'
import { useSelectableProjects } from './useAllProjects'
import { PRINCIPAL_ID_FIELD, roleAssignmentsQueryKey, useAlreadyAssignedRoles } from './useAlreadyAssignedRoles'

const PAGE_SIZE = 20

type NamedOption = { value: string; label: string }

function assignmentAddedDescription(
  data: AssignRoleFormData,
  userOptions: NamedOption[],
  groupOptions: NamedOption[],
  serviceAccountOptions: NamedOption[]
): string {
  const optionsByType = {
    [RolePrincipalType.USER]: userOptions,
    [RolePrincipalType.GROUP]: groupOptions,
    [RolePrincipalType.SERVICE_ACCOUNT]: serviceAccountOptions,
  }
  const idByType = {
    [RolePrincipalType.USER]: data.userId,
    [RolePrincipalType.GROUP]: data.groupId,
    [RolePrincipalType.SERVICE_ACCOUNT]: data.serviceAccountId,
  }
  const principalId = idByType[data.principalType]
  const principalName =
    optionsByType[data.principalType].find((option) => option.value === principalId)?.label ?? principalId
  return `Assignment for ${principalName} has been added.`
}

function ScopeSelect({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [isOpen, setIsOpen] = useState(false)
  return (
    <SynSelect
      id="scope"
      isOpen={isOpen}
      selected={value}
      onSelect={(_event, val) => {
        onChange(String(val))
        setIsOpen(false)
      }}
      onOpenChange={setIsOpen}
      toggle={(toggleRef: React.Ref<MenuToggleElement>) => (
        <MenuToggle
          ref={toggleRef}
          onClick={() => setIsOpen((prev) => !prev)}
          isExpanded={isOpen}
          isFullWidth
          aria-label="Scope"
        >
          {value === 'system' ? 'System' : 'Project'}
        </MenuToggle>
      )}
    >
      <SelectList>
        <SelectOption value="system">System</SelectOption>
        <SelectOption value="project">Project</SelectOption>
      </SelectList>
    </SynSelect>
  )
}

type AssignRoleFormBodyProps = {
  form: UseSynFormReturn<AssignRoleFormData>
  principalType: RolePrincipalType
  isProjectScoped: boolean
  projectOptions: { value: string; label: string }[]
  userOptions: { value: string; label: string }[]
  groupOptions: { value: string; label: string }[]
  serviceAccountOptions: { value: string; label: string }[]
  roleOptions: { value: string; label: string }[]
  roleDisabled: boolean
  isProjectsLoading: boolean
  onUserSearchChange: (term: string) => void
  hasMoreUsers: boolean
  isUsersLoading: boolean
  onGroupSearchChange: (term: string) => void
  hasMoreGroups: boolean
  isGroupsLoading: boolean
  onServiceAccountSearchChange: (term: string) => void
  hasMoreServiceAccounts: boolean
  isServiceAccountsLoading: boolean
  onRoleSearchChange: (term: string) => void
  hasMoreRoles: boolean
  isRolesLoading: boolean
  isAssignmentsError: boolean
  onPrincipalTypeChange: (value: RolePrincipalType) => void
  onScopeChange: (value: string) => void
  onProjectChange: (value: string) => void
}

function AssignRoleFormBody({
  form,
  principalType,
  isProjectScoped,
  projectOptions,
  userOptions,
  groupOptions,
  serviceAccountOptions,
  roleOptions,
  roleDisabled,
  isProjectsLoading,
  onUserSearchChange,
  hasMoreUsers,
  isUsersLoading,
  onGroupSearchChange,
  hasMoreGroups,
  isGroupsLoading,
  onServiceAccountSearchChange,
  hasMoreServiceAccounts,
  isServiceAccountsLoading,
  onRoleSearchChange,
  hasMoreRoles,
  isRolesLoading,
  isAssignmentsError,
  onPrincipalTypeChange,
  onScopeChange,
  onProjectChange,
}: Readonly<AssignRoleFormBodyProps>) {
  return (
    <SynForm form={form}>
      <SynFormField<AssignRoleFormData, 'principalType'>
        name="principalType"
        label="Principal type"
        fieldId="principal-type"
        isRequired
        labelHelp={accessControlHelp.principalType}
      >
        {({ field }) => (
          <PrincipalTypeSelect
            value={field.value}
            onChange={(value) => {
              field.onChange(value)
              onPrincipalTypeChange(value as RolePrincipalType)
            }}
          />
        )}
      </SynFormField>

      {principalType !== RolePrincipalType.SERVICE_ACCOUNT && (
        <SynFormField<AssignRoleFormData, 'scope'>
          name="scope"
          label="Scope"
          fieldId="scope"
          isRequired
          labelHelp={accessControlHelp.scope}
        >
          {({ field }) => (
            <ScopeSelect
              value={field.value}
              onChange={(value) => {
                field.onChange(value)
                onScopeChange(value)
              }}
            />
          )}
        </SynFormField>
      )}

      {isProjectScoped && (
        <SynFormField<AssignRoleFormData, 'projectId'>
          name="projectId"
          label="Project"
          fieldId="project-id"
          isRequired
        >
          {({ field, fieldState }) => (
            <TypeaheadSelect
              id="project-id"
              ariaLabel="Project"
              options={projectOptions}
              selected={field.value ?? ''}
              onChange={(value) => {
                field.onChange(value)
                onProjectChange(value)
              }}
              placeholder="Select a project..."
              hasError={!!fieldState.error}
              isLoading={isProjectsLoading}
            />
          )}
        </SynFormField>
      )}

      {principalType === RolePrincipalType.USER && (
        <PrincipalField<AssignRoleFormData>
          name="userId"
          label="User"
          fieldId="user-id"
          options={userOptions}
          placeholder="Select a user..."
          onSearchChange={onUserSearchChange}
          hasMore={hasMoreUsers}
          isLoading={isUsersLoading}
        />
      )}

      {principalType === RolePrincipalType.GROUP && (
        <PrincipalField<AssignRoleFormData>
          name="groupId"
          label="Group"
          fieldId="group-id"
          options={groupOptions}
          placeholder="Select a group..."
          onSearchChange={onGroupSearchChange}
          hasMore={hasMoreGroups}
          isLoading={isGroupsLoading}
        />
      )}

      {principalType === RolePrincipalType.SERVICE_ACCOUNT && (
        <PrincipalField<AssignRoleFormData>
          name="serviceAccountId"
          label="Service account"
          fieldId="service-account-id"
          options={serviceAccountOptions}
          placeholder="Select a service account..."
          onSearchChange={onServiceAccountSearchChange}
          hasMore={hasMoreServiceAccounts}
          isLoading={isServiceAccountsLoading}
        />
      )}

      <SynFormField<AssignRoleFormData, 'roleName'>
        name="roleName"
        label="Role"
        fieldId="role-select"
        isRequired
        labelHelp={accessControlHelp.role}
      >
        {({ field, fieldState }) => (
          <>
            <TypeaheadSelect
              id="role-select"
              ariaLabel="Role"
              options={roleOptions}
              selected={field.value ?? ''}
              onChange={field.onChange}
              placeholder={roleDisabled ? 'Select a project first...' : 'Select a role...'}
              hasError={!!fieldState.error}
              isDisabled={roleDisabled}
              onSearchChange={onRoleSearchChange}
              hasMore={hasMoreRoles}
              isLoading={isRolesLoading}
            />
            <FormFieldWarning message={isAssignmentsError ? 'Unable to check existing assignments' : undefined} />
          </>
        )}
      </SynFormField>
    </SynForm>
  )
}

type AssignRoleDialogProps = {
  onClose: () => void
  onSuccess: () => void
}

export function AssignRoleDialog({ onClose, onSuccess }: Readonly<AssignRoleDialogProps>) {
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

  const principalType = useWatch({ control, name: 'principalType' })
  const scope = useWatch({ control, name: 'scope' })
  const selectedProjectId = useWatch({ control, name: 'projectId' })
  const selectedPrincipalId = useWatch({ control, name: PRINCIPAL_ID_FIELD[principalType] })
  const isProjectScoped = scope === 'project'

  const { projects: allProjects, isLoading: isProjectsLoading } = useSelectableProjects()
  const projectOptions = useMemo(
    () =>
      allProjects.filter((p): p is typeof p & { id: string } => !!p.id).map((p) => ({ value: p.id, label: p.name })),
    [allProjects]
  )

  const [userSearchTerm, setUserSearchTerm] = useState('')
  const debouncedUserSearch = useDebouncedValue(userSearchTerm)
  const usersQuery = accessClient.useQuery('get', '/users/directory', {
    params: {
      query: {
        sort: 'username',
        limit: PAGE_SIZE,
        ...(debouncedUserSearch ? { 'username[contains]': debouncedUserSearch } : {}),
      },
    },
  })
  const userOptions = useMemo(
    () => (usersQuery.data?.resources ?? []).map((u) => ({ value: u.id, label: u.username })),
    [usersQuery.data]
  )

  const [groupSearchTerm, setGroupSearchTerm] = useState('')
  const debouncedGroupSearch = useDebouncedValue(groupSearchTerm)
  const groupsQuery = accessClient.useQuery('get', '/groups/directory', {
    params: {
      query: {
        sort: 'name',
        limit: PAGE_SIZE,
        ...(debouncedGroupSearch ? { 'name[contains]': debouncedGroupSearch } : {}),
      },
    },
  })
  const groupOptions = useMemo(
    () => (groupsQuery.data?.resources ?? []).map((g) => ({ value: g.id, label: g.name })),
    [groupsQuery.data]
  )

  const [saSearchTerm, setSaSearchTerm] = useState('')
  const debouncedSaSearch = useDebouncedValue(saSearchTerm)
  const serviceAccountsQuery = accessClient.useQuery(
    'get',
    '/service_accounts',
    {
      params: {
        query: { sort: 'name', limit: PAGE_SIZE, ...(debouncedSaSearch ? { name: debouncedSaSearch } : {}) },
      },
    },
    { enabled: principalType === RolePrincipalType.SERVICE_ACCOUNT }
  )
  const serviceAccountOptions = useMemo(
    () => (serviceAccountsQuery.data?.resources ?? []).map((sa) => ({ value: sa.id, label: sa.name })),
    [serviceAccountsQuery.data]
  )

  const {
    assigned: alreadyAssignedRoles,
    isLoading: isAssignmentsLoading,
    isError: isAssignmentsError,
  } = useAlreadyAssignedRoles(principalType, selectedPrincipalId ?? '', isProjectScoped, selectedProjectId ?? '')
  const [roleSearchTerm, setRoleSearchTerm] = useState('')
  const debouncedRoleSearch = useDebouncedValue(roleSearchTerm)
  const systemRolesQuery = accessClient.useQuery('get', '/roles', {
    params: {
      query: {
        sort: 'name',
        limit: PAGE_SIZE,
        scope: 'system',
        ...(debouncedRoleSearch ? { 'name[contains]': debouncedRoleSearch } : {}),
      },
    },
  })
  const projectRolesQuery = accessClient.useQuery(
    'get',
    '/projects/{project_id}/roles',
    {
      params: {
        path: { project_id: selectedProjectId || '' },
        query: {
          sort: 'name',
          limit: PAGE_SIZE,
          ...(debouncedRoleSearch ? { 'name[contains]': debouncedRoleSearch } : {}),
        },
      },
    },
    { enabled: isProjectScoped && !!selectedProjectId }
  )
  const activeRolesQuery = isProjectScoped ? projectRolesQuery : systemRolesQuery
  const roleOptions = useMemo(
    () =>
      isAssignmentsLoading
        ? []
        : (activeRolesQuery.data?.resources ?? [])
            .filter((r) => !alreadyAssignedRoles.has(r.name))
            .map((r) => ({ value: r.name, label: r.name })),
    [activeRolesQuery.data, alreadyAssignedRoles, isAssignmentsLoading]
  )

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
        description: assignmentAddedDescription(data, userOptions, groupOptions, serviceAccountOptions),
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

  return (
    <Modal isOpen onClose={handleClose} variant="small">
      <ModalHeader title="Add Assignment" />
      <ModalBody>
        <Form id="assign-role-form" onSubmit={handleSubmit(onSubmit)}>
          <AssignRoleFormBody
            form={form}
            principalType={principalType}
            isProjectScoped={isProjectScoped}
            projectOptions={projectOptions}
            userOptions={userOptions}
            groupOptions={groupOptions}
            serviceAccountOptions={serviceAccountOptions}
            roleOptions={roleOptions}
            roleDisabled={isProjectScoped && !selectedProjectId}
            isProjectsLoading={isProjectsLoading}
            onUserSearchChange={setUserSearchTerm}
            hasMoreUsers={!!usersQuery.data?.next}
            isUsersLoading={usersQuery.isFetching}
            onGroupSearchChange={setGroupSearchTerm}
            hasMoreGroups={!!groupsQuery.data?.next}
            isGroupsLoading={groupsQuery.isFetching}
            onServiceAccountSearchChange={setSaSearchTerm}
            hasMoreServiceAccounts={!!serviceAccountsQuery.data?.next}
            isServiceAccountsLoading={serviceAccountsQuery.isFetching}
            onRoleSearchChange={setRoleSearchTerm}
            hasMoreRoles={!!activeRolesQuery.data?.next}
            isRolesLoading={activeRolesQuery.isFetching || isAssignmentsLoading}
            isAssignmentsError={isAssignmentsError}
            onPrincipalTypeChange={onPrincipalTypeChange}
            onScopeChange={onScopeChange}
            onProjectChange={onProjectChange}
          />
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          form="assign-role-form"
          type="submit"
          isDisabled={isPending}
          isLoading={isPending}
          icon={<RhUiAddIcon />}
        >
          Add assignment
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isPending}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
