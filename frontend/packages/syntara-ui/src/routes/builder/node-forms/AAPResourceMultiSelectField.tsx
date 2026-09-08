import {
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Label,
  LabelGroup,
  MenuToggle,
  SearchInput,
  SelectList,
  SelectOption,
  Spinner,
  StackItem,
  type MenuToggleElement,
} from '@patternfly/react-core'
import type { AAPAPI } from '@syntara/contracts'
import React, { useEffect, useRef, useState, type ReactElement } from 'react'
import { Controller, useFormContext } from 'react-hook-form'

import { SynSelect } from '../../../components/SynSelect'
import { DEBOUNCE_MS } from '../../../constants/timing'

import type { AAPJobTemplateFormData } from './aapJobTemplateSchema'

type AAPResourceItem = {
  readonly id: number
  readonly name: string
}

type AAPDefaultValue = AAPAPI.components['schemas']['AAPSummaryField']

type AAPResourceMultiSelectFieldProps = {
  readonly label: string
  readonly fieldId: string
  readonly nameField: 'job_credentials' | 'labels' // Multi-select fields with number[] arrays
  readonly items: readonly AAPResourceItem[]
  readonly isLoading: boolean
  readonly helperText: string
  readonly placeholderText: string
  readonly defaultValues?: readonly AAPDefaultValue[]
  readonly onSearchChange?: (search: string) => void
  readonly labelHelp?: ReactElement
}

type MultiSelectToggleProps = {
  readonly toggleRef: React.Ref<MenuToggleElement>
  readonly isOpen: boolean
  readonly isLoading: boolean
  readonly selectedItems: readonly AAPResourceItem[]
  readonly placeholder: React.ReactNode
  readonly onToggle: () => void
  readonly ariaDescribedBy?: string
}

function MultiSelectToggle({
  toggleRef,
  isOpen,
  isLoading,
  selectedItems,
  placeholder,
  onToggle,
  ariaDescribedBy,
}: MultiSelectToggleProps) {
  return (
    <MenuToggle
      ref={toggleRef}
      onClick={onToggle}
      isExpanded={isOpen}
      isFullWidth
      isDisabled={isLoading}
      aria-describedby={ariaDescribedBy}
      style={{
        textAlign: 'left',
        minHeight: 'var(--pf-t--global--control-height--default)',
      }}
      icon={isLoading ? <Spinner size="md" /> : undefined}
    >
      {selectedItems.length === 0 ? (
        placeholder
      ) : (
        <LabelGroup numLabels={3}>
          {selectedItems.map((item) => (
            <Label key={item.id}>{item.name}</Label>
          ))}
        </LabelGroup>
      )}
    </MenuToggle>
  )
}

type MultiSelectContentProps = {
  readonly label: string
  readonly items: readonly AAPResourceItem[]
  readonly isLoading: boolean
  readonly isOpen: boolean
  readonly selectedIds: readonly number[]
  readonly placeholder: React.ReactNode
  readonly filterValue: string
  readonly onSearchChange?: (search: string) => void
  readonly onSelect: (event: React.MouseEvent | undefined, value: string | number | undefined) => void
  readonly onOpenChange: (open: boolean) => void
  readonly onToggle: () => void
  readonly onFilterChange: (value: string) => void
  readonly onFilterClear: () => void
  readonly ariaDescribedBy?: string
  readonly defaultValues?: readonly AAPDefaultValue[]
}

type RenderToggleProps = {
  readonly isOpen: boolean
  readonly isLoading: boolean
  readonly selectedItems: readonly AAPResourceItem[]
  readonly placeholder: React.ReactNode
  readonly onToggle: () => void
  readonly ariaDescribedBy?: string
}

function createToggleRenderer({
  isOpen,
  isLoading,
  selectedItems,
  placeholder,
  onToggle,
  ariaDescribedBy,
}: RenderToggleProps) {
  return (toggleRef: React.Ref<MenuToggleElement>) => (
    <MultiSelectToggle
      toggleRef={toggleRef}
      isOpen={isOpen}
      isLoading={isLoading}
      selectedItems={selectedItems}
      placeholder={placeholder}
      onToggle={onToggle}
      ariaDescribedBy={ariaDescribedBy}
    />
  )
}

