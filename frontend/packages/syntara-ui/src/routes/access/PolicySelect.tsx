import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { accessClient } from './accessClient'
import { fetchAllPoliciesForSelect } from './fetchAllPoliciesForSelect'
import { filterPoliciesForRoleSelect } from './policySelectConstants'
import { PolicySelectField } from './PolicySelectDropdown'
import { buildPolicyOptionList, filterPolicyOptionsByTerm, usePolicySelectField } from './policySelectShared'

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

  const field = usePolicySelectField({
    selected,
    onChange,
    fetchPolicies: fetchAllMatchingPolicies,
  })

  useEffect(() => {
    filterValueRef.current = field.filterValue
  }, [field.filterValue])

  useEffect(() => {
    debouncedFilterRef.current = debouncedFilter
  }, [debouncedFilter])

  useEffect(() => {
    debounceRef.current = setTimeout(() => {
      setDebouncedFilter(field.filterValue)
    }, DEBOUNCE_MS)
    return () => clearTimeout(debounceRef.current)
  }, [field.filterValue])

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
    { enabled: field.isOpen }
  )

  const scopedPolicies = useMemo(
    () => filterPoliciesForRoleSelect(policiesQuery.data?.resources ?? [], { scopeProjectId, projectEligible }),
    [policiesQuery.data?.resources, scopeProjectId, projectEligible]
  )

  const policyOptions = useMemo(() => buildPolicyOptionList(scopedPolicies, selected), [scopedPolicies, selected])

  const filteredOptions = useMemo(() => {
    if (field.filterValue && field.filterValue !== debouncedFilter) {
      return filterPolicyOptionsByTerm(policyOptions, field.filterValue)
    }
    return policyOptions
  }, [policyOptions, field.filterValue, debouncedFilter])

  const isLoading = policiesQuery.isLoading || policiesQuery.isFetching

  return (
    <PolicySelectField
      id="role-policies"
      selected={selected}
      filteredOptions={filteredOptions}
      filterValue={field.filterValue}
      isOpen={field.isOpen}
      isLoading={isLoading}
      isSelectingAll={field.isSelectingAll}
      hasError={hasError}
      isDisabled={isDisabled}
      inputRef={field.inputRef}
      onOpenChange={field.handleOpenChange}
      onSelect={field.onSelect}
      onFilterChange={(value: string) => {
        field.setFilterValue(value)
        field.openDropdown()
      }}
      onFilterFocus={field.openDropdown}
      onRemovePolicy={field.removePolicy}
      onClearAll={field.clearAll}
      onToggle={() => field.handleOpenChange(!field.isOpen)}
    />
  )
}
