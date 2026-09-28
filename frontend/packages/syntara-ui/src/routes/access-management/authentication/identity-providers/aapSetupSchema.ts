import { z } from 'zod'

const authMethods = ['credentials', 'token'] as const
type AuthMethod = (typeof authMethods)[number]

export const aapSetupSchema = z
  .object({
    aap_url: z.string().min(1, 'Ansible Automation Platform URL is required').url('Must be a valid URL'),
    organization: z.string().min(1, 'Organization is required').max(64, 'Organization must be 64 characters or fewer'),
    auth_method: z.enum(authMethods),
    admin_username: z.string().max(150, 'Username must be 150 characters or fewer'),
    admin_password: z.string(),
    personal_access_token: z.string(),
    insecure_skip_tls_verify: z.boolean(),
  })
  .superRefine((data, ctx) => {
    if (data.auth_method === 'credentials') {
      if (!data.admin_username) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Platform admin username is required',
          path: ['admin_username'],
        })
      }
      if (!data.admin_password) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Platform admin password is required',
          path: ['admin_password'],
        })
      }
    } else if (!data.personal_access_token) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Personal access token is required',
        path: ['personal_access_token'],
      })
    }
  })

export type AAPSetupFormData = z.infer<typeof aapSetupSchema>
export type { AuthMethod }
