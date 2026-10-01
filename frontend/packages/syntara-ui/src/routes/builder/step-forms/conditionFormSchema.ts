import { z } from 'zod'

/**
 * Zod schema for the Condition step form.
 *
 * **Backend Evaluation Architecture (Two-Tier):**
 *
 * The condition expressions written in the UI use JavaScript syntax (&&, ||, !, 'contains')
 * but are transformed to Python operators (and, or, not, in) by the visual builder
 * before being sent to the backend. Note: 'contains' in UI becomes 'in' in Python.
 *
 * The backend evaluates conditions using a two-tier architecture:
 *
 * **Tier 1 (Template Substitution)**: `NamespaceResolver.resolve_value()`
 * - Used for ALL non-condition fields (inputs, outputs, loop items, etc.)
 * - String interpolation with str() for value conversion
 * - Example: "${status}" → "completed" when status = "completed"
 *
 * **Tier 2 (Context-Aware AST Evaluation)**: `safe_eval_with_namespace()`
 * - Used EXCLUSIVELY for boolean condition expressions
 * - AST evaluation with direct namespace lookup (no string substitution)
 * - Values preserve original types (no repr() conversion)
 * - Eliminates string quoting issues (quotes, backslashes in values)
 * - Better security (no string concatenation before eval)
 * - Example: "${status} == 'completed'" evaluated with namespace {"status": "completed"}
 *
 * This means condition expressions are validated in the frontend using JavaScript semantics,
 * transformed to Python syntax, and then evaluated using AST with full type preservation.
 */
export const conditionFormSchema = z.object({
  name: z.string(),
  condition: z.string().optional(),
})

export type ConditionFormData = z.infer<typeof conditionFormSchema>
