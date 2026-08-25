import { describe, it, expect } from 'vitest';
import {
  decideAlert,
  inferPreviousHealthFromJobs,
  UNHEALTHY_ALERT_STEP,
  RECOVERY_ALERT_STEP,
  UNHEALTHY_MARKER_STEP,
  HEALTHY_MARKER_STEP,
} from '../health-state.js';

describe('inferPreviousHealthFromJobs', () => {
  it('returns healthy when the recovery alert step succeeded', () => {
    const health = inferPreviousHealthFromJobs([
      {
        steps: [
          { name: UNHEALTHY_ALERT_STEP, conclusion: 'skipped' },
          { name: RECOVERY_ALERT_STEP, conclusion: 'success' },
          { name: HEALTHY_MARKER_STEP, conclusion: 'success' },
        ],
      },
    ]);

    expect(health).toBe('healthy');
  });

  it('returns unhealthy when the unhealthy alert step succeeded', () => {
    const health = inferPreviousHealthFromJobs([
      {
        steps: [
          { name: UNHEALTHY_ALERT_STEP, conclusion: 'success' },
          { name: RECOVERY_ALERT_STEP, conclusion: 'skipped' },
          { name: UNHEALTHY_MARKER_STEP, conclusion: 'success' },
        ],
      },
    ]);

    expect(health).toBe('unhealthy');
  });

  it('returns unhealthy from the marker step when no alert fired', () => {
    const health = inferPreviousHealthFromJobs([
      {
        steps: [
          { name: 'Check queue health', conclusion: 'success' },
          { name: UNHEALTHY_MARKER_STEP, conclusion: 'success' },
          { name: UNHEALTHY_ALERT_STEP, conclusion: 'skipped' },
        ],
      },
    ]);

    expect(health).toBe('unhealthy');
  });

  it('returns healthy from the marker step when no alert fired', () => {
    const health = inferPreviousHealthFromJobs([
      {
        steps: [
          { name: 'Check queue health', conclusion: 'success' },
          { name: HEALTHY_MARKER_STEP, conclusion: 'success' },
          { name: RECOVERY_ALERT_STEP, conclusion: 'skipped' },
        ],
      },
    ]);

    expect(health).toBe('healthy');
  });

  it('returns unknown when there are no recognizable steps', () => {
    expect(
      inferPreviousHealthFromJobs([
        { steps: [{ name: 'Check queue health', conclusion: 'success' }] },
      ])
    ).toBe('unknown');
    expect(inferPreviousHealthFromJobs([])).toBe('unknown');
    expect(inferPreviousHealthFromJobs([{ steps: [] }])).toBe('unknown');
    expect(inferPreviousHealthFromJobs([{ steps: null }])).toBe('unknown');
  });

  it('prefers recovery alert over unhealthy alert when both somehow succeeded', () => {
    const health = inferPreviousHealthFromJobs([
      {
        steps: [
          { name: UNHEALTHY_ALERT_STEP, conclusion: 'success' },
          { name: RECOVERY_ALERT_STEP, conclusion: 'success' },
        ],
      },
    ]);

    expect(health).toBe('healthy');
  });
});

describe('decideAlert', () => {
  it('alerts unhealthy on healthy → unhealthy', () => {
    expect(decideAlert('unhealthy', 'healthy')).toBe('unhealthy');
  });

  it('alerts unhealthy on unknown → unhealthy (cold start)', () => {
    expect(decideAlert('unhealthy', 'unknown')).toBe('unhealthy');
  });

  it('does not re-alert while staying unhealthy', () => {
    expect(decideAlert('unhealthy', 'unhealthy')).toBe('none');
  });

  it('alerts recovery on unhealthy → healthy', () => {
    expect(decideAlert('healthy', 'unhealthy')).toBe('recovery');
  });

  it('does not alert while staying healthy', () => {
    expect(decideAlert('healthy', 'healthy')).toBe('none');
  });

  it('does not alert recovery from unknown → healthy', () => {
    expect(decideAlert('healthy', 'unknown')).toBe('none');
  });
});
