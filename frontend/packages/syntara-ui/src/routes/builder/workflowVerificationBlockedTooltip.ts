/** Tooltip when Publish/Run is blocked by recorded workflow validation findings. */
export function workflowVerificationBlockedTooltip(
  action: 'publishing' | 'running',
  validationErrorCount: number
): string {
  const errorSuffix = validationErrorCount === 1 ? '' : 's'
  return `Verify your workflow before ${action} — ${validationErrorCount} error${errorSuffix} found`
}
