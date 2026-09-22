import { z } from 'zod'

/** Inline hint shown under the policy name field before validation errors */
export const PROJECT_POLICY_NAME_HINT = 'Lowercase alphanumeric with hyphens (e.g. my-custom-policy)'

/** Inline hint shown under the statements JSON field before validation errors */
export const STATEMENTS_JSON_HINT =
  'JSON array of statement objects with effect, actions, scope and optional conditions fields'

/** Resource type whose actions a deny-effect statement may target (ANSTRAT-1750). */
export const NODE_RESOURCE_TYPE = 'workflow_node'

/** Actions of `workflow_node` that a deny-effect statement may target. */
export const NODE_DENIABLE_ACTIONS = ['write', 'execute', '*'] as const

/** Condition label that pins a `workflow_node` statement to one node kind. */
export const NODE_KIND_LABEL = 'kind'

/** Rejection message when a deny statement targets anything but node actions. */
export const DENY_REQUIRES_NODE_ACTIONS_MESSAGE =
  'A deny statement may only target workflow_node:write, workflow_node:execute or workflow_node:*'

/**
 * True when an action string is a `workflow_node` action a deny may target.
 *
 * @param action Action string such as `workflow_node:write`.
 */
export function isDeniableNodeAction(action: string): boolean {
  const [resourceType, ...rest] = action.split(':')
  if (resourceType !== NODE_RESOURCE_TYPE || rest.length !== 1) return false
  return (NODE_DENIABLE_ACTIONS as readonly string[]).includes(rest[0])
}

/**
 * Mirror of the backend rule: a deny effect is only accepted when every action
 * is a `workflow_node` action. Anything else would risk locking users out, so
 * the backend rejects it with 422 and the form rejects it before submitting.
 *
 * @param statement Parsed policy statement.
 */
export function isDenyEffectAllowed(statement: { effect: string; actions: string[] }): boolean {
  if (statement.effect !== 'deny') return true
  return statement.actions.length > 0 && statement.actions.every(isDeniableNodeAction)
}

/**
 * Statement conditions.
 *
 * `resource_labels` is the structured part the node-kind statements use
 * (`{ kind: "<NodeType>" }`); any other condition key is passed through
 * untouched so existing policies keep round-tripping.
 */
export const policyConditionsSchema = z.looseObject({
  resource_labels: z.record(z.string(), z.string()).optional(),
})

export const policyStatementSchema = z
  .object({
    effect: z.enum(['allow', 'deny']),
    actions: z.array(z.string()).min(1, 'At least one action is required'),
    scope: z.enum(['any', 'self', 'project', 'own']),
    conditions: policyConditionsSchema.optional().nullable(),
  })
  .refine(isDenyEffectAllowed, { message: DENY_REQUIRES_NODE_ACTIONS_MESSAGE, path: ['effect'] })

export const STATEMENTS_JSON_INVALID_MESSAGE =
  'Must be a valid JSON array of statement objects with effect ("allow"/"deny"), actions (string[]), and scope ("any"/"self"/"project"/"own")'

/**
 * Validate the raw statements JSON, returning the first problem to report.
 *
 * @param value Raw textarea contents.
 * @returns `null` when valid, otherwise the message to show.
 */
export function validateStatementsJson(value: string): string | null {
  let parsed: unknown
  try {
    parsed = JSON.parse(value)
  } catch {
    return STATEMENTS_JSON_INVALID_MESSAGE
  }
  if (!Array.isArray(parsed)) return STATEMENTS_JSON_INVALID_MESSAGE

  const result = z.array(policyStatementSchema).safeParse(parsed)
  if (result.success) return null

  const denyIssue = result.error.issues.find((issue) => issue.message === DENY_REQUIRES_NODE_ACTIONS_MESSAGE)
  return denyIssue ? DENY_REQUIRES_NODE_ACTIONS_MESSAGE : STATEMENTS_JSON_INVALID_MESSAGE
}

export const addProjectPolicySchema = z.object({
  name: z
    .string()
    .min(1, 'Name is required')
    .max(255, 'Name must be 255 characters or fewer')
    .regex(
      /^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/,
      'Name must be lowercase alphanumeric with hyphens, starting and ending with a letter or number'
    ),
  description: z.string().max(1024, 'Description must be 1024 characters or fewer').optional().or(z.literal('')),
  statementsJson: z
    .string()
    .min(1, 'Statements are required')
    .superRefine((val, ctx) => {
      const message = validateStatementsJson(val)
      if (message) ctx.addIssue({ code: 'custom', message })
    }),
})

export type AddProjectPolicyFormData = z.infer<typeof addProjectPolicySchema>
export type PolicyStatement = z.infer<typeof policyStatementSchema>
