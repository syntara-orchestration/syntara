import {
  Alert,
  Button,
  FormGroup,
  HelperText,
  HelperTextItem,
  MenuToggle,
  SelectList,
  SelectOption,
  Spinner,
  Stack,
  StackItem,
  TextInput,
  TextInputGroup,
  TextInputGroupMain,
  TextInputGroupUtilities,
} from '@patternfly/react-core'
import { RhUiCloseIcon } from '@patternfly/react-icons'
import type { ReactElement, RefObject } from 'react'
import { useEffect, useRef, useState } from 'react'

import { SynSelect } from '../../../components/SynSelect'

import type { ChildWorkflowOption, InvocationTrigger } from './useChildWorkflowSelector'

const DEBOUNCE_MS = 300
const LOAD_MORE_VALUE = '__load_more_workflows__'
const ELIGIBILITY_HELP_TEXT_NO_SEARCH =
  'This picker shows enabled, published workflows in this project that have a Sub-workflow Trigger. To make one eligible, add a Sub-workflow Trigger to a child workflow in this project and publish it, then refresh workflows.'
const ELIGIBILITY_HELP_TEXT_WITH_SEARCH =
  'No workflows match your search. This picker shows enabled, published workflows in this project that have a Sub-workflow Trigger.'

export type ChildWorkflowSelectorProps = {
  options: ChildWorkflowOption[]
  selectedOption?: ChildWorkflowOption
  selectedWorkflowLabel?: string
  selectedWorkflowId: string | null
  selectedTriggerNodeId: string
  workflowError?: string
  triggerError?: string
  onWorkflowChange: (workflowId: string | null, defaultTriggerId: string) => void
  onTriggerChange: (triggerNodeId: string) => void
  setSearchTerm: (searchTerm: string) => void
  isLoading: boolean
  hasNextPage: boolean
  isFetchingNextPage: boolean
  onLoadMore: () => void
  hasError: boolean
  errorMessage: string
  errorVariant: 'danger' | 'warning'
  onRetry: () => void
  label?: string
  labelHelp?: ReactElement
  triggerLabelHelp?: ReactElement
  isRequired?: boolean
  isDisabled?: boolean
}

function getTriggerLabel(trigger: InvocationTrigger, index: number) {
  return trigger.name?.trim() || `Trigger ${index + 1}`
}

function defaultTriggerId(option: ChildWorkflowOption | undefined): string {
  return option?.triggers.length === 1 ? option.triggers[0].trigger_node_id : ''
}

function InvocationTriggerSelector({
  triggers,
  selectedTriggerNodeId,
  onChange,
  isDisabled,
  error,
  labelHelp,
}: Readonly<{
  triggers: InvocationTrigger[]
  selectedTriggerNodeId: string
  onChange: (triggerNodeId: string) => void
  isDisabled: boolean
  error?: string
  labelHelp?: ReactElement
}>) {
  const [isOpen, setIsOpen] = useState(false)
  const selectedIndex = triggers.findIndex((trigger) => trigger.trigger_node_id === selectedTriggerNodeId)
  const selectedLabel =
    selectedIndex >= 0 ? getTriggerLabel(triggers[selectedIndex], selectedIndex) : 'Select a trigger...'

  return (
    <FormGroup label="Workflow trigger" labelHelp={labelHelp} isRequired fieldId="subworkflow-trigger-selector">
      <SynSelect
        id="subworkflow-trigger-selector"
        aria-label="Workflow trigger"
        isOpen={isOpen}
        selected={selectedTriggerNodeId || undefined}
        onSelect={(_event, value) => {
          if (value !== undefined) onChange(String(value))
          setIsOpen(false)
        }}
        onOpenChange={setIsOpen}
        shouldFocusToggleOnSelect
        toggle={(toggleRef) => (
          <MenuToggle
            ref={toggleRef}
            onClick={() => setIsOpen((open) => !open)}
            isExpanded={isOpen}
            isFullWidth
            isDisabled={isDisabled}
            aria-label="Workflow trigger"
          >
            {selectedLabel}
          </MenuToggle>
        )}
      >
        <SelectList>
          {triggers.map((trigger, index) => (
            <SelectOption key={trigger.trigger_node_id} value={trigger.trigger_node_id}>
              {getTriggerLabel(trigger, index)}
            </SelectOption>
          ))}
        </SelectList>
      </SynSelect>
      {error && (
        <HelperText>
          <HelperTextItem variant="error">{error}</HelperTextItem>
        </HelperText>
      )}
    </FormGroup>
  )
}

