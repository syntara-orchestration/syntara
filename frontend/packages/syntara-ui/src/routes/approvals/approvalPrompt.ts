/**
 * Designer Message/prompt on an approval activity.
 * v2 stores it on `parameters.prompt`; older shapes used `config.prompt`.
 * Runtime approvals persist the resolved prompt on the approval record.
 */

export function getApprovalPromptFromRecord(approval: { prompt?: string | null } | undefined): string | undefined {
  return trimPrompt(approval?.prompt)
}

export function getApprovalPromptFromNode(
  node: { parameters?: unknown; config?: unknown } | undefined
): string | undefined {
  if (!node) return undefined
  return getPromptFromBag(node.parameters) ?? getPromptFromBag(node.config)
}

function getPromptFromBag(bag: unknown): string | undefined {
  if (typeof bag !== 'object' || bag === null || !('prompt' in bag)) return undefined
  return trimPrompt((bag as { prompt?: unknown }).prompt)
}

function trimPrompt(prompt: unknown): string | undefined {
  if (typeof prompt !== 'string') return undefined
  const trimmed = prompt.trim()
  return trimmed === '' ? undefined : trimmed
}
