import { z } from 'zod'

import { stepSettingsSchema } from './shared/stepSettingsSchema'

// Maximum array lengths to prevent DoS attacks and UI performance issues.
// Limits match backend validation constraints.
// Groups have a lower limit (50 vs 100) because each group can contain many members,
// multiplying the effective number of authorized approvers.
const MAX_APPROVER_USERS = 100
const MAX_APPROVER_GROUPS = 50

/**
 * Zod schema for the Approval step form.
 * Single source of truth for shape and client-side validation.
 */
export const approvalFormSchema = z.object({
  name: z.string(),
  approver_users: z
    .array(z.string())
    .max(MAX_APPROVER_USERS, `Cannot select more than ${MAX_APPROVER_USERS} users`)
    .optional(), // Array of usernames who can approve
  approver_groups: z
    .array(z.string())
    .max(MAX_APPROVER_GROUPS, `Cannot select more than ${MAX_APPROVER_GROUPS} groups`)
    .optional(), // Array of group names whose members can approve
  prompt: z.string().optional(),
  fallback_decision: z.enum(['approve', 'reject']).optional(),
  decision_window: z.number().int().positive().optional(),
  settings: stepSettingsSchema.optional(),
})

export type ApprovalFormData = z.infer<typeof approvalFormSchema>
