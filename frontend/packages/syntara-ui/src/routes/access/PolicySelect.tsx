import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { accessClient } from './accessClient'
import { fetchAllPoliciesForSelect } from './fetchAllPoliciesForSelect'
import { PolicySelectBase } from './PolicySelectBase'
import { filterPoliciesForRoleSelect } from './policySelectConstants'

type PolicySelectProps = {
  selected: string[]
  onChange: (selected: string[]) => void
  hasError?: boolean
  /** Filter policies by project scope. Omit or pass `null`/`undefined` for system (unfiltered), UUID for project-scoped. */
  scopeProjectId?: string | null
  /** When true, fetch only policies whose actions are valid for project-scoped roles. */
  projectEligible?: boolean
  /** When true, the select is disabled (e.g. waiting for project selection). */
  isDisabled?: boolean
}

const DEBOUNCE_MS = 300
const PAGE_SIZE = 50

export function PolicySelect({
  selected,
  onChange,
  hasError,
  scopeProjectId,
  projectEligible,
  isDisabled,
}: Readonly<PolicySelectProps>) {
  const [debouncedFilter, setDebouncedFilter] = useState('')
  const [isOpen, setIsOpen] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const filterValueRef = useRef('')
  const debouncedFilterRef = useRef('')

  const fetchAllMatchingPolicies = useCallback(
    () =>
      fetchAllPoliciesForSelect({
        scopeProjectId,
        projectEligible,
        nameContains: filterValueRef.current || debouncedFilterRef.current || undefined,
      }),
    [scopeProjectId, projectEligible]
  )

  useEffect(() => {
    debouncedFilterRef.current = debouncedFilter
  }, [debouncedFilter])

  const handleFilterValueChange = useCallback((value: string) => {
    filterValueRef.current = value
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setDebouncedFilter(value)
    }, DEBOUNCE_MS)
  }, [])

  useEffect(() => () => clearTimeout(debounceRef.current), [])

  const policiesQuery = accessClient.useQuery(
    'get',
    '/policies',
    {
      params: {
        query: {
          sort: 'name',
          limit: PAGE_SIZE,
          'name[contains]': debouncedFilter || undefined,
          ...(scopeProjectId ? { project_id: scopeProjectId } : {}),
          ...(projectEligible ? { project_eligible: true } : {}),
        },
      },
    },
    { enabled: isOpen }
  )

  const scopedPolicies = useMemo(
    () => filterPoliciesForRoleSelect(policiesQuery.data?.resources ?? [], { scopeProjectId, projectEligible }),
    [policiesQuery.data?.resources, scopeProjectId, projectEligible]
  )

  const isLoading = policiesQuery.isLoading || policiesQuery.isFetching

  return (
    <PolicySelectBase
      id="role-policies"
      selected={selected}
      onChange={onChange}
      hasError={hasError}
      isDisabled={isDisabled}
      policyResources={scopedPolicies}
      isLoading={isLoading}
      fetchAllMatchingPolicies={fetchAllMatchingPolicies}
      apiFilterTerm={debouncedFilter}
      onDropdownOpenChange={setIsOpen}
      onFilterValueChange={handleFilterValueChange}
    />
  )
}
