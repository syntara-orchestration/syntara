import {
  Button,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  InputGroup,
  InputGroupItem,
  LabelGroup,
  MenuToggle,
  SelectList,
  SelectOption,
  Switch,
  TextInput,
  TextInputGroup,
  TextInputGroupMain,
  TextInputGroupUtilities,
} from '@patternfly/react-core'
import { RhUiCloseIcon, RhUiErrorIcon, RhUiViewIcon, RhUiViewOffIcon } from '@patternfly/react-icons'
import { type ReactElement, type Ref, useCallback, useMemo, useRef, useState } from 'react'
import type { Control, ControllerFieldState, ControllerRenderProps } from 'react-hook-form'
import { Controller } from 'react-hook-form'

import { NxLabel } from '../../../components/labels/NxLabel'
import { NxSelect } from '../../../components/NxSelect'
import { useAllGroups } from '../../access/useAllGroups'
import { excludeAuthenticatedGroup } from '../adminConstants'
import { PASSWORD_CHARACTER_CLASSES_MESSAGE, PASSWORD_MIN_LENGTH_MESSAGE } from '../passwordComplexity'
import type { UserFormData } from '../userFormSchema'

import { userHelp } from './userFieldHelp'
import { GROUPS_AUTHENTICATED_HINT } from './userFieldHelpText'

type ControlledTextFieldProps = {
  name: 'username' | 'first_name' | 'last_name' | 'email' | 'password'
  control: Control<UserFormData>
  label: string
  fieldId: string
  placeholder?: string
  isRequired?: boolean
  isDisabled?: boolean
  type?: 'text' | 'email' | 'password' | 'search' | 'tel' | 'url' | 'date' | 'time' | 'number'
  autoComplete?: string
  labelHelp?: ReactElement
}

function ControlledTextField({
  name,
  control,
  label,
  fieldId,
  placeholder,
  isRequired,
  isDisabled,
  type,
  autoComplete,
  labelHelp,
}: Readonly<ControlledTextFieldProps>) {
  return (
    <Controller
      name={name}
      control={control}
      render={({ field, fieldState }) => (
        <FormGroup label={label} fieldId={fieldId} isRequired={isRequired} labelHelp={labelHelp}>
          <TextInput
            id={fieldId}
            aria-label={label}
            placeholder={placeholder}
            type={type}
            validated={fieldState.error ? 'error' : 'default'}
            isDisabled={isDisabled}
            value={field.value ?? ''}
            onChange={field.onChange}
            onBlur={field.onBlur}
            name={field.name}
            autoComplete={autoComplete}
          />
          {fieldState.error && (
            <FormHelperText>
              <HelperText>
                <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                  {fieldState.error.message}
                </HelperTextItem>
              </HelperText>
            </FormHelperText>
          )}
        </FormGroup>
      )}
    />
  )
}

type GroupOption = {
  name: string
  description: string | null
}

