import type { FormsAPI } from '@syntara/contracts'

type FormPromptRead = FormsAPI.components['schemas']['FormPromptRead']

export function isFormPromptPastResponseTimeout(timeoutAt: string | null | undefined, nowMs = Date.now()): boolean {
  if (!timeoutAt) return false
  const timeoutMs = Date.parse(timeoutAt)
  return !Number.isNaN(timeoutMs) && nowMs >= timeoutMs
}

/** Whether the user can still fill out and submit the response form. */
export function isFormPromptResponsePending(prompt: FormPromptRead, nowMs = Date.now()): boolean {
  if (prompt.status === 'submitted' || prompt.status === 'cancelled') {
    return false
  }
  if (isFormPromptPastResponseTimeout(prompt.timeout_at, nowMs)) {
    return false
  }
  // Backend may mark `expired` before `timeout_at`; keep the form open until the deadline.
  return prompt.status === 'pending' || prompt.status === 'expired'
}

export function formPromptClosedStatusLabel(prompt: FormPromptRead, nowMs = Date.now()): string {
  if (isFormPromptPastResponseTimeout(prompt.timeout_at, nowMs) || prompt.status === 'expired') {
    return 'expired'
  }
  return prompt.status ?? 'closed'
}
