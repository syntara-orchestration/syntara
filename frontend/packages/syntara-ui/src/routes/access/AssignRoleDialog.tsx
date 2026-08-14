import { zodResolver } from '@hookform/resolvers/zod'
import {
  Button,
  Form,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
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
import { useMemo, useState } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'

import { NxSelect } from '../../components/NxSelect'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { useFormMutationErrorHandler } from '../../hooks/useFormMutationErrorHandler'
import { useAlerts } from '../../providers/alerts'
import { buildAssignmentBody, RolePrincipalType } from '../access-management/RoleAssignmentTypes'

import { accessClient } from './accessClient'
import { accessControlHelp } from './accessControlFieldHelp'
import { assignRoleSchema } from './assignRoleSchema'
import type { AssignRoleFormData } from './assignRoleSchema'
import { PrincipalTypeSelect } from './PrincipalTypeSelect'
import { TypeaheadSelect } from './TypeaheadSelect'
import { useSelectableProjects } from './useAllProjects'

const PAGE_SIZE = 20

// ── Principal selector field ──────────────────────────────────────────────

type PrincipalFieldProps = {
  control: ReturnType<typeof useForm<AssignRoleFormData>>['control']
  name: 'userId' | 'groupId' | 'serviceAccountId'
  label: string
  fieldId: string
  options: { value: string; label: string }[]
  placeholder: string
  onSearchChange?: (term: string) => void
  hasMore?: boolean
  isLoading?: boolean
}

function PrincipalField({
  control,
  name,
  label,
  fieldId,
  options,
  placeholder,
  onSearchChange,
  hasMore,
  isLoading,
}: Readonly<PrincipalFieldProps>) {
  return (
    <FormGroup label={label} isRequired fieldId={fieldId}>
      <Controller
        name={name}
        control={control}
        render={({ field, fieldState }) => (
          <>
            <TypeaheadSelect
              id={fieldId}
              ariaLabel={label}
              options={options}
              selected={field.value ?? ''}
              onChange={field.onChange}
              placeholder={placeholder}
              hasError={!!fieldState.error}
              onSearchChange={onSearchChange}
              hasMore={hasMore}
              isLoading={isLoading}
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
  )
}

// ── Form body (extracted to stay within max-lines-per-function) ───────────

type AssignRoleFormBodyProps = {
  control: ReturnType<typeof useForm<AssignRoleFormData>>['control']
  setValue: ReturnType<typeof useForm<AssignRoleFormData>>['setValue']
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
}

function ScopeSelect({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [isOpen, setIsOpen] = useState(false)
  return (
    <NxSelect
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
    </NxSelect>
  )
}

function AssignRoleFormBody({
  control,
  setValue,
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
}: Readonly<AssignRoleFormBodyProps>) {
  return (
    <>
      <FormGroup label="Principal type" isRequired fieldId="principal-type" labelHelp={accessControlHelp.principalType}>
        <Controller
          name="principalType"
          control={control}
          render={({ field }) => (
            <PrincipalTypeSelect
              value={field.value}
              onChange={(value) => {
                field.onChange(value)
                setValue('userId', '')
                setValue('groupId', '')
                setValue('serviceAccountId', '')
                if (value === RolePrincipalType.SERVICE_ACCOUNT) {
                  setValue('scope', 'project')
                  setValue('roleName', '')
                }
              }}
            />
          )}
        />
      </FormGroup>

      {principalType !== RolePrincipalType.SERVICE_ACCOUNT && (
        <FormGroup label="Scope" isRequired fieldId="scope" labelHelp={accessControlHelp.scope}>
          <Controller
            name="scope"
            control={control}
            render={({ field }) => (
              <ScopeSelect
                value={field.value}
                onChange={(value) => {
                  field.onChange(value)
                  setValue('roleName', '')
                }}
              />
            )}
          />
        </FormGroup>
      )}

      {isProjectScoped && (
        <FormGroup label="Project" isRequired fieldId="project-id">
          <Controller
            name="projectId"
            control={control}
            render={({ field, fieldState }) => (
              <>
                <TypeaheadSelect
                  id="project-id"
                  ariaLabel="Project"
                  options={projectOptions}
                  selected={field.value ?? ''}
                  onChange={(value) => {
                    field.onChange(value)
                    setValue('roleName', '')
                  }}
                  placeholder="Select a project..."
                  hasError={!!fieldState.error}
                  isLoading={isProjectsLoading}
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
      )}

      {principalType === RolePrincipalType.USER && (
        <PrincipalField
          control={control}
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
        <PrincipalField
          control={control}
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
        <PrincipalField
          control={control}
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

      <FormGroup label="Role" isRequired fieldId="role-select" labelHelp={accessControlHelp.role}>
        <Controller
          name="roleName"
          control={control}
          render={({ field, fieldState }) => (
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
    </>
  )
}

// ── Dialog ─────────────────────────────────────────────────────────────────

type AssignRoleDialogProps = {
  onClose: () => void
  onSuccess: () => void
}

export function AssignRoleDialog({ onClose, onSuccess }: Readonly<AssignRoleDialogProps>) {
  const { showSuccess } = useAlerts()

  const { handleSubmit, control, setValue, setError } = useForm<AssignRoleFormData>({
    resolver: zodResolver(assignRoleSchema, undefined, { mode: 'sync' }),
    defaultValues: {
      principalType: RolePrincipalType.USER,
      scope: 'project',
      projectId: '',
      userId: '',
      groupId: '',
      serviceAccountId: '',
      roleName: '',
    },
  })

  const principalType = useWatch({ control, name: 'principalType' })
  const scope = useWatch({ control, name: 'scope' })
  const selectedProjectId = useWatch({ control, name: 'projectId' })
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
    () => (activeRolesQuery.data?.resources ?? []).map((role) => ({ value: role.name, label: role.name })),
    [activeRolesQuery.data]
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

  const handleError = useFormMutationErrorHandler<AssignRoleFormData>(setError)

  const onSubmit = (data: AssignRoleFormData) => {
    const onMutationSuccess = () => {
      showSuccess({ title: 'Assignment added', description: 'Assignment created successfully' })
      onSuccess()
      onClose()
    }
    const onMutationError = handleError({ title: 'Failed to add assignment' })
    const principalIdByType: Record<RolePrincipalType, string> = {
      [RolePrincipalType.USER]: data.userId,
      [RolePrincipalType.GROUP]: data.groupId,
      [RolePrincipalType.SERVICE_ACCOUNT]: data.serviceAccountId,
    }
    const principalId = principalIdByType[data.principalType]
    const body = buildAssignmentBody(data.principalType, principalId, data.roleName)

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
    <Modal isOpen onClose={onClose} variant="small">
      <ModalHeader title="Add Assignment" />
      <ModalBody>
        <Form id="assign-role-form" onSubmit={handleSubmit(onSubmit)}>
          <AssignRoleFormBody
            control={control}
            setValue={setValue}
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
            isRolesLoading={activeRolesQuery.isFetching}
          />
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" form="assign-role-form" type="submit" isLoading={isPending} icon={<RhUiAddIcon />}>
          Add assignment
        </Button>
        <Button variant="link" onClick={onClose}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
