import type { TaskActivity } from '@syntara/contracts'

import {
  detectTaskExecutorType,
  type TaskActivityWithMetadata as StepTaskActivityWithMetadata,
  type TaskExecutorTypeDetectionResult,
} from './detectTaskExecutorType'

export { DetectedExecutorType } from './detectTaskExecutorType'
export type TaskActivityWithMetadata = StepTaskActivityWithMetadata
export type DetectedNodeTypeResult = TaskExecutorTypeDetectionResult

/** Compatibility wrapper for callers that still use node terminology. */
export function detectTaskNodeType(data: TaskActivity): DetectedNodeTypeResult {
  return detectTaskExecutorType(data)
}
