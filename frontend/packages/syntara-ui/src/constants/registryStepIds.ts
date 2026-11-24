import { RegistryStepId, type RegistryStepIdUnion } from '@syntara/contracts'

export { RegistryStepId, type RegistryStepIdUnion } from '@syntara/contracts'

/**
 * Set of all AAP (Ansible Automation Platform) step type IDs.
 * Use this to check if a step is any AAP variant instead of manually checking each type.
 *
 * @example
 * if (AAP_STEP_IDS.has(stepId as RegistryStepIdUnion)) {
 *   // Handle AAP step (custom icon, colors, etc.)
 * }
 */
export const AAP_STEP_IDS = new Set<RegistryStepIdUnion>([
  RegistryStepId.AAP_EXECUTION,
  RegistryStepId.AAP_JOB_TEMPLATE,
  RegistryStepId.AAP_WORKFLOW_TEMPLATE,
])
