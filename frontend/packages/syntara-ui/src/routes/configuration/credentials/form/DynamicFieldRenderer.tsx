import {
  Button,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
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
import { RhUiErrorIcon, RhUiViewIcon, RhUiViewOffIcon } from '@patternfly/react-icons'
import { useMemo, useState, type Ref } from 'react'

import { FormLabelWithHelp } from '../../../../components/FormLabelWithHelp'
import { SynSelect } from '../../../../components/SynSelect'
import { ENCRYPTED_SENTINEL } from '../credentialConstants'

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
  value: unknown
  onChange: (fieldId: string, value: unknown) => void
  isRequired?: boolean
  isEditMode?: boolean
  error?: string
}

function FieldHelperText({ error, helpText }: Readonly<{ error?: string; helpText?: string }>) {
  if (error) {
    return (
      <FormHelperText>
        <HelperText>
          <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
            {error}
          </HelperTextItem>
        </HelperText>
      </FormHelperText>
    )
  }
  if (helpText) {
    return (
      <FormHelperText>
        <HelperText>
          <HelperTextItem>{helpText}</HelperTextItem>
        </HelperText>
      </FormHelperText>
    )
  }
  return null
}

type FieldWrapperProps = {
  field: FieldDefinition
  isRequired?: boolean
  error?: string
  children: React.ReactNode
}

function FieldWrapper({ field, isRequired, error, children }: Readonly<FieldWrapperProps>) {
  const fieldLabel = useMemo(() => {
    if (field.help_text) return <FormLabelWithHelp label={field.label} helpText={field.help_text} />
    return field.label
  }, [field.label, field.help_text])

  return (
    <FormGroup label={fieldLabel} isRequired={isRequired} fieldId={field.id}>
      {children}
      <FieldHelperText error={error} />
    </FormGroup>
  )
}

function BooleanField({ field, value, onChange, error }: DynamicFieldRendererProps) {
  return (
    <FieldWrapper field={field} error={error}>
      <Switch
        id={field.id}
        isChecked={value === true || value === 'true'}
        onChange={(_event, checked) => onChange(field.id, checked)}
        label="Enabled"
      />
    </FieldWrapper>
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

function ChoicesField({ field, value, onChange, isRequired, error }: DynamicFieldRendererProps) {
  const stringValue = value != null ? String(value as string | number | boolean) : ''

  return (
    <FieldWrapper field={field} isRequired={isRequired} error={error}>
      <ChoicesSelect
        value={stringValue}
        onChange={(val) => onChange(field.id, val)}
        choices={field.choices ?? []}
        fieldId={field.id}
        label={field.label}
        validated={error ? 'error' : 'default'}
      />
    </FieldWrapper>
  )
}

function MultilineField({ field, value, onChange, isRequired, error }: DynamicFieldRendererProps) {
  const stringValue = value != null ? String(value as string | number | boolean) : ''
  const validated = error ? 'error' : 'default'

  return (
    <FieldWrapper field={field} isRequired={isRequired} error={error}>
      <TextArea
        id={field.id}
        value={stringValue}
        onChange={(_event, val) => onChange(field.id, val)}
        validated={validated}
        rows={6}
        placeholder={field.placeholder ?? field.help_text}
        aria-label={field.label}
      />
    </FieldWrapper>
  )
}

function SecretField({ field, value, onChange, isRequired, isEditMode, error }: DynamicFieldRendererProps) {
  const [showSecret, setShowSecret] = useState(false)
  const [secretTouched, setSecretTouched] = useState(false)

  const stringValue = value != null ? String(value as string | number | boolean) : ''
  const isEncryptedPlaceholder = isEditMode && !secretTouched && stringValue === ENCRYPTED_SENTINEL
  const displayValue = isEncryptedPlaceholder ? '' : stringValue
  const validated = error ? 'error' : 'default'

  const handleSecretChange = (_event: React.FormEvent, val: string) => {
    if (!secretTouched) setSecretTouched(true)
    onChange(field.id, val)
  }

  return (
    <FieldWrapper field={field} isRequired={isRequired} error={error}>
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
    </FieldWrapper>
  )
}

function PlainTextField({ field, value, onChange, isRequired, error }: DynamicFieldRendererProps) {
  const stringValue = value != null ? String(value as string | number | boolean) : ''
  const validated = error ? 'error' : 'default'

  return (
    <FieldWrapper field={field} isRequired={isRequired} error={error}>
      <TextInput
        id={field.id}
        type="text"
        value={stringValue}
        onChange={(_event, val) => onChange(field.id, val)}
        validated={validated}
        placeholder={field.placeholder ?? field.help_text}
        aria-label={field.label}
      />
    </FieldWrapper>
  )
}

export function DynamicFieldRenderer(props: DynamicFieldRendererProps) {
  const { field } = props

  if (field.type === 'boolean') return <BooleanField {...props} />
  if (field.choices && field.choices.length > 0) return <ChoicesField {...props} />
  if (field.multiline) return <MultilineField {...props} />
  if (field.secret) return <SecretField {...props} />
  return <PlainTextField {...props} />
}
