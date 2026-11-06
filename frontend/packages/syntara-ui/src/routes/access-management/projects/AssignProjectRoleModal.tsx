import { Button, Form, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'
import { useMemo, useState } from 'react'
import { useWatch } from 'react-hook-form'

import { SynForm } from '../../../components/forms/SynForm'
import { SynFormField } from '../../../components/forms/SynFormField'
import { useDebouncedValue } from '../../../hooks/useDebouncedValue'
import type { UseSynFormReturn } from '../../../hooks/useSynForm'
import { useSynForm } from '../../../hooks/useSynForm'
import { useAlerts } from '../../../providers/alerts'
import { accessClient } from '../../access/accessClient'
import { accessControlHelp } from '../../access/accessControlFieldHelp'
import { PrincipalTypeSelect } from '../../access/PrincipalTypeSelect'
import { TypeaheadSelect } from '../../access/TypeaheadSelect'
import { useAllProjectRoles } from '../../access/useAllProjectRoles'
import { buildAssignmentBody, RolePrincipalType } from '../RoleAssignmentTypes'

import {
  assignProjectRoleDefaultValues,
  assignProjectRoleSchema,
  type AssignProjectRoleFormData,
} from './assignProjectRoleSchema'

const PAGE_SIZE = 20

type AssignProjectRoleModalProps = {
  projectId: string
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
  assignedRolesByPrincipal: Map<string, Set<string>>
}

type TypeaheadOption = { value: string; label: string; description?: string }

type AssignProjectRoleFormFieldsProps = {
  form: UseSynFormReturn<AssignProjectRoleFormData>
  principalType: RolePrincipalType
  selectedPrincipalId: string
  userOptions: TypeaheadOption[]
  groupOptions: TypeaheadOption[]
  serviceAccountOptions: TypeaheadOption[]
  roleOptions: TypeaheadOption[]
  rolesLoading: boolean
  onUserSearchChange: (term: string) => void
  hasMoreUsers: boolean
  isUsersLoading: boolean
  onGroupSearchChange: (term: string) => void
  hasMoreGroups: boolean
  isGroupsLoading: boolean
  onServiceAccountSearchChange: (term: string) => void
  hasMoreServiceAccounts: boolean
  isServiceAccountsLoading: boolean
  onResetDependentFields: () => void
  onPrincipalSelected: () => void
}

function getSelectedPrincipalId(
  principalType: RolePrincipalType,
  userId: string,
  groupId: string,
  serviceAccountId: string
): string {
  switch (principalType) {
    case RolePrincipalType.USER:
      return userId
    case RolePrincipalType.GROUP:
      return groupId
    case RolePrincipalType.SERVICE_ACCOUNT:
      return serviceAccountId
    default:
      return ''
  }
}

function AssignProjectRoleFormFields({
  form,
  principalType,
  selectedPrincipalId,
  userOptions,
  groupOptions,
  serviceAccountOptions,
  roleOptions,
  rolesLoading,
  onUserSearchChange,
  hasMoreUsers,
  isUsersLoading,
  onGroupSearchChange,
  hasMoreGroups,
  isGroupsLoading,
  onServiceAccountSearchChange,
  hasMoreServiceAccounts,
  isServiceAccountsLoading,
  onResetDependentFields,
  onPrincipalSelected,
}: Readonly<AssignProjectRoleFormFieldsProps>) {
  return (
    <SynForm form={form}>
      <SynFormField<AssignProjectRoleFormData, 'principalType'>
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
              onResetDependentFields()
            }}
          />
        )}
      </SynFormField>

      {principalType === RolePrincipalType.USER && (
        <SynFormField<AssignProjectRoleFormData, 'userId'> name="userId" label="User" fieldId="user-select" isRequired>
          {({ field, fieldState }) => (
            <TypeaheadSelect
              id="user-select"
              ariaLabel="User"
              options={userOptions}
              selected={field.value}
              onChange={(value) => {
                field.onChange(value)
                onPrincipalSelected()
              }}
              placeholder="Select a user..."
              hasError={!!fieldState.error}
              onSearchChange={onUserSearchChange}
              hasMore={hasMoreUsers}
              isLoading={isUsersLoading}
            />
          )}
        </SynFormField>
      )}

      {principalType === RolePrincipalType.GROUP && (
        <SynFormField<AssignProjectRoleFormData, 'groupId'>
          name="groupId"
          label="Group"
          fieldId="group-select"
          isRequired
        >
          {({ field, fieldState }) => (
            <TypeaheadSelect
              id="group-select"
              ariaLabel="Group"
              options={groupOptions}
              selected={field.value}
              onChange={(value) => {
                field.onChange(value)
                onPrincipalSelected()
              }}
              placeholder="Select a group..."
              hasError={!!fieldState.error}
              onSearchChange={onGroupSearchChange}
              hasMore={hasMoreGroups}
              isLoading={isGroupsLoading}
            />
          )}
        </SynFormField>
      )}

      {principalType === RolePrincipalType.SERVICE_ACCOUNT && (
        <SynFormField<AssignProjectRoleFormData, 'serviceAccountId'>
          name="serviceAccountId"
          label="Service account"
          fieldId="service-account-select"
          isRequired
        >
          {({ field, fieldState }) => (
            <TypeaheadSelect
              id="service-account-select"
              ariaLabel="Service account"
              options={serviceAccountOptions}
              selected={field.value}
              onChange={(value) => {
                field.onChange(value)
                onPrincipalSelected()
              }}
              placeholder="Select a service account..."
              hasError={!!fieldState.error}
              onSearchChange={onServiceAccountSearchChange}
              hasMore={hasMoreServiceAccounts}
              isLoading={isServiceAccountsLoading}
            />
          )}
        </SynFormField>
      )}

      <SynFormField<AssignProjectRoleFormData, 'roleName'>
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
            placeholder={rolesLoading ? 'Loading roles...' : 'Select a role...'}
            hasError={!!fieldState.error}
            isDisabled={rolesLoading || !selectedPrincipalId}
          />
        )}
      </SynFormField>
    </SynForm>
  )
}

