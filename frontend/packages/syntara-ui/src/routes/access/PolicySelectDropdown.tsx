import { type Ref } from 'react'

import { SynSelect } from '../../components/SynSelect'

import { PolicySelectOptionsList } from './PolicySelectOptionsList'
import type { PolicySelectOption } from './policySelectShared'
import { PolicySelectToggle } from './PolicySelectToggle'

type PolicySelectFieldProps = {
  id: string
  selected: string[]
  filteredOptions: PolicySelectOption[]
  filterValue: string
  isOpen: boolean
  isLoading: boolean
  isSelectingAll: boolean
  hasError?: boolean
  isDisabled?: boolean
  toggleTestId?: string
  inputRef: React.RefObject<HTMLInputElement | null>
  onOpenChange: (open: boolean) => void
  onSelect: (event: React.MouseEvent<Element, MouseEvent> | undefined, value: string | number | undefined) => void
  onFilterChange: (value: string) => void
  onFilterFocus: () => void
  onRemovePolicy: (name: string) => void
  onClearAll: () => void
  onToggle: () => void
}

export function PolicySelectField({
  id,
  selected,
  filteredOptions,
  filterValue,
  isOpen,
  isLoading,
  isSelectingAll,
  hasError,
  isDisabled,
  toggleTestId,
  inputRef,
  onOpenChange,
  onSelect,
  onFilterChange,
  onFilterFocus,
  onRemovePolicy,
  onClearAll,
  onToggle,
}: Readonly<PolicySelectFieldProps>) {
  const toggle = (toggleRef: Ref<HTMLButtonElement>) => (
    <PolicySelectToggle
      toggleRef={toggleRef}
      isOpen={isOpen}
      onToggle={onToggle}
      filterValue={filterValue}
      onFilterChange={onFilterChange}
      onFilterFocus={onFilterFocus}
      selected={selected}
      onRemovePolicy={onRemovePolicy}
      onClearAll={onClearAll}
      inputRef={inputRef}
      isDisabled={isDisabled}
      hasError={hasError}
      toggleTestId={toggleTestId}
    />
  )

  return (
    <SynSelect
      id={id}
      aria-label="Policies"
      isOpen={isOpen}
      onOpenChange={onOpenChange}
      onSelect={onSelect}
      selected={selected}
      toggle={toggle}
      shouldFocusToggleOnSelect={false}
    >
      <PolicySelectOptionsList
        isLoading={isLoading}
        filterValue={filterValue}
        filteredOptions={filteredOptions}
        selected={selected}
        isSelectingAll={isSelectingAll}
      />
    </SynSelect>
  )
}
