/** Step name written when an unhealthy alert is sent (must match workflow YAML). */
export const UNHEALTHY_ALERT_STEP = 'Send unhealthy alert';

/** Step name written when a recovery alert is sent (must match workflow YAML). */
export const RECOVERY_ALERT_STEP = 'Send recovery alert';

/**
 * Marker step recorded every run when the queue is unhealthy.
 * Lets the next run infer steady unhealthy state when no alert fired.
 */
export const UNHEALTHY_MARKER_STEP = 'Health is unhealthy';

/**
 * Marker step recorded every run when the queue is healthy.
 * Lets the next run infer steady healthy state when no alert fired.
 */
export const HEALTHY_MARKER_STEP = 'Health is healthy';

export type PreviousHealth = 'healthy' | 'unhealthy' | 'unknown';
export type CurrentHealth = 'healthy' | 'unhealthy';
export type AlertKind = 'unhealthy' | 'recovery' | 'none';

type JobStep = {
  name?: string;
  conclusion?: string | null;
};

type WorkflowJob = {
  steps?: JobStep[] | null;
};

function stepSucceeded(steps: JobStep[], name: string): boolean {
  return steps.some((step) => step.name === name && step.conclusion === 'success');
}

/**
 * Infers the health state the previous monitoring run ended in.
 * Prefers alert steps (transition runs), then health marker steps (steady state).
 */
export function inferPreviousHealthFromJobs(
  jobs: WorkflowJob[]
): PreviousHealth {
  const steps = jobs[0]?.steps ?? [];

  // Alert steps are authoritative for the run that sent them
  if (stepSucceeded(steps, RECOVERY_ALERT_STEP)) {
    return 'healthy';
  }

  if (stepSucceeded(steps, UNHEALTHY_ALERT_STEP)) {
    return 'unhealthy';
  }

  // Marker steps record assessed health even when no alert was sent
  if (stepSucceeded(steps, HEALTHY_MARKER_STEP)) {
    return 'healthy';
  }

  if (stepSucceeded(steps, UNHEALTHY_MARKER_STEP)) {
    return 'unhealthy';
  }

  return 'unknown';
}

/**
 * Decides which Slack alert (if any) to send given current vs previous health.
 * Alerts only on transitions; steady unhealthy/healthy yields none.
 */
export function decideAlert(
  currentHealth: CurrentHealth,
  previousHealth: PreviousHealth
): AlertKind {
  if (
    currentHealth === 'unhealthy' &&
    (previousHealth === 'healthy' || previousHealth === 'unknown')
  ) {
    return 'unhealthy';
  }

  if (currentHealth === 'healthy' && previousHealth === 'unhealthy') {
    return 'recovery';
  }

  return 'none';
}
