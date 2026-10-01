import { useCallback, useMemo } from 'react'

import type { PolicySelectListItem } from './policySelectConstants'
import { PolicySelectField } from './PolicySelectDropdown'
import { buildPolicyOptionList, filterPolicyOptionsByTerm, usePolicySelectField } from './policySelectShared'

export type PolicySelectBaseProps = {
  id: string
  toggleTestId?: string
  selected: string[]
  onChange: (selected: string[]) => void
  hasError?: boolean
  isDisabled?: boolean
  policyResources: readonly { name: string; description?: string | null }[]
  isLoading: boolean
  fetchAllMatchingPolicies: () => Promise<PolicySelectListItem[]>
  /** When true, options are filtered in the UI only. When false, pass `apiFilterTerm` from a debounced query. */
  clientSideFilterOnly?: boolean
  /** Debounced filter sent to the policies API (global PolicySelect only). */
  apiFilterTerm?: string
  onDropdownOpenChange?: (isOpen: boolean) => void
  onFilterValueChange?: (value: string) => void
}

export function PolicySelectBase({
  id,
  toggleTestId,
  selected,
  onChange,
  hasError,
  isDisabled,
  policyResources,
  isLoading,
  fetchAllMatchingPolicies,
  clientSideFilterOnly = false,
  apiFilterTerm = '',
  onDropdownOpenChange,
  onFilterValueChange,
}: Readonly<PolicySelectBaseProps>) {
  const field = usePolicySelectField({
    selected,
    onChange,
    fetchPolicies: fetchAllMatchingPolicies,
  })

  const policyOptions = useMemo(() => buildPolicyOptionList(policyResources, selected), [policyResources, selected])

  const filteredOptions = useMemo(() => {
    if (clientSideFilterOnly) {
      return filterPolicyOptionsByTerm(policyOptions, field.filterValue)
    }
    if (field.filterValue && field.filterValue !== apiFilterTerm) {
      return filterPolicyOptionsByTerm(policyOptions, field.filterValue)
    }
    return policyOptions
  }, [policyOptions, field.filterValue, apiFilterTerm, clientSideFilterOnly])

  const handleOpenChange = useCallback(
    (open: boolean) => {
      field.handleOpenChange(open)
      onDropdownOpenChange?.(open)
    },
    [field, onDropdownOpenChange]
  )

  return (
    <PolicySelectField
      id={id}
      selected={selected}
      filteredOptions={filteredOptions}
      filterValue={field.filterValue}
      isOpen={field.isOpen}
      isLoading={isLoading}
      isSelectingAll={field.isSelectingAll}
      hasError={hasError}
      isDisabled={isDisabled}
      inputRef={field.inputRef}
      toggleTestId={toggleTestId}
      onOpenChange={handleOpenChange}
      onSelect={field.onSelect}
      onFilterChange={(value: string) => {
        field.setFilterValue(value)
        onFilterValueChange?.(value)
        field.openDropdown()
      }}
      onFilterFocus={field.openDropdown}
      onRemovePolicy={field.removePolicy}
      onClearAll={field.clearAll}
      onToggle={() => field.handleOpenChange(!field.isOpen)}
    />
  )
}
