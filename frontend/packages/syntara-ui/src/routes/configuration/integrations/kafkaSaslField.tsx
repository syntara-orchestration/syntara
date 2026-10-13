import { FormGroup, MenuToggle, type MenuToggleElement, SelectList, SelectOption } from '@patternfly/react-core'
import { type ReactNode, type Ref, useState } from 'react'
import { Controller, type Control, type FieldPath, type FieldValues } from 'react-hook-form'

import { SynSelect } from '../../../components/SynSelect'

import { integrationHelp } from './integrationFieldHelp'
import { KAFKA_SASL_MECHANISMS } from './kafkaSasl'

export function KafkaSaslMechanismField<T extends FieldValues>({
  control,
  name,
  fieldId,
}: Readonly<{
  control: Control<T>
  name: FieldPath<T>
  fieldId: string
}>) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <FormGroup label="SASL mechanism" fieldId={fieldId} isRequired labelHelp={integrationHelp.kafkaSaslMechanism}>
      <Controller
        name={name}
        control={control}
        render={({ field }) => {
          const value = String(field.value ?? '')
          const label = KAFKA_SASL_MECHANISMS.find((option) => option.value === value)?.label ?? value
          const renderToggle = (toggleRef: Ref<MenuToggleElement>): ReactNode => (
            <MenuToggle ref={toggleRef} onClick={() => setIsOpen((open) => !open)} isExpanded={isOpen} isFullWidth>
              {label}
            </MenuToggle>
          )
          return (
            <SynSelect
              id={fieldId}
              isOpen={isOpen}
              selected={value}
              onSelect={(_event, selected) => {
                if (typeof selected !== 'string') return
                if (!KAFKA_SASL_MECHANISMS.some((option) => option.value === selected)) return
                field.onChange(selected)
                setIsOpen(false)
              }}
              onOpenChange={setIsOpen}
              toggle={renderToggle}
              shouldFocusToggleOnSelect
            >
              <SelectList>
                {KAFKA_SASL_MECHANISMS.map((option) => (
                  <SelectOption key={option.value} value={option.value}>
                    {option.label}
                  </SelectOption>
                ))}
              </SelectList>
            </SynSelect>
          )
        }}
      />
    </FormGroup>
  )
}
