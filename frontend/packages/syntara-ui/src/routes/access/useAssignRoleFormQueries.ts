import { useMemo, useState } from 'react'
import type { Control } from 'react-hook-form'
import { useWatch } from 'react-hook-form'

import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { RolePrincipalType } from '../access-management/RoleAssignmentTypes'

import { accessClient } from './accessClient'
import type { AssignRoleFormData } from './assignRoleSchema'
import { useSelectableProjects } from './useAllProjects'
import { PRINCIPAL_ID_FIELD, useAlreadyAssignedRoles } from './useAlreadyAssignedRoles'

const PAGE_SIZE = 20

export function useAssignRoleFormQueries(control: Control<AssignRoleFormData>) {
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

  return {
    principalType,
    isProjectScoped,
    selectedProjectId,
    projectOptions,
    userOptions,
    groupOptions,
    serviceAccountOptions,
    roleOptions,
    isProjectsLoading,
    setUserSearchTerm,
    usersQuery,
    setGroupSearchTerm,
    groupsQuery,
    setSaSearchTerm,
    serviceAccountsQuery,
    setRoleSearchTerm,
    activeRolesQuery,
    isAssignmentsLoading,
    isAssignmentsError,
  }
}
