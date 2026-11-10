import { NumberInput } from '@patternfly/react-core'

import { parseSynNumberInputDisplayValue } from './synNumberInputDisplayValue'

/** Stored value when the user clears the number input. */
export type SynNumberInputEmptyValue = null | ''

type SynNumberInputControlProps = {
  fieldId: string
  ariaLabel: string
  value: unknown
  emptyValue: SynNumberInputEmptyValue
  onChange: (value: number | SynNumberInputEmptyValue) => void
  onBlur?: () => void
  isDisabled?: boolean
  validated?: 'default' | 'warning' | 'success' | 'error'
  placeholder?: string
  inputName?: string
}

export function SynNumberInputControl({
  fieldId,
  ariaLabel,
  value,
  emptyValue,
  onChange,
  onBlur,
  isDisabled,
  validated = 'default',
  placeholder,
  inputName,
}: Readonly<SynNumberInputControlProps>) {
  const displayValue = parseSynNumberInputDisplayValue(value)

  return (
    <NumberInput
      // NumberInput spreads unknown props onto its wrapper div, so the id
      // and accessible name have to be routed to the inner text input for
      // the FormGroup label to point at it.
      inputProps={{ id: fieldId, ...(placeholder ? { placeholder } : {}) }}
      inputName={inputName}
      inputAriaLabel={ariaLabel}
      value={displayValue}
      isDisabled={isDisabled}
      validated={validated}
      onMinus={() => {
        const base = displayValue === '' ? 0 : displayValue
        onChange(base - 1)
      }}
      onPlus={() => {
        const base = displayValue === '' ? 0 : displayValue
        onChange(base + 1)
      }}
      onBlur={onBlur}
      onChange={(event) => {
        const target = event.target as HTMLInputElement
        // On blur NumberInput rewrites the input to `Number(value)` and
        // reports it through onChange, turning an empty field into 0.
        // Undo that write so an intentionally empty field stays empty;
        // the form value is already empty so React will not re-render here.
        if (event.type === 'blur' && displayValue === '') {
          target.value = ''
          return
        }
        if (target.value === '') {
          onChange(emptyValue)
          return
        }
        const parsed = Number.parseFloat(target.value)
        if (!Number.isNaN(parsed)) {
          onChange(parsed)
        }
      }}
    />
  )
}
