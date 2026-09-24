import {
  Button,
  InputGroup,
  InputGroupItem,
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  Switch,
  TextArea,
  TextInput,
} from '@patternfly/react-core'
import { RhUiViewIcon, RhUiViewOffIcon } from '@patternfly/react-icons'
import { useMemo, useState, type Ref } from 'react'
import type { FieldPath } from 'react-hook-form'

import { createFieldHelp } from '../../../../components/createFieldHelp'
import { SynFormField } from '../../../../components/forms/SynFormField'
import { SynSelect } from '../../../../components/SynSelect'
import { ENCRYPTED_SENTINEL } from '../credentialConstants'

import type { CredentialFormData } from './credentialFormSchema'

export type FieldDefinition = {
  id: string
  label: string
  type: string
  secret?: boolean
  choices?: string[]
  help_text?: string
  placeholder?: string
  default?: unknown
  multiline?: boolean
}

type DynamicFieldRendererProps = {
  field: FieldDefinition
  isRequired?: boolean
  isEditMode?: boolean
  onSecretTouch?: (fieldId: string) => void
}

function inputFieldName(fieldId: string): FieldPath<CredentialFormData> {
  return `inputs.${fieldId}` as FieldPath<CredentialFormData>
}

function toFieldString(value: unknown): string {
  return value != null && (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean')
    ? String(value)
    : ''
}

type DynamicSynFormFieldProps = DynamicFieldRendererProps & {
  children: (renderProps: {
    value: unknown
    onValueChange: (value: unknown) => void
    validated: 'error' | 'default'
  }) => React.ReactNode
}

function DynamicSynFormField({ field, isRequired, children }: Readonly<DynamicSynFormFieldProps>) {
  const labelHelp = useMemo(
    () => (field.help_text ? createFieldHelp(field.label, field.help_text) : undefined),
    [field.label, field.help_text]
  )

  return (
    <SynFormField
      name={inputFieldName(field.id)}
      label={field.label}
      fieldId={field.id}
      isRequired={isRequired}
      labelHelp={labelHelp}
    >
      {({ field: rhfField, fieldState }) =>
        children({
          value: rhfField.value,
          onValueChange: rhfField.onChange,
          validated: fieldState.error ? 'error' : 'default',
        })
      }
    </SynFormField>
  )
}

function BooleanField({ field, isRequired }: Readonly<DynamicFieldRendererProps>) {
  return (
    <DynamicSynFormField field={field} isRequired={isRequired}>
      {({ value, onValueChange }) => (
        <Switch
          id={field.id}
          isChecked={value === true || value === 'true'}
          onChange={(_event, checked) => onValueChange(checked)}
          label="Enabled"
        />
      )}
    </DynamicSynFormField>
  )
}

function ChoicesSelect({
  value,
  onChange,
  choices,
  fieldId,
  label,
  validated,
}: {
  value: string
  onChange: (value: string) => void
  choices: string[]
  fieldId: string
  label: string
  validated?: 'error' | 'default'
}) {
  const [isOpen, setIsOpen] = useState(false)
  const toggleText = value || 'Select...'
  return (
    <SynSelect
      id={fieldId}
      isOpen={isOpen}
      selected={value || undefined}
      onSelect={(_event, val: string | number | undefined) => {
        onChange(String(val))
        setIsOpen(false)
      }}
      onOpenChange={setIsOpen}
      toggle={(toggleRef: Ref<MenuToggleElement>) => (
        <MenuToggle
          ref={toggleRef}
          onClick={() => setIsOpen((prev) => !prev)}
          isExpanded={isOpen}
          isFullWidth
          isPlaceholder={!value}
          status={validated === 'error' ? 'danger' : undefined}
          aria-label={label}
        >
          {toggleText}
        </MenuToggle>
      )}
    >
      <SelectList>
        {choices.map((choice) => (
          <SelectOption key={choice} value={choice}>
            {choice}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}

function ChoicesField({ field, isRequired }: Readonly<DynamicFieldRendererProps>) {
  return (
    <DynamicSynFormField field={field} isRequired={isRequired}>
      {({ value, onValueChange, validated }) => (
        <ChoicesSelect
          value={toFieldString(value)}
          onChange={onValueChange}
          choices={field.choices ?? []}
          fieldId={field.id}
          label={field.label}
          validated={validated}
        />
      )}
    </DynamicSynFormField>
  )
}

function MultilineField({ field, isRequired }: Readonly<DynamicFieldRendererProps>) {
  return (
    <DynamicSynFormField field={field} isRequired={isRequired}>
      {({ value, onValueChange, validated }) => (
        <TextArea
          id={field.id}
          value={toFieldString(value)}
          onChange={(_event, val) => onValueChange(val)}
          validated={validated}
          rows={6}
          placeholder={field.placeholder ?? field.help_text}
          aria-label={field.label}
        />
      )}
    </DynamicSynFormField>
  )
}

function SecretField({ field, isRequired, isEditMode, onSecretTouch }: Readonly<DynamicFieldRendererProps>) {
  const [showSecret, setShowSecret] = useState(false)
  const [secretTouched, setSecretTouched] = useState(false)

  return (
    <DynamicSynFormField field={field} isRequired={isRequired}>
      {({ value, onValueChange, validated }) => {
        const stringValue = toFieldString(value)
        const isEncryptedPlaceholder = isEditMode && !secretTouched && stringValue === ENCRYPTED_SENTINEL
        const displayValue = isEncryptedPlaceholder ? '' : stringValue

        const handleSecretChange = (_event: React.FormEvent, val: string) => {
          if (!secretTouched) setSecretTouched(true)
          onSecretTouch?.(field.id)
          onValueChange(val)
        }

        return (
          <InputGroup>
            <InputGroupItem isFill>
              <TextInput
                id={field.id}
                type={showSecret ? 'text' : 'password'}
                autoComplete="off"
                value={displayValue}
                onChange={handleSecretChange}
                validated={validated}
                placeholder={
                  isEncryptedPlaceholder
                    ? '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022'
                    : (field.placeholder ?? field.help_text)
                }
                aria-label={field.label}
              />
            </InputGroupItem>
            <InputGroupItem>
              <Button
                variant="control"
                onClick={() => setShowSecret(!showSecret)}
                aria-label={showSecret ? 'Hide secret' : 'Show secret'}
              >
                {showSecret ? <RhUiViewOffIcon /> : <RhUiViewIcon />}
              </Button>
            </InputGroupItem>
          </InputGroup>
        )
      }}
    </DynamicSynFormField>
  )
}

function PlainTextField({ field, isRequired }: Readonly<DynamicFieldRendererProps>) {
  return (
    <DynamicSynFormField field={field} isRequired={isRequired}>
      {({ value, onValueChange, validated }) => (
        <TextInput
          id={field.id}
          type="text"
          value={toFieldString(value)}
          onChange={(_event, val) => onValueChange(val)}
          validated={validated}
          placeholder={field.placeholder ?? field.help_text}
          aria-label={field.label}
        />
      )}
    </DynamicSynFormField>
  )
}

export function DynamicFieldRenderer(props: Readonly<DynamicFieldRendererProps>) {
  const { field } = props

  if (field.type === 'boolean') return <BooleanField {...props} />
  if (field.choices && field.choices.length > 0) return <ChoicesField {...props} />
  if (field.multiline) return <MultilineField {...props} />
  if (field.secret) return <SecretField {...props} />
  return <PlainTextField {...props} />
}
