/** Return policy labels other than the node kind in stable insertion order. */
export function formatNodeAttributeLabels(labels: Readonly<Record<string, string>> | undefined): string {
  return Object.entries(labels ?? {})
    .filter(([name, value]) => name !== 'kind' && value !== '')
    .map(([name, value]) => `${name}=${value}`)
    .join(', ')
}

/** Add a parenthesized attribute-label suffix to a node kind. */
export function describeNodeLabels(kind: string, labels: Readonly<Record<string, string>> | undefined): string {
  const attributes = formatNodeAttributeLabels(labels)
  return attributes ? `${kind} (${attributes})` : kind
}
