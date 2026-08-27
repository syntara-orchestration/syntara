import {
  Button,
  InputGroup,
  InputGroupItem,
  MenuToggle,
  SearchInput,
  SelectList,
  SelectOption,
  ToolbarItem,
} from '@patternfly/react-core'
import type { MenuToggleElement } from '@patternfly/react-core'
import { RhUiArrowRightIcon, RhUiFilterIcon } from '@patternfly/react-icons'
import React, { useCallback, useMemo, useRef, useState } from 'react'

import type { FilterConfig, FilterFieldDefinition } from '../../types/filters'
import { detachPromise } from '../../utils/detachPromise'
import { SynSelect } from '../SynSelect'

import styles from './textFilterSelectControls.module.css'

export const SEARCH_THRESHOLD = 10

/**
 * Field selector dropdown component
 */
type FieldSelectorProps = {
  selectedField: FilterFieldDefinition
  fieldDefinitions: FilterFieldDefinition[]
  isOpen: boolean
  onOpenChange: (isOpen: boolean) => void
  onSelect: (_event: React.MouseEvent | undefined, value: string | number | undefined) => void
  popperProps?: Record<string, unknown>
}

type FieldSelectorMenuToggleProps = {
  toggleRef: React.Ref<MenuToggleElement>
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  label: string
}

function FieldSelectorMenuToggle({ toggleRef, isOpen, onOpenChange, label }: Readonly<FieldSelectorMenuToggleProps>) {
  return (
    <MenuToggle ref={toggleRef} onClick={() => onOpenChange(!isOpen)} icon={<RhUiFilterIcon />}>
      {label}
    </MenuToggle>
  )
}

function fieldSelectorSelectToggle(
  toggleRef: React.Ref<MenuToggleElement>,
  state: Pick<FieldSelectorMenuToggleProps, 'isOpen' | 'onOpenChange' | 'label'>
) {
  return (
    <FieldSelectorMenuToggle
      toggleRef={toggleRef}
      isOpen={state.isOpen}
      onOpenChange={state.onOpenChange}
      label={state.label}
    />
  )
}

