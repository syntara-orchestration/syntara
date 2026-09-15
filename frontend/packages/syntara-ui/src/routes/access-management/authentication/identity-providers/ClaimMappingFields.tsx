import {
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  MenuToggle,
  SelectList,
  SelectOption,
  TextInput,
  TextInputGroup,
  TextInputGroupMain,
} from '@patternfly/react-core'
import { RhUiErrorIcon } from '@patternfly/react-icons'
import type { ReactElement, Ref } from 'react'
import { Controller, type Control, type ControllerFieldState, type ControllerRenderProps } from 'react-hook-form'

import { SynSelect } from '../../../../components/SynSelect'

import { type IdentityProviderFormData } from './identityProviderFormSchema'
import { idpHelp } from './idpFieldHelp'
import { type ClaimMappingFieldTypeahead, useClaimMappingFieldTypeahead } from './useClaimMappingFieldTypeahead'

const CUSTOM_OPTION = '__custom__'

export type ClaimMappingFieldsProps = {
  control: Control<IdentityProviderFormData>
  claimsSupported?: string[] | null
  claimAliases?: Record<string, string[]> | null
  isReadOnly?: boolean
}

function buildOptions(
  syntaraField: string,
  claimsSupported: string[] | null | undefined,
  claimAliases: Record<string, string[]> | null | undefined
): string[] | null {
  if (!claimsSupported) return null

  const aliases = claimAliases?.[syntaraField] ?? []
  const aliasSet = new Set(aliases)
  const matched = claimsSupported.filter((c) => aliasSet.has(c))
  const rest = claimsSupported.filter((c) => !aliasSet.has(c))
  return [...matched, ...rest]
}

type ClaimMappingFieldName = `claimMapping.${keyof IdentityProviderFormData['claimMapping']}`

type ClaimSelectDeps = Readonly<{
  onFieldChange: ControllerRenderProps<IdentityProviderFormData, ClaimMappingFieldName>['onChange']
  setUseCustom: (value: boolean) => void
  setIsOpen: (value: boolean) => void
  setFilterValue: (value: string) => void
}>

function claimMappingOnSelect(deps: ClaimSelectDeps, _event: unknown, value: unknown): void {
  const val = String(value)
  if (val === CUSTOM_OPTION) {
    deps.setUseCustom(true)
    deps.setIsOpen(false)
    deps.setFilterValue('')
    return
  }
  deps.onFieldChange(val || null)
  deps.setIsOpen(false)
  deps.setFilterValue('')
}

function claimMappingOnOpenChange(setFilterValue: (value: string) => void, open: boolean): void {
  if (!open) setFilterValue('')
}

function claimMappingHandleOpenChange(
  setIsOpen: (value: boolean) => void,
  setFilterValue: (value: string) => void,
  open: boolean
): void {
  setIsOpen(open)
  claimMappingOnOpenChange(setFilterValue, open)
}

function claimMappingTypeaheadChange(
  setFilterValue: (value: string) => void,
  setIsOpen: (value: boolean) => void,
  isOpen: boolean,
  _event: unknown,
  val: string
): void {
  setFilterValue(val)
  if (!isOpen) setIsOpen(true)
}

function claimMappingTypeaheadClick(setIsOpen: (value: boolean) => void, isOpen: boolean): void {
  if (!isOpen) setIsOpen(true)
}

function toggleClaimMenuExpanded(setIsOpen: ClaimMappingFieldTypeahead['setIsOpen']): void {
  setIsOpen((prev) => !prev)
}

type ClaimMappingTypeaheadToggleProps = Readonly<{
  toggleRef: Ref<HTMLButtonElement>
  typeahead: Pick<ClaimMappingFieldTypeahead, 'isOpen' | 'setIsOpen' | 'filterValue' | 'setFilterValue' | 'inputRef'>
  currentValue: string
  hint: string
  hasError: boolean
}>

