import { MissedSchedulePolicyEnum, ScheduleTypeEnum, TriggerTypeEnum, WEBHOOK_TRIGGER_TYPES } from '@syntara/contracts'

import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'
import { getBrowserTimezone } from '../../../utils/timezoneList'
import { getDefaultRepeatingInterval } from '../../../utils/triggerFormatting'
import { generateWebhookPath } from '../../../utils/webhookPath'

import type { TriggerFormData } from './triggerFormSchema'

export function buildTriggerFormDefaults(initialData?: Partial<TriggerFormData>): TriggerFormData {
  const values: TriggerFormData = {
    name: '',
    triggerType: initialData?.triggerType ?? TriggerTypeEnum.MANUAL_TRIGGER,
    scheduleType: ScheduleTypeEnum.INTERVAL,
    interval: '',
    cron: '',
    timezone: getBrowserTimezone(),
    missedSchedulePolicy: MissedSchedulePolicyEnum.SKIP,
    inputSchema: '',
    webhookPath: '',
    form_definition: initialData?.form_definition ?? createEmptyFormDefinition(),
    message: '',
    submit_label: '',
    success_message: '',
    css_override: '',
    ...initialData,
  }

  if (WEBHOOK_TRIGGER_TYPES.has(values.triggerType) && !values.webhookPath) {
    values.webhookPath = generateWebhookPath()
  }

  if (
    values.triggerType === TriggerTypeEnum.SCHEDULED &&
    values.scheduleType === ScheduleTypeEnum.INTERVAL &&
    !values.interval?.trim()
  ) {
    values.interval = getDefaultRepeatingInterval(values.timezone ?? 'UTC')
  }

  return values
}
