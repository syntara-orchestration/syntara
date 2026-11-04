import {
  Button,
  Divider,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  MenuToggle,
  type MenuToggleElement,
  SelectGroup,
  SelectList,
  SelectOption,
  Spinner,
} from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'
import React, { type ReactElement, useCallback, useMemo, useState } from 'react'

import { credentialsClient } from '../../../client'
import { FormFieldError } from '../../../components/FormFieldError'
import { SynSelect } from '../../../components/SynSelect'
import { detachPromise } from '../../../utils/detachPromise'
import type { Credential, CredentialType } from '../../configuration/credentials/credentialConstants'
import { CredentialFormModal } from '../../configuration/credentials/form/CredentialFormModal'

import { resolveFormGroupLabelHelp } from './resolveFormGroupLabelHelp'
import { TypeaheadMenuToggle } from './TypeaheadMenuToggle'
import { useAllCredentials } from './useAllCredentials'

export type CredentialSelectorProps = {
  /** Currently selected credential ID */
  value?: string
  /** Callback when selection changes */
  onChange: (credentialId: string | undefined) => void
  /** Credential type names to filter by (only show compatible credentials) */
  compatibleTypeNames?: string[]
  /** Label for the form group */
  label?: string
  /** Field ID for form group */
  fieldId?: string
  /** Whether the field is disabled */
  isDisabled?: boolean
  /** Whether to show "Create new credential" option */
  allowCreate?: boolean
  /** Credential type ID to pre-select when creating (locks the type dropdown) */
  preSelectedTypeId?: string
  /** Placeholder text shown when no credential is selected */
  placeholder?: string
  /** Help text shown in a popover next to the label */
  helpText?: React.ReactNode
  /** Pre-built label help (takes precedence over helpText) */
  labelHelp?: ReactElement
  /** Filter credentials to this project */
  projectId?: string
  /** Whether the credential field is required */
  isRequired?: boolean
  /** Validation error message — when set, shows danger styling and error text */
  errorMessage?: string
  isSearchable?: boolean
}

const NO_CREDENTIAL_VALUE = '__none__'
const CREATE_NEW_VALUE = '__create_new__'

function credentialMessageIds(fieldId: string, errorMessage: string | undefined, isReadOnlyCredential: boolean) {
  const errorId = `${fieldId}-error`
  const warningId = `${fieldId}-readonly-warning`
  const describedBy =
    [errorMessage ? errorId : '', isReadOnlyCredential ? warningId : ''].filter(Boolean).join(' ') || undefined
  return { errorId, warningId, describedBy }
}

function credentialDescription(credential: { enabled?: boolean; description?: string | null }) {
  if (credential.enabled) return credential.description ?? undefined
  return `${credential.description ?? ''} (disabled)`.trim()
}

function buildTypeGroups(credentials: Credential[], credentialTypes: CredentialType[]): TypeGroup[] {
  if (credentialTypes.length === 0) {
    return credentials.length > 0 ? [{ typeId: '__ungrouped__', typeName: '', credentials }] : []
  }
  const typeMap = new Map<string, CredentialType>()
  for (const ct of credentialTypes) {
    if (ct.id) typeMap.set(ct.id, ct)
  }
  const groupMap = new Map<string, TypeGroup>()
  for (const cred of credentials) {
    const typeId = cred.credential_type_id
    if (!groupMap.has(typeId)) {
      const ct = typeMap.get(typeId)
      groupMap.set(typeId, { typeId, typeName: ct?.name ?? 'Unknown', credentials: [] })
    }
    groupMap.get(typeId)?.credentials.push(cred)
  }
  return Array.from(groupMap.values())
}

type TypeGroup = {
  typeId: string
  typeName: string
  credentials: Credential[]
}

function CredentialOption({ credential, value }: Readonly<{ credential: Credential; value?: string }>) {
  return (
    <SelectOption
      key={credential.id}
      value={credential.id}
      isSelected={credential.id === value}
      isDisabled={!credential.enabled}
      description={credentialDescription(credential)}
    >
      {credential.name}
    </SelectOption>
  )
}

