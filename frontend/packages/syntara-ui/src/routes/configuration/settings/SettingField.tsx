import {
  Dropdown,
  DropdownItem,
  DropdownList,
  Flex,
  FlexItem,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  MenuToggle,
} from '@patternfly/react-core'
import { RhUiEllipsisVerticalFillIcon } from '@patternfly/react-icons'
import type { SettingsAPI } from '@syntara/contracts'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { HelpPopover } from '../../../components/expressions/HelpPopover'

import { SettingInput } from './SettingInput'
import { valuesEqual } from './valuesEqual'

type RuntimeSetting = SettingsAPI.components['schemas']['RuntimeSettingRead']

type SettingFieldProps = {
  readonly setting: RuntimeSetting
  readonly value: unknown
  readonly onChange: (key: string, value: unknown) => void
  readonly onResetSingle: (key: string) => void
  readonly onValidationChange?: (key: string, hasError: boolean) => void
  readonly readOnly?: boolean
}

function KebabToggle({
  toggleRef,
  onClick,
  isExpanded,
  label,
}: {
  readonly toggleRef: React.Ref<HTMLButtonElement>
  readonly onClick: () => void
  readonly isExpanded: boolean
  readonly label: string
}) {
  return (
    <MenuToggle
      ref={toggleRef}
      variant="plain"
      onClick={onClick}
      isExpanded={isExpanded}
      aria-label={label}
      icon={<RhUiEllipsisVerticalFillIcon />}
    />
  )
}

type SettingFieldKebabToggleState = {
  readonly onClick: () => void
  readonly isExpanded: boolean
  readonly settingName: string
}

function settingFieldKebabDropdownToggle(toggleRef: React.Ref<HTMLButtonElement>, state: SettingFieldKebabToggleState) {
  return (
    <KebabToggle
      toggleRef={toggleRef}
      onClick={state.onClick}
      isExpanded={state.isExpanded}
      label={`Actions for ${state.settingName}`}
    />
  )
}

export function SettingField({
  setting,
  value,
  onChange,
  onResetSingle,
  onValidationChange,
  readOnly,
}: SettingFieldProps) {
  const [kebabOpen, setKebabOpen] = useState(false)
  const [stringError, setStringError] = useState<string | null>(null)
  const handleToggleClick = useCallback(() => setKebabOpen((prev) => !prev), [])

  const kebabToggleState = useMemo(
    () => ({
      onClick: handleToggleClick,
      isExpanded: kebabOpen,
      settingName: setting.name,
    }),
    [handleToggleClick, kebabOpen, setting.name]
  )

  const renderKebabToggle = useCallback(
    (toggleRef: React.Ref<HTMLButtonElement>) => settingFieldKebabDropdownToggle(toggleRef, kebabToggleState),
    [kebabToggleState]
  )

  const isNotifications = setting.category === 'notifications'

  const helpPopover =
    !isNotifications && setting.description ? (
      <HelpPopover ariaLabel={`Help for ${setting.name}`} bodyContent={setting.description} />
    ) : undefined

  const numericBounds = useMemo(() => {
    if (setting.value_type !== 'integer' && setting.value_type !== 'float') return null
    const schema = (setting.validation_schema ?? {}) as Record<string, unknown>
    return {
      min: schema.min as number | undefined,
      max: schema.max as number | undefined,
    }
  }, [setting.value_type, setting.validation_schema])

  const numericError = useMemo(() => {
    if (!numericBounds) return null
    const num = value as number | null | undefined
    if (num === null || num === undefined) return null
    const { min, max } = numericBounds
    if (min !== undefined && num < min) {
      return `Value must be at least ${min.toString()}`
    }
    if (max !== undefined && num > max) {
      return `Value must be at most ${max.toString()}`
    }
    return null
  }, [numericBounds, value])

  const fieldError = numericError || stringError

  useEffect(() => {
    onValidationChange?.(setting.key, !!fieldError)
    return () => {
      onValidationChange?.(setting.key, false)
    }
  }, [fieldError, setting.key, onValidationChange])

  const helperText = setting.helper_text ?? null

  const kebabMenu = (
    <Dropdown
      isOpen={kebabOpen}
      onSelect={() => setKebabOpen(false)}
      onOpenChange={setKebabOpen}
      toggle={renderKebabToggle}
      popperProps={{ position: 'right' }}
    >
      <DropdownList>
        <DropdownItem
          key="reset"
          isDisabled={valuesEqual(value, setting.default_value)}
          onClick={() => onResetSingle(setting.key)}
        >
          Reset to default
        </DropdownItem>
      </DropdownList>
    </Dropdown>
  )

  const schema = (setting.validation_schema ?? {}) as Record<string, unknown>
  const shouldGrow =
    setting.value_type === 'json' || (setting.value_type === 'string' && !Array.isArray(schema.allowed_values))
  const showKebab = setting.value_type !== 'boolean' && setting.category !== 'notifications' && !readOnly

  return (
    <FormGroup label={setting.name} fieldId={setting.key} labelHelp={helpPopover}>
      <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
        <FlexItem grow={shouldGrow ? { default: 'grow' } : undefined}>
          <SettingInput
            setting={setting}
            value={value}
            numericBounds={numericBounds}
            numericError={numericError}
            onChange={onChange}
            stringError={stringError}
            onStringError={setStringError}
            readOnly={readOnly}
          />
        </FlexItem>
        {showKebab && <FlexItem>{kebabMenu}</FlexItem>}
      </Flex>
      {(fieldError || helperText) && (
        <FormHelperText>
          <HelperText>
            {fieldError ? (
              <HelperTextItem variant="error">{fieldError}</HelperTextItem>
            ) : (
              <HelperTextItem variant="default">{helperText}</HelperTextItem>
            )}
          </HelperText>
        </FormHelperText>
      )}
    </FormGroup>
  )
}
