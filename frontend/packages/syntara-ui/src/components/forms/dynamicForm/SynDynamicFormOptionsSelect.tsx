import {
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  type SelectOptionProps,
} from '@patternfly/react-core'
import { useCallback, useMemo, useState } from 'react'
import type { ControllerRenderProps, FieldValues } from 'react-hook-form'

import { SynSelect } from '../../SynSelect'
import type { DynamicOptionsResolver } from '../SynDynamicForm.types'

import type { OptionsFormField } from './synDynamicFormFieldTypes'
import {
  getSelectedOptionLabels,
  getSelectedScalarValues,
  getSelectToggleLabel,
  optionKey,
} from './synDynamicFormSelectHelpers'
import { useDynamicFormFieldOptions } from './useDynamicFormFieldOptions'

type SynDynamicFormOptionsSelectToggleProps = Readonly<{
  toggleRef: React.Ref<MenuToggleElement>
  fieldId: string
  isOpen: boolean
  onToggleClick: () => void
  toggleDisabled: boolean
  hasSelection: boolean
  toggleLabel: string
  ariaLabel: string
}>

function SynDynamicFormOptionsSelectToggle({
  toggleRef,
  fieldId,
  isOpen,
  onToggleClick,
  toggleDisabled,
  hasSelection,
  toggleLabel,
  ariaLabel,
}: SynDynamicFormOptionsSelectToggleProps) {
  return (
    <MenuToggle
      ref={toggleRef}
      id={fieldId}
      onClick={onToggleClick}
      isExpanded={isOpen}
      isFullWidth
      isDisabled={toggleDisabled}
      isPlaceholder={!hasSelection}
      aria-label={ariaLabel}
    >
      {toggleLabel}
    </MenuToggle>
  )
}

type SynDynamicFormOptionsSelectProps<T extends FieldValues> = {
  field: OptionsFormField
  rhfField: ControllerRenderProps<T>
  fieldId: string
  ariaLabel: string
  isMulti: boolean
  isDisabled?: boolean
  resolveDynamicOptions?: DynamicOptionsResolver
}

function SynDynamicFormOptionsSelectInner<T extends FieldValues>({
  field,
  rhfField,
  fieldId,
  ariaLabel,
  isMulti,
  isDisabled,
  resolveDynamicOptions,
}: Readonly<SynDynamicFormOptionsSelectProps<T>>) {
  const [isOpen, setIsOpen] = useState(false)
  const { options, isLoading, loadErrorMessage } = useDynamicFormFieldOptions(field, resolveDynamicOptions)

  const selectedValues = getSelectedScalarValues(rhfField.value, isMulti)
  const selectedKeys = selectedValues.map((value) => optionKey(value))
  const selectedLabels = getSelectedOptionLabels(options, selectedValues)

  const emptyPlaceholder = isMulti ? 'Select options' : 'Select an option'
  const placeholder = isLoading ? 'Loading options…' : (loadErrorMessage ?? emptyPlaceholder)
  const selectionLabelKey = selectedLabels.join('\u0001')
  const toggleDisabled = isDisabled || Boolean(loadErrorMessage)

  const handleSelect = (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
    if (value === undefined || value === null) {
      return
    }

    const matched = options.find((option) => optionKey(option.value) === String(value))
    if (!matched) {
      return
    }

    if (isMulti) {
      const current = Array.isArray(rhfField.value) ? rhfField.value : []
      const exists = current.some((item) => optionKey(item) === optionKey(matched.value))
      const next = exists
        ? current.filter((item) => optionKey(item) !== optionKey(matched.value))
        : [...current, matched.value]
      rhfField.onChange(next)
      return
    }

    rhfField.onChange(matched.value)
    setIsOpen(false)
  }

  const onToggleClick = useCallback(() => {
    setIsOpen((open) => !open)
  }, [])

  const toggleState = useMemo(() => {
    const labels = selectionLabelKey.length > 0 ? selectionLabelKey.split('\u0001') : []
    return {
      fieldId,
      isOpen,
      onToggleClick,
      toggleDisabled,
      hasSelection: labels.length > 0,
      toggleLabel: getSelectToggleLabel(labels, placeholder, isMulti),
      ariaLabel,
    }
    // eslint-disable-next-line react-hooks/preserve-manual-memoization -- stable PF toggle; labels keyed by selectionLabelKey
  }, [fieldId, isOpen, onToggleClick, toggleDisabled, selectionLabelKey, placeholder, isMulti, ariaLabel])

  const renderToggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) => (
      <SynDynamicFormOptionsSelectToggle toggleRef={toggleRef} {...toggleState} />
    ),
    [toggleState]
  )

  return (
    <SynSelect
      id={fieldId}
      isOpen={isOpen}
      selected={isMulti ? selectedKeys : selectedKeys[0]}
      onSelect={handleSelect}
      onOpenChange={setIsOpen}
      toggle={renderToggle}
    >
      <SelectList aria-label={ariaLabel}>
        {options.length === 0 ? (
          <SelectOption isDisabled value="__empty__">
            {isLoading ? 'Loading…' : 'No options available'}
          </SelectOption>
        ) : (
          options.map((option) => {
            const key = optionKey(option.value)
            const isSelected = selectedKeys.includes(key)
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

export function SynDynamicFormOptionsSelect<T extends FieldValues>(
  props: Readonly<SynDynamicFormOptionsSelectProps<T>>
) {
  return <SynDynamicFormOptionsSelectInner {...props} />
}