type MenuToggleProps = {
  toggleRef: React.Ref<MenuToggleElement>
  isOpen: boolean
  isDisabled: boolean
  isPending: boolean
  describedBy?: string
  isReadOnlyCredential: boolean
  hasDanger: boolean
  label: string
  toggleLabel: string
  setIsOpen: React.Dispatch<React.SetStateAction<boolean>>
}

function CredentialMenuToggle({
  toggleRef,
  isOpen,
  isDisabled,
  isPending,
  describedBy,
  hasDanger,
  label,
  toggleLabel,
  setIsOpen,
}: Readonly<MenuToggleProps>) {
  return (
    <MenuToggle
      ref={toggleRef}
      onClick={() => setIsOpen((prev) => !prev)}
      isExpanded={isOpen}
      isDisabled={isDisabled || isPending}
      aria-describedby={describedBy}
      aria-invalid={hasDanger || undefined}
      isFullWidth
      status={hasDanger ? 'danger' : undefined}
      aria-label={label}
    >
      {isPending ? (
        <>
          <Spinner size="sm" aria-label="Loading credentials" /> {toggleLabel}
        </>
      ) : (
        toggleLabel
      )}
    </MenuToggle>
  )
}

function NoCredentialOption({ isRequired, value }: { isRequired: boolean; value?: string }) {
  if (isRequired) return null
  return (
    <>
      <SelectOption value={NO_CREDENTIAL_VALUE} isSelected={!value}>
        No credential
      </SelectOption>
      <Divider />
    </>
  )
}

function CredentialOptions({
  label,
  isRequired,
  value,
  allowCreate,
  typeGroups,
  hasGroups,
  isPending,
  isError,
  filterText,
  credentialCount,
}: Readonly<{
  label: string
  isRequired: boolean
  value?: string
  allowCreate: boolean
  typeGroups: TypeGroup[]
  hasGroups: boolean
  isPending: boolean
  isError: boolean
  filterText: string
  credentialCount: number
}>) {
  return (
    <SelectList aria-label={`${label} options`}>
      <NoCredentialOption isRequired={isRequired} value={value} />
      {allowCreate && (
        <>
          <SelectOption value={CREATE_NEW_VALUE} icon={<RhUiAddIcon />}>
            Create new credential
          </SelectOption>
          <Divider />
        </>
      )}
      {hasGroups
        ? typeGroups.map((group) => (
            <SelectGroup key={group.typeId} label={group.typeName.toUpperCase()}>
              {group.credentials.map((credential) => (
                <CredentialOption key={credential.id} credential={credential} value={value} />
              ))}
            </SelectGroup>
          ))
        : typeGroups
            .flatMap((group) => group.credentials)
            .map((credential) => <CredentialOption key={credential.id} credential={credential} value={value} />)}
      {filterText && !typeGroups.length && !isPending && (
        <SelectOption isDisabled value="__no_matches__">
          No matching credentials
        </SelectOption>
      )}
      {credentialCount === 0 && !isPending && !allowCreate && (
        <SelectOption isDisabled value="__empty__">
          {isError ? 'Failed to load credentials' : 'No credentials available'}
        </SelectOption>
      )}
    </SelectList>
  )
}

function ReadOnlyCredentialWarning({ show, id }: { show: boolean; id: string }) {
  if (!show) return null
  return (
    <FormHelperText>
      <HelperText>
        <HelperTextItem id={id} variant="warning">
          You do not have permission to use this credential. Contact a project administrator for access.
        </HelperTextItem>
      </HelperText>
    </FormHelperText>
  )
}

