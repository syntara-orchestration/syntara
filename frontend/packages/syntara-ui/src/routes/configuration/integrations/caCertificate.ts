import { z } from 'zod'

export const CA_CERTIFICATE_REQUIRED_MESSAGE = 'CA certificate is required'

export const CA_CERTIFICATE_HINT = "PEM-encoded CA certificate to trust for this integration's TLS connections."

export const CA_CERTIFICATE_PLACEHOLDER = '-----BEGIN CERTIFICATE-----\n\n-----END CERTIFICATE-----'

/** Adds a field error when an execution-plane CA certificate is missing or blank. */
export function addRequiredCaCertificateIssue(value: string | null | undefined, ctx: z.RefinementCtx): void {
  if (value?.trim()) return
  ctx.addIssue({
    code: z.ZodIssueCode.custom,
    message: CA_CERTIFICATE_REQUIRED_MESSAGE,
    path: ['ca_certificate'],
  })
}
