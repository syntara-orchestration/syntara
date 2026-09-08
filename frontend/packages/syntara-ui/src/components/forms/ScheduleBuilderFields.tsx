import {
  Button,
  DatePicker,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  MenuToggle,
  type MenuToggleElement,
  NumberInput,
  SelectList,
  SelectOption,
  Stack,
  StackItem,
  TextInputGroup,
  TextInputGroupMain,
  TextInputGroupUtilities,
  TimePicker,
  type TimePickerProps,
} from '@patternfly/react-core'
import { RhUiCloseIcon, RhUiErrorIcon } from '@patternfly/react-icons'
import { type Dispatch, useCallback, useMemo, useState } from 'react'

import { formatDateYMD, parseDateYMD } from '../../utils/dateUtils'
import type { ScheduleFrequency } from '../../utils/triggerFormatting'
import { FieldHelpPopover } from '../FieldHelpPopover'
import { SynSelect } from '../SynSelect'

import styles from './ScheduleBuilderFields.module.css'
import { END_DATE_HELP, FREQUENCY_HELP, INTERVAL_HELP, START_DATE_HELP } from './scheduleHelpText'
import { type BuilderAction, useScheduleBuilder } from './useScheduleBuilder'

const startDateLabelHelp = <FieldHelpPopover headerContent="Start date and time" helpText={START_DATE_HELP} />
const endDateLabelHelp = <FieldHelpPopover headerContent="End date" helpText={END_DATE_HELP} />
const frequencyLabelHelp = <FieldHelpPopover headerContent="Frequency" helpText={FREQUENCY_HELP} />
const intervalLabelHelp = <FieldHelpPopover headerContent="Interval" helpText={INTERVAL_HELP} />

export type ScheduleBuilderFieldsProps = Readonly<{
  value?: string
  onChange?: (interval: string) => void
  timezone?: string
  onTimezoneChange?: (tz: string) => void
  required?: boolean
  error?: boolean
  errorMessage?: string
}>

// ── Frequency options ────────────────────────────────────────────────────

const frequencyOptions: { value: ScheduleFrequency; label: string }[] = [
  { value: 'none', label: 'Does not repeat' },
  { value: 'minutely', label: 'Minutely' },
  { value: 'hourly', label: 'Hourly' },
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'yearly', label: 'Yearly' },
]

// ── Timezone list ────────────────────────────────────────────────────────

let cachedTimezones: string[] | null = null

function getTimezones(): string[] {
  if (!cachedTimezones) {
    try {
      cachedTimezones = Intl.supportedValuesOf('timeZone')
    } catch {
      cachedTimezones = ['UTC']
    }
  }
  return cachedTimezones
}

// ── Sub-components (module-scoped per S6478) ─────────────────────────────

type DispatchBuilder = Dispatch<BuilderAction>

/**
 * Converts an internal 24-hour "HH:MM" time to the "h:mm AM/PM" string PF's `TimePicker`
 * expects for its `time` prop once `is24Hour` is unset (its default is 12-hour display).
 * Passing the bare 24-hour string directly would be misread as 12-hour input.
 */
function to12HourTimeString(hhmm: string): string {
  const [hourStr, minuteStr] = hhmm.split(':')
  const hour = Number(hourStr)
  if (hhmm === '' || minuteStr === undefined || Number.isNaN(hour)) return hhmm
  const suffix = hour >= 12 ? 'PM' : 'AM'
  const displayHour = hour % 12 === 0 ? 12 : hour % 12
  return `${displayHour}:${minuteStr} ${suffix}`
}