function StaticInvocationTrigger({
  trigger,
  labelHelp,
}: Readonly<{ trigger: InvocationTrigger; labelHelp?: ReactElement }>) {
  return (
    <FormGroup label="Workflow trigger" labelHelp={labelHelp} fieldId="selected-workflow-trigger">
      <TextInput
        id="selected-workflow-trigger"
        aria-label="Workflow trigger"
        value={getTriggerLabel(trigger, 0)}
        readOnly
        readOnlyVariant="plain"
      />
    </FormGroup>
  )
}

type WorkflowSelectorToggleProps = {
  toggleRef: RefObject<HTMLButtonElement | null>
  label: string
  isOpen: boolean
  isDisabled: boolean
  hasError: boolean
  workflowError?: string
  isLoading: boolean
  filterValue: string
  displayLabel: string
  selectedWorkflowId: string | null
  inputRef: RefObject<HTMLInputElement | null>
  onToggle: () => void
  onInputChange: (event: React.FormEvent<HTMLInputElement>, value: string) => void
  onClear: () => void
}

function WorkflowSelectorToggle({
  toggleRef,
  label,
  isOpen,
  isDisabled,
  hasError,
  workflowError,
  isLoading,
  filterValue,
  displayLabel,
  selectedWorkflowId,
  inputRef,
  onToggle,
  onInputChange,
  onClear,
}: Readonly<WorkflowSelectorToggleProps>) {
  const isClearSearchAction = isOpen && Boolean(filterValue)
  const hasClearAction = isClearSearchAction || (!isOpen && Boolean(selectedWorkflowId))
  const clearLabel = isClearSearchAction ? 'Clear search' : 'Clear selection'

  return (
    <MenuToggle
      ref={toggleRef}
      variant="typeahead"
      onClick={onToggle}
      isExpanded={isOpen}
      isFullWidth
      isDisabled={isDisabled}
      aria-label={label}
      status={hasError || workflowError ? 'danger' : undefined}
    >
      <TextInputGroup isPlain isDisabled={isDisabled}>
        <TextInputGroupMain
          value={isOpen ? filterValue : displayLabel}
          id="child-workflow-selector-input"
          aria-label={label}
          onChange={onInputChange}
          onClick={() => {
            if (!isOpen) onToggle()
          }}
          placeholder="Search for a published workflow..."
          autoComplete="off"
          innerRef={inputRef}
        />
        <TextInputGroupUtilities>
          {isLoading && <Spinner size="sm" aria-label="Loading workflows" />}
          {hasClearAction && !isDisabled && (
            <Button
              variant="plain"
              type="button"
              onClick={(event) => {
                event.stopPropagation()
                onClear()
              }}
              aria-label={clearLabel}
            >
              <RhUiCloseIcon />
            </Button>
          )}
        </TextInputGroupUtilities>
      </TextInputGroup>
    </MenuToggle>
  )
}

function WorkflowSelectorOptions({
  options,
  selectedWorkflowId,
  noResultsText,
  hasNextPage,
  isFetchingNextPage,
  isDisabled,
  onLoadMore,
}: Readonly<{
  options: ChildWorkflowOption[]
  selectedWorkflowId: string | null
  noResultsText: string
  hasNextPage: boolean
  isFetchingNextPage: boolean
  isDisabled: boolean
  onLoadMore: () => void
}>) {
  return (
    <SelectList>
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
      {hasNextPage && (
        <SelectOption
          value={LOAD_MORE_VALUE}
          isLoadButton={!isFetchingNextPage}
          isLoading={isFetchingNextPage}
          isDisabled={isDisabled || isFetchingNextPage}
          onClick={onLoadMore}
        >
          {isFetchingNextPage ? 'Loading more workflows...' : 'Load more workflows'}
        </SelectOption>
      )}
    </SelectList>
  )
}

