import {
  Button,
  InputGroup,
  InputGroupItem,
  MenuToggle,
  type MenuToggleElement,
  Popover,
  SelectList,
  SelectOption,
  Switch,
  TextArea,
  TextInput,
} from '@patternfly/react-core'
import { RhUiViewIcon, RhUiViewOffIcon } from '@patternfly/react-icons'
import { useMemo, useState, type ReactElement, type Ref } from 'react'
import type { ControllerRenderProps, FieldPath } from 'react-hook-form'

import { FieldHelpIcon } from '../../../../components/FieldHelpIcon'
import { SynFormField } from '../../../../components/forms/SynFormField'
import { SynSelect } from '../../../../components/SynSelect'
import { ENCRYPTED_SENTINEL } from '../credentialConstants'

import styles from './CredentialFormModal.module.css'
import type { CredentialFormData } from './credentialFormSchema'

const STORED_VALUE_MASK = '\u2022'.repeat(8)

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
  min_length?: number
}

type DynamicFieldRendererProps = {
  field: FieldDefinition
  isRequired?: boolean
  isEditMode?: boolean
  isMtlsIdentity?: boolean
  onSecretTouch?: (fieldId: string) => void
}

function inputFieldName(fieldId: string): FieldPath<CredentialFormData> {
  return `inputs.${fieldId}` as FieldPath<CredentialFormData>
}

/** Matches legacy `FormLabelWithHelp` aria labels for credential dynamic fields (E2E + a11y). */
function dynamicFieldLabelHelp(label: string, helpText: string): ReactElement {
  const helpAriaLabel = `${label} help`
  return (
    <Popover bodyContent={helpText} aria-label={helpAriaLabel}>
      <Button variant="plain" aria-label={helpAriaLabel} icon={<FieldHelpIcon />} />
    </Popover>
  )
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
    inputProps: Partial<Pick<ControllerRenderProps<CredentialFormData>, 'name' | 'onBlur' | 'ref'>> & {
      'aria-describedby'?: string
      'aria-required'?: boolean
    }
  }) => React.ReactNode
}

function DynamicSynFormField({ field, isRequired, isMtlsIdentity, children }: Readonly<DynamicSynFormFieldProps>) {
  const labelHelp = useMemo(
    () => (!isMtlsIdentity && field.help_text ? dynamicFieldLabelHelp(field.label, field.help_text) : undefined),
    [field.label, field.help_text, isMtlsIdentity]
  )

  return (
    <SynFormField
      name={inputFieldName(field.id)}
      label={field.label}
      fieldId={field.id}
      isRequired={isRequired}
      labelHelp={labelHelp}
      hint={isMtlsIdentity ? field.help_text : undefined}
    >
      {({ field: rhfField, fieldState, describedBy }) => (
        <>
          {children({
            value: rhfField.value,
            onValueChange: rhfField.onChange,
            validated: fieldState.error ? 'error' : 'default',
            inputProps: isMtlsIdentity
              ? {
                  name: rhfField.name,
                  onBlur: rhfField.onBlur,
                  ref: rhfField.ref,
                  'aria-describedby': describedBy,
                  'aria-required': isRequired,
                }
              : {},
          })}
          {isMtlsIdentity && (
            <span className="pf-v6-u-screen-reader" aria-live="polite">
              {fieldState.error?.message}
            </span>
          )}
        </>
      )}
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

function MultilineField({ field, isRequired, isMtlsIdentity }: Readonly<DynamicFieldRendererProps>) {
  const defaultPlaceholder = isMtlsIdentity ? undefined : field.help_text
  return (
    <DynamicSynFormField field={field} isRequired={isRequired} isMtlsIdentity={isMtlsIdentity}>
      {({ value, onValueChange, validated, inputProps }) => (
        <TextArea
          {...inputProps}
          id={field.id}
          value={toFieldString(value)}
          onChange={(_event, val) => onValueChange(val)}
          validated={validated}
          rows={6}
          placeholder={field.placeholder ?? defaultPlaceholder}
          aria-label={field.label}
        />
      )}
    </DynamicSynFormField>
  )
}

function SecretField({
  field,
  isRequired,
  isEditMode,
  isMtlsIdentity,
  onSecretTouch,
}: Readonly<DynamicFieldRendererProps>) {
  const [showSecret, setShowSecret] = useState(false)
  const [secretTouched, setSecretTouched] = useState(false)
  const fieldPlaceholder = field.placeholder ?? (isMtlsIdentity ? undefined : field.help_text)
  const groupClassName = isMtlsIdentity ? styles.identitySecretInputGroup : undefined
  const autoComplete = isMtlsIdentity ? 'new-password' : 'off'
  const ariaControls = isMtlsIdentity ? field.id : undefined

  function updateSecretValue(value: string, onValueChange: (value: unknown) => void) {
    if (!secretTouched) setSecretTouched(true)
    if (isMtlsIdentity && !value) setShowSecret(false)
    onSecretTouch?.(field.id)
    onValueChange(value)
  }

  return (
    <DynamicSynFormField field={field} isRequired={isRequired} isMtlsIdentity={isMtlsIdentity}>
      {({ value, onValueChange, validated, inputProps }) => {
        const stringValue = toFieldString(value)
        const isEncryptedPlaceholder = isEditMode && !secretTouched && stringValue === ENCRYPTED_SENTINEL
        const displayValue = isEncryptedPlaceholder ? '' : stringValue
        const canReveal = !isMtlsIdentity || Boolean(displayValue)
        const isRevealed = canReveal && showSecret

        const secretInputProps = {
          ...inputProps,
          id: field.id,
          value: displayValue,
          onChange: (_event: React.FormEvent, val: string) => updateSecretValue(val, onValueChange),
          validated,
          placeholder: isEncryptedPlaceholder ? STORED_VALUE_MASK : fieldPlaceholder,
          'aria-label': field.label,
        }
        return (
          <InputGroup className={groupClassName}>
            <InputGroupItem isFill>
              {field.multiline ? (
                <TextArea
                  {...secretInputProps}
                  className={isRevealed ? undefined : styles.maskedSecretTextarea}
                  rows={4}
                  autoComplete="off"
                  spellCheck={false}
                />
              ) : (
                <TextInput {...secretInputProps} type={isRevealed ? 'text' : 'password'} autoComplete={autoComplete} />
              )}
            </InputGroupItem>
            <InputGroupItem>
              <Button
                variant="control"
                type="button"
                isAriaDisabled={!canReveal}
                onClick={canReveal ? () => setShowSecret(!showSecret) : undefined}
                aria-controls={ariaControls}
                aria-label={isRevealed ? `Hide ${field.label} secret` : `Show ${field.label} secret`}
              >
                {isRevealed ? <RhUiViewOffIcon /> : <RhUiViewIcon />}
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
  if (field.secret && props.isMtlsIdentity) return <SecretField {...props} />
  if (field.multiline) return <MultilineField {...props} />
  if (field.secret) return <SecretField {...props} />
  return <PlainTextField {...props} />
}