function StartDateTimeField({
  startDate,
  startTime,
  timezone,
  dispatch,
  onTimezoneChange,
  required,
  error,
  errorMessage,
}: Readonly<{
  startDate: string
  startTime: string
  timezone: string
  dispatch: DispatchBuilder
  onTimezoneChange?: (tz: string) => void
  required: boolean
  error: boolean
  errorMessage?: string
}>) {
  const [tzOpen, setTzOpen] = useState(false)
  const [tzFilter, setTzFilter] = useState('')

  const timezones = getTimezones()
  const filteredTimezones = tzFilter
    ? timezones.filter((tz) => tz.toLowerCase().includes(tzFilter.toLowerCase()))
    : timezones

  const handleTzSelect = useCallback(
    (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
      if (value === undefined) return
      onTimezoneChange?.(String(value))
      setTzOpen(false)
      setTzFilter('')
    },
    [onTimezoneChange]
  )

  // Rest-param signature keeps this under the max-params lint limit; PF's TimePicker calls
  // onChange with (event, time, hour, minute, seconds, isValid) — hour/minute are always 24-hour.
  const handleStartTimeChange = useCallback<NonNullable<TimePickerProps['onChange']>>(
    (...args) => {
      const [, , hour, minute, , isValid] = args
      if (!isValid || hour == null || minute == null) return
      const hh = String(hour).padStart(2, '0')
      const mm = String(minute).padStart(2, '0')
      dispatch({ type: 'SET_START_TIME', payload: `${hh}:${mm}` })
    },
    [dispatch]
  )

  const tzToggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) => (
      <MenuToggle ref={toggleRef} onClick={() => setTzOpen((prev) => !prev)} isExpanded={tzOpen} isFullWidth>
        {timezone || 'UTC'}
      </MenuToggle>
    ),
    [tzOpen, timezone]
  )

  return (
    <StackItem>
      <FormGroup
        label="Start date and time"
        labelHelp={startDateLabelHelp}
        fieldId="schedule-start-date"
        isRequired={required}
      >
        <div className={styles.startDateTimeRow}>
          <DatePicker
            value={startDate}
            onChange={(_event, value) => {
              if (value === '' || /^\d{4}-\d{2}-\d{2}$/.test(value)) {
                dispatch({ type: 'SET_START_DATE', payload: value })
              }
            }}
            dateFormat={formatDateYMD}
            dateParse={parseDateYMD}
            aria-label="Start date"
            inputProps={{
              id: 'schedule-start-date',
              validated: error ? 'error' : 'default',
              'aria-required': required || undefined,
            }}
            appendTo={() => document.body}
          />
          <div className={styles.timeInput}>
            <TimePicker
              id="schedule-start-time"
              aria-label="Start time"
              time={to12HourTimeString(startTime)}
              onChange={handleStartTimeChange}
              menuAppendTo="parent"
              width="100%"
            />
          </div>
          <div className={styles.timezoneSelect}>
            <SynSelect
              id="schedule-timezone"
              isOpen={tzOpen}
              selected={timezone}
              onSelect={handleTzSelect}
              onOpenChange={(open) => {
                setTzOpen(open)
                if (!open) setTzFilter('')
              }}
              toggle={tzToggle}
            >
              <TextInputGroup>
                <TextInputGroupMain
                  value={tzFilter}
                  onChange={(_event, val) => setTzFilter(val)}
                  placeholder="Filter timezones"
                  aria-label="Filter timezones"
                />
                {tzFilter && (
                  <TextInputGroupUtilities>
                    <Button variant="plain" onClick={() => setTzFilter('')} aria-label="Clear timezone filter">
                      <RhUiCloseIcon />
                    </Button>
                  </TextInputGroupUtilities>
                )}
              </TextInputGroup>
              <SelectList aria-label="Timezone options">
                {filteredTimezones.slice(0, 50).map((tz) => (
                  <SelectOption key={tz} value={tz}>
                    {tz}
                  </SelectOption>
                ))}
              </SelectList>
            </SynSelect>
          </div>
        </div>
        {error && errorMessage && (
          <FormHelperText>
            <HelperText>
              <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                {errorMessage}
              </HelperTextItem>
            </HelperText>
          </FormHelperText>
        )}
      </FormGroup>
    </StackItem>
  )
}

function buildEndDateValidators(startDate: string): ((date: Date) => string)[] {
  return [
    (date: Date) => {
      if (!startDate) return ''
      const start = new Date(`${startDate}T00:00:00`)
      return date < start ? 'End date must be on or after the start date.' : ''
    },
  ]
}

function EndDateField({
  endDate,
  startDate,
  dispatch,
}: Readonly<{ endDate: string; startDate: string; dispatch: DispatchBuilder }>) {
  const validators = useMemo(() => buildEndDateValidators(startDate), [startDate])
  const endBeforeStart = Boolean(endDate && startDate && endDate < startDate)

  return (
    <StackItem>
      <FormGroup label="End date" labelHelp={endDateLabelHelp} fieldId="schedule-end-date">
        <DatePicker
          value={endDate}
          onChange={(_event, value) => {
            if (value === '' || /^\d{4}-\d{2}-\d{2}$/.test(value)) {
              dispatch({ type: 'SET_END_DATE', payload: value })
            }
          }}
          dateFormat={formatDateYMD}
          dateParse={parseDateYMD}
          aria-label="End date"
          validators={validators}
          inputProps={{
            id: 'schedule-end-date',
            validated: endBeforeStart ? 'error' : 'default',
          }}
          appendTo={() => document.body}
          helperText={
            <HelperText>
              <HelperTextItem
                variant={endBeforeStart ? 'error' : 'default'}
                icon={endBeforeStart ? <RhUiErrorIcon /> : undefined}
              >
                {endBeforeStart
                  ? 'End date must be on or after the start date.'
                  : 'If this field is left empty, the schedule will not have an end date.'}
              </HelperTextItem>
            </HelperText>
          }
        />
      </FormGroup>
    </StackItem>
  )
}

