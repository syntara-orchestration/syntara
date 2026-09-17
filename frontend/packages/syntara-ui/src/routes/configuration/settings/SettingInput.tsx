import {
  Button,
  Label,
  LabelGroup,
  MenuToggle,
  type MenuToggleElement,
  NumberInput,
  SelectList,
  SelectOption,
  Switch,
  TextInput,
  TextInputGroup,
  TextInputGroupMain,
  TextInputGroupUtilities,
} from '@patternfly/react-core'
import { RhUiCloseIcon } from '@patternfly/react-icons'
import type { SettingsAPI } from '@syntara/contracts'
import React, { useEffect, useRef, useState } from 'react'
import { z } from 'zod'

import { SynSelect } from '../../../components/SynSelect'

type RuntimeSetting = SettingsAPI.components['schemas']['RuntimeSettingRead']

type NumericBounds = {
  min: number | undefined
  max: number | undefined
}

type SettingInputProps = {
  readonly setting: RuntimeSetting
  readonly value: unknown
  readonly numericBounds: NumericBounds | null
  readonly numericError: string | null
  readonly onChange: (key: string, value: unknown) => void
  readonly stringError: string | null
  readonly onStringError: (error: string | null) => void
  readonly readOnly?: boolean
}

const emailSchema = z.email({ error: 'Invalid email address' })
const urlSchema = z
  .url({ error: 'Must be a valid URL' })
  .refine((url) => /^https?:\/\//i.test(url), { message: 'Must be an HTTP or HTTPS URL' })

function useStringPatternValidation(
  valueType: string,
  value: unknown,
  pattern: string | undefined,
  onStringError: (error: string | null) => void
) {
  useEffect(() => {
    if (valueType !== 'string' || !pattern) return
    const val = (value as string) ?? ''
    if (!val) {
      onStringError(null)
      return
    }
    if (pattern === 'url') {
      const result = urlSchema.safeParse(val)
      onStringError(result.success ? null : result.error.issues[0].message)
    } else if (pattern === 'email') {
      const result = emailSchema.safeParse(val)
      onStringError(result.success ? null : result.error.issues[0].message)
    }
  }, [value, valueType, pattern, onStringError])
}

type JsonInputProps = {
  readonly setting: RuntimeSetting
  readonly value: unknown
  readonly pattern: string | undefined
  readonly onChange: (key: string, value: unknown) => void
  readonly stringError: string | null
  readonly onStringError: (error: string | null) => void
  readonly readOnlyVariant?: 'default'
}

function JsonInput({ setting, value, pattern, onChange, stringError, onStringError, readOnlyVariant }: JsonInputProps) {
  const [inputValue, setInputValue] = useState('')
  const items = Array.isArray(value) ? (value as string[]).filter(Boolean) : []
  const itemsRef = useRef(items)
  useEffect(() => {
    itemsRef.current = items
  })

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key !== 'Enter') return
    event.preventDefault()
    const trimmed = inputValue.trim()
    if (!trimmed) return
    if (pattern === 'email') {
      const result = emailSchema.safeParse(trimmed)
      if (!result.success) {
        onStringError(result.error.issues[0].message)
        return
      }
    }
    if (stringError) onStringError(null)
    const currentItems = itemsRef.current
    if (!currentItems.includes(trimmed)) {
      const updated = [...currentItems, trimmed]
      itemsRef.current = updated
      onChange(setting.key, updated)
      setInputValue('')
    }
  }

  return (
    <TextInputGroup>
      <TextInputGroupMain
        id={setting.key}
        value={inputValue}
        onChange={(_event, val) => {
          if (stringError) onStringError(null)
          setInputValue(val)
        }}
        onKeyDown={handleKeyDown}
        placeholder={readOnlyVariant ? undefined : 'Type a value and press Enter'}
        inputProps={readOnlyVariant ? { readOnly: true } : undefined}
      >
        {items.length > 0 && (
          <LabelGroup aria-label={setting.name}>
            {items.map((item) => (
              <Label
                key={item}
                onClose={
                  readOnlyVariant
                    ? undefined
                    : () =>
                        onChange(
                          setting.key,
                          items.filter((i) => i !== item)
                        )
                }
              >
                {item}
              </Label>
            ))}
          </LabelGroup>
        )}
      </TextInputGroupMain>
      {!readOnlyVariant && items.length > 0 && (
        <TextInputGroupUtilities>
          <Button
            variant="plain"
            aria-label="Clear all"
            onClick={() => {
              onChange(setting.key, [])
              setInputValue('')
            }}
            icon={<RhUiCloseIcon />}
          />
        </TextInputGroupUtilities>
      )}
    </TextInputGroup>
  )
}

