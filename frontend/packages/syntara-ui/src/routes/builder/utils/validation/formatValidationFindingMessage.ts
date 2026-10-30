/**
 * Rewrites backend validation finding messages so user-facing UI shows step
 * display names instead of raw activity ids when a name is known.
 *
 * Example:
 *   Node 'activity_7f0feaf7_…' is unreachable from any trigger
 *   → Step "My Script" is unreachable from any trigger
 */
export function formatValidationFindingMessage(
  message: string,
  nodeId: string | null,
  nodeName: string | undefined
): string {
  if (!nodeId || !nodeName || nodeName === nodeId) {
    return message
  }

  const escapedId = nodeId.replace(/[.*+?^${}()|[\]\\]/g, String.raw`\$&`)
  const idPattern = new RegExp(String.raw`\b${escapedId}\b`, 'g')
  let formatted = message.replace(idPattern, nodeName)

  const nodeQuoted = `Node '${nodeName}'`
  if (formatted.startsWith(nodeQuoted)) {
    formatted = `Step "${nodeName}"${formatted.slice(nodeQuoted.length)}`
  }

  return formatted
}
