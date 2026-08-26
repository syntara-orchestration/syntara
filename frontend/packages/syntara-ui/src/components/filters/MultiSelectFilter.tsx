import { Badge, Divider, MenuToggle, SelectList, SelectOption, type MenuToggleElement } from '@patternfly/react-core'
import React, { useCallback, useMemo, useState } from 'react'

import { FilterOperatorEnum, type FilterConfig, type FilterOperator } from '../../types/filters'
import { SynSelect } from '../SynSelect'

const SELECT_ALL_VALUE = '__select_all__'
const CLEAR_ALL_VALUE = '__clear_all__'

type MultiSelectFilterMenuToggleProps = {
  toggleRef: React.Ref<MenuToggleElement>
  isOpen: boolean
  onToggle: () => void
  selectedCount: number
  toggleLabel: string
}

function MultiSelectFilterMenuToggle({
  toggleRef,
  isOpen,
  onToggle,
  selectedCount,
  toggleLabel,
}: Readonly<MultiSelectFilterMenuToggleProps>) {
  return (
    <MenuToggle
      ref={toggleRef}
      onClick={onToggle}
      isExpanded={isOpen}
      {...(selectedCount > 0 && {
        badge: (
          <Badge data-testid="filter-badge" isRead>
            {selectedCount}
          </Badge>
        ),
      })}
    >
      {toggleLabel}
    </MenuToggle>
  )
}

function multiSelectFilterToggle(
  toggleRef: React.Ref<MenuToggleElement>,
  state: Pick<MultiSelectFilterMenuToggleProps, 'isOpen' | 'onToggle' | 'selectedCount' | 'toggleLabel'>
) {
  return (
    <MultiSelectFilterMenuToggle
      toggleRef={toggleRef}
      isOpen={state.isOpen}
      onToggle={state.onToggle}
      selectedCount={state.selectedCount}
      toggleLabel={state.toggleLabel}
    />
  )
}

/**
 * Props for MultiSelectFilter component
 */
export type MultiSelectFilterProps = {
  /** Filter field key (e.g., 'status') */
  fieldKey: string
  /** Display label shown on the toggle */
  label: string
  /** Available options for selection */
  options: { label: string; value: string }[]
  /** Currently selected values */
  selectedValues: string[]
  /** Callback when selection changes. Passes null when all values are deselected. */
  onChange: (filter: FilterConfig | null, fieldKey?: string) => void
  /** Filter operator to use (defaults to 'in') */
  operator?: FilterOperator
  /** Placeholder text when no values are selected */
  placeholder?: string
}

/**
 * Multi-select filter component using PatternFly Select with checkboxes.
 *
 * Renders a dropdown with checkbox options plus Select All / Clear All actions.
 * Emits a single FilterConfig with operator 'in' and value as string[] of selected
 * option values. When all values are deselected, emits null to clear the filter.
 * The toggle badge shows how many values are active.
 *
 * @example
 * ```tsx
 * <MultiSelectFilter
 *   fieldKey="status"
 *   label="Status"
 *   options={[
 *     { label: 'Running', value: 'running' },
 *     { label: 'Failed', value: 'failed' },
 *   ]}
 *   selectedValues={['running']}
 *   onChange={(filter) => updateFilter(filter)}
 * />
 * ```
 */
export function MultiSelectFilter({
  fieldKey,
  label,
  options,
  selectedValues,
  onChange,
  operator = FilterOperatorEnum.IN,
  placeholder,
}: MultiSelectFilterProps) {
  const [isOpen, setIsOpen] = useState(false)

  const allOptionValues = useMemo(() => options.map((option) => option.value), [options])

  const toggleOpen = useCallback(() => {
    setIsOpen((prev) => !prev)
  }, [])

  const emitValues = useCallback(
    (values: string[]) => {
      if (values.length === 0) {
        onChange(null, fieldKey)
      } else {
        onChange({ key: fieldKey, operator, value: values })
      }
    },
    [fieldKey, onChange, operator]
  )

  const handleSelect = useCallback(
    (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
      if (value === undefined || value === null) return
      const stringValue = String(value)

      if (stringValue === SELECT_ALL_VALUE) {
        emitValues(allOptionValues)
        return
      }

      if (stringValue === CLEAR_ALL_VALUE) {
        emitValues([])
        return
      }

      const newValues = selectedValues.includes(stringValue)
        ? selectedValues.filter((v) => v !== stringValue)
        : [...selectedValues, stringValue]

      emitValues(newValues)
    },
    [allOptionValues, emitValues, selectedValues]
  )

  const toggleLabel = placeholder ?? `Filter by ${label.toLowerCase()}`

  const toggleState = useMemo(
    () => ({
      isOpen,
      onToggle: toggleOpen,
      selectedCount: selectedValues.length,
      toggleLabel,
    }),
    [isOpen, toggleOpen, selectedValues.length, toggleLabel]
  )

  const renderToggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) => multiSelectFilterToggle(toggleRef, toggleState),
    [toggleState]
  )

  return (
    <SynSelect
      role="menu"
      isOpen={isOpen}
      selected={selectedValues}
      onSelect={handleSelect}
      onOpenChange={setIsOpen}
      toggle={renderToggle}
    >
      <SelectList aria-label={`Filter by ${label}`}>
        <SelectOption value={SELECT_ALL_VALUE} isDisabled={options.length === 0}>
          Select All
        </SelectOption>
        <SelectOption value={CLEAR_ALL_VALUE} isDisabled={selectedValues.length === 0}>
          Clear All
        </SelectOption>
        <Divider component="li" />
        {options.map((option) => (
          <SelectOption
            key={option.value}
            value={option.value}
            hasCheckbox
            isSelected={selectedValues.includes(option.value)}
          >
            {option.label}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}