function AllowedValuesSelect({
  id,
  label,
  value,
  allowedValues,
  isDisabled,
  onChange,
}: {
  id: string
  label: string
  value: string
  allowedValues: string[]
  isDisabled?: boolean
  onChange: (value: string) => void
}) {
  const [isOpen, setIsOpen] = useState(false)
  return (
    <SynSelect
      id={id}
      isOpen={isOpen}
      selected={value || undefined}
      onSelect={(_event, val) => {
        onChange(String(val))
        setIsOpen(false)
      }}
      onOpenChange={setIsOpen}
      toggle={(toggleRef: React.Ref<MenuToggleElement>) => (
        <MenuToggle
          ref={toggleRef}
          onClick={() => setIsOpen((prev) => !prev)}
          isExpanded={isOpen}
          isFullWidth
          isDisabled={isDisabled}
          aria-label={label}
        >
          {value || allowedValues[0] || ''}
        </MenuToggle>
      )}
    >
      <SelectList>
        {allowedValues.map((v) => (
          <SelectOption key={v} value={v}>
            {v}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}

export function SettingInput({
  setting,
  value,
  numericBounds,
  numericError,
  onChange,
  stringError,
  onStringError,
  readOnly,
}: SettingInputProps) {
  const schema = (setting.validation_schema ?? {}) as Record<string, unknown>
  const pattern = schema.pattern as string | undefined

  useStringPatternValidation(setting.value_type, value, pattern, onStringError)

  const readOnlyVariant = readOnly ? ('default' as const) : undefined

  switch (setting.value_type) {
    case 'boolean':
      return (
        <Switch
          id={setting.key}
          label={value ? 'Enabled' : 'Disabled'}
          isChecked={value as boolean}
          isDisabled={readOnly}
          onChange={(_event, checked) => onChange(setting.key, checked)}
        />
      )

    case 'integer':
    case 'float': {
      const numValue = (value as number) ?? 0
      const min = numericBounds?.min
      const max = numericBounds?.max
      const step = setting.value_type === 'float' ? 0.1 : 1

      const handleBlur = () => {
        let snapped = numValue
        if (min !== undefined && snapped < min) snapped = min
        if (max !== undefined && snapped > max) snapped = max
        if (snapped !== numValue) onChange(setting.key, snapped)
      }

      return (
        <NumberInput
          id={setting.key}
          value={numValue}
          min={min}
          max={max}
          isDisabled={readOnly}
          validated={numericError ? 'error' : 'default'}
          onMinus={() => onChange(setting.key, Math.round((numValue - step) * 100) / 100)}
          onPlus={() => onChange(setting.key, Math.round((numValue + step) * 100) / 100)}
          onBlur={handleBlur}
          onChange={(event) => {
            const target = event.target as HTMLInputElement
            const parsed =
              setting.value_type === 'float' ? Number.parseFloat(target.value) : Number.parseInt(target.value, 10)
            if (!Number.isNaN(parsed)) onChange(setting.key, parsed)
          }}
        />
      )
    }

    case 'string': {
      const allowedValues = schema.allowed_values as string[] | undefined
      if (allowedValues) {
        return (
          <AllowedValuesSelect
            id={setting.key}
            label={setting.name}
            value={value as string}
            allowedValues={allowedValues}
            isDisabled={readOnly}
            onChange={(val) => onChange(setting.key, val)}
          />
        )
      }
      return (
        <TextInput
          id={setting.key}
          value={(value as string) ?? ''}
          validated={stringError ? 'error' : 'default'}
          readOnlyVariant={readOnlyVariant}
          onChange={(_event, val) => onChange(setting.key, val)}
        />
      )
    }

    case 'json':
      return (
        <JsonInput
          setting={setting}
          value={value}
          pattern={pattern}
          onChange={onChange}
          stringError={stringError}
          onStringError={onStringError}
          readOnlyVariant={readOnlyVariant}
        />
      )

    default:
      return (
        <TextInput
          id={setting.key}
          value={String(value as string)}
          readOnlyVariant={readOnlyVariant}
          onChange={(_event, val) => onChange(setting.key, val)}
        />
      )
  }
}
