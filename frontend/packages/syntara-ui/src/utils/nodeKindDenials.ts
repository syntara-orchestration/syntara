import { describeNodeLabels } from './nodeLabels'

/** Error code of the 403 problem details returned when a save introduces a denied node kind. */
export const NODE_KIND_WRITE_DENIED_CODE = 'NODE_KIND_WRITE_DENIED'

/** One node kind the save was not allowed to introduce. */
export type NodeKindDenial = {
  kind: string
  labels: Record<string, string>
  denied_by: string
  reason: string
}

function stringRecord(value: unknown): Record<string, string> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const entries = Object.entries(value).filter((entry): entry is [string, string] => typeof entry[1] === 'string')
  return Object.fromEntries(entries)
}

function unwrapErrorBody(error: unknown): Record<string, unknown> | null {
  if (!error || typeof error !== 'object') return null
  const body = error as Record<string, unknown>
  if (Array.isArray(body.denied_kinds)) return body
  for (const wrapper of ['cause', 'data'] as const) {
    const nested = body[wrapper]
    if (nested && typeof nested === 'object' && Array.isArray((nested as Record<string, unknown>).denied_kinds)) {
      return nested as Record<string, unknown>
    }
  }
  return body
}

function toDenial(entry: unknown): NodeKindDenial | null {
  if (!entry || typeof entry !== 'object') return null
  const row = entry as Record<string, unknown>
  if (typeof row.kind !== 'string' || !row.kind) return null
  return {
    kind: row.kind,
    labels: stringRecord(row.labels) ?? { kind: row.kind },
    denied_by: typeof row.denied_by === 'string' ? row.denied_by : '',
    reason: typeof row.reason === 'string' ? row.reason : '',
  }
}

/**
 * Read the problem-details `code`, including bodies nested under `cause`/`data`.
 *
 * Deliberately self-contained rather than reusing `getErrorCode`, so mutation
 * handlers keep recognizing the denial even where `utils/apiErrors` is mocked.
 */
function readErrorCode(error: unknown): string | undefined {
  if (!error || typeof error !== 'object') return undefined
  const err = error as Record<string, unknown>
  if (typeof err.code === 'string') return err.code
  for (const wrapper of ['cause', 'data'] as const) {
    const nested = err[wrapper]
    if (nested && typeof nested === 'object') {
      const code = (nested as Record<string, unknown>).code
      if (typeof code === 'string') return code
    }
  }
  return undefined
}

/**
 * True when a workflow save, publish or restore was refused because it would
 * introduce a node kind the principal may not write.
 *
 * Kinds already present in the last saved version are always allowed, so this
 * only fires for kinds the attempted save adds (F-7/F-8).
 */
export function isNodeKindWriteDeniedError(error: unknown): boolean {
  return readErrorCode(error) === NODE_KIND_WRITE_DENIED_CODE
}

/** Read the denied node kinds out of a `NODE_KIND_WRITE_DENIED` problem-details body. */
export function extractNodeKindDenials(error: unknown): NodeKindDenial[] {
  const body = unwrapErrorBody(error)
  if (!body || !Array.isArray(body.denied_kinds)) return []
  return body.denied_kinds.reduce<NodeKindDenial[]>((denials, entry) => {
    const denial = toDenial(entry)
    if (denial) denials.push(denial)
    return denials
  }, [])
}

/** Render one denial as `kind (denied by policy-name)`. */
function describeDenial(denial: NodeKindDenial): string {
  const labelSet = describeNodeLabels(denial.kind, denial.labels)
  if (!denial.denied_by) return labelSet
  const hasAttributes = labelSet !== denial.kind
  return hasAttributes
    ? `${labelSet} — denied by ${denial.denied_by}`
    : `${denial.kind} (denied by ${denial.denied_by})`
}

/**
 * Build the alert for a refused save, or `null` when the error is something else.
 *
 * The workflow is not saved and the canvas is left untouched, so the message
 * names the offending kinds and the policies that denied them instead of the
 * generic backend detail string.
 *
 * @param error Error thrown by the save, publish or restore mutation.
 * @param action Verb for the alert title, for example `save` or `publish`.
 */
export function nodeKindWriteDeniedAlert(
  error: unknown,
  action: string
): { title: string; description: string } | null {
  if (!isNodeKindWriteDeniedError(error)) return null

  const denials = extractNodeKindDenials(error)
  const kinds = denials.map(describeDenial).join(', ')
  const description = kinds
    ? `Your changes were not saved. You are not allowed to add nodes of kind: ${kinds}.`
    : 'Your changes were not saved. You are not allowed to add one or more of the node kinds in this workflow.'

  return { title: `Cannot ${action} workflow: node kind not allowed`, description }
}
