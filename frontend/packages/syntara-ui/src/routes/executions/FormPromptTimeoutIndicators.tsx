import { Alert } from '@patternfly/react-core'
import { useEffect, useMemo, useState } from 'react'

import { formatElapsedTime } from '../../utils/dateUtils'

const RUNNING_LONG_FRACTION = 0.8

type FormPromptWaitingDurationProps = Readonly<{
  waitingStartedAt?: string | null
  isPending: boolean
}>

/** Elapsed time since the form step entered waiting (resets when the run reaches waiting again). */
export function FormPromptWaitingDuration({ waitingStartedAt, isPending }: FormPromptWaitingDurationProps) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!isPending) return undefined
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [isPending])

  const display = useMemo(() => {
    if (!isPending || !waitingStartedAt) return null
    const started = new Date(waitingStartedAt).getTime()
    return formatElapsedTime(Math.max(0, now - started))
  }, [waitingStartedAt, isPending, now])

  if (!display) return null
  return display
}

type FormPromptRunningLongAlertProps = Readonly<{
  waitingStartedAt?: string | null
  timeoutAt?: string | null
  isPending: boolean
}>

export function FormPromptRunningLongAlert({
  waitingStartedAt,
  timeoutAt,
  isPending,
}: FormPromptRunningLongAlertProps) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!isPending) return undefined
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [isPending])

  const showRunningLong = useMemo(() => {
    if (!isPending || !waitingStartedAt || !timeoutAt) return false
    const started = new Date(waitingStartedAt).getTime()
    const deadline = new Date(timeoutAt).getTime()
    const totalWindow = deadline - started
    const elapsed = Math.max(0, now - started)
    return totalWindow > 0 && elapsed >= totalWindow * RUNNING_LONG_FRACTION
  }, [waitingStartedAt, timeoutAt, isPending, now])

  if (!showRunningLong) return null

  return (
    <Alert variant="warning" isInline title="Running long">
      This prompt is approaching its response deadline.
    </Alert>
  )
}
