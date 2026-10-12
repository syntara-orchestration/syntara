/** Returns trimmed workflow-authored CSS for the form step panel, or undefined when empty. */
export function resolveFormPromptCssOverride(cssOverride?: string | null): string | undefined {
  if (cssOverride == null) {
    return undefined
  }
  const trimmed = cssOverride.trim()
  return trimmed.length > 0 ? trimmed : undefined
}
