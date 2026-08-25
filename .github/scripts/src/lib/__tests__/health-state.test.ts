import { describe, it, expect } from 'vitest';
import {
  inferPreviousHealthFromJobs,
  UNHEALTHY_ALERT_STEP,
  RECOVERY_ALERT_STEP,
} from '../health-state.js';

describe('inferPreviousHealthFromJobs', () => {
  it('returns healthy when the recovery alert step succeeded', () => {
    const health = inferPreviousHealthFromJobs([
      {
        steps: [
          { name: UNHEALTHY_ALERT_STEP, conclusion: 'skipped' },
          { name: RECOVERY_ALERT_STEP, conclusion: 'success' },
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
        ],
      },
    ]);

    expect(health).toBe('unhealthy');
  });

  it('returns unknown when neither alert step ran', () => {
    const health = inferPreviousHealthFromJobs([
      {
        steps: [
          { name: 'Check queue health and notify', conclusion: 'success' },
        ],
      },
    ]);

    expect(health).toBe('unknown');
  });

  it('returns unknown when there are no jobs or steps', () => {
    expect(inferPreviousHealthFromJobs([])).toBe('unknown');
    expect(inferPreviousHealthFromJobs([{ steps: [] }])).toBe('unknown');
    expect(inferPreviousHealthFromJobs([{ steps: null }])).toBe('unknown');
  });

  it('prefers recovery over unhealthy when both somehow succeeded', () => {
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
