import type { TaskActivity } from '@syntara/contracts'
import type { ReactNode } from 'react'

import { detectTaskExecutorType } from './common/detectTaskExecutorType'
import { renderStepIcon, type StepIconVariant } from './renderStepIcon'
import { getTaskIconDescriptor } from './stepIconResolver'
import { executorMetadata } from './stepMetadata'

/** Canvas icon for a task-shaped step (detailed header or semantic zoom tile). */
export function getTaskCanvasIcon(
  data: TaskActivity,
  iconColor?: string,
  variant: StepIconVariant = 'canvas'
): ReactNode | undefined {
  const { actualExecutor } = detectTaskExecutorType(data)
  const executorMeta = executorMetadata[actualExecutor] ?? executorMetadata[data.type ?? '']
  const { id: iconId } = getTaskIconDescriptor(data)
  return renderStepIcon(executorMeta?.icon, iconId, variant, iconColor)
}
