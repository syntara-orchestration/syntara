import {
  Button,
  Checkbox,
  Flex,
  FlexItem,
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  Stack,
  StackItem,
  TextInput,
} from '@patternfly/react-core'
import { RhUiAddIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { useId, useState } from 'react'

import { SynSelect } from '../../../components/SynSelect'

import styles from './SimpleSchemaBuilder.module.css'
import { type SimpleField, type SimpleFieldType, SIMPLE_FIELD_TYPES, createEmptyField } from './simpleSchemaUtils'

type SimpleSchemaBuilderProps = {
  fields: SimpleField[]
  onFieldsChange: (fields: SimpleField[]) => void
}

function fieldTypeToggle(
  toggleRef: React.Ref<MenuToggleElement>,
  onClick: () => void,
  isExpanded: boolean,
  label: string
) {
  return (
    <MenuToggle ref={toggleRef} onClick={onClick} isExpanded={isExpanded} isFullWidth>
      {label}
    </MenuToggle>
  )
}

function FieldTypeSelect({
  fieldId,
  value,
  onChange,
}: Readonly<{ fieldId: string; value: SimpleFieldType; onChange: (type: SimpleFieldType) => void }>) {
  const [isOpen, setIsOpen] = useState(false)
  const selected = SIMPLE_FIELD_TYPES.find((t) => t.value === value)

  return (
    <SynSelect
      id={fieldId}
      isOpen={isOpen}
      onOpenChange={setIsOpen}
      onSelect={(_event, val) => {
        onChange(val as SimpleFieldType)
        setIsOpen(false)
      }}
      selected={value}
      shouldFocusToggleOnSelect
      toggle={(toggleRef) =>
        fieldTypeToggle(toggleRef, () => setIsOpen((prev) => !prev), isOpen, selected?.label ?? 'String')
      }
    >
      <SelectList>
        {SIMPLE_FIELD_TYPES.map((t) => (
          <SelectOption key={t.value} value={t.value}>
            {t.label}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}

function FieldRow({
  field,
  index,
  onUpdate,
  onRemove,
}: Readonly<{
  field: SimpleField
  index: number
  onUpdate: (id: string, updates: Partial<SimpleField>) => void
  onRemove: (id: string) => void
}>) {
  const idPrefix = useId()
  const position = String(index + 1)
  const nameId = `${idPrefix}-name`
  const typeId = `${idPrefix}-type`
  const requiredId = `${idPrefix}-required`
  const nameLabel = `Field name ${position}`
  const removeLabel = `Remove field ${field.name || position}`
  const handleNameChange = (_event: React.FormEvent, val: string) => onUpdate(field.id, { name: val })
  const handleTypeChange = (type: SimpleFieldType) => onUpdate(field.id, { type })
  const handleRequiredChange = (_event: React.FormEvent, checked: boolean) => onUpdate(field.id, { required: checked })
  const handleRemove = () => onRemove(field.id)

  return (
    <Flex alignItems={{ default: 'alignItemsFlexStart' }} gap={{ default: 'gapSm' }}>
      <FlexItem grow={{ default: 'grow' }} className={styles.fieldName}>
        <TextInput
          id={nameId}
          aria-label={nameLabel}
          placeholder="Field name"
          value={field.name}
          onChange={handleNameChange}
        />
      </FlexItem>
      <FlexItem className={styles.fieldType}>
        <FieldTypeSelect fieldId={typeId} value={field.type} onChange={handleTypeChange} />
      </FlexItem>
      <FlexItem alignSelf={{ default: 'alignSelfCenter' }}>
        <Checkbox id={requiredId} label="Required" isChecked={field.required} onChange={handleRequiredChange} />
      </FlexItem>
      <FlexItem>
        <Button variant="plain" aria-label={removeLabel} onClick={handleRemove}>
          <RhUiTrashIcon />
        </Button>
      </FlexItem>
    </Flex>
  )
}

export function SimpleSchemaBuilder({ fields, onFieldsChange }: Readonly<SimpleSchemaBuilderProps>) {
  function handleUpdate(id: string, updates: Partial<SimpleField>) {
    onFieldsChange(fields.map((f) => (f.id === id ? { ...f, ...updates } : f)))
  }

  function handleRemove(id: string) {
    onFieldsChange(fields.filter((f) => f.id !== id))
  }

  function handleAdd() {
    onFieldsChange([...fields, createEmptyField()])
  }

  return (
    <Stack hasGutter>
      {fields.map((field, index) => (
        <StackItem key={field.id}>
          <FieldRow field={field} index={index} onUpdate={handleUpdate} onRemove={handleRemove} />
        </StackItem>
      ))}
      <StackItem>
        <Button variant="link" icon={<RhUiAddIcon />} onClick={handleAdd}>
          Add field
        </Button>
      </StackItem>
    </Stack>
  )
}
