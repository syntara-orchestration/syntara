import {
  Checkbox,
  FormGroup,
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
} from '@patternfly/react-core'
import { type ReactNode, type Ref, useState } from 'react'
import { Controller, useWatch, type Control, type FieldPath, type FieldValues } from 'react-hook-form'

import { SynSelect } from '../../../components/SynSelect'

const PROTOCOLS = [
  { value: 'SASL_SSL', label: 'SASL_SSL — TLS with username and password' },
  { value: 'SSL', label: 'SSL — TLS without SASL authentication' },
  { value: 'PLAINTEXT', label: 'PLAINTEXT — unencrypted and unauthenticated' },
]

export function KafkaTransportFields<T extends FieldValues>({
  control,
  protocolName,
  plaintextName,
  fieldId,
}: Readonly<{
  control: Control<T>
  protocolName: FieldPath<T>
  plaintextName: FieldPath<T>
  fieldId: string
}>) {
  const [isOpen, setIsOpen] = useState(false)
  const protocol = String(useWatch({ control, name: protocolName }) ?? 'SASL_SSL')
  return (
    <>
      <FormGroup label="Security protocol" fieldId={fieldId} isRequired>
        <Controller
          control={control}
          name={protocolName}
          render={({ field }) => {
            const value = String(field.value ?? 'SASL_SSL')
            const renderToggle = (ref: Ref<MenuToggleElement>): ReactNode => (
              <MenuToggle
                ref={ref}
                aria-label="Security protocol"
                isFullWidth
                isExpanded={isOpen}
                onClick={() => setIsOpen((open) => !open)}
              >
                {value}
              </MenuToggle>
            )
            return (
              <SynSelect
                id={fieldId}
                selected={value}
                isOpen={isOpen}
                onOpenChange={setIsOpen}
                toggle={renderToggle}
                shouldFocusToggleOnSelect
                onSelect={(_event, selected) => {
                  if (typeof selected !== 'string' || !PROTOCOLS.some((option) => option.value === selected)) return
                  field.onChange(selected)
                  setIsOpen(false)
                }}
              >
                <SelectList>
                  {PROTOCOLS.map((option) => (
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
      {protocol === 'PLAINTEXT' && (
        <Controller
          control={control}
          name={plaintextName}
          render={({ field, fieldState }) => (
            <FormGroup fieldId={`${fieldId}-allow-plaintext`}>
              <Checkbox
                id={`${fieldId}-allow-plaintext`}
                label="Allow unencrypted, unauthenticated connections"
                isChecked={field.value ?? false}
                onChange={(_event, checked) => field.onChange(checked)}
                description={
                  fieldState.error?.message ??
                  'Anyone with network access may read or modify traffic. Enable only for trusted development environments.'
                }
              />
            </FormGroup>
          )}
        />
      )}
    </>
  )
}
