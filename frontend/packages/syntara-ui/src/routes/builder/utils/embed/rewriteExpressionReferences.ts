/**
 * Expression reference rewriting for Embed Mode.
 *
 * When a published workflow's nodes are copied into the parent workflow at design
 * time, every copied node receives a fresh id (see copyWorkflowGraph). Any template
 * expression inside a copied node that referenced another copied node by its OLD id
 * must be rewritten to the NEW id, so the embedded subgraph is self-contained and
 * carries no reference to the source workflow (SDP R12).
 *
 * Template references use the format `${namespace.field.path}` where the FIRST dotted
 * segment is the referenced node id (see utils/expressions/templateBuilder.ts). This
 * rewriter is STRUCTURAL at the `${...}` + first-segment level — it never does a blind
 * global string replace that could corrupt a field path containing an id-like substring.
 *
 * Non-node namespaces (e.g. `trigger`, `input`, `loop`, `context`) are left untouched.
 * A reference whose namespace is a SOURCE node id that was NOT copied (for example a
 * reference into an excluded trigger, or a node outside the copied set) is left as-is
 * and reported as a dangling reference for the caller to surface.
 *
 * NOTE (verify on-computer): condition/switch nodes may store their operands in a
 * structured form as well as `${...}` strings. This rewriter covers every `${...}`
 * occurrence found in any string value within a node's parameters (recursively), which
 * covers the common case. Confirm the structured condition/switch operand shape and
 * extend `collectStrings`/rewrite accordingly if operands are stored without `${}`.
 */

const TEMPLATE_PATTERN = /\$\{([^}]+)\}/g

export type RewriteResult<T> = {
  value: T
  /** References to a source node id that was not copied (e.g. an excluded trigger). */
  danglingRefs: Array<{ namespace: string; expression: string }>
}

/** Extract the node-id namespace (first dotted segment) from a `${...}` inner body. */
function namespaceOf(inner: string): string {
  const trimmed = inner.trim()
  const dot = trimmed.indexOf('.')
  return dot === -1 ? trimmed : trimmed.slice(0, dot)
}

function rewriteString(
  value: string,
  idMap: ReadonlyMap<string, string>,
  sourceNodeIds: ReadonlySet<string>,
  dangling: Array<{ namespace: string; expression: string }>
): string {
  return value.replace(TEMPLATE_PATTERN, (match, inner: string) => {
    const namespace = namespaceOf(inner)
    const newId = idMap.get(namespace)
    if (newId !== undefined) {
      // Preserve everything after the node-id segment verbatim (field path, brackets).
      const rest = inner.trim().slice(namespace.length)
      return `\${${newId}${rest}}`
    }
    // Namespace is a source node that was not copied → dangling (e.g. excluded trigger).
    if (sourceNodeIds.has(namespace)) {
      dangling.push({ namespace, expression: match })
    }
    // Otherwise it is a non-node namespace (trigger/input/loop/context) — leave untouched.
    return match
  })
}

/**
 * Recursively rewrite every `${sourceNodeId...}` reference in an arbitrary JSON value,
 * mapping copied source node ids to their new ids. Returns a new value (no mutation).
 */
export function rewriteExpressionReferences<T>(
  value: T,
  idMap: ReadonlyMap<string, string>,
  sourceNodeIds: ReadonlySet<string>
): RewriteResult<T> {
  const danglingRefs: Array<{ namespace: string; expression: string }> = []

  const walk = (node: unknown): unknown => {
    if (typeof node === 'string') return rewriteString(node, idMap, sourceNodeIds, danglingRefs)
    if (Array.isArray(node)) return node.map(walk)
    if (node !== null && typeof node === 'object') {
      const out: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(node)) out[k] = walk(v)
      return out
    }
    return node
  }

  return { value: walk(value) as T, danglingRefs }
}
