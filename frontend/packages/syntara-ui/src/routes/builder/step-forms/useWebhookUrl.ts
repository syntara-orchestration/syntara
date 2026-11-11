import { useFormContext, useWatch } from 'react-hook-form'

import { normalizeWebhookPath, type TriggerFormData } from './triggerFormSchema'

/** Derive the full webhook URL from the current form's `webhookPath` field. */
export function useWebhookUrl(baseUrl: string): string {
  const { control } = useFormContext<TriggerFormData>()
  const webhookPath = useWatch({ control, name: 'webhookPath' })
  const cleanPath = normalizeWebhookPath(webhookPath ?? '')
  return cleanPath ? `${baseUrl}/${cleanPath}` : baseUrl
}