function GroupMultiSelect({
  selected,
  onChange,
  isLoading,
  groupOptions,
}: Readonly<{
  selected: string[]
  onChange: (names: string[]) => void
  isLoading: boolean
  groupOptions: GroupOption[]
}>) {
  const [isOpen, setIsOpen] = useState(false)
  const [filterValue, setFilterValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const filteredOptions = useMemo(() => {
    if (!filterValue) return groupOptions
    const term = filterValue.toLowerCase()
    return groupOptions.filter((o) => o.name.toLowerCase().includes(term))
  }, [groupOptions, filterValue])

  const handleSelect = (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
    if (!value) return
    const name = String(value)
    if (selected.includes(name)) {
      onChange(selected.filter((n) => n !== name))
    } else {
      onChange([...selected, name])
    }
    inputRef.current?.focus()
  }

  const handleRemoveGroup = (e: React.MouseEvent, name: string) => {
    e.stopPropagation()
    onChange(selected.filter((n) => n !== name))
  }

  const handleClear = (e?: React.MouseEvent) => {
    e?.stopPropagation()
    onChange([])
    setFilterValue('')
    inputRef.current?.focus()
  }

  const handleFilterChange = (_e: React.SyntheticEvent, val: string) => {
    setFilterValue(val)
    if (!isOpen) setIsOpen(true)
  }

  const handleInputClick = () => {
    if (!isOpen) setIsOpen(true)
  }

  const toggle = (toggleRef: Ref<HTMLButtonElement>) => (
    <MenuToggle ref={toggleRef} variant="typeahead" onClick={() => setIsOpen(!isOpen)} isExpanded={isOpen} isFullWidth>
      <TextInputGroup isPlain>
        <TextInputGroupMain
          value={filterValue}
          onChange={handleFilterChange}
          onClick={handleInputClick}
          placeholder={selected.length === 0 ? 'Select groups...' : ''}
          autoComplete="off"
          innerRef={inputRef}
          aria-label="Filter groups"
        >
          {selected.length > 0 && (
            <LabelGroup>
              {selected.map((name) => (
                <NxLabel key={name} color="blue" onClose={(e) => handleRemoveGroup(e, name)}>
                  {name}
                </NxLabel>
              ))}
            </LabelGroup>
          )}
        </TextInputGroupMain>
        {selected.length > 0 && (
          <TextInputGroupUtilities>
            <Button variant="plain" onClick={handleClear} aria-label="Clear all groups">
              <RhUiCloseIcon />
            </Button>
          </TextInputGroupUtilities>
        )}
      </TextInputGroup>
    </MenuToggle>
  )

  const handleOpenChange = useCallback((open: boolean) => {
    setIsOpen(open)
    if (!open) setFilterValue('')
  }, [])

  return (
    <NxSelect
      id="user-groups-select"
      aria-label="Select groups"
      isOpen={isOpen}
      onOpenChange={handleOpenChange}
      onSelect={handleSelect}
      selected={selected}
      toggle={toggle}
    >
      <SelectList style={{ maxHeight: '200px', overflow: 'auto' }}>
        {isLoading && <SelectOption isDisabled>Loading...</SelectOption>}
        {!isLoading && filteredOptions.length === 0 && (
          <SelectOption isDisabled>
            {filterValue ? `No results match "${filterValue}"` : 'No groups available'}
          </SelectOption>
        )}
        {!isLoading &&
          filteredOptions.map((group) => (
            <SelectOption
              key={group.name}
              value={group.name}
              hasCheckbox
              isSelected={selected.includes(group.name)}
              description={group.description ?? undefined}
            >
              {group.name}
            </SelectOption>
          ))}
      </SelectList>
    </NxSelect>
  )
}

type UserFormFieldsProps = {
  control: Control<UserFormData>
  isEdit: boolean
  isBuiltinUser?: boolean
  isBuiltinSelf?: boolean
  isFederatedUser?: boolean
}

function GroupField({ control }: Readonly<{ control: Control<UserFormData> }>) {
  const { groups, isLoading: isLoadingGroups } = useAllGroups()
  const groupOptions = useMemo(
    () => excludeAuthenticatedGroup(groups).map((g) => ({ name: g.name, description: g.description ?? null })),
    [groups]
  )
  return (
    <Controller
      name="group_names"
      control={control}
      render={({ field }) => (
        <FormGroup label="Groups" fieldId="user-groups-select" labelHelp={userHelp.groups}>
          <GroupMultiSelect
            selected={field.value ?? []}
            onChange={field.onChange}
            isLoading={isLoadingGroups}
            groupOptions={groupOptions}
          />
          <FormHelperText>
            <HelperText>
              <HelperTextItem>{GROUPS_AUTHENTICATED_HINT}</HelperTextItem>
            </HelperText>
          </FormHelperText>
        </FormGroup>
      )}
    />
  )
}

type PasswordFieldInputProps = {
  field: ControllerRenderProps<UserFormData, 'password'>
  fieldState: ControllerFieldState
  isEdit: boolean
  isDisabled: boolean
}

function PasswordFieldInput({ field, fieldState, isEdit, isDisabled }: Readonly<PasswordFieldInputProps>) {
  const [isPasswordVisible, setIsPasswordVisible] = useState(false)
  const validated = fieldState.error ? 'error' : 'default'
  const placeholder = isEdit ? 'Leave blank to keep current password' : 'Enter password'

  return (
    <>
      <InputGroup>
        <InputGroupItem isFill>
          <TextInput
            id="user-password"
            aria-label="Password"
            placeholder={placeholder}
            type={isPasswordVisible ? 'text' : 'password'}
            autoComplete="new-password"
            validated={validated}
            isDisabled={isDisabled}
            value={field.value ?? ''}
            onChange={field.onChange}
            onBlur={field.onBlur}
            name={field.name}
          />
        </InputGroupItem>
        <InputGroupItem>
          <Button
            variant="control"
            isDisabled={isDisabled}
            onClick={() => setIsPasswordVisible((visible) => !visible)}
            aria-label={isPasswordVisible ? 'Hide password' : 'Show password'}
          >
            {isPasswordVisible ? <RhUiViewOffIcon /> : <RhUiViewIcon />}
          </Button>
        </InputGroupItem>
      </InputGroup>
      {!fieldState.error && (
        <FormHelperText>
          <HelperText>
            <HelperTextItem>{PASSWORD_MIN_LENGTH_MESSAGE}</HelperTextItem>
            <HelperTextItem>{PASSWORD_CHARACTER_CLASSES_MESSAGE}</HelperTextItem>
          </HelperText>
        </FormHelperText>
      )}
      {fieldState.error && (
        <FormHelperText>
          <HelperText>
            <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
              {fieldState.error.message}
            </HelperTextItem>
          </HelperText>
        </FormHelperText>
      )}
    </>
  )
}

export function UserFormFields({
  control,
  isEdit,
  isBuiltinUser = false,
  isBuiltinSelf = false,
  isFederatedUser,
}: Readonly<UserFormFieldsProps>) {
  const federatedUser = Boolean(isFederatedUser)
  const emailLabelHelp = isEdit && federatedUser ? userHelp.emailFederatedEdit : userHelp.email

  return (
    <>
      <ControlledTextField
        name="username"
        control={control}
        label="Username"
        fieldId="user-username"
        placeholder="Enter username"
        isRequired
        isDisabled={isBuiltinUser}
        autoComplete="off"
        labelHelp={userHelp.username}
      />
      <ControlledTextField
        name="first_name"
        control={control}
        label="First Name"
        fieldId="user-first-name"
        placeholder="Enter first name"
        isDisabled={isBuiltinUser}
      />
      <ControlledTextField
        name="last_name"
        control={control}
        label="Last Name"
        fieldId="user-last-name"
        placeholder="Enter last name"
        isDisabled={isBuiltinUser}
      />
      <ControlledTextField
        name="email"
        control={control}
        label="Email"
        fieldId="user-email"
        placeholder="Enter email address"
        isDisabled={isBuiltinUser}
        labelHelp={emailLabelHelp}
      />
      {!federatedUser && (
        <Controller
          name="password"
          control={control}
          render={({ field, fieldState }) => (
            <FormGroup label="Password" fieldId="user-password" isRequired={!isEdit}>
              <PasswordFieldInput
                field={field}
                fieldState={fieldState}
                isEdit={isEdit}
                isDisabled={isBuiltinUser && !isBuiltinSelf}
              />
            </FormGroup>
          )}
        />
      )}
      {!isEdit && <GroupField control={control} />}
      {!isEdit && (
        <Controller
          name="is_enabled"
          control={control}
          render={({ field }) => (
            <FormGroup label="Status" fieldId="user-is-enabled" labelHelp={userHelp.status}>
              <Switch
                id="user-is-enabled"
                aria-label="Enabled"
                label={field.value ? 'Enabled' : 'Disabled'}
                isChecked={field.value}
                onChange={(_event, checked) => field.onChange(checked)}
              />
            </FormGroup>
          )}
        />
      )}
    </>
  )
}