function FrequencySelectField({
  frequency,
  dispatch,
  required,
}: Readonly<{
  frequency: ScheduleFrequency
  dispatch: DispatchBuilder
  required: boolean
}>) {
  const [isOpen, setIsOpen] = useState(false)
  const selectedLabel = frequencyOptions.find((o) => o.value === frequency)?.label ?? 'Does not repeat'

  const handleSelect = useCallback(
    (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
      if (value === undefined) return
      dispatch({ type: 'SET_FREQUENCY', payload: value as ScheduleFrequency })
      setIsOpen(false)
    },
    [dispatch]
  )

  const renderToggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) => (
      <MenuToggle
        ref={toggleRef}
        onClick={() => setIsOpen((prev) => !prev)}
        isExpanded={isOpen}
        isFullWidth
        aria-label="Frequency"
        aria-required={required || undefined}
      >
        {selectedLabel}
      </MenuToggle>
    ),
    [isOpen, selectedLabel, required]
  )

  return (
    <StackItem>
      <FormGroup label="Frequency" labelHelp={frequencyLabelHelp} fieldId="schedule-frequency" isRequired={required}>
        <SynSelect
          id="schedule-frequency"
          isOpen={isOpen}
          selected={frequency}
          onSelect={handleSelect}
          onOpenChange={setIsOpen}
          shouldFocusToggleOnSelect
          toggle={renderToggle}
        >
          <SelectList aria-label="Frequency options">
            {frequencyOptions.map((option) => (
              <SelectOption key={option.value} value={option.value}>
                {option.label}
              </SelectOption>
            ))}
          </SelectList>
        </SynSelect>
      </FormGroup>
    </StackItem>
  )
}

function IntervalCountField({
  intervalCount,
  dispatch,
  required,
}: Readonly<{
  intervalCount: number
  dispatch: DispatchBuilder
  required: boolean
}>) {
  return (
    <StackItem>
      <FormGroup label="Interval" labelHelp={intervalLabelHelp} fieldId="schedule-interval" isRequired={required}>
        <div className={styles.intervalInput}>
          <NumberInput
            id="schedule-interval"
            value={intervalCount}
            min={1}
            onMinus={() => dispatch({ type: 'SET_INTERVAL_COUNT', payload: intervalCount - 1 })}
            onPlus={() => dispatch({ type: 'SET_INTERVAL_COUNT', payload: intervalCount + 1 })}
            onChange={(event) => {
              const val = Number((event.target as HTMLInputElement).value)
              if (!Number.isNaN(val)) dispatch({ type: 'SET_INTERVAL_COUNT', payload: val })
            }}
            aria-label="Interval"
            inputAriaLabel="Interval count"
          />
        </div>
      </FormGroup>
    </StackItem>
  )
}

// ── Main component ───────────────────────────────────────────────────────

export function ScheduleBuilderFields({
  value = '',
  onChange,
  timezone = 'UTC',
  onTimezoneChange,
  required = false,
  error = false,
  errorMessage,
}: ScheduleBuilderFieldsProps) {
  const { state, dispatch } = useScheduleBuilder(value, timezone, onChange)
  const { startDate, startTime, endDate, frequency, intervalCount } = state

  return (
    <Stack hasGutter data-testid="schedule-builder-fields">
      <StartDateTimeField
        startDate={startDate}
        startTime={startTime}
        timezone={timezone}
        dispatch={dispatch}
        onTimezoneChange={onTimezoneChange}
        required={required}
        error={error}
        errorMessage={errorMessage}
      />
      <EndDateField endDate={endDate} startDate={startDate} dispatch={dispatch} />
      <FrequencySelectField frequency={frequency} dispatch={dispatch} required={required} />
      {frequency !== 'none' && (
        <IntervalCountField intervalCount={intervalCount} dispatch={dispatch} required={required} />
      )}
    </Stack>
  )
}
