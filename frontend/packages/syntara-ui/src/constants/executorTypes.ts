import { ActivityTypeEnum } from '@syntara/contracts'

/**
 * SECURITY: API executor types — used to validate metadata overrides from untrusted workflow JSON.
 *
 * Only includes types that correspond to real backend node types (from ActivityTypeEnum).
 * Does NOT include internal-only types like 'aap' to prevent an attacker from forcing
 * arbitrary nodes to render with AAP styling via metadata.__executorType injection.
 */
export const API_EXECUTOR_TYPES = new Set([
  ActivityTypeEnum.SCRIPT,
  ActivityTypeEnum.HTTP_REQUEST,
  ActivityTypeEnum.AGENTIC,
  ActivityTypeEnum.AAP_JOB_TEMPLATE,
  ActivityTypeEnum.APPROVAL,
  ActivityTypeEnum.INTERNAL_ACTIVITY,
] as const)

/**
 * TypeScript type for API executor types (from contracts).
 */
export type ApiExecutorType =
  | 'script'
  | 'http_request'
  | 'agentic'
  | 'aap_job_template'
  | 'approval'
  | 'internal_activity'