function MultiSelectContent({
  label,
  items,
  isLoading,
  isOpen,
  selectedIds,
  placeholder,
  filterValue,
  onSearchChange,
  onSelect,
  onOpenChange,
  onToggle,
  onFilterChange,
  onFilterClear,
  ariaDescribedBy,
  defaultValues,
}: MultiSelectContentProps) {
  // Merge items with defaultValues to ensure selected items always have names
  // This handles the case where default credentials from the template aren't in the items list yet
  const allItems = React.useMemo(() => {
    if (!defaultValues?.length) return items

    const itemsMap = new Map(items.map((item) => [item.id, item]))
    defaultValues.forEach((dv) => {
      if (!itemsMap.has(dv.id)) {
        itemsMap.set(dv.id, { id: dv.id, name: dv.name })
      }
    })
    return Array.from(itemsMap.values())
  }, [items, defaultValues])

  const selectedItems = allItems.filter((item) => selectedIds.includes(item.id))

  const renderToggle = createToggleRenderer({
    isOpen,
    isLoading,
    selectedItems,
    placeholder,
    onToggle,
    ariaDescribedBy,
  })

  return (
    <SynSelect
      isOpen={isOpen}
      selected={selectedIds.map(String)}
      onSelect={onSelect}
      onOpenChange={onOpenChange}
      toggle={renderToggle}
    >
      {onSearchChange && (
        <SearchInput
          placeholder="Search"
          value={filterValue}
          onChange={(_event, value) => onFilterChange(value)}
          onClear={onFilterClear}
        />
      )}
      <SelectList aria-label={label}>
        {allItems.length === 0 ? (
          <SelectOption isDisabled>{isLoading ? 'Loading...' : 'No items available'}</SelectOption>
        ) : (
          allItems.map((item) => (
            <SelectOption key={item.id} value={String(item.id)} hasCheckbox isSelected={selectedIds.includes(item.id)}>
              {item.name}
            </SelectOption>
          ))
        )}
      </SelectList>
    </SynSelect>
  )
}

function useMultiSelectHandlers(
  nameField: 'job_credentials' | 'labels',
  setValue: ReturnType<typeof useFormContext<AAPJobTemplateFormData>>['setValue'],
  setIsOpen: React.Dispatch<React.SetStateAction<boolean>>,
  setFilterValue: React.Dispatch<React.SetStateAction<string>>
) {
  const handleSelect = (field: { onChange: (value: number[]) => void }, selectedIds: readonly number[]) => {
    return (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
      if (value === undefined || value === null) return
      const numericId = typeof value === 'string' ? Number.parseInt(value, 10) : value
      if (Number.isNaN(numericId)) return

      const newIds = selectedIds.includes(numericId)
        ? selectedIds.filter((id) => id !== numericId)
        : [...selectedIds, numericId]

      field.onChange(newIds)
      setValue(nameField, newIds)
    }
  }

  const handleOpenChange = (open: boolean) => {
    setIsOpen(open)
    if (!open) {
      setFilterValue('')
    }
  }

  const handleToggle = () => {
    setIsOpen((prev) => !prev)
  }

  return { handleSelect, handleOpenChange, handleToggle }
}

export function AAPResourceMultiSelectField({
  label,
  fieldId,
  nameField,
  items,
  isLoading,
  helperText,
  placeholderText,
  defaultValues,
  onSearchChange,
  labelHelp,
}: AAPResourceMultiSelectFieldProps) {
  const { control, setValue } = useFormContext<AAPJobTemplateFormData>()
  const [isOpen, setIsOpen] = useState(false)
  const [filterValue, setFilterValue] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  const { handleSelect, handleOpenChange, handleToggle } = useMultiSelectHandlers(
    nameField,
    setValue,
    setIsOpen,
    setFilterValue
  )

  // Debounce the search callback for server-side filtering
  useEffect(() => {
    if (!onSearchChange) return
    debounceRef.current = setTimeout(() => {
      onSearchChange(filterValue)
    }, DEBOUNCE_MS)
    return () => clearTimeout(debounceRef.current)
  }, [filterValue, onSearchChange])

  // Clear debounce on unmount
  useEffect(() => () => clearTimeout(debounceRef.current), [])

  const helperTextId = `${fieldId}-helper`

  return (
    <StackItem>
      <FormGroup label={label} labelHelp={labelHelp} fieldId={fieldId}>
        <Controller
          control={control}
          name={nameField}
          render={({ field }) => {
            // Type is inferred from schema: number[] | undefined
            // Ensure selectedIds is always an array (handle legacy single-value data, empty strings, or undefined)
            let selectedIds: readonly number[] = []
            if (Array.isArray(field.value)) {
              selectedIds = field.value as number[]
            } else if (typeof field.value === 'number') {
              selectedIds = [field.value]
            }

            return (
              <MultiSelectContent
                label={label}
                items={items}
                isLoading={isLoading}
                isOpen={isOpen}
                selectedIds={selectedIds}
                placeholder={placeholderText}
                filterValue={filterValue}
                onSearchChange={onSearchChange}
                onSelect={handleSelect(field, selectedIds)}
                onOpenChange={handleOpenChange}
                onToggle={handleToggle}
                onFilterChange={setFilterValue}
                onFilterClear={() => setFilterValue('')}
                ariaDescribedBy={helperTextId}
                defaultValues={defaultValues}
              />
            )
          }}
        />
        <FormHelperText>
          <HelperText id={helperTextId}>
            <HelperTextItem>{helperText}</HelperTextItem>
          </HelperText>
        </FormHelperText>
      </FormGroup>
    </StackItem>
  )
}
