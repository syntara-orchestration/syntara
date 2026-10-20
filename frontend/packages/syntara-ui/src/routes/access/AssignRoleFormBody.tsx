import { MenuToggle, type MenuToggleElement, SelectList, SelectOption } from '@patternfly/react-core'
import { useState } from 'react'

import { FormFieldWarning } from '../../components/FormFieldError'
import { SynForm } from '../../components/forms/SynForm'
import { SynFormField } from '../../components/forms/SynFormField'
import { SynSelect } from '../../components/SynSelect'
import type { UseSynFormReturn } from '../../hooks/useSynForm'
import { RolePrincipalType } from '../access-management/RoleAssignmentTypes'

import { accessControlHelp } from './accessControlFieldHelp'
import type { AssignRoleFormData } from './assignRoleSchema'
import { PrincipalField } from './PrincipalField'
import { PrincipalTypeSelect } from './PrincipalTypeSelect'
import { TypeaheadSelect } from './TypeaheadSelect'

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

export type AssignRoleFormBodyProps = {
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

export function AssignRoleFormBody({
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
        <SynFormField<AssignRoleFormData, 'projectId'> name="projectId" label="Project" fieldId="project-id" isRequired>
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
