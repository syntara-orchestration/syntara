/**
 * Designer Message/prompt on an approval activity.
 * v2 stores it on `parameters.prompt`; older shapes used `config.prompt`.
 */
export function getApprovalPromptFromNode(
  node: { parameters?: unknown; config?: unknown } | undefined
): string | undefined {
  if (!node) return undefined
  return getPromptFromBag(node.parameters) ?? getPromptFromBag(node.config)
}

function getPromptFromBag(bag: unknown): string | undefined {
  if (typeof bag !== 'object' || bag === null || !('prompt' in bag)) return undefined
  const prompt = bag.prompt
  if (typeof prompt !== 'string') return undefined
  const trimmed = prompt.trim()
  return trimmed === '' ? undefined : trimmed
}
