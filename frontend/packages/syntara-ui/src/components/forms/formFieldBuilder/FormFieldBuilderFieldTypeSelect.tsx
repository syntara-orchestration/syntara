import { MenuToggle, type MenuToggleElement, SelectList, SelectOption } from '@patternfly/react-core'
import { useCallback, useState } from 'react'

import { type FormFieldType } from '../../../forms'
import { SynSelect } from '../../SynSelect'

import { fieldTypeLabel, FORM_FIELD_TYPE_SELECT_OPTIONS } from './createDefaultField'

type FormFieldBuilderFieldTypeSelectProps = {
  fieldId: string
  value: FormFieldType
  isDisabled?: boolean
  onChange: (type: FormFieldType) => void
}

type FieldTypeSelectToggleProps = Readonly<{
  toggleRef: React.Ref<MenuToggleElement>
  isOpen: boolean
  isDisabled?: boolean
  label: string
  onToggle: () => void
}>

function FieldTypeSelectToggle({ toggleRef, isOpen, isDisabled, label, onToggle }: FieldTypeSelectToggleProps) {
  return (
    <MenuToggle ref={toggleRef} onClick={onToggle} isExpanded={isOpen} isDisabled={isDisabled} isFullWidth>
      {label}
    </MenuToggle>
  )
}

export function FormFieldBuilderFieldTypeSelect({
  fieldId,
  value,
  isDisabled,
  onChange,
}: Readonly<FormFieldBuilderFieldTypeSelectProps>) {
  const [isOpen, setIsOpen] = useState(false)
  const handleToggle = useCallback(() => setIsOpen((open) => !open), [])
  const label = fieldTypeLabel(value)
  const renderToggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) => (
      <FieldTypeSelectToggle
        toggleRef={toggleRef}
        isOpen={isOpen}
        isDisabled={isDisabled}
        label={label}
        onToggle={handleToggle}
      />
    ),
    [handleToggle, isDisabled, isOpen, label]
  )

  return (
    <SynSelect
      id={fieldId}
      isOpen={isOpen}
      onOpenChange={setIsOpen}
      selected={value}
      onSelect={(_event, selected) => {
        onChange(selected as FormFieldType)
        setIsOpen(false)
      }}
      shouldFocusToggleOnSelect
      toggle={renderToggle}
    >
      <SelectList>
        {FORM_FIELD_TYPE_SELECT_OPTIONS.map((option) => (
          <SelectOption key={option.value} value={option.value}>
            {option.label}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}
