import { type MenuToggleElement, SelectList, SelectOption, type SelectOptionProps } from '@patternfly/react-core'
import { useCallback, useMemo } from 'react'

import { SynSelect } from '../../SynSelect'
import type { SynDynamicFormSelectOption } from '../SynDynamicForm.types'

import styles from './optionsTypeaheadSelect.module.css'
import { OptionsTypeaheadMenuToggle } from './OptionsTypeaheadSelectToggles'
import { optionKey } from './synDynamicFormSelectHelpers'
import { useOptionsTypeaheadSelect } from './useOptionsTypeaheadSelect'

type AdditionalOption = Readonly<{
  key: string
  label: string
  isSelected: boolean
  onSelect: () => void
}>

type OptionsTypeaheadSelectProps = Readonly<{
  fieldId: string
  ariaLabel: string
  listAriaLabel?: string
  options: readonly SynDynamicFormSelectOption[]
  value: unknown
  onChange: (value: unknown) => void
  isMulti: boolean
  isDisabled?: boolean
  isLoading?: boolean
  loadErrorMessage?: string | null
  emptyPlaceholder?: string
  additionalOptions?: readonly AdditionalOption[]
}>

export function OptionsTypeaheadSelect({
  fieldId,
  ariaLabel,
  listAriaLabel,
  options,
  value,
  onChange,
  isMulti,
  isDisabled,
  isLoading,
  loadErrorMessage,
  emptyPlaceholder,
  additionalOptions,
}: OptionsTypeaheadSelectProps) {
  const state = useOptionsTypeaheadSelect({
    options,
    value,
    onChange,
    isMulti,
    isLoading,
    loadErrorMessage,
    emptyPlaceholder,
    additionalOptions,
  })

  const listLabel = listAriaLabel ?? ariaLabel
  const toggleDisabled = isDisabled || state.toggleDisabled

  const toggleProps = useMemo(
    () => ({
      isMulti,
      fieldId,
      ariaLabel,
      isOpen: state.isOpen,
      toggleDisabled,
      filterValue: state.filterValue,
      displayValue: state.displayValue,
      placeholder: state.placeholder,
      selectedChips: state.selectedChips,
      hasSelection: state.hasSelection,
      onToggle: state.handleToggle,
      onFilterChange: state.handleFilterChange,
      onClearSingle: state.clearSingleSelection,
      onRemoveMulti: state.removeMultiValue,
      onClearMulti: state.clearMultiSelection,
      inputRef: state.inputRef,
    }),
    [
      ariaLabel,
      fieldId,
      isMulti,
      state.clearMultiSelection,
      state.clearSingleSelection,
      state.displayValue,
      state.filterValue,
      state.handleFilterChange,
      state.handleToggle,
      state.hasSelection,
      state.inputRef,
      state.isOpen,
      state.placeholder,
      state.removeMultiValue,
      state.selectedChips,
      toggleDisabled,
    ]
  )

  const renderToggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) => <OptionsTypeaheadMenuToggle toggleRef={toggleRef} {...toggleProps} />,
    [toggleProps]
  )

  return (
    <SynSelect
      id={fieldId}
      isOpen={state.isOpen}
      selected={isMulti ? state.selectedKeys : state.selectedKeys[0]}
      onSelect={state.handleSelect}
      onOpenChange={state.handleOpenChange}
      shouldFocusToggleOnSelect={isMulti}
      toggle={renderToggle}
    >
      <SelectList aria-label={listLabel} className={styles.optionsList}>
        {state.filteredAdditionalOptions.map((option) => (
          <SelectOption key={option.key} value={option.key} isSelected={option.isSelected}>
            {option.label}
          </SelectOption>
        ))}
        {state.showEmptyRow ? (
          <SelectOption isDisabled value="__empty__">
            {state.emptyListMessage}
          </SelectOption>
        ) : (
          state.filteredOptions.map((option) => {
            const key = optionKey(option.value)
            const isSelected = state.selectedKeys.includes(key)
            const optionProps: SelectOptionProps = {
              value: key,
              hasCheckbox: isMulti,
              isSelected,
            }
            return (
              <SelectOption key={key} {...optionProps}>
                {option.label}
              </SelectOption>
            )
          })
        )}
      </SelectList>
    </SynSelect>
  )
}
