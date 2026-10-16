import { Button, Flex, FlexItem, FormGroup, TextInput } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import type { ReactElement } from 'react'

import { generateUUID } from '../../../utils/generateUUID'

import styles from './KeyValueFields.module.css'

type InputMappingEntry = {
  id: string
  key: string
  value: string
}

type InputMappingFieldsProps = {
  entries: InputMappingEntry[]
  onChange: (entries: InputMappingEntry[]) => void
  isDisabled?: boolean
  /** Optional PatternFly FormGroup labelHelp (e.g. FieldHelpPopover). */
  labelHelp?: ReactElement
}

function addEntry(entries: InputMappingEntry[]): InputMappingEntry[] {
  return [...entries, { id: generateUUID(), key: '', value: '' }]
}

function removeEntry(entries: InputMappingEntry[], index: number): InputMappingEntry[] {
  const next = entries.slice()
  next.splice(index, 1)
  return next
}

function updateKey(entries: InputMappingEntry[], index: number, newKey: string): InputMappingEntry[] {
  const next = entries.slice()
  next[index] = { ...next[index], key: newKey }
  return next
}

function updateValue(entries: InputMappingEntry[], index: number, newValue: string): InputMappingEntry[] {
  const next = entries.slice()
  next[index] = { ...next[index], value: newValue }
  return next
}

/**
 * Input mapping configuration for Sub-workflow step.
 *
 * Maps parent workflow variables to child workflow inputs.
 * Supports static values and Jinja2 expressions (e.g., ${ parent_var }).
 *
 * @param entries - Current input mappings
 * @param onChange - Callback when mappings change
 * @param isDisabled - Disable editing
 * @param labelHelp - Optional help popover
 */
function InputMappingFields({ entries, onChange, isDisabled, labelHelp }: Readonly<InputMappingFieldsProps>) {
  return (
    <FormGroup label="Input Mapping" labelHelp={labelHelp} fieldId="input-mapping">
      {entries.map((entry, index) => (
        <Flex
          key={entry.id}
          className={styles.entryRow}
          alignItems={{ default: 'alignItemsFlexStart' }}
          gap={{ default: 'gapSm' }}
        >
          <FlexItem grow={{ default: 'grow' }}>
            <TextInput
              aria-label={`Child input name ${String(index + 1)}`}
              value={entry.key}
              onChange={(_event, val) => onChange(updateKey(entries, index, val))}
              placeholder="Child input name"
              isDisabled={isDisabled}
            />
          </FlexItem>
          <FlexItem grow={{ default: 'grow' }}>
            <TextInput
              aria-label={`Parent value ${String(index + 1)}`}
              value={entry.value}
              onChange={(_event, val) => onChange(updateValue(entries, index, val))}
              placeholder="Parent value or ${ expression }"
              isDisabled={isDisabled}
            />
          </FlexItem>
          {!isDisabled && (
            <FlexItem>
              <Button
                variant="plain"
                aria-label={`Remove input mapping ${String(index + 1)}`}
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
          Add input mapping
        </Button>
      )}
    </FormGroup>
  )
}

export { InputMappingFields }
export type { InputMappingEntry, InputMappingFieldsProps }
