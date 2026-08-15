import { useEffect, useReducer, useRef } from 'react'

import {
  durationToFrequencyAndInterval,
  frequencyAndIntervalToDuration,
  parseRepeatingInterval,
  type ScheduleFrequency,
} from '../../utils/triggerFormatting'

export type BuilderState = {
  startDate: string
  startTime: string
  endDate: string
  frequency: ScheduleFrequency
  intervalCount: number
}

export type BuilderAction =
  | { type: 'SET_START_DATE'; payload: string }
  | { type: 'SET_START_TIME'; payload: string }
  | { type: 'SET_END_DATE'; payload: string }
  | { type: 'SET_FREQUENCY'; payload: ScheduleFrequency }
  | { type: 'SET_INTERVAL_COUNT'; payload: number }
  | { type: 'INIT'; payload: BuilderState }

function builderReducer(state: BuilderState, action: BuilderAction): BuilderState {
  switch (action.type) {
    case 'SET_START_DATE':
      return { ...state, startDate: action.payload }
    case 'SET_START_TIME':
      return { ...state, startTime: action.payload }
    case 'SET_END_DATE':
      return { ...state, endDate: action.payload }
    case 'SET_FREQUENCY':
      return { ...state, frequency: action.payload }
    case 'SET_INTERVAL_COUNT':
      return { ...state, intervalCount: Math.max(1, action.payload) }
    case 'INIT':
      return action.payload
    default:
      return state
  }
}

function toDateOnly(isoString: string): string {
  if (!isoString) return ''
  const tIndex = isoString.indexOf('T')
  if (tIndex === -1) return ''
  const datePart = isoString.substring(0, tIndex)
  return /^\d{4}-\d{2}-\d{2}$/.test(datePart) ? datePart : ''
}

function extractTimeHHMM(isoString: string): string {
  if (!isoString) return ''
  const tIndex = isoString.indexOf('T')
  if (tIndex === -1) return ''
  const timePart = isoString.substring(tIndex + 1)
  const match = /^(\d{2}):(\d{2})/.exec(timePart)
  return match ? `${match[1]}:${match[2]}` : ''
}

function buildISOString(dateStr: string, timeStr: string, tzOffset: string): string {
  if (!dateStr) return ''
  return `${dateStr}T${timeStr}${tzOffset}`
}

function getTimezoneOffset(timezone: string, referenceDate?: string): string {
  try {
    const refDate = referenceDate ? new Date(`${referenceDate}T12:00:00`) : new Date()
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: timezone,
      timeZoneName: 'longOffset',
    })
    const parts = formatter.formatToParts(refDate)
    const tzPart = parts.find((p) => p.type === 'timeZoneName')
    if (!tzPart) return 'Z'
    const offset = tzPart.value.replace('GMT', '')
    return offset || '+00:00'
  } catch {
    return 'Z'
  }
}

function parseInitialState(value: string): BuilderState {
  const parsed = parseRepeatingInterval(value)
  const { frequency, count } = durationToFrequencyAndInterval(parsed.cadence)

  return {
    startDate: toDateOnly(parsed.start),
    startTime: extractTimeHHMM(parsed.start),
    endDate: parsed.end ? toDateOnly(parsed.end) : '',
    frequency: parsed.cadence === 'PT0S' ? 'none' : frequency,
    intervalCount: count,
  }
}

export function useScheduleBuilder(value: string, timezone: string, onChange?: (interval: string) => void) {
  const [state, dispatch] = useReducer(builderReducer, value, parseInitialState)
  const prevValueRef = useRef(value)
  const lastEmittedRef = useRef<string | undefined>(undefined)

  useEffect(() => {
    if (value !== prevValueRef.current && value !== lastEmittedRef.current) {
      dispatch({ type: 'INIT', payload: parseInitialState(value) })
    }
    prevValueRef.current = value
  }, [value])

  const { startDate, startTime, endDate, frequency, intervalCount } = state

  useEffect(() => {
    const now = new Date()
    const pad = (n: number) => String(n).padStart(2, '0')
    const effectiveDate = startDate || `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
    const effectiveTime = startDate ? startTime || '00:00' : `${pad(now.getHours())}:${pad(now.getMinutes())}`

    const tzOffset = getTimezoneOffset(timezone, effectiveDate)
    const start = buildISOString(effectiveDate, `${effectiveTime}:00`, tzOffset)
    if (!start) return

    const duration = frequencyAndIntervalToDuration(frequency, intervalCount)
    if (!duration) {
      const runOnce = `R1/${start}/PT0S`
      if (runOnce !== value) {
        lastEmittedRef.current = runOnce
        onChange?.(runOnce)
      }
      return
    }

    let interval = `R/${start}/${duration}`
    if (endDate) {
      const endTzOffset = getTimezoneOffset(timezone, endDate)
      interval += `/${buildISOString(endDate, '23:59:59', endTzOffset)}`
    }

    if (interval !== value) {
      lastEmittedRef.current = interval
      onChange?.(interval)
    }
  }, [startDate, startTime, endDate, frequency, intervalCount, timezone, onChange, value])

  return { state, dispatch }
}
