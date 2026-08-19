import { addDays, startOfDay } from 'date-fns'
import { useCallback, useMemo, useState } from 'react'

import { formatDateYMD, parseDateYMD } from '../../../utils/dateUtils'

function dateRangeValidator(minDate: Date, maxDate: Date | null) {
  return (date: Date): string => {
    if (date < minDate) return 'Date must be in the future'
    if (maxDate && date > maxDate) return 'Date exceeds maximum credential lifetime'
    return ''
  }
}

export function useCredentialExpirationDate(maxLifetimeDays = 180) {
  const isUnlimited = maxLifetimeDays === 0
  const today = useMemo(() => startOfDay(new Date()), [])
  const tomorrow = useMemo(() => addDays(today, 1), [today])
  const maxDate = useMemo(
    () => (isUnlimited ? null : addDays(today, Math.max(1, maxLifetimeDays - 1))),
    [today, maxLifetimeDays, isUnlimited]
  )
  const defaultDate = maxDate ?? addDays(today, 365)

  const [value, setValue] = useState(() => formatDateYMD(defaultDate))
  const [error, setError] = useState('')

  const validator = useMemo(() => dateRangeValidator(tomorrow, maxDate), [tomorrow, maxDate])

  const handleChange = useCallback(
    (_event: React.FormEvent<HTMLInputElement>, val: string, dateValue?: Date) => {
      setValue(val)
      if (!dateValue) {
        setError(val ? 'Invalid date format' : '')
        return
      }
      setError(validator(dateValue))
    },
    [validator]
  )

  const validate = useCallback((): boolean => {
    if (!value.trim()) {
      setError('Credential expiration date is required')
      return false
    }
    const dateValue = parseDateYMD(value)
    if (!dateValue) {
      setError('Invalid date format')
      return false
    }
    const validationError = validator(dateValue)
    setError(validationError)
    return validationError === ''
  }, [value, validator])

  const reset = useCallback(() => {
    setValue(formatDateYMD(defaultDate))
    setError('')
  }, [defaultDate])

  const helperText = isUnlimited
    ? 'No maximum lifetime configured'
    : `Maximum lifetime: ${maxLifetimeDays} days (until ${formatDateYMD(maxDate!)})`

  return { value, error, handleChange, validator, helperText, validate, reset }
}
