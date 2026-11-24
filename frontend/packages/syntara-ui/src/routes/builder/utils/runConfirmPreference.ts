const RUN_CONFIRM_DISMISSED_KEY = 'syntara-run-workflow-confirm-dismissed'

export function getRunConfirmDismissed(): boolean {
  try {
    return localStorage.getItem(RUN_CONFIRM_DISMISSED_KEY) === 'true'
  } catch {
    return false
  }
}

export function setRunConfirmDismissed(): void {
  try {
    localStorage.setItem(RUN_CONFIRM_DISMISSED_KEY, 'true')
  } catch {
    // ignore – storage unavailable
  }
}