function ClaimMappingTypeaheadToggle({
  toggleRef,
  typeahead,
  currentValue,
  hint,
  hasError,
}: ClaimMappingTypeaheadToggleProps) {
  const { isOpen, setIsOpen, filterValue, setFilterValue, inputRef } = typeahead

  function handleMenuToggleClick(): void {
    toggleClaimMenuExpanded(setIsOpen)
  }

  function handleMainChange(event: unknown, val: string): void {
    claimMappingTypeaheadChange(setFilterValue, setIsOpen, isOpen, event, val)
  }

  function handleMainClick(): void {
    claimMappingTypeaheadClick(setIsOpen, isOpen)
  }

  return (
    <MenuToggle
      ref={toggleRef}
      variant="typeahead"
      onClick={handleMenuToggleClick}
      isExpanded={isOpen}
      isFullWidth
      status={hasError ? 'danger' : undefined}
    >
      <TextInputGroup isPlain>
        <TextInputGroupMain
          value={isOpen ? filterValue : currentValue}
          onChange={handleMainChange}
          onClick={handleMainClick}
          placeholder={hint}
          autoComplete="off"
          innerRef={inputRef}
        />
      </TextInputGroup>
    </MenuToggle>
  )
}

type ClaimMappingSelectOptionsProps = Readonly<{
  isRequired: boolean
  currentValue: string
  filteredOptions: string[]
  filterValue: string
}>

function ClaimMappingSelectOptions({
  isRequired,
  currentValue,
  filteredOptions,
  filterValue,
}: ClaimMappingSelectOptionsProps) {
  const showEmptyMatch = filteredOptions.length === 0 && Boolean(filterValue)

  return (
    <>
      {!isRequired && (
        <SelectOption value="" isSelected={!currentValue}>
          None
        </SelectOption>
      )}
      {showEmptyMatch ? (
        <SelectOption isDisabled>No claims match &quot;{filterValue}&quot;</SelectOption>
      ) : (
        filteredOptions.map((opt) => (
          <SelectOption key={opt} value={opt} isSelected={currentValue === opt}>
            {opt}
          </SelectOption>
        ))
      )}
      <SelectOption value={CUSTOM_OPTION}>Custom...</SelectOption>
    </>
  )
}

type ClaimFieldProps = {
  control: Control<IdentityProviderFormData>
  name: ClaimMappingFieldName
  label: string
  hint: string
  options: string[] | null
  isRequired?: boolean
  isReadOnly?: boolean
  labelHelp?: ReactElement
}

type ClaimFieldMeta = Readonly<{
  name: ClaimMappingFieldName
  label: string
  hint: string
  options: string[] | null
  isRequired?: boolean
  isReadOnly?: boolean
  labelHelp?: ReactElement
}>

type ClaimFieldBodyProps = Readonly<{
  meta: ClaimFieldMeta
  controller: {
    field: ControllerRenderProps<IdentityProviderFormData, ClaimMappingFieldName>
    fieldState: ControllerFieldState
  }
  typeahead: ClaimMappingFieldTypeahead
}>