export function FieldSelector({
  selectedField,
  fieldDefinitions,
  isOpen,
  onOpenChange,
  onSelect,
  popperProps,
}: Readonly<FieldSelectorProps>) {
  const fieldToggleState = useMemo(
    () => ({
      isOpen,
      onOpenChange,
      label: selectedField.label,
    }),
    [isOpen, onOpenChange, selectedField.label]
  )

  const renderFieldToggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) => fieldSelectorSelectToggle(toggleRef, fieldToggleState),
    [fieldToggleState]
  )

  return (
    <SynSelect
      id="attribute-search-field-select"
      isOpen={isOpen}
      selected={selectedField.key}
      onSelect={onSelect}
      onOpenChange={onOpenChange}
      popperProps={popperProps}
      toggle={renderFieldToggle}
    >
      <SelectList>
        {fieldDefinitions.map((field) => (
          <SelectOption key={field.key} value={field.key}>
            {field.label}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}

/**
 * Text filter input with search and apply button
 */
type TextFilterInputProps = {
  inputValue: string
  selectedField: FilterFieldDefinition
  onInputChange: (_event: React.FormEvent<HTMLInputElement>, value: string) => void
  onClear: () => void
  onKeyDown: (event: React.KeyboardEvent) => void
  onApply: () => void
}

export function TextFilterInput({
  inputValue,
  selectedField,
  onInputChange,
  onClear,
  onKeyDown,
  onApply,
}: Readonly<TextFilterInputProps>) {
  return (
    <ToolbarItem>
      <InputGroup>
        <InputGroupItem isFill>
          <SearchInput
            value={inputValue}
            onChange={onInputChange}
            onClear={onClear}
            onKeyDown={onKeyDown}
            placeholder={selectedField.placeholder ?? `Filter by ${selectedField.label.toLowerCase()}`}
            aria-label={`${selectedField.label} filter`}
          />
        </InputGroupItem>
        <InputGroupItem>
          <Button variant="control" aria-label="Apply filter" onClick={onApply} icon={<RhUiArrowRightIcon />} />
        </InputGroupItem>
      </InputGroup>
    </ToolbarItem>
  )
}

/**
 * Select filter dropdown with search capability (client-side or server-side)
 */
type SelectFilterInputProps = {
  selectedField: FilterFieldDefinition
  currentFilter: FilterConfig | null
  isOpen: boolean
  onOpenChange: (isOpen: boolean) => void
  onSelect: (_event: React.MouseEvent | undefined, value: string | number | undefined) => void
  popperProps?: Record<string, unknown>
}

type SelectFilterInputMenuToggleProps = {
  toggleRef: React.Ref<MenuToggleElement>
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  toggleLabel: string
}

function SelectFilterInputMenuToggle({
  toggleRef,
  isOpen,
  onOpenChange,
  toggleLabel,
}: Readonly<SelectFilterInputMenuToggleProps>) {
  return (
    <MenuToggle ref={toggleRef} onClick={() => onOpenChange(!isOpen)} className={styles.truncatedToggle}>
      {toggleLabel}
    </MenuToggle>
  )
}

function selectFilterInputSelectToggle(
  toggleRef: React.Ref<MenuToggleElement>,
  state: Pick<SelectFilterInputMenuToggleProps, 'isOpen' | 'onOpenChange' | 'toggleLabel'>
) {
  return (
    <SelectFilterInputMenuToggle
      toggleRef={toggleRef}
      isOpen={state.isOpen}
      onOpenChange={state.onOpenChange}
      toggleLabel={state.toggleLabel}
    />
  )
}

export function SelectFilterInput({
  selectedField,
  currentFilter,
  isOpen,
  onOpenChange,
  onSelect,
  popperProps,
}: Readonly<SelectFilterInputProps>) {
  const [searchValue, setSearchValue] = useState('')
  const [asyncOptions, setAsyncOptions] = useState<{ label: string; value: string; description?: string }[]>([])
  const [isLoadingOptions, setIsLoadingOptions] = useState(false)
  // Store the selected option separately to preserve it when it's not in current async results
  const [selectedOption, setSelectedOption] = useState<{ label: string; value: string } | null>(null)

  // Determine if this is an async select
  const isAsync = Boolean(selectedField.asyncOptions)

  // Normalize current filter value to string for comparison with option values
  const activeOption = useMemo(() => {
    if (!currentFilter) return null
    const options = isAsync ? asyncOptions : (selectedField.options ?? [])
    const found = options.find((opt) => String(opt.value) === String(currentFilter.value))
    // For async, prefer the stored selected option if the current filter matches but not found in current results
    if (isAsync && !found && selectedOption && String(selectedOption.value) === String(currentFilter.value)) {
      return selectedOption
    }
    if (
      isAsync &&
      !found &&
      typeof selectedField.getOptionLabel === 'function' &&
      currentFilter.value !== undefined &&
      currentFilter.value !== null
    ) {
      const label = selectedField.getOptionLabel(String(currentFilter.value))
      if (label !== undefined && label !== '') {
        return { value: String(currentFilter.value), label }
      }
    }
    return found
  }, [currentFilter, isAsync, asyncOptions, selectedField, selectedOption])

  // Fetch async options when search value changes (debounced)
  const searchTimeoutRef = useRef<NodeJS.Timeout | undefined>(undefined)
  const asyncFetchGenerationRef = useRef(0)
  const asyncOptionsFn = selectedField.asyncOptions
  const loadAsyncOptions = useCallback(
    async (search: string) => {
      if (!asyncOptionsFn) return

      const generation = ++asyncFetchGenerationRef.current
      setIsLoadingOptions(true)
      try {
        const options = await asyncOptionsFn(search)
        if (generation !== asyncFetchGenerationRef.current) {
          return
        }
        setAsyncOptions(options)
      } catch {
        if (generation !== asyncFetchGenerationRef.current) {
          return
        }
        // Failed to load options - show empty list
        setAsyncOptions([])
      } finally {
        if (generation === asyncFetchGenerationRef.current) {
          setIsLoadingOptions(false)
        }
      }
    },
    [asyncOptionsFn]
  )

  // Handle search value changes
  const handleSearchChange = useCallback(
    (_event: React.FormEvent<HTMLInputElement>, value: string) => {
      setSearchValue(value)

      if (isAsync) {
        // Debounce async calls
        if (searchTimeoutRef.current) {
          clearTimeout(searchTimeoutRef.current)
        }
        searchTimeoutRef.current = setTimeout(() => {
          detachPromise(loadAsyncOptions(value))
        }, 300)
      }
    },
    [isAsync, loadAsyncOptions]
  )

  // Load initial async options on mount
  React.useEffect(() => {
    if (isAsync && isOpen && asyncOptions.length === 0) {
      detachPromise(loadAsyncOptions(''))
    }
  }, [isAsync, isOpen, asyncOptions.length, loadAsyncOptions])

  React.useEffect(() => {
    return () => {
      asyncFetchGenerationRef.current += 1
      if (searchTimeoutRef.current !== undefined) {
        clearTimeout(searchTimeoutRef.current)
      }
    }
  }, [])

  // Client-side filtered options (for static options)
  const filteredOptions = useMemo(() => {
    if (isAsync) return asyncOptions
    if (!searchValue) return selectedField.options ?? []
    const search = searchValue.toLowerCase()
    return (selectedField.options ?? []).filter((opt) => opt.label.toLowerCase().includes(search))
  }, [isAsync, asyncOptions, searchValue, selectedField.options])

  const handleOpenChange = useCallback(
    (open: boolean) => {
      if (!open) {
        setSearchValue('') // Clear search when closing
        if (isAsync) {
          if (searchTimeoutRef.current !== undefined) {
            clearTimeout(searchTimeoutRef.current)
            searchTimeoutRef.current = undefined
          }
          asyncFetchGenerationRef.current += 1
          setIsLoadingOptions(false)
          setAsyncOptions([])
        }
      }
      onOpenChange(open)
    },
    [isAsync, onOpenChange]
  )

  const handleClearSearch = useCallback(() => {
    setSearchValue('')
    if (isAsync) {
      detachPromise(loadAsyncOptions(''))
    }
  }, [isAsync, loadAsyncOptions])

  // Wrap onSelect to capture the selected option for async filters
  const onOptionSelectedFn = selectedField.onOptionSelected
  const handleSelect = useCallback(
    (event: React.MouseEvent | undefined, value: string | number | undefined) => {
      if (value) {
        // Find and store the selected option
        const option = filteredOptions.find((opt) => String(opt.value) === String(value))
        if (option) {
          if (isAsync) {
            setSelectedOption(option)
          }
          // Call the onOptionSelected callback if provided
          onOptionSelectedFn?.(String(value), option.label)
        }
      }
      onSelect(event, value)
    },
    [isAsync, filteredOptions, onSelect, onOptionSelectedFn]
  )

  const toggleLabel = activeOption
    ? activeOption.label
    : (selectedField.placeholder ?? `Filter by ${selectedField.label.toLowerCase()}`)

  const valueToggleState = useMemo(
    () => ({
      isOpen,
      onOpenChange: handleOpenChange,
      toggleLabel,
    }),
    [isOpen, handleOpenChange, toggleLabel]
  )

  const renderValueToggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) => selectFilterInputSelectToggle(toggleRef, valueToggleState),
    [valueToggleState]
  )

  if (!selectedField.options && !selectedField.asyncOptions) return null

  const showSearch =
    isAsync || (selectedField.searchable !== false && (selectedField.options?.length ?? 0) >= SEARCH_THRESHOLD)

  let selectListBody: React.ReactNode
  if (isLoadingOptions) {
    selectListBody = <SelectOption isDisabled>Loading...</SelectOption>
  } else if (filteredOptions.length > 0) {
    selectListBody = filteredOptions.map((option) => (
      <SelectOption key={option.value} value={option.value} description={option.description}>
        {option.label}
      </SelectOption>
    ))
  } else {
    selectListBody = <SelectOption isDisabled>No results found</SelectOption>
  }

  return (
    <ToolbarItem>
      <SynSelect
        id="attribute-search-value-select"
        isOpen={isOpen}
        selected={activeOption?.value}
        onSelect={handleSelect}
        onOpenChange={handleOpenChange}
        popperProps={{
          ...popperProps,
          maxWidth: typeof popperProps?.maxWidth === 'string' ? popperProps.maxWidth : '20rem',
        }}
        toggle={renderValueToggle}
      >
        {showSearch && (
          <SearchInput
            value={searchValue}
            onChange={handleSearchChange}
            onClear={handleClearSearch}
            placeholder="Search..."
            style={{ padding: 'var(--pf-t--global--spacer--sm)' }}
          />
        )}
        <SelectList>{selectListBody}</SelectList>
      </SynSelect>
    </ToolbarItem>
  )
}

/**
 * Multi-select filter input with checkboxes
 */
type MultiSelectFilterInputProps = {
  selectedField: FilterFieldDefinition
  values: string[]
  isOpen: boolean
  onOpenChange: (isOpen: boolean) => void
  onSelect: (_event: React.MouseEvent | undefined, value: string | number | undefined) => void
}

type MultiSelectFilterInputMenuToggleProps = {
  toggleRef: React.Ref<MenuToggleElement>
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  displayText: string
}

function MultiSelectFilterInputMenuToggle({
  toggleRef,
  isOpen,
  onOpenChange,
  displayText,
}: Readonly<MultiSelectFilterInputMenuToggleProps>) {
  return (
    <MenuToggle ref={toggleRef} onClick={() => onOpenChange(!isOpen)}>
      {displayText}
    </MenuToggle>
  )
}

function multiSelectFilterInputSelectToggle(
  toggleRef: React.Ref<MenuToggleElement>,
  state: Pick<MultiSelectFilterInputMenuToggleProps, 'isOpen' | 'onOpenChange' | 'displayText'>
) {
  return (
    <MultiSelectFilterInputMenuToggle
      toggleRef={toggleRef}
      isOpen={state.isOpen}
      onOpenChange={state.onOpenChange}
      displayText={state.displayText}
    />
  )
}

export function MultiSelectFilterInput({
  selectedField,
  values,
  isOpen,
  onOpenChange,
  onSelect,
}: Readonly<MultiSelectFilterInputProps>) {
  const displayText = values.length > 0 ? `${values.length} selected` : (selectedField.placeholder ?? 'Select values')

  const multiValueToggleState = useMemo(
    () => ({
      isOpen,
      onOpenChange,
      displayText,
    }),
    [isOpen, onOpenChange, displayText]
  )

  const renderMultiValueToggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) => multiSelectFilterInputSelectToggle(toggleRef, multiValueToggleState),
    [multiValueToggleState]
  )

  if (!selectedField.options) return null

  return (
    <ToolbarItem>
      <SynSelect
        id="attribute-search-multiselect"
        isOpen={isOpen}
        onOpenChange={onOpenChange}
        onSelect={onSelect}
        toggle={renderMultiValueToggle}
      >
        <SelectList>
          {selectedField.options.map((option) => (
            <SelectOption
              key={option.value}
              value={option.value}
              hasCheckbox
              isSelected={values.includes(option.value)}
            >
              {option.label}
            </SelectOption>
          ))}
        </SelectList>
      </SynSelect>
    </ToolbarItem>
  )
}
