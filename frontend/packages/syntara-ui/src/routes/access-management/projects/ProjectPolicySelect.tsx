import { useCallback, useEffect, useMemo, useRef } from 'react'

import { accessClient } from '../../access/accessClient'
import { fetchAllProjectPoliciesForSelect } from '../../access/fetchAllPoliciesForSelect'
import { PolicySelectField } from '../../access/PolicySelectDropdown'
import { buildPolicyOptionList, filterPolicyOptionsByTerm, usePolicySelectField } from '../../access/policySelectShared'

type ProjectPolicySelectProps = {
  projectId: string
  selected: string[]
  onChange: (selected: string[]) => void
  hasError?: boolean
}

const PAGE_SIZE = 50

export function ProjectPolicySelect({ projectId, selected, onChange, hasError }: Readonly<ProjectPolicySelectProps>) {
  const filterValueRef = useRef('')

  const fetchAllMatchingPolicies = useCallback(
    () => fetchAllProjectPoliciesForSelect(projectId, filterValueRef.current || undefined),
    [projectId]
  )

  const field = usePolicySelectField({
    selected,
    onChange,
    fetchPolicies: fetchAllMatchingPolicies,
  })

  useEffect(() => {
    filterValueRef.current = field.filterValue
  }, [field.filterValue])

  const policiesQuery = accessClient.useQuery(
    'get',
    '/projects/{project_id}/policies',
    {
      params: {
        path: { project_id: projectId },
        query: { sort: 'name', limit: PAGE_SIZE },
      },
    },
    { enabled: field.isOpen }
  )

  const policyOptions = useMemo(
    () => buildPolicyOptionList(policiesQuery.data?.resources ?? [], selected),
    [policiesQuery.data?.resources, selected]
  )

  const filteredOptions = useMemo(
    () => filterPolicyOptionsByTerm(policyOptions, field.filterValue),
    [policyOptions, field.filterValue]
  )

  const isLoading = policiesQuery.isLoading || policiesQuery.isFetching

  return (
    <PolicySelectField
      id="project-role-policies"
      selected={selected}
      filteredOptions={filteredOptions}
      filterValue={field.filterValue}
      isOpen={field.isOpen}
      isLoading={isLoading}
      isSelectingAll={field.isSelectingAll}
      hasError={hasError}
      inputRef={field.inputRef}
      toggleTestId="policy-select-toggle"
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
