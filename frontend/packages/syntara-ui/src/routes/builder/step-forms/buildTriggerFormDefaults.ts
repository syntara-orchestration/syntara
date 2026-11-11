import { MissedSchedulePolicyEnum, ScheduleTypeEnum, TriggerTypeEnum, WEBHOOK_TRIGGER_TYPES } from '@syntara/contracts'

import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'
import { getBrowserTimezone } from '../../../utils/timezoneList'
import { getDefaultRepeatingInterval } from '../../../utils/triggerFormatting'
import { generateWebhookPath } from '../../../utils/webhookPath'

import type { TriggerFormData } from './triggerFormSchema'

const STATIC_TRIGGER_DEFAULTS: Omit<TriggerFormData, 'timezone' | 'form_definition'> = {
  name: '',
  triggerType: TriggerTypeEnum.MANUAL_TRIGGER,
  scheduleType: ScheduleTypeEnum.INTERVAL,
  interval: '',
  cron: '',
  missedSchedulePolicy: MissedSchedulePolicyEnum.SKIP,
  inputSchema: '',
  webhookPath: '',
  authorizedServiceAccountIds: undefined,
  message: '',
  submit_label: '',
  success_message: '',
  css_override: '',
}

function baseTriggerFormValues(initialData?: Partial<TriggerFormData>): TriggerFormData {
  return {
    ...STATIC_TRIGGER_DEFAULTS,
    ...initialData,
    timezone: initialData?.timezone ?? getBrowserTimezone(),
    form_definition: initialData?.form_definition ?? createEmptyFormDefinition(),
  }
}

function applyTriggerTypeDefaults(values: TriggerFormData): TriggerFormData {
  const next = { ...values }

  if (WEBHOOK_TRIGGER_TYPES.has(next.triggerType) && !next.webhookPath) {
    next.webhookPath = generateWebhookPath()
  }

  if (
    next.triggerType === TriggerTypeEnum.SCHEDULED &&
    next.scheduleType === ScheduleTypeEnum.INTERVAL &&
    !next.interval?.trim()
  ) {
    next.interval = getDefaultRepeatingInterval(next.timezone ?? 'UTC')
  }

  return next
}

export function buildTriggerFormDefaults(initialData?: Partial<TriggerFormData>): TriggerFormData {
  return applyTriggerTypeDefaults(baseTriggerFormValues(initialData))
}
