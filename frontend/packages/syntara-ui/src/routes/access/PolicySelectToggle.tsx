import {
  Button,
  LabelGroup,
  MenuToggle,
  TextInputGroup,
  TextInputGroupMain,
  TextInputGroupUtilities,
} from '@patternfly/react-core'
import { RhUiCloseIcon } from '@patternfly/react-icons'
import type { Ref, RefObject } from 'react'

import { SynLabel } from '../../components/labels/SynLabel'

type PolicySelectToggleProps = {
  toggleRef: Ref<HTMLButtonElement>
  isOpen: boolean
  onToggle: () => void
  filterValue: string
  onFilterChange: (value: string) => void
  onFilterFocus: () => void
  selected: string[]
  onRemovePolicy: (name: string) => void
  onClearAll: () => void
  inputRef: RefObject<HTMLInputElement | null>
  isDisabled?: boolean
  hasError?: boolean
  toggleTestId?: string
}

export function PolicySelectToggle({
  toggleRef,
  isOpen,
  onToggle,
  filterValue,
  onFilterChange,
  onFilterFocus,
  selected,
  onRemovePolicy,
  onClearAll,
  inputRef,
  isDisabled,
  hasError,
  toggleTestId,
}: Readonly<PolicySelectToggleProps>) {
  return (
    <MenuToggle
      ref={toggleRef}
      data-testid={toggleTestId}
      variant="typeahead"
      onClick={onToggle}
      isExpanded={isOpen}
      isFullWidth
      isDisabled={isDisabled}
      status={hasError ? 'danger' : undefined}
    >
      <TextInputGroup isPlain isDisabled={isDisabled}>
        <TextInputGroupMain
          value={filterValue}
          onChange={(_e, val) => onFilterChange(val)}
          onClick={onFilterFocus}
          placeholder={selected.length === 0 ? 'Select policies...' : ''}
          autoComplete="off"
          innerRef={inputRef}
        >
          {selected.length > 0 && (
            <LabelGroup>
              {selected.map((name) => (
                <SynLabel
                  key={name}
                  color="blue"
                  onClose={(e) => {
                    e.stopPropagation()
                    onRemovePolicy(name)
                  }}
                >
                  {name}
                </SynLabel>
              ))}
            </LabelGroup>
          )}
        </TextInputGroupMain>
        {selected.length > 0 && (
          <TextInputGroupUtilities>
            <Button
              variant="plain"
              onClick={(e) => {
                e.stopPropagation()
                onClearAll()
              }}
              aria-label="Clear all selected policies"
            >
              <RhUiCloseIcon />
            </Button>
          </TextInputGroupUtilities>
        )}
      </TextInputGroup>
    </MenuToggle>
  )
}
