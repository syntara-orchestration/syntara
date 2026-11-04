import { z } from 'zod'

const emailSchema = z.email({ error: 'Invalid email address' })
const urlSchema = z
  .url({ error: 'Must be a valid URL' })
  .refine((url) => /^https?:\/\//i.test(url), { message: 'Must be an HTTP or HTTPS URL' })

export function getEmailPatternError(value: string): string | null {
  const result = emailSchema.safeParse(value)
  return result.success ? null : result.error.issues[0].message
}

export function getStringPatternError(valueType: string, value: unknown, pattern: string | undefined): string | null {
  if (valueType !== 'string' || !pattern) return null

  const val = (value as string) ?? ''
  if (!val) return null

  if (pattern === 'url') {
    const result = urlSchema.safeParse(val)
    return result.success ? null : result.error.issues[0].message
  }
  if (pattern === 'email') {
    const result = emailSchema.safeParse(val)
    return result.success ? null : result.error.issues[0].message
  }
  return null
}