export function AssignProjectRoleModal({
  projectId,
  isOpen,
  onClose,
  onSuccess,
  assignedRolesByPrincipal,
}: Readonly<AssignProjectRoleModalProps>) {
  const { showSuccess } = useAlerts()

  const form = useSynForm({
    schema: assignProjectRoleSchema,
    defaultValues: assignProjectRoleDefaultValues,
    onClose,
  })
  const { handleSubmit, handleError, handleClose: formHandleClose, setValue, control } = form

  const principalType = useWatch({ control, name: 'principalType' })
  const selectedUserId = useWatch({ control, name: 'userId' })
  const selectedGroupId = useWatch({ control, name: 'groupId' })
  const selectedServiceAccountId = useWatch({ control, name: 'serviceAccountId' })
  const selectedPrincipalId = getSelectedPrincipalId(
    principalType,
    selectedUserId,
    selectedGroupId,
    selectedServiceAccountId
  )

  const [userSearchTerm, setUserSearchTerm] = useState('')
  const debouncedUserSearch = useDebouncedValue(userSearchTerm)

  const usersQuery = accessClient.useQuery(
    'get',
    '/users/directory',
    {
      params: {
        query: {
          sort: 'username',
          limit: PAGE_SIZE,
          ...(debouncedUserSearch ? { 'username[contains]': debouncedUserSearch } : {}),
        },
      },
    },
    { enabled: isOpen && principalType === RolePrincipalType.USER }
  )

  const [groupSearchTerm, setGroupSearchTerm] = useState('')
  const debouncedGroupSearch = useDebouncedValue(groupSearchTerm)

  const groupsQuery = accessClient.useQuery(
    'get',
    '/groups/directory',
    {
      params: {
        query: {
          sort: 'name',
          limit: PAGE_SIZE,
          ...(debouncedGroupSearch ? { 'name[contains]': debouncedGroupSearch } : {}),
        },
      },
    },
    { enabled: isOpen && principalType === RolePrincipalType.GROUP }
  )

  const [serviceAccountSearchTerm, setServiceAccountSearchTerm] = useState('')
  const debouncedServiceAccountSearch = useDebouncedValue(serviceAccountSearchTerm)

  const serviceAccountsQuery = accessClient.useQuery(
    'get',
    '/service_accounts',
    {
      params: {
        query: {
          sort: 'name',
          limit: PAGE_SIZE,
          ...(debouncedServiceAccountSearch ? { 'name[contains]': debouncedServiceAccountSearch } : {}),
        },
      },
    },
    { enabled: isOpen && principalType === RolePrincipalType.SERVICE_ACCOUNT }
  )

  const { roles: projectRoles, isLoading: rolesLoading } = useAllProjectRoles(projectId)

  const userOptions = useMemo(
    () => (usersQuery.data?.resources ?? []).map((u) => ({ value: u.id, label: u.username })),
    [usersQuery.data]
  )

  const groupOptions = useMemo(
    () => (groupsQuery.data?.resources ?? []).map((g) => ({ value: g.id, label: g.name })),
    [groupsQuery.data]
  )

  const serviceAccountOptions = useMemo(
    () => (serviceAccountsQuery.data?.resources ?? []).map((sa) => ({ value: sa.id, label: sa.name })),
    [serviceAccountsQuery.data]
  )

  const roleOptions = useMemo(() => {
    const assignedForPrincipal = selectedPrincipalId ? assignedRolesByPrincipal.get(selectedPrincipalId) : undefined
    return projectRoles
      .filter((r) => !assignedForPrincipal?.has(r.name))
      .map((r) => ({
        value: r.name,
        label: r.name,
        description: r.description ?? undefined,
      }))
  }, [projectRoles, selectedPrincipalId, assignedRolesByPrincipal])

  const { mutate: assignRole, isPending } = accessClient.useMutation('post', '/projects/{project_id}/role_assignments')

  const handleClose = () => {
    setUserSearchTerm('')
    setGroupSearchTerm('')
    setServiceAccountSearchTerm('')
    formHandleClose()
  }

  const resetDependentFields = () => {
    setValue('userId', '', { shouldValidate: false })
    setValue('groupId', '', { shouldValidate: false })
    setValue('serviceAccountId', '', { shouldValidate: false })
    setValue('roleName', '', { shouldValidate: false })
  }

  const clearRoleSelection = () => {
    setValue('roleName', '', { shouldValidate: false })
  }

  const onSubmit = (data: AssignProjectRoleFormData) => {
    const principalId = getSelectedPrincipalId(data.principalType, data.userId, data.groupId, data.serviceAccountId)
    const body = buildAssignmentBody(data.principalType, principalId, data.roleName)
    assignRole(
      {
        params: { path: { project_id: projectId } },
        body,
      },
      {
        onSuccess: () => {
          showSuccess({ title: 'Role assigned', description: `Role "${data.roleName}" has been assigned.` })
          handleClose()
          onSuccess()
        },
        onError: handleError({ title: 'Failed to assign role' }),
      }
    )
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="small">
      <ModalHeader title="Assign role" />
      <ModalBody>
        <Form id="assign-project-role-form" onSubmit={handleSubmit(onSubmit)}>
          <AssignProjectRoleFormFields
            form={form}
            principalType={principalType}
            selectedPrincipalId={selectedPrincipalId}
            userOptions={userOptions}
            groupOptions={groupOptions}
            serviceAccountOptions={serviceAccountOptions}
            roleOptions={roleOptions}
            rolesLoading={rolesLoading}
            onUserSearchChange={setUserSearchTerm}
            hasMoreUsers={!!usersQuery.data?.next}
            isUsersLoading={usersQuery.isFetching}
            onGroupSearchChange={setGroupSearchTerm}
            hasMoreGroups={!!groupsQuery.data?.next}
            isGroupsLoading={groupsQuery.isFetching}
            onServiceAccountSearchChange={setServiceAccountSearchTerm}
            hasMoreServiceAccounts={!!serviceAccountsQuery.data?.next}
            isServiceAccountsLoading={serviceAccountsQuery.isFetching}
            onResetDependentFields={resetDependentFields}
            onPrincipalSelected={clearRoleSelection}
          />
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          type="submit"
          form="assign-project-role-form"
          isDisabled={isPending}
          isLoading={isPending}
          icon={<RhUiAddIcon />}
        >
          Assign role
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isPending}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
