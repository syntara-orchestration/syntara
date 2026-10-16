import { DatePicker, Stack, StackItem, TimePicker, type TimePickerProps } from '@patternfly/react-core'
import { useCallback } from 'react'

import type { DateComponentName, DateValueShape } from '../../forms/dateFieldUtils'
import { formatDateMDY, isoYmdToLocalDate, normalizePickerDateToIsoYmd, parseDateMDY } from '../../utils/dateUtils'

import { to12HourTimeString } from './formDateTimeUtils'
import styles from './FormDateValueInputs.module.css'
import { FormTimezoneSelect } from './FormTimezoneSelect'

type FormDateValueInputsProps = Readonly<{
  included: DateComponentName[]
  value: DateValueShape | null | undefined
  onChange: (next: DateValueShape | null) => void
  onBlur?: () => void
  idPrefix: string
  isDisabled?: boolean
  validated?: 'error' | 'default'
  dateAriaLabel?: string
  timeAriaLabel?: string
  timezoneAriaLabel?: string
  allowEmptyTimezone?: boolean
}>

function readComponent(value: DateValueShape | null | undefined, name: DateComponentName): string {
  if (!value || typeof value !== 'object') {
    return ''
  }
  const part = value[name]
  return typeof part === 'string' ? part : ''
}

function mergeComponent(
  value: DateValueShape | null | undefined,
  name: DateComponentName,
  nextPart: string,
  included: DateComponentName[]
): DateValueShape | null {
  const base: DateValueShape = value && typeof value === 'object' ? { ...value } : {}
  for (const component of included) {
    if (component === name) {
      if (nextPart === '') {
        delete base[component]
      } else {
        base[component] = nextPart
      }
    } else if (base[component] == null || base[component] === '') {
      delete base[component]
    }
  }

  if (base.date == null && base.time == null && base.timezone == null) {
    return null
  }
  return base
}

export function FormDateValueInputs({
  included,
  value,
  onChange,
  onBlur,
  idPrefix,
  isDisabled,
  validated = 'default',
  dateAriaLabel = 'Date',
  timeAriaLabel = 'Time',
  timezoneAriaLabel = 'Time zone',
  allowEmptyTimezone = false,
}: FormDateValueInputsProps) {
  const showDate = included.includes('date')
  const showTime = included.includes('time')
  const showTimezone = included.includes('timezone')
  const isoDate = readComponent(value, 'date')
  const timeValue = readComponent(value, 'time')
  const timezoneValue = readComponent(value, 'timezone')

  const handleTimeChange = useCallback<NonNullable<TimePickerProps['onChange']>>(
    (...args) => {
      const [, , hour, minute, , isValid] = args
      if (!isValid || hour == null || minute == null) {
        return
      }
      const hh = String(hour).padStart(2, '0')
      const mm = String(minute).padStart(2, '0')
      onChange(mergeComponent(value, 'time', `${hh}:${mm}`, included))
    },
    [included, onChange, value]
  )

  return (
    <Stack hasGutter>
      {(showDate || showTime) && (
        <StackItem>
          <div className={styles.dateTimeRow}>
            {showDate && (
              <div className={styles.dateInput}>
                <DatePicker
                  value={isoDate ? formatDateMDY(isoYmdToLocalDate(isoDate)) : ''}
                  onChange={(_event, displayValue) => {
                    if (displayValue === '') {
                      onChange(mergeComponent(value, 'date', '', included))
                      return
                    }
                    const iso = normalizePickerDateToIsoYmd(displayValue)
                    if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
                      onChange(mergeComponent(value, 'date', iso, included))
                    }
                  }}
                  dateFormat={formatDateMDY}
                  dateParse={parseDateMDY}
                  isDisabled={isDisabled}
                  aria-label={dateAriaLabel}
                  inputProps={{
                    id: `${idPrefix}-date`,
                    validated,
                    onBlur,
                  }}
                  appendTo={() => document.body}
                />
              </div>
            )}
            {showTime && (
              <div className={styles.timeInput}>
                <TimePicker
                  id={`${idPrefix}-time`}
                  aria-label={timeAriaLabel}
                  time={to12HourTimeString(timeValue)}
                  onChange={handleTimeChange}
                  isDisabled={isDisabled}
                  menuAppendTo="parent"
                  width="100%"
                />
              </div>
            )}
          </div>
        </StackItem>
      )}
      {showTimezone && (
        <StackItem className={styles.timezoneRow}>
          <FormTimezoneSelect
            id={`${idPrefix}-timezone`}
            value={timezoneValue}
            onChange={(tz) => onChange(mergeComponent(value, 'timezone', tz, included))}
            isDisabled={isDisabled}
            ariaLabel={timezoneAriaLabel}
            allowEmpty={allowEmptyTimezone}
          />
        </StackItem>
      )}
    </Stack>
  )
}