function WorkflowSelectorFeedback({
  workflowError,
  hasError,
  errorVariant,
  errorMessage,
  hasOptions,
  showEligibilityHelp,
  hasSearchTerm,
  onRetry,
}: Readonly<{
  workflowError?: string
  hasError: boolean
  errorVariant: 'danger' | 'warning'
  errorMessage: string
  hasOptions: boolean
  showEligibilityHelp: boolean
  hasSearchTerm: boolean
  onRetry: () => void
}>) {
  const eligibilityHelpText = hasSearchTerm ? ELIGIBILITY_HELP_TEXT_WITH_SEARCH : ELIGIBILITY_HELP_TEXT_NO_SEARCH
  return (
    <>
      {workflowError && (
        <HelperText>
          <HelperTextItem variant="error">{workflowError}</HelperTextItem>
        </HelperText>
      )}
      {hasError && (
        <Alert variant={errorVariant} isInline isPlain title={errorMessage}>
          {hasOptions
            ? 'Successfully verified workflows remain selectable. '
            : 'Retry to check for eligible workflows. '}
          <Button variant="link" type="button" onClick={onRetry}>
            Retry
          </Button>
        </Alert>
      )}
      {showEligibilityHelp && (
        <HelperText>
          <HelperTextItem>{eligibilityHelpText}</HelperTextItem>
        </HelperText>
      )}
      {showEligibilityHelp && !hasSearchTerm && (
        <Button variant="link" type="button" onClick={onRetry}>
          Refresh workflows
        </Button>
      )}
    </>
  )
}

function getNoResultsText({
  isLoading,
  hasError,
  hasNextPage,
  hasSearchTerm,
}: Readonly<{
  isLoading: boolean
  hasError: boolean
  hasNextPage: boolean
  hasSearchTerm: boolean
}>): string {
  if (isLoading) return 'Loading eligible workflows...'
  if (hasError) return 'Unable to verify eligible workflows. Retry below.'
  if (hasNextPage) return 'No eligible workflows on this page. Load more to continue searching.'
  if (hasSearchTerm) return 'No eligible workflows match this search.'
  return 'No eligible workflows are available.'
}

function SelectedWorkflowTriggerFields({
  selectedOption,
  selectedTriggerNodeId,
  onTriggerChange,
  isDisabled,
  triggerError,
  triggerLabelHelp,
}: Readonly<{
  selectedOption?: ChildWorkflowOption
  selectedTriggerNodeId: string
  onTriggerChange: (triggerNodeId: string) => void
  isDisabled: boolean
  triggerError?: string
  triggerLabelHelp?: ReactElement
}>) {
  const triggers = selectedOption?.triggers ?? []
  if (triggers.length === 1) {
    return (
      <StackItem>
        <StaticInvocationTrigger trigger={triggers[0]} labelHelp={triggerLabelHelp} />
      </StackItem>
    )
  }
  if (triggers.length > 1 && selectedOption) {
    return (
      <StackItem>
        <InvocationTriggerSelector
          triggers={triggers}
          selectedTriggerNodeId={selectedTriggerNodeId}
          onChange={onTriggerChange}
          isDisabled={isDisabled}
          error={triggerError}
          labelHelp={triggerLabelHelp}
        />
      </StackItem>
    )
  }
  return null
}

