import type { TaskActivity } from '@syntara/contracts'

import { semanticZoomActivityTitle } from '../semanticZoom'

import { detectTaskExecutorType } from './common/detectTaskExecutorType'
import { executorMetadata } from './stepMetadata'

/**
 * Title and type label for semantic-zoom tooltips on task-shaped canvas nodes.
 */
export function getTaskSemanticLabels(data: TaskActivity): { title: string; typeLabel: string } {
  const { actualExecutor } = detectTaskExecutorType(data)
  const executorMeta = executorMetadata[actualExecutor]
  const typeLabel = executorMeta?.label ?? 'Task'

  return {
    title: semanticZoomActivityTitle(data.name, 'Untitled task'),
    typeLabel,
  }
}
