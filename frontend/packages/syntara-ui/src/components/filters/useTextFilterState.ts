import React, { useCallback, useMemo, useRef, useState } from 'react'

import type { FilterConfig, FilterFieldDefinition } from '../../types/filters'
import { FilterOperatorEnum, FilterTypeEnum } from '../../types/filters'

function getInitialSelectedField(
  filters: FilterConfig[],
  fieldDefinitions: FilterFieldDefinition[]
): FilterFieldDefinition | null {
  if (filters.length > 0) {
    const lastFilter = filters[filters.length - 1]
    const matchingField = fieldDefinitions.find((f) => f.key === lastFilter.key)
    if (matchingField) return matchingField
  }
  return fieldDefinitions[0] ?? null
}

export function useTextFilterState(
  fieldDefinitions: FilterFieldDefinition[],
  filters: FilterConfig[],
  onFilterChange: (filter: FilterConfig | null, fieldKey?: string) => void
) {
  const [selectedField, setSelectedField] = useState<FilterFieldDefinition | null>(() =>
    getInitialSelectedField(filters, fieldDefinitions)
  )
  const [isFieldSelectOpen, setIsFieldSelectOpen] = useState(false)
  const [isValueSelectOpen, setIsValueSelectOpen] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const lastFilterValueRef = useRef<string>('')
  const hasUserSelectedFieldRef = useRef(false)

  const currentFilter = useMemo(
    () => (selectedField ? (filters.find((f) => f.key === selectedField.key) ?? null) : null),
    [filters, selectedField]
  )

  React.useEffect(() => {
    if (!selectedField) return
    const matchingField = fieldDefinitions.find((f) => f.key === selectedField.key)
    if (matchingField && matchingField !== selectedField) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- keep selectedField object identity in sync when fieldDefinitions reloads
      setSelectedField(matchingField)
    } else if (!matchingField) {
      setSelectedField(fieldDefinitions[0] ?? null)
      hasUserSelectedFieldRef.current = false
    }
  }, [fieldDefinitions, selectedField])

  React.useEffect(() => {
    const currentFilterValue = currentFilter ? String(currentFilter.value) : ''
    if (currentFilterValue !== lastFilterValueRef.current && currentFilterValue !== inputValue) {
      lastFilterValueRef.current = currentFilterValue
      setInputValue(currentFilterValue)
    }
  }, [currentFilter, inputValue])

  const handleFieldSelect = useCallback(
    (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
      const field = fieldDefinitions.find((f) => f.key === value)
      if (field) {
        setSelectedField(field)
        setInputValue('')
        lastFilterValueRef.current = ''
        setIsFieldSelectOpen(false)
        hasUserSelectedFieldRef.current = true
      }
    },
    [fieldDefinitions]
  )

  const handleValueSelect = useCallback(
    (_event: React.MouseEvent | undefined, selectedValue: string | number | undefined) => {
      if (!selectedField || !selectedValue) return

      if (selectedField.type === FilterTypeEnum.MULTISELECT) {
        const currentValues = Array.isArray(currentFilter?.value) ? currentFilter.value : []
        const stringValue = String(selectedValue)
        const newValues = currentValues.includes(stringValue)
          ? currentValues.filter((v) => v !== stringValue)
          : [...currentValues, stringValue]

        if (newValues.length === 0) {
          onFilterChange(null, selectedField.key)
        } else {
          onFilterChange({
            key: selectedField.key,
            operator: FilterOperatorEnum.IN,
            value: newValues,
          })
        }
        return
      }

      const operator = selectedField.operators?.[0] ?? selectedField.defaultOperator ?? 'eq'
      onFilterChange({ key: selectedField.key, operator, value: selectedValue })
      setIsValueSelectOpen(false)
    },
    [selectedField, currentFilter, onFilterChange]
  )

  const handleTextInputChange = useCallback((_event: React.FormEvent<HTMLInputElement>, value: string) => {
    setInputValue(value)
  }, [])

  const applyFilter = useCallback(() => {
    if (!selectedField) return
    const trimmedValue = inputValue.trim()
    const existingFilter = filters.find((f) => f.key === selectedField.key)
    if (trimmedValue && existingFilter?.value !== trimmedValue) {
      onFilterChange({
        key: selectedField.key,
        operator: selectedField.defaultOperator ?? 'contains',
        value: trimmedValue,
      })
    } else if (!trimmedValue && existingFilter) {
      onFilterChange(null, selectedField.key)
    }
    lastFilterValueRef.current = trimmedValue
  }, [selectedField, inputValue, filters, onFilterChange])

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key === 'Enter') applyFilter()
    },
    [applyFilter]
  )

  const handleClear = useCallback(() => {
    setInputValue('')
    lastFilterValueRef.current = ''
    if (selectedField && currentFilter) {
      onFilterChange(null, selectedField.key)
    }
  }, [selectedField, currentFilter, onFilterChange])

  return {
    selectedField,
    isFieldSelectOpen,
    setIsFieldSelectOpen,
    isValueSelectOpen,
    setIsValueSelectOpen,
    inputValue,
    currentFilter,
    handleFieldSelect,
    handleValueSelect,
    handleTextInputChange,
    applyFilter,
    handleKeyDown,
    handleClear,
  }
}
