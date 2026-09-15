import {
  Button,
  Divider,
  Content,
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  TextInput,
  TextInputGroup,
  TextInputGroupMain,
} from '@patternfly/react-core'
import { RhUiAddIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { Td, Tr } from '@patternfly/react-table'
import {
  type Dispatch,
  type Ref,
  type RefObject,
  type SetStateAction,
  useCallback,
  useMemo,
  useRef,
  useState,
} from 'react'
import { Controller, useWatch, type Control } from 'react-hook-form'

import { SynSelect } from '../../../../components/SynSelect'
import { LinkCell } from '../../../../components/table/LinkCell'
import { APP_TITLE } from '../../../../utils/appTitle'
import { getGroupDetailPath } from '../../accessManagementPaths'

import type { GroupMappingEditFormValues } from './groupMappingEditFormSchema'
import type { GroupMappingEntry, MappedGroup } from './groupMappingUtils'
import { idpHelp } from './idpFieldHelp'

const CREATE_GROUP_VALUE = '__create__' as const

/** Column header label + field help for IdP group value (popover title matches field name). */
export function IdpGroupValueColumnLabel() {
  return (
    <>
      IdP group value
      {idpHelp.idpGroupValue}
    </>
  )
}

/**
 * Column header label + field help for the local group column.
 * Visible header may include APP_TITLE; popover title is always "Group".
 */
export function GroupColumnLabel() {
  return (
    <>
      {`${APP_TITLE} group`}
      {idpHelp.group}
    </>
  )
}

export type IdpGroupValueInputProps = {
  index: number
  value: string
  onChange: (value: string) => void
  isReadOnly?: boolean
  /** When set, associates with a surrounding FormGroup; aria-label is omitted */
  inputId?: string
  errorMessage?: string
}

export function IdpGroupValueInput({
  index,
  value,
  onChange,
  isReadOnly,
  inputId,
  errorMessage,
}: Readonly<IdpGroupValueInputProps>) {
  return (
    <TextInput
      id={inputId}
      aria-label={inputId ? undefined : `IdP group value ${index + 1}`}
      placeholder="IdP group value"
      value={value}
      onChange={(_event, nextValue) => onChange(nextValue)}
      isDisabled={isReadOnly}
      validated={errorMessage ? 'error' : 'default'}
    />
  )
}

export type MappedGroupMappingSelectProps = {
  entry: GroupMappingEntry
  mappedGroups: MappedGroup[]
  isReadOnly?: boolean
  showValidation?: boolean
  errorMessage?: string
  onChange: (entry: GroupMappingEntry) => void
  onCreateGroup: () => void
  toggleId?: string
}

type MappedGroupMappingSelectToggleProps = {
  toggleRef: Ref<MenuToggleElement>
  toggleId?: string
  isOpen: boolean
  isReadOnly?: boolean
  missingGroup: boolean
  filterValue: string
  selectedDisplayName: string
  setFilterValue: Dispatch<SetStateAction<string>>
  setIsOpen: Dispatch<SetStateAction<boolean>>
  inputRef: RefObject<HTMLInputElement | null>
}

function MappedGroupMappingSelectToggle({
  toggleRef,
  toggleId,
  isOpen,
  isReadOnly,
  missingGroup,
  filterValue,
  selectedDisplayName,
  setFilterValue,
  setIsOpen,
  inputRef,
}: Readonly<MappedGroupMappingSelectToggleProps>) {
  return (
    <div style={{ display: 'contents' }} data-group-mapping-invalid={missingGroup ? 'true' : 'false'}>
      <MenuToggle
        ref={toggleRef}
        id={toggleId}
        variant="typeahead"
        onClick={() => {
          if (isReadOnly !== true) setIsOpen((prev) => !prev)
        }}
        isExpanded={isOpen}
        isFullWidth
        isDisabled={isReadOnly}
        status={missingGroup ? 'danger' : undefined}
      >
        <TextInputGroup isPlain isDisabled={isReadOnly}>
          <TextInputGroupMain
            value={isOpen ? filterValue : selectedDisplayName}
            onChange={(_e, val) => {
              setFilterValue(val)
              if (isOpen === false) setIsOpen(true)
            }}
            onClick={() => {
              if (isOpen === false) setIsOpen(true)
            }}
            placeholder="Select a group..."
            autoComplete="off"
            innerRef={inputRef}
          />
        </TextInputGroup>
      </MenuToggle>
    </div>
  )
}

export function MappedGroupMappingSelect({
  entry,
  mappedGroups,
  isReadOnly,
  showValidation,
  errorMessage,
  onChange,
  onCreateGroup,
  toggleId,
}: Readonly<MappedGroupMappingSelectProps>) {
  const [isOpen, setIsOpen] = useState(false)
  const [filterValue, setFilterValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const selectedGroup = mappedGroups.find((g) => g.id === entry.mappedGroupId)
  const missingGroup =
    Boolean(errorMessage) || (showValidation === true && Boolean(entry.idpGroupValue) && entry.mappedGroupId === '')

  const filteredGroups = useMemo(() => {
    if (filterValue === '') return mappedGroups
    const term = filterValue.toLowerCase()
    return mappedGroups.filter((g) => g.name?.toLowerCase().includes(term))
  }, [mappedGroups, filterValue])

  const selectedDisplayName = selectedGroup?.name ?? ''

  const renderToggle = useCallback(
    (toggleRef: Ref<MenuToggleElement>) => (
      <MappedGroupMappingSelectToggle
        toggleRef={toggleRef}
        toggleId={toggleId}
        isOpen={isOpen}
        isReadOnly={isReadOnly}
        missingGroup={missingGroup}
        filterValue={filterValue}
        selectedDisplayName={selectedDisplayName}
        setFilterValue={setFilterValue}
        setIsOpen={setIsOpen}
        inputRef={inputRef}
      />
    ),
    [toggleId, isOpen, isReadOnly, missingGroup, filterValue, selectedDisplayName, inputRef]
  )

  return (
    <SynSelect
      isOpen={isOpen}
      selected={entry.mappedGroupId || undefined}
      onSelect={(_event, value) => {
        const val = String(value)
        if (val === CREATE_GROUP_VALUE) {
          onCreateGroup()
          setIsOpen(false)
          setFilterValue('')
          return
        }
        onChange({ ...entry, mappedGroupId: val })
        setIsOpen(false)
        setFilterValue('')
      }}
      onOpenChange={(open) => {
        setIsOpen(open)
        if (open === false) setFilterValue('')
      }}
      toggle={renderToggle}
    >
      <SelectList>
        {filteredGroups.length === 0 && filterValue ? (
          <SelectOption isDisabled>No groups match &quot;{filterValue}&quot;</SelectOption>
        ) : (
          filteredGroups.map((g) => (
            <SelectOption
              key={g.id}
              value={g.id}
              description={g.description ?? undefined}
              isSelected={entry.mappedGroupId === g.id}
            >
              {g.name}
            </SelectOption>
          ))
        )}
      </SelectList>
      <Divider />
      <SelectList>
        <SelectOption value={CREATE_GROUP_VALUE} icon={<RhUiAddIcon />}>
          Create new group
        </SelectOption>
      </SelectList>
    </SynSelect>
  )
}

type MappingRowProps = {
  entry: GroupMappingEntry
  index: number
  mappedGroups: MappedGroup[]
  isReadOnly?: boolean
  /** When true with isReadOnly, show per-row delete (list view with actions column) */
  readOnlyAllowRemove?: boolean
  /** When true with isReadOnly, render data cells as text (list view) instead of disabled inputs */
  readOnlyPlainCells?: boolean
  showValidation?: boolean
  idpErrorMessage?: string
  groupErrorMessage?: string
  onIdpGroupValueChange?: (index: number, value: string) => void
  onMappedGroupIdChange?: (index: number, mappedGroupId: string) => void
  onRemove: (index: number) => void
  onCreateGroup: (index: number) => void
}

export function MappingRow({
  entry,
  index,
  mappedGroups,
  isReadOnly,
  readOnlyAllowRemove,
  readOnlyPlainCells,
  showValidation,
  idpErrorMessage,
  groupErrorMessage,
  onIdpGroupValueChange,
  onMappedGroupIdChange,
  onRemove,
  onCreateGroup,
}: Readonly<MappingRowProps>) {
  const showActionColumn = Boolean(isReadOnly !== true || readOnlyAllowRemove)

  if (isReadOnly === true && readOnlyPlainCells === true) {
    const groupName = mappedGroups.find((g) => g.id === entry.mappedGroupId)?.name ?? ''
    const idpDisplay = entry.idpGroupValue === '' ? '—' : entry.idpGroupValue
    const groupDisplay = groupName === '' ? '—' : groupName
    return (
      <Tr>
        <Td dataLabel="IdP Group Value">
          <Content>{idpDisplay}</Content>
        </Td>
        <Td dataLabel={`${APP_TITLE} Group`}>
          {entry.mappedGroupId !== '' && groupName !== '' ? (
            <LinkCell href={getGroupDetailPath(entry.mappedGroupId)}>{groupDisplay}</LinkCell>
          ) : (
            <Content>{groupDisplay}</Content>
          )}
        </Td>
        {showActionColumn && (
          <Td isActionCell>
            <Button
              variant="plain"
              aria-label={`Remove mapping ${index + 1}`}
              onClick={() => onRemove(index)}
              icon={<RhUiTrashIcon />}
            />
          </Td>
        )}
      </Tr>
    )
  }

  return (
    <Tr>
      <Td dataLabel="IdP Group Value">
        <IdpGroupValueInput
          index={index}
          value={entry.idpGroupValue}
          onChange={(value) => onIdpGroupValueChange?.(index, value)}
          isReadOnly={isReadOnly}
          errorMessage={idpErrorMessage}
        />
      </Td>
      <Td dataLabel={`${APP_TITLE} Group`}>
        <MappedGroupMappingSelect
          entry={entry}
          mappedGroups={mappedGroups}
          isReadOnly={isReadOnly}
          showValidation={showValidation}
          errorMessage={groupErrorMessage}
          onChange={(updated) => onMappedGroupIdChange?.(index, updated.mappedGroupId)}
          onCreateGroup={() => onCreateGroup(index)}
        />
      </Td>
      {showActionColumn && (
        <Td isActionCell>
          <Button
            variant="plain"
            aria-label={`Remove mapping ${index + 1}`}
            onClick={() => onRemove(index)}
            icon={<RhUiTrashIcon />}
          />
        </Td>
      )}
    </Tr>
  )
}

export type EditMappingRowProps = {
  index: number
  rowId: string
  control: Control<GroupMappingEditFormValues>
  mappedGroups: MappedGroup[]
  onRemove: (index: number) => void
  onCreateGroup: (index: number) => void
}

export function EditMappingRow({
  index,
  rowId,
  control,
  mappedGroups,
  onRemove,
  onCreateGroup,
}: Readonly<EditMappingRowProps>) {
  const idpGroupValue = useWatch({ control, name: `entries.${index}.idpGroupValue` }) ?? ''

  return (
    <Tr>
      <Td dataLabel="IdP Group Value">
        <Controller
          name={`entries.${index}.idpGroupValue`}
          control={control}
          render={({ field, fieldState }) => (
            <IdpGroupValueInput
              index={index}
              value={field.value}
              onChange={field.onChange}
              errorMessage={fieldState.error?.message}
            />
          )}
        />
      </Td>
      <Td dataLabel={`${APP_TITLE} Group`}>
        <Controller
          name={`entries.${index}.mappedGroupId`}
          control={control}
          render={({ field, fieldState }) => (
            <MappedGroupMappingSelect
              entry={{ key: rowId, idpGroupValue, mappedGroupId: field.value }}
              mappedGroups={mappedGroups}
              errorMessage={fieldState.error?.message}
              onChange={(updated) => field.onChange(updated.mappedGroupId)}
              onCreateGroup={() => onCreateGroup(index)}
            />
          )}
        />
      </Td>
      <Td isActionCell>
        <Button
          variant="plain"
          aria-label={`Remove mapping ${index + 1}`}
          onClick={() => onRemove(index)}
          icon={<RhUiTrashIcon />}
        />
      </Td>
    </Tr>
  )
}
