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
import { useEffect, useRef, useState, type ReactElement } from 'react'
import { Controller, useFormContext } from 'react-hook-form'

import { SynSelect } from '../../../components/SynSelect'
import { DEBOUNCE_MS } from '../../../constants/timing'
import type { AAPLabel } from '../../../hooks/useAAPBrowser'

import type { AAPJobTemplateFormData } from './aapJobTemplateSchema'

type AAPLabelsFieldProps = {
  readonly label: string
  readonly fieldId: string
  readonly availableLabels: readonly AAPLabel[]
  readonly isLoading: boolean
  readonly helperText: string
  readonly placeholderText: string
  readonly onSearchChange?: (search: string) => void
  readonly labelHelp?: ReactElement
}

type MultiSelectToggleProps = {
  readonly toggleRef: React.Ref<MenuToggleElement>
  readonly isOpen: boolean
  readonly isLoading: boolean
  readonly selectedLabels: readonly string[]
  readonly placeholder: React.ReactNode
  readonly onToggle: () => void
  readonly ariaDescribedBy?: string
}

type LabelToggleRenderProps = {
  readonly isOpen: boolean
  readonly isLoading: boolean
  readonly selectedLabels: readonly string[]
  readonly placeholderText: string
  readonly onToggle: () => void
  readonly ariaDescribedBy: string
}

/**
 * Render prop component for the Select toggle - extracted to satisfy Sonar S6478.
 * This component is passed data as props and is defined at module scope.
 */
function LabelToggleRender({
  isOpen,
  isLoading,
  selectedLabels,
  placeholderText,
  onToggle,
  ariaDescribedBy,
}: LabelToggleRenderProps) {
  return (toggleRef: React.Ref<MenuToggleElement>) => (
    <MultiSelectToggle
      toggleRef={toggleRef}
      isOpen={isOpen}
      isLoading={isLoading}
      selectedLabels={selectedLabels}
      placeholder={placeholderText}
      onToggle={onToggle}
      ariaDescribedBy={ariaDescribedBy}
    />
  )
}

function MultiSelectToggle({
  toggleRef,
  isOpen,
  isLoading,
  selectedLabels,
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
      {selectedLabels.length === 0 ? (
        placeholder
      ) : (
        <LabelGroup numLabels={3}>
          {selectedLabels.map((label) => (
            <Label key={label}>{label}</Label>
          ))}
        </LabelGroup>
      )}
    </MenuToggle>
  )
}

export function AAPLabelsField({
  label,
  fieldId,
  availableLabels,
  isLoading,
  helperText,
  placeholderText,
  onSearchChange,
  labelHelp,
}: AAPLabelsFieldProps) {
  const { control } = useFormContext<AAPJobTemplateFormData>()
  const [isOpen, setIsOpen] = useState(false)
  const [filterValue, setFilterValue] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  const helperTextId = `${fieldId}-helper`

  // Debounce the search callback for server-side filtering
  useEffect(() => {
    if (!onSearchChange) return
    debounceRef.current = setTimeout(() => {
      onSearchChange(filterValue)
    }, DEBOUNCE_MS)
    return () => clearTimeout(debounceRef.current)
  }, [filterValue, onSearchChange])

  return (
    <StackItem>
      <FormGroup label={label} labelHelp={labelHelp} fieldId={fieldId}>
        <Controller
          control={control}
          name="labels"
          render={({ field }) => {
            // Extract label names from available labels
            const labelNames: readonly string[] = availableLabels.map((l) => l.name)

            // Simple: labels are always strings
            const selectedLabels: readonly string[] = Array.isArray(field.value) ? field.value : []

            // Merge known + custom labels
            const knownSet = new Set(labelNames)
            const customLabels = selectedLabels.filter((name) => !knownSet.has(name))
            const allLabels = Array.from(new Set([...labelNames, ...customLabels]))

            // Filter all labels based on search input
            const filteredLabels = filterValue
              ? allLabels.filter((labelName) => labelName.toLowerCase().includes(filterValue.toLowerCase()))
              : allLabels

            // Check if the current filter value could create a new label
            const trimmedFilter = filterValue.trim()
            const canCreateNew =
              trimmedFilter.length > 0 && !allLabels.some((name) => name.toLowerCase() === trimmedFilter.toLowerCase())

            const handleSelect = (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
              if (!value || typeof value !== 'string') return

              const isSelected = selectedLabels.includes(value)
              const newLabels = isSelected
                ? selectedLabels.filter((label) => label !== value)
                : [...selectedLabels, value]

              field.onChange(newLabels)
            }

            const handleToggle = () => {
              setIsOpen((prev) => !prev)
            }

            const handleOpenChange = (open: boolean) => {
              setIsOpen(open)
              if (!open) {
                setFilterValue('')
              }
            }

            return (
              <SynSelect
                isOpen={isOpen}
                selected={selectedLabels}
                onSelect={handleSelect}
                onOpenChange={handleOpenChange}
                toggle={LabelToggleRender({
                  isOpen,
                  isLoading,
                  selectedLabels,
                  placeholderText,
                  onToggle: handleToggle,
                  ariaDescribedBy: helperTextId,
                })}
              >
                <SearchInput
                  placeholder={placeholderText}
                  value={filterValue}
                  onChange={(_event, value) => setFilterValue(value)}
                  onClear={() => setFilterValue('')}
                />
                <SelectList aria-label={label}>
                  {canCreateNew && (
                    <SelectOption
                      key={`create-${trimmedFilter}`}
                      value={trimmedFilter}
                      description="Create new label"
                      hasCheckbox
                      isSelected={selectedLabels.includes(trimmedFilter)}
                    >
                      {trimmedFilter}
                    </SelectOption>
                  )}
                  {filteredLabels.length === 0 && !canCreateNew ? (
                    <SelectOption isDisabled>{isLoading ? 'Loading...' : 'No labels available'}</SelectOption>
                  ) : (
                    filteredLabels.map((labelName) => (
                      <SelectOption
                        key={labelName}
                        value={labelName}
                        hasCheckbox
                        isSelected={selectedLabels.includes(labelName)}
                      >
                        {labelName}
                      </SelectOption>
                    ))
                  )}
                </SelectList>
              </SynSelect>
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
