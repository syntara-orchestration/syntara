import { Button, Flex, FlexItem, FormGroup, TextInput } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import type { ReactElement } from 'react'

import { generateUUID } from '../../../utils/generateUUID'

import styles from './KeyValueFields.module.css'

type KeyValueEntry = {
  id: string
  key: string
  value: string
}

type KeyValueFieldsProps = {
  entries: KeyValueEntry[]
  onChange: (entries: KeyValueEntry[]) => void
  isDisabled?: boolean
  keyPlaceholder?: string
  valuePlaceholder?: string
  addButtonLabel?: string
  /** Optional PatternFly FormGroup labelHelp (e.g. FieldHelpPopover). */
  labelHelp?: ReactElement
}

function addEntry(entries: KeyValueEntry[]): KeyValueEntry[] {
  return [...entries, { id: generateUUID(), key: '', value: '' }]
}

function removeEntry(entries: KeyValueEntry[], index: number): KeyValueEntry[] {
  const next = entries.slice()
  next.splice(index, 1)
  return next
}

function updateKey(entries: KeyValueEntry[], index: number, newKey: string): KeyValueEntry[] {
  const next = entries.slice()
  next[index] = { ...next[index], key: newKey }
  return next
}

function updateValue(entries: KeyValueEntry[], index: number, newValue: string): KeyValueEntry[] {
  const next = entries.slice()
  next[index] = { ...next[index], value: newValue }
  return next
}

function KeyValueFields({
  entries,
  onChange,
  isDisabled,
  keyPlaceholder,
  valuePlaceholder,
  addButtonLabel,
  labelHelp,
}: Readonly<KeyValueFieldsProps>) {
  const resolvedKeyPlaceholder = keyPlaceholder ?? 'Header name'
  const resolvedValuePlaceholder = valuePlaceholder ?? 'Header value'
  const resolvedAddButtonLabel = addButtonLabel ?? 'Add header'

  return (
    <FormGroup label="Headers" labelHelp={labelHelp} fieldId="action-headers">
      {entries.map((entry, index) => (
        <Flex
          key={entry.id}
          className={styles.entryRow}
          alignItems={{ default: 'alignItemsFlexStart' }}
          gap={{ default: 'gapSm' }}
        >
          <FlexItem grow={{ default: 'grow' }}>
            <TextInput
              aria-label={`Header name ${String(index + 1)}`}
              value={entry.key}
              onChange={(_event, val) => onChange(updateKey(entries, index, val))}
              placeholder={resolvedKeyPlaceholder}
              isDisabled={isDisabled}
            />
          </FlexItem>
          <FlexItem grow={{ default: 'grow' }}>
            <TextInput
              aria-label={`Header value ${String(index + 1)}`}
              value={entry.value}
              onChange={(_event, val) => onChange(updateValue(entries, index, val))}
              placeholder={resolvedValuePlaceholder}
              isDisabled={isDisabled}
            />
          </FlexItem>
          {!isDisabled && (
            <FlexItem>
              <Button
                variant="plain"
                aria-label={`Remove header ${String(index + 1)}`}
                onClick={() => onChange(removeEntry(entries, index))}
              >
                <RhUiTrashIcon />
              </Button>
            </FlexItem>
          )}
        </Flex>
      ))}
      {!isDisabled && (
        <Button variant="link" icon={<RhUiAddIcon />} onClick={() => onChange(addEntry(entries))}>
          {resolvedAddButtonLabel}
        </Button>
      )}
    </FormGroup>
  )
}

export { KeyValueFields }
export type { KeyValueEntry, KeyValueFieldsProps }
