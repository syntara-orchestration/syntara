/** Step name written when an unhealthy alert is sent (must match workflow YAML). */
export const UNHEALTHY_ALERT_STEP = 'Send unhealthy alert';

/** Step name written when a recovery alert is sent (must match workflow YAML). */
export const RECOVERY_ALERT_STEP = 'Send recovery alert';

type JobStep = {
  name?: string;
  conclusion?: string | null;
};

type WorkflowJob = {
  steps?: JobStep[] | null;
};

/**
 * Infers the health state the previous monitoring run ended in.
 * Uses which alert step succeeded: recovery → healthy, unhealthy → unhealthy.
 * Returns unknown when neither alert ran (steady state / no transition).
 */
export function inferPreviousHealthFromJobs(
  jobs: WorkflowJob[]
): 'healthy' | 'unhealthy' | 'unknown' {
  const steps = jobs[0]?.steps ?? [];

  const sentUnhealthyAlert = steps.some(
    (step) => step.name === UNHEALTHY_ALERT_STEP && step.conclusion === 'success'
  );

  const sentRecoveryAlert = steps.some(
    (step) => step.name === RECOVERY_ALERT_STEP && step.conclusion === 'success'
  );

  // Recovery alert means the previous run ended healthy
  if (sentRecoveryAlert) {
    return 'healthy';
  }

  // Unhealthy alert means the previous run ended unhealthy
  if (sentUnhealthyAlert) {
    return 'unhealthy';
  }

  return 'unknown';
}
