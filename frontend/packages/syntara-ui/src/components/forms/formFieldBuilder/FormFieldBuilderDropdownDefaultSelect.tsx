import { FormGroup, MenuToggle, type MenuToggleElement, SelectList, SelectOption } from '@patternfly/react-core'
import type { FormDefinition } from '@syntara/contracts'
import type { ReactElement } from 'react'
import { useCallback, useMemo, useState } from 'react'
import { Controller, useFormContext, useWatch, type FieldError } from 'react-hook-form'

import { FormFieldError } from '../../FormFieldError'
import { SynSelect } from '../../SynSelect'
import { optionKey, type OptionScalarValue } from '../dynamicForm/synDynamicFormSelectHelpers'

import styles from './formFieldBuilder.module.css'
import { useFormFieldBuilderCommit } from './formFieldBuilderCommitContext'

const STATIC_DEFAULT_NONE = '__form_field_builder_default_none__'

type StaticOptionRow = {
  display_label: string
  value: OptionScalarValue
}

type FormFieldBuilderDropdownDefaultSelectProps = {
  index: number
  idPrefix: string
  isDisabled?: boolean
  labelHelp?: ReactElement
}

function findOptionByKey(options: ReadonlyArray<StaticOptionRow>, key: string): StaticOptionRow | undefined {
  return options.find((option) => optionKey(option.value) === key)
}

function defaultToggleText(
  current: OptionScalarValue | null | undefined,
  options: ReadonlyArray<StaticOptionRow>
): string {
  if (current == null) {
    return 'Select a default...'
  }
  const match = options.find((option) => option.value === current)
  return match?.display_label ?? String(current)
}

type DropdownDefaultSelectToggleProps = Readonly<{
  toggleRef: React.Ref<MenuToggleElement>
  isOpen: boolean
  isDisabled?: boolean
  isPlaceholder: boolean
  toggleText: string
  onToggle: () => void
}>

function DropdownDefaultSelectToggle({
  toggleRef,
  isOpen,
  isDisabled,
  isPlaceholder,
  toggleText,
  onToggle,
}: DropdownDefaultSelectToggleProps) {
  return (
    <MenuToggle
      ref={toggleRef}
      onClick={onToggle}
      isExpanded={isOpen}
      isDisabled={isDisabled}
      isFullWidth
      aria-label="Default value"
    >
      <span className={isPlaceholder ? styles.staticDefaultPlaceholder : undefined}>{toggleText}</span>
    </MenuToggle>
  )
}

type DropdownDefaultSelectControlProps = Readonly<{
  idPrefix: string
  labelHelp?: ReactElement
  isDisabled?: boolean
  options: ReadonlyArray<StaticOptionRow>
  isOpen: boolean
  setIsOpen: React.Dispatch<React.SetStateAction<boolean>>
  currentDefault: OptionScalarValue | null | undefined
  onDefaultChange: (value: OptionScalarValue | null) => void
  fieldError?: FieldError
}>

function DropdownDefaultSelectControl({
  idPrefix,
  labelHelp,
  isDisabled,
  options,
  isOpen,
  setIsOpen,
  currentDefault,
  onDefaultChange,
  fieldError,
}: DropdownDefaultSelectControlProps) {
  const commit = useFormFieldBuilderCommit()
  const selectedKey = currentDefault == null ? STATIC_DEFAULT_NONE : optionKey(currentDefault)
  const toggleText = defaultToggleText(currentDefault, options)
  const isPlaceholder = currentDefault == null
  const handleToggle = useCallback(() => setIsOpen((open) => !open), [setIsOpen])
  const renderToggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) => (
      <DropdownDefaultSelectToggle
        toggleRef={toggleRef}
        isOpen={isOpen}
        isDisabled={isDisabled}
        isPlaceholder={isPlaceholder}
        toggleText={toggleText}
        onToggle={handleToggle}
      />
    ),
    [handleToggle, isDisabled, isOpen, isPlaceholder, toggleText]
  )

  return (
    <FormGroup label="Default value" fieldId={`${idPrefix}-default`} labelHelp={labelHelp}>
      <SynSelect
        id={`${idPrefix}-default`}
        isOpen={isOpen}
        onOpenChange={setIsOpen}
        selected={selectedKey}
        onSelect={(_event, selection) => {
          const key = String(selection)
          if (key === STATIC_DEFAULT_NONE) {
            onDefaultChange(null)
          } else {
            const matched = findOptionByKey(options, key)
            onDefaultChange(matched?.value ?? null)
          }
          commit()
          setIsOpen(false)
        }}
        shouldFocusToggleOnSelect
        toggle={renderToggle}
      >
        <SelectList aria-label="Default value options">
          <SelectOption value={STATIC_DEFAULT_NONE} isSelected={currentDefault == null}>
            None
          </SelectOption>
          {options.map((option) => {
            const key = optionKey(option.value)
            return (
              <SelectOption key={key} value={key} isSelected={currentDefault === option.value}>
                {option.display_label}
              </SelectOption>
            )
          })}
        </SelectList>
      </SynSelect>
      <FormFieldError error={fieldError} />
    </FormGroup>
  )
}

export function FormFieldBuilderDropdownDefaultSelect({
  index,
  idPrefix,
  isDisabled,
  labelHelp,
}: Readonly<FormFieldBuilderDropdownDefaultSelectProps>) {
  const [isOpen, setIsOpen] = useState(false)
  const { control } = useFormContext<FormDefinition>()

  const staticValues = useWatch({
    control,
    name: `fields.${index}.options.values`,
  }) as ReadonlyArray<StaticOptionRow> | undefined

  const options = useMemo(() => staticValues ?? [], [staticValues])

  return (
    <Controller
      control={control}
      name={`fields.${index}.default`}
      render={({ field: rhfField, fieldState }) => (
        <DropdownDefaultSelectControl
          idPrefix={idPrefix}
          labelHelp={labelHelp}
          isDisabled={isDisabled}
          options={options}
          isOpen={isOpen}
          setIsOpen={setIsOpen}
          currentDefault={rhfField.value as OptionScalarValue | null | undefined}
          onDefaultChange={rhfField.onChange}
          fieldError={fieldState.error}
        />
      )}
    />
  )
}
