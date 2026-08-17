import { Button, Flex, FlexItem, TextInput, Title } from '@patternfly/react-core'
import { RhUiTrashIcon } from '@patternfly/react-icons'
import { useCallback } from 'react'

import { generateUUID } from '../../../../utils/generateUUID'
import { EXPRESSION_FIELD_PLACEHOLDER } from '../utils/dragTypes'

import { ExpressionFormField } from './ExpressionFormField'

type InputMapping = {
  id: string
  key: string
  value: string
}

type InputMappingFieldsProps = {
  mappings: InputMapping[]
  onChange: (mappings: InputMapping[]) => void
}

function InputMappingFields({ mappings, onChange }: Readonly<InputMappingFieldsProps>) {
  const handleAdd = useCallback(() => {
    onChange([...mappings, { id: generateUUID(), key: '', value: '' }])
  }, [mappings, onChange])

  const handleRemove = useCallback(
    (index: number) => {
      onChange(mappings.filter((_, i) => i !== index))
    },
    [mappings, onChange]
  )

  const handleKeyChange = useCallback(
    (index: number, newKey: string) => {
      const updated = mappings.map((m, i) => (i === index ? { ...m, key: newKey } : m))
      onChange(updated)
    },
    [mappings, onChange]
  )

  const handleValueChange = useCallback(
    (index: number, newValue: string) => {
      const updated = mappings.map((m, i) => (i === index ? { ...m, value: newValue } : m))
      onChange(updated)
    },
    [mappings, onChange]
  )

  return (
    <div>
      <Title headingLevel="h3" size="md">
        Inputs
      </Title>
      {mappings.map((mapping, index) => (
        <Flex
          key={mapping.id}
          alignItems={{ default: 'alignItemsFlexStart' }}
          gap={{ default: 'gapSm' }}
          style={{ marginBottom: 'var(--pf-t--global--spacer--sm)' }}
        >
          <FlexItem>
            <TextInput
              aria-label={`Input key ${String(index + 1)}`}
              value={mapping.key}
              onChange={(_event, val) => handleKeyChange(index, val)}
              placeholder="Name"
            />
          </FlexItem>
          <FlexItem grow={{ default: 'grow' }}>
            <ExpressionFormField
              id={`input-mapping-value-${String(index)}`}
              label={`Input value ${String(index + 1)}`}
              value={mapping.value}
              onChange={(val) => handleValueChange(index, val)}
              placeholder={EXPRESSION_FIELD_PLACEHOLDER}
            />
          </FlexItem>
          <FlexItem>
            <Button
              variant="plain"
              aria-label={`Remove input ${String(index + 1)}`}
              onClick={() => handleRemove(index)}
              icon={<RhUiTrashIcon />}
            />
          </FlexItem>
        </Flex>
      ))}
      <Button variant="link" onClick={handleAdd}>
        Add input
      </Button>
    </div>
  )
}

export { InputMappingFields }
export type { InputMapping, InputMappingFieldsProps }