/** Select a published same-project workflow and one of its Subworkflow Triggers. */
export function ChildWorkflowSelector({
  options,
  selectedOption,
  selectedWorkflowLabel,
  selectedWorkflowId,
  selectedTriggerNodeId,
  workflowError,
  triggerError,
  onWorkflowChange,
  onTriggerChange,
  setSearchTerm,
  isLoading,
  hasNextPage,
  isFetchingNextPage,
  onLoadMore,
  hasError,
  errorMessage,
  errorVariant,
  onRetry,
  label = 'Workflow',
  labelHelp,
  triggerLabelHelp,
  isRequired = false,
  isDisabled = false,
}: Readonly<ChildWorkflowSelectorProps>) {
  const [isOpen, setIsOpen] = useState(false)
  const [filterValue, setFilterValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  useEffect(() => {
    debounceRef.current = setTimeout(() => setSearchTerm(filterValue), DEBOUNCE_MS)
    return () => clearTimeout(debounceRef.current)
  }, [filterValue, setSearchTerm])

  useEffect(() => () => clearTimeout(debounceRef.current), [])

  const onSelect = (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
    if (value === LOAD_MORE_VALUE) return

    const workflowId = value === undefined ? null : String(value)
    const option = options.find((candidate) => candidate.value === workflowId)

    onWorkflowChange(workflowId, defaultTriggerId(option))
    setFilterValue('')
    setIsOpen(false)
  }

  const clear = () => {
    onWorkflowChange(null, '')
    setFilterValue('')
    inputRef.current?.focus()
  }

  const clearSearch = () => {
    setFilterValue('')
    inputRef.current?.focus()
  }

  const onInputChange = (_event: React.FormEvent<HTMLInputElement>, value: string) => {
    setFilterValue(value)
    setIsOpen(true)
  }

  const onOpenChange = (open: boolean) => {
    setIsOpen(open)
    setFilterValue('')
  }

  const onClear = () => {
    if (isOpen && filterValue) {
      clearSearch()
    } else {
      clear()
    }
  }

  const displayLabel = selectedOption?.label ?? selectedWorkflowLabel ?? selectedWorkflowId ?? ''
  const noResultsText = getNoResultsText({
    isLoading,
    hasError,
    hasNextPage: hasNextPage && options.length === 0,
    hasSearchTerm: Boolean(filterValue.trim()),
  })
  const showEligibilityHelp = options.length === 0 && !isLoading && !hasError && !hasNextPage
  return (
    <Stack hasGutter>
      <StackItem>
        <FormGroup label={label} labelHelp={labelHelp} isRequired={isRequired} fieldId="child-workflow-selector-input">
          <SynSelect
            id="child-workflow-selector"
            aria-label={label}
            isOpen={isOpen}
            onOpenChange={onOpenChange}
            onSelect={onSelect}
            selected={selectedWorkflowId ?? undefined}
            toggle={(toggleRef) => (
              <WorkflowSelectorToggle
                toggleRef={toggleRef}
                label={label}
                isOpen={isOpen}
                isDisabled={isDisabled}
                hasError={hasError}
                workflowError={workflowError}
                isLoading={isLoading}
                filterValue={filterValue}
                displayLabel={displayLabel}
                selectedWorkflowId={selectedWorkflowId}
                inputRef={inputRef}
                onToggle={() => setIsOpen((open) => !open)}
                onInputChange={onInputChange}
                onClear={onClear}
              />
            )}
          >
            <WorkflowSelectorOptions
              options={options}
              selectedWorkflowId={selectedWorkflowId}
              noResultsText={noResultsText}
              hasNextPage={hasNextPage}
              isFetchingNextPage={isFetchingNextPage}
              isDisabled={isDisabled}
              onLoadMore={onLoadMore}
            />
          </SynSelect>
        </FormGroup>
        <WorkflowSelectorFeedback
          workflowError={workflowError}
          hasError={hasError}
          errorVariant={errorVariant}
          errorMessage={errorMessage}
          hasOptions={options.length > 0}
          showEligibilityHelp={showEligibilityHelp}
          hasSearchTerm={Boolean(filterValue.trim())}
          onRetry={onRetry}
        />
      </StackItem>
      <SelectedWorkflowTriggerFields
        selectedOption={selectedOption}
        selectedTriggerNodeId={selectedTriggerNodeId}
        onTriggerChange={onTriggerChange}
        isDisabled={isDisabled}
        triggerError={triggerError}
        triggerLabelHelp={triggerLabelHelp}
      />
    </Stack>
  )
}
