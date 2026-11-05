import { useCallback, useMemo, useRef, useState } from 'react'

import type { SynDynamicFormSelectOption } from '../SynDynamicForm.types'

import type { SelectedChip } from './OptionsTypeaheadSelectToggles'
import {
  filterOptionsByLabel,
  getSelectedOptionLabels,
  getSelectedScalarValues,
  getSelectToggleLabel,
  optionKey,
  type OptionScalarValue,
} from './synDynamicFormSelectHelpers'

type AdditionalOption = Readonly<{
  key: string
  label: string
  isSelected: boolean
  onSelect: () => void
}>

type UseOptionsTypeaheadSelectArgs = Readonly<{
  options: readonly SynDynamicFormSelectOption[]
  value: unknown
  onChange: (value: unknown) => void
  isMulti: boolean
  isLoading?: boolean
  loadErrorMessage?: string | null
  emptyPlaceholder?: string
  additionalOptions?: readonly AdditionalOption[]
}>

function isOptionScalar(value: unknown): value is OptionScalarValue {
  const kind = typeof value
  return kind === 'string' || kind === 'number' || kind === 'boolean'
}

function buildSelectedChips(
  options: readonly SynDynamicFormSelectOption[],
  selectedValues: readonly OptionScalarValue[]
): SelectedChip[] {
  return selectedValues.map((scalar) => {
    const key = optionKey(scalar)
    const label = options.find((option) => optionKey(option.value) === key)?.label ?? String(scalar)
    return { key, label, value: scalar }
  })
}

export function useOptionsTypeaheadSelect({
  options,
  value,
  onChange,
  isMulti,
  isLoading,
  loadErrorMessage,
  emptyPlaceholder,
  additionalOptions,
}: UseOptionsTypeaheadSelectArgs) {
  const [isOpen, setIsOpen] = useState(false)
  const [filterValue, setFilterValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const selectedValues = getSelectedScalarValues(value, isMulti)
  const selectedKeys = selectedValues.map((entry) => optionKey(entry))
  const selectedLabels = getSelectedOptionLabels(options, selectedValues)

  const emptyPlaceholderText = emptyPlaceholder ?? (isMulti ? 'Select options' : 'Select an option')
  const placeholder = isLoading ? 'Loading options…' : (loadErrorMessage ?? emptyPlaceholderText)
  const toggleDisabled = Boolean(loadErrorMessage)

  const filteredOptions = useMemo(
    () => filterOptionsByLabel(options, filterValue),
    [options, filterValue]
  )

  const filteredAdditionalOptions = useMemo(() => {
    if (!additionalOptions?.length) {
      return []
    }
    return filterOptionsByLabel(additionalOptions, filterValue)
  }, [additionalOptions, filterValue])

  const selectedChips = useMemo(() => {
    const values = getSelectedScalarValues(value, isMulti)
    return buildSelectedChips(options, values)
  }, [isMulti, options, value])

  const displayValue = getSelectToggleLabel(selectedLabels, placeholder, false)

  const handleOpenChange = useCallback((open: boolean) => {
    setIsOpen(open)
    if (!open) {
      setFilterValue('')
    }
  }, [])

  const handleSelect = useCallback(
    (_event: React.MouseEvent | undefined, selection: string | number | undefined) => {
      if (selection === undefined || selection === null) {
        return
      }

      const selectionKey = String(selection)
      const additional = additionalOptions?.find((option) => option.key === selectionKey)
      if (additional) {
        additional.onSelect()
        setFilterValue('')
        if (!isMulti) {
          setIsOpen(false)
        }
        return
      }

      const matched = options.find((option) => optionKey(option.value) === selectionKey)
      if (!matched) {
        return
      }

      if (isMulti) {
        const current = Array.isArray(value) ? value.filter(isOptionScalar) : []
        const exists = current.some((item) => optionKey(item) === optionKey(matched.value))
        const next = exists
          ? current.filter((item) => optionKey(item) !== optionKey(matched.value))
          : [...current, matched.value]
        onChange(next)
        setFilterValue('')
        return
      }

      onChange(matched.value)
      setFilterValue('')
      setIsOpen(false)
    },
    [additionalOptions, isMulti, onChange, options, value]
  )

  const handleFilterChange = useCallback((val: string) => {
    setFilterValue(val)
    setIsOpen(true)
  }, [])

  const handleToggle = useCallback(() => {
    setIsOpen((open) => !open)
  }, [])

  const clearSingleSelection = useCallback(() => {
    onChange('')
    setFilterValue('')
    setIsOpen(false)
  }, [onChange])

  const clearMultiSelection = useCallback(() => {
    onChange([])
    setFilterValue('')
    inputRef.current?.focus()
  }, [onChange])

  const removeMultiValue = useCallback(
    (valueToRemove: OptionScalarValue) => {
      const current = getSelectedScalarValues(value, true)
      onChange(current.filter((entry) => optionKey(entry) !== optionKey(valueToRemove)))
    },
    [onChange, value]
  )

  const emptyListMessage = useMemo(() => {
    if (isLoading) {
      return 'Loading…'
    }
    if (options.length === 0) {
      return 'No options available'
    }
    if (filterValue.trim()) {
      return `No results match "${filterValue}"`
    }
    return 'No options available'
  }, [filterValue, isLoading, options.length])

  const showEmptyRow = filteredOptions.length === 0 && filteredAdditionalOptions.length === 0

  return {
    inputRef,
    isOpen,
    isMulti,
    selectedKeys,
    selectedChips,
    displayValue,
    placeholder,
    toggleDisabled,
    filterValue,
    filteredOptions,
    filteredAdditionalOptions,
    emptyListMessage,
    showEmptyRow,
    hasSelection: selectedLabels.length > 0,
    handleOpenChange,
    handleSelect,
    handleFilterChange,
    handleToggle,
    clearSingleSelection,
    clearMultiSelection,
    removeMultiValue,
  }
}