function useReadOnlyCredential(value: string | undefined, usableCredentials: Credential[], isListPending: boolean) {
  const selectedCredential = useMemo(() => usableCredentials.find((c) => c.id === value), [usableCredentials, value])

  const singleCredEnabled = !!value && !selectedCredential && !isListPending
  const { data: readOnlyCredData, isFetching: isSingleCredFetching } = credentialsClient.useQuery(
    'get',
    '/credentials/{credential_id}',
    { params: { path: { credential_id: value ?? '' } } },
    { enabled: singleCredEnabled }
  )
  const isSingleCredPending = singleCredEnabled && isSingleCredFetching

  const isReadOnly = !!value && !selectedCredential && !isListPending && !!readOnlyCredData
  const readOnlyLabel = isReadOnly ? `${readOnlyCredData.name} (no permission to use)` : undefined

  return { selectedCredential, isReadOnly, readOnlyLabel, isSingleCredPending }
}

/**
 * A PatternFly Select dropdown for choosing a credential.
 * Fetches credentials from the API with optional type filtering.
 * Credentials are grouped by credential type when type data is available.
 */

export function CredentialSelector({
  value,
  onChange,
  compatibleTypeNames,
  label = 'Credential',
  fieldId = 'credential-selector',
  isDisabled = false,
  allowCreate = false,
  preSelectedTypeId,
  placeholder = 'Select a credential...',
  helpText,
  labelHelp,
  projectId,
  isRequired = false,
  errorMessage,
  isSearchable = false,
}: Readonly<CredentialSelectorProps>) {
  const [isOpen, setIsOpen] = useState(false)
  const [filterText, setFilterText] = useState('')
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)

  const {
    credentials: allCredentials,
    isLoading: isCredentialsPending,
    error: credentialsError,
    refetch,
  } = useAllCredentials({ projectId })
  const typesQuery = credentialsClient.useQuery('get', '/credential_types')
  const typesData = typesQuery.data
  const isError = Boolean(credentialsError) || Boolean(compatibleTypeNames && typesQuery.isError)
  const isPending = isCredentialsPending || Boolean(compatibleTypeNames && typesQuery.isPending)

  const credentialTypes: CredentialType[] = useMemo(() => typesData?.resources ?? [], [typesData?.resources])

  // Derive compatible type IDs from type names
  const compatibleTypeIds = useMemo(() => {
    if (!compatibleTypeNames) return null
    return credentialTypes.filter((t) => compatibleTypeNames.includes(t.name)).map((t) => t.id)
  }, [compatibleTypeNames, credentialTypes])

  // Auto-resolve preSelectedTypeId only when exactly one compatible type exists
  const resolvedPreSelectedTypeId = useMemo(() => {
    if (preSelectedTypeId) return preSelectedTypeId
    if (compatibleTypeIds?.length === 1) return compatibleTypeIds[0]
    return undefined
  }, [preSelectedTypeId, compatibleTypeIds])

  // Filter credentials by compatible types (client-side)
  const credentials: Credential[] = useMemo(() => {
    if (!compatibleTypeIds) return allCredentials
    return allCredentials.filter((c) => compatibleTypeIds.includes(c.credential_type_id))
  }, [allCredentials, compatibleTypeIds])

  const typeGroups: TypeGroup[] = useMemo(
    () =>
      buildTypeGroups(
        credentials.filter((item) => item.name.toLowerCase().includes(filterText.toLowerCase())),
        credentialTypes
      ),
    [credentials, credentialTypes, filterText]
  )

  const {
    selectedCredential,
    isReadOnly: isReadOnlyCredential,
    readOnlyLabel,
    isSingleCredPending,
  } = useReadOnlyCredential(value, allCredentials, isPending)

  const toggleLabel = useMemo(() => {
    if (isPending || isSingleCredPending) return 'Loading credentials...'
    if (isError) return 'Error loading credentials'
    return readOnlyLabel ?? selectedCredential?.name ?? placeholder
  }, [isPending, isSingleCredPending, isError, readOnlyLabel, selectedCredential?.name, placeholder])

  const handleSelect = useCallback(
    (_event: React.MouseEvent | undefined, selectedValue: string | number | undefined) => {
      setIsOpen(false)
      setFilterText('')
      if (selectedValue === CREATE_NEW_VALUE) {
        setIsCreateModalOpen(true)
      } else {
        onChange(selectedValue === NO_CREDENTIAL_VALUE ? undefined : String(selectedValue))
      }
    },
    [onChange]
  )

  const handleCreated = useCallback(
    (newCredentialId: string) => {
      detachPromise(refetch())
      onChange(newCredentialId)
    },
    [onChange, refetch]
  )

  const resolvedLabelHelp = resolveFormGroupLabelHelp(label, labelHelp, helpText)

  const { errorId, warningId, describedBy } = credentialMessageIds(fieldId, errorMessage, isReadOnlyCredential)
  const hasGroups = credentialTypes.length > 0
  const hasDanger = [isError, errorMessage].some(Boolean)

  const renderToggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) =>
      isSearchable ? (
        <TypeaheadMenuToggle
          toggleRef={toggleRef}
          displayText={value ? toggleLabel : ''}
          ariaLabel={label}
          fieldId={fieldId}
          isOpen={isOpen}
          isDisabled={isDisabled}
          isPending={isPending || isSingleCredPending}
          hasSelection={Boolean(value)}
          filterText={filterText}
          placeholder={placeholder}
          loadingPlaceholder="Loading credentials..."
          onFilterChange={setFilterText}
          onClear={() => onChange(undefined)}
          onToggle={() => setIsOpen(!isOpen)}
          isInvalid={hasDanger}
          describedBy={describedBy}
        />
      ) : (
        <CredentialMenuToggle
          toggleRef={toggleRef}
          isOpen={isOpen}
          isDisabled={isDisabled}
          isPending={isPending || isSingleCredPending}
          isReadOnlyCredential={isReadOnlyCredential}
          describedBy={describedBy}
          hasDanger={hasDanger}
          label={label}
          toggleLabel={toggleLabel}
          setIsOpen={setIsOpen}
        />
      ),
    [
      isOpen,
      isDisabled,
      isPending,
      isSingleCredPending,
      isReadOnlyCredential,
      hasDanger,
      label,
      toggleLabel,
      isSearchable,
      fieldId,
      value,
      filterText,
      placeholder,
      onChange,
      describedBy,
    ]
  )

  return (
    <FormGroup label={label} labelHelp={resolvedLabelHelp} fieldId={fieldId} isRequired={isRequired}>
      <SynSelect
        id={fieldId}
        isOpen={isOpen}
        selected={value ?? NO_CREDENTIAL_VALUE}
        onSelect={handleSelect}
        onOpenChange={(open) => {
          setIsOpen(open)
          if (!open) setFilterText('')
        }}
        shouldFocusToggleOnSelect
        toggle={renderToggle}
      >
        <CredentialOptions
          label={label}
          isRequired={isRequired}
          value={value}
          allowCreate={allowCreate}
          typeGroups={typeGroups}
          hasGroups={hasGroups}
          isPending={isPending}
          isError={isError}
          filterText={filterText}
          credentialCount={credentials.length}
        />
      </SynSelect>

      <FormFieldError id={errorId} message={errorMessage} />
      <ReadOnlyCredentialWarning id={warningId} show={isReadOnlyCredential} />
      {isError && (
        <Button
          variant="link"
          size="sm"
          onClick={() => {
            detachPromise(refetch())
            if (typesQuery.isError) detachPromise(typesQuery.refetch())
          }}
        >
          Retry loading credentials
        </Button>
      )}
      {allowCreate && (
        <CredentialFormModal
          isOpen={isCreateModalOpen}
          onClose={() => setIsCreateModalOpen(false)}
          preSelectedTypeId={resolvedPreSelectedTypeId}
          onCreated={handleCreated}
          defaultProjectId={projectId}
          compatibleTypeNames={compatibleTypeNames}
        />
      )}
    </FormGroup>
  )
}