function ClaimFieldBody({ meta, controller, typeahead }: ClaimFieldBodyProps) {
  const { name, label, hint, options, isRequired = true, isReadOnly, labelHelp } = meta
  const { field, fieldState } = controller
  const { useCustom, setUseCustom, isOpen, setIsOpen, filterValue, setFilterValue, filteredOptions } = typeahead

  const showDropdown = options && !useCustom && !isReadOnly
  const currentValue = field.value ?? ''
  const helperMessage = isReadOnly
    ? 'Pre-configured by provider template. Select Custom to modify.'
    : (fieldState.error?.message ?? hint)

  const selectDeps: ClaimSelectDeps = {
    onFieldChange: field.onChange,
    setUseCustom,
    setIsOpen,
    setFilterValue,
  }

  return (
    <FormGroup label={label} fieldId={name} isRequired={isRequired} labelHelp={labelHelp}>
      {showDropdown ? (
        <SynSelect
          id={name}
          isOpen={isOpen}
          selected={currentValue || undefined}
          onSelect={(event, value) => claimMappingOnSelect(selectDeps, event, value)}
          onOpenChange={(open) => claimMappingHandleOpenChange(setIsOpen, setFilterValue, open)}
          toggle={(toggleRef) => (
            <ClaimMappingTypeaheadToggle
              toggleRef={toggleRef}
              typeahead={typeahead}
              currentValue={currentValue}
              hint={hint}
              hasError={Boolean(fieldState.error)}
            />
          )}
        >
          <SelectList style={{ maxHeight: '200px', overflow: 'auto' }}>
            <ClaimMappingSelectOptions
              isRequired={isRequired}
              currentValue={currentValue}
              filteredOptions={filteredOptions}
              filterValue={filterValue}
            />
          </SelectList>
        </SynSelect>
      ) : (
        <TextInput
          id={name}
          placeholder={hint}
          validated={fieldState.error ? 'error' : 'default'}
          value={currentValue}
          onChange={(_event, value) => field.onChange(value)}
          onBlur={field.onBlur}
          name={field.name}
          isDisabled={isReadOnly}
        />
      )}
      <FormHelperText>
        <HelperText>
          <HelperTextItem
            variant={fieldState.error ? 'error' : 'default'}
            icon={fieldState.error ? <RhUiErrorIcon /> : undefined}
          >
            {helperMessage}
          </HelperTextItem>
        </HelperText>
      </FormHelperText>
    </FormGroup>
  )
}

/** One claim row (typeahead or text). Local UI state is owned by `useClaimMappingFieldTypeahead`. */
function ClaimField({
  control,
  name,
  label,
  hint,
  options,
  isRequired = true,
  isReadOnly,
  labelHelp,
}: Readonly<ClaimFieldProps>) {
  const typeahead = useClaimMappingFieldTypeahead(options)

  return (
    <Controller
      name={name}
      control={control}
      render={({ field, fieldState }) => (
        <ClaimFieldBody
          meta={{ name, label, hint, options, isRequired, isReadOnly, labelHelp }}
          controller={{ field, fieldState }}
          typeahead={typeahead}
        />
      )}
    />
  )
}

export function UserClaimMappingFields({
  control,
  claimsSupported,
  claimAliases,
  isReadOnly,
}: Readonly<ClaimMappingFieldsProps>) {
  return (
    <>
      <ClaimField
        control={control}
        name="claimMapping.subject"
        label="Subject claim"
        hint="IdP claim for the unique user identifier (e.g. sub)"
        options={buildOptions('sub', claimsSupported, claimAliases)}
        isReadOnly={isReadOnly}
        labelHelp={idpHelp.subjectClaim}
      />
      <ClaimField
        control={control}
        name="claimMapping.email"
        label="Email claim"
        hint="IdP claim for the user email (e.g. email, mail, upn)"
        options={buildOptions('email', claimsSupported, claimAliases)}
        isReadOnly={isReadOnly}
        labelHelp={idpHelp.emailClaim}
      />
      <ClaimField
        control={control}
        name="claimMapping.username"
        label="Username claim"
        hint="IdP claim for the username (e.g. preferred_username)"
        options={buildOptions('username', claimsSupported, claimAliases)}
        isReadOnly={isReadOnly}
      />
      <ClaimField
        control={control}
        name="claimMapping.firstName"
        label="First name claim"
        hint="IdP claim for the first name (e.g. given_name, givenName)"
        options={buildOptions('first_name', claimsSupported, claimAliases)}
        isReadOnly={isReadOnly}
      />
      <ClaimField
        control={control}
        name="claimMapping.lastName"
        label="Last name claim"
        hint="IdP claim for the last name (e.g. family_name, familyName)"
        options={buildOptions('last_name', claimsSupported, claimAliases)}
        isReadOnly={isReadOnly}
      />
    </>
  )
}
