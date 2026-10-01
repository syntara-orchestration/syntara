import { generateActivityId } from '../../../utils/generateUUID'

import { getStepDisplayName } from './stepNaming'

export function buildNamedActivity<TActivity>(
  baseName: string,
  requestedName: string | undefined,
  buildActivity: (activityId: string, name: string) => TActivity
): { activityId: string; name: string; activity: TActivity } {
  const activityId = generateActivityId()
  const name = getStepDisplayName(baseName, requestedName)
  const activity = buildActivity(activityId, name)

  return { activityId, name, activity }
}

export function buildNamedTrigger<TTrigger>(
  baseName: string,
  requestedName: string | undefined,
  buildTrigger: (triggerId: string, name: string) => TTrigger
): { triggerId: string; name: string; trigger: TTrigger } {
  const triggerId = generateActivityId()
  const name = getStepDisplayName(baseName, requestedName)
  const trigger = buildTrigger(triggerId, name)

  return { triggerId, name, trigger }
}
