import { z } from 'zod'

import { getPasswordComplexityError } from './passwordComplexity'

/** Zod schema for the user create/edit form. */
const baseSchema = z.object({
  username: z.string().min(1, 'Username is required').max(255, 'Username must be 255 characters or fewer'),
  first_name: z.string().max(127, 'First name must be 127 characters or fewer').optional().or(z.literal('')),
  last_name: z.string().max(127, 'Last name must be 127 characters or fewer').optional().or(z.literal('')),
  email: z.string().email('Must be a valid email address').max(255).optional().or(z.literal('')),
  password: z
    .string()
    .optional()
    .or(z.literal(''))
    .superRefine((value, ctx) => {
      if (!value) return
      const error = getPasswordComplexityError(value)
      if (error) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: error,
        })
      }
    }),
  is_enabled: z.boolean(),
  group_names: z.array(z.string()).optional(),
})

/** Schema that enforces password on create mode */
export const userCreateSchema = baseSchema.refine((data) => !!data.password, {
  message: 'Password is required',
  path: ['password'],
})

/** Schema for edit mode — password is optional */
export const userFormSchema = baseSchema

export type UserFormData = z.infer<typeof userFormSchema>
