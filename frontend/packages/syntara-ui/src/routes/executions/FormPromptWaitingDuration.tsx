import { useEffect, useMemo, useState } from 'react'

import { formatElapsedTime } from '../../utils/dateUtils'

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
