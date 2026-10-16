import {
  Button,
  FormGroup,
  type FormGroupLabelInfo,
  MenuToggle,
  SelectList,
  SelectOption,
  Spinner,
  TextInputGroup,
  TextInputGroupMain,
  TextInputGroupUtilities,
} from '@patternfly/react-core'
import { RhUiCloseIcon } from '@patternfly/react-icons'
import { useEffect, useRef, useState } from 'react'

import { SynSelect } from '../../../components/SynSelect'

import { useChildWorkflowSelector } from './useChildWorkflowSelector'

const DEBOUNCE_MS = 300

export type ChildWorkflowSelectorProps = {
  projectId: string | null
  selectedWorkflowId: string | null
  onChange: (workflowId: string | null) => void
  label?: string
  labelHelp?: FormGroupLabelInfo
  isRequired?: boolean
  isDisabled?: boolean
}

/**
 * Child workflow selector dropdown for Sub-workflow step configuration.
 *
 * Provides a typeahead dropdown for selecting a child workflow from the current project.
 * Filters to published workflows only (reference mode).
 *
 * Features:
 * - Typeahead search with 300ms debounce
 * - Displays workflow name and version: "Workflow Name (vN)"
 * - Loading and error states
 * - Clear button to reset selection
 *
 * V1 Scope: Same-project workflows only
 *
 * @param projectId - Current project ID (null disables selector)
 * @param selectedWorkflowId - Currently selected workflow ID
 * @param onChange - Callback when workflow selection changes
 * @param label - Form label (default: "Workflow")
 * @param labelHelp - Optional help popover for the field
 * @param isRequired - Show required indicator
 * @param isDisabled - Disable the selector
 */
export function ChildWorkflowSelector({
  projectId,
  selectedWorkflowId,
  onChange,
  label = 'Workflow',
  labelHelp,
  isRequired = false,
  isDisabled = false,
}: ChildWorkflowSelectorProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [filterValue, setFilterValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  const { options, selectedOption, onSelectionChange, setSearchTerm, isLoading, hasError } = useChildWorkflowSelector({
    projectId,
    selectedWorkflowId,
    onChange,
  })

  // Debounce search for server-side filtering
  useEffect(() => {
    debounceRef.current = setTimeout(() => {
      setSearchTerm(filterValue)
    }, DEBOUNCE_MS)
    return () => clearTimeout(debounceRef.current)
  }, [filterValue, setSearchTerm])

  // Cleanup on unmount
  useEffect(() => () => clearTimeout(debounceRef.current), [])

  const onSelect = (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
    onSelectionChange(String(value ?? ''))
    setFilterValue('')
    setIsOpen(false)
  }

  const clear = () => {
    onSelectionChange(null)
    setFilterValue('')
    inputRef.current?.focus()
  }

  const onInputChange = (_e: React.FormEvent<HTMLInputElement>, val: string) => {
    setFilterValue(val)
    if (!isOpen) setIsOpen(true)
  }

  const displayLabel = selectedOption?.label ?? ''
  const noResultsText = isLoading ? 'Loading...' : `No workflows match "${filterValue}"`

  const toggle = (toggleRef: React.Ref<HTMLButtonElement>) => (
    <MenuToggle
      ref={toggleRef}
      variant="typeahead"
      onClick={() => setIsOpen(!isOpen)}
      isExpanded={isOpen}
      isFullWidth
      isDisabled={isDisabled}
      status={hasError ? 'danger' : undefined}
    >
      <TextInputGroup isPlain>
        <TextInputGroupMain
          value={isOpen ? filterValue : displayLabel}
          onChange={onInputChange}
          onClick={() => {
            if (!isOpen) setIsOpen(true)
          }}
          placeholder="Select a workflow..."
          autoComplete="off"
          innerRef={inputRef}
        />
        <TextInputGroupUtilities>
          {isLoading && <Spinner size="sm" aria-label="Loading workflows" />}
          {selectedWorkflowId && !isLoading && !isDisabled && (
            <Button
              variant="plain"
              onClick={(e) => {
                e.stopPropagation()
                clear()
              }}
              aria-label="Clear selection"
            >
              <RhUiCloseIcon />
            </Button>
          )}
        </TextInputGroupUtilities>
      </TextInputGroup>
    </MenuToggle>
  )

  return (
    <FormGroup label={label} labelHelp={labelHelp} isRequired={isRequired}>
      <SynSelect
        id="child-workflow-selector"
        aria-label={label}
        isOpen={isOpen}
        onOpenChange={(open) => {
          setIsOpen(open)
          if (!open) setFilterValue('')
        }}
        onSelect={onSelect}
        selected={selectedWorkflowId ?? undefined}
        toggle={toggle}
      >
        <SelectList style={{ maxHeight: '200px', overflow: 'auto' }}>
          {options.length === 0 ? (
            <SelectOption isDisabled>{noResultsText}</SelectOption>
          ) : (
            options.map((option) => (
              <SelectOption
                key={option.value}
                value={option.value}
                isSelected={option.value === selectedWorkflowId}
                description={option.description}
              >
                {option.label}
              </SelectOption>
            ))
          )}
        </SelectList>
      </SynSelect>
    </FormGroup>
  )
}
