/**
 * E2E Tests: Retry from failure
 *
 * Objective: Verify the user-visible retry-from-failure flow on the execution
 * detail page — eligibility, the retry review panel, starting a retry, and the
 * replay indicators that tell an operator which steps reused a previous run's
 * output.
 *
 * Runs against the mock API, which seeds the states a retry-from-failure needs
 * and that a real engine cannot reliably reproduce on demand:
 * - `exec-retry-demo`  — a FAILED run (step1 completed, step2 failed) with real
 *                        eligible retry points.
 * - `exec-1`           — a COMPLETED run, which is not eligible for retry *from
 *                        failure* (only a full re-run).
 * - `exec-3-retry`     — a run created by retrying `exec-3`, carrying the
 *                        "Retried from" indicator.
 *
 * The seeded UI cases below are skipped in real-backend mode. The companion
 * retry-from-failure-live.spec.ts provisions real workflows and executions so
 * Konflux exercises the feature against Temporal instead of relying on seeds.
 *
 * Critical paths covered:
 * - Retry offered on a failed run, hidden on a completed run.
 * - Retry review panel: open → plan → cancel.
 * - Confirm → "Retry started" → land on a new run marked "Retried from".
 * - "Retried from" badge on an already-retried run.
 * - "Reused output" badge on a step the retry replayed from the source run.
 * - Accessibility of the retry review panel.
 */

import AxeBuilder from '@axe-core/playwright'

import { test, expect, toAppUrl, type Page } from '../fixtures'
import { WCAG_TAGS } from '../fixtures/accessibility'
import { isSkipWebServerForPlaywrightTests } from '../playwrightWebServerEnv'

const isRealBackend = isSkipWebServerForPlaywrightTests()

const FAILED_EXECUTION_ID = 'exec-retry-demo'
const COMPLETED_EXECUTION_ID = 'exec-1'
const RETRIED_EXECUTION_ID = 'exec-3-retry'

/** Open a seeded execution's detail page and wait for it to render. */
async function openExecutionDetail(app: Page, executionId: string): Promise<void> {
  await app.goto(toAppUrl(`/executions/${executionId}`))
  await expect(app.getByRole('heading', { level: 1 })).toBeVisible()
}

/** Open the retry actions dropdown. */
async function openRetryActionsMenu(app: Page): Promise<void> {
  await app.getByRole('button', { name: 'Retry' }).click()
  // Execution permission checks resolve asynchronously; avoid clicking the
  // menu item while it is still aria-disabled during the check.
  await expect(app.getByTestId('retry-from-failure-button')).toBeEnabled()
}

/** Stub only workflow edit permission; let the mock API answer every other check. */
async function stubWorkflowEditPermission(app: Page, allowed: boolean): Promise<void> {
  await app.route('**/api/v1/authz/can_i', async (route) => {
    const payload: unknown = route.request().postDataJSON()
    const isWorkflowUpdateCheck =
      typeof payload === 'object' &&
      payload !== null &&
      'action' in payload &&
      payload.action === 'update' &&
      'resource_type' in payload &&
      payload.resource_type === 'workflow'

    if (isWorkflowUpdateCheck) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ allowed }),
      })
      return
    }

    await route.continue()
  })
}

/** Give the demo run two retry points so the scope selector is rendered. */
async function stubMultipleRetryFailurePoints(app: Page): Promise<void> {
  await app.route(`**/api/v1/executions/${FAILED_EXECUTION_ID}/retry_from_failure_preview**`, async (route) => {
    const requestedPointIds = new URL(route.request().url()).searchParams.getAll('retry_point_ids')
    const allPointIds = ['step1', 'step2']
    const eligiblePointIds = requestedPointIds.length > 0 ? requestedPointIds : allPointIds
    const stepCountByEligiblePoint = Object.fromEntries(eligiblePointIds.map((id) => [id, id === 'step2' ? 2 : 1]))

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        eligible: true,
        reason: null,
        eligible_point_ids: eligiblePointIds,
        sanitized_node_ids: [],
        auto_included_node_ids: [],
        sanitized_replacements: {},
        step_count_by_eligible_point: stepCountByEligiblePoint,
        total_step_count: Object.values(stepCountByEligiblePoint).reduce((total, count) => total + count, 0),
        retained_result_count: 0,
      }),
    })
  })
}

/**
 * Scan only the retry panel. The execution detail page embeds a ReactFlow
 * canvas and PatternFly tabs with pre-existing, unrelated axe findings, so a
 * whole-page scan here would report violations this feature does not own.
 */
async function expectRetryPanelHasNoA11yViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page })
    .include('[data-testid="retry-from-failure-panel"]')
    .withTags([...WCAG_TAGS])
    .analyze()
  expect(results.violations).toEqual([])
}

test.describe('Retry from failure', { tag: '@local-only' }, () => {
  test.skip(isRealBackend, 'relies on mock API seed data')

  test.describe('Execution detail — eligibility', () => {
    test('offers retry from failure on a failed run', async ({ app }) => {
      await openExecutionDetail(app, FAILED_EXECUTION_ID)

      await openRetryActionsMenu(app)
      await expect(app.getByTestId('retry-from-failure-button')).toBeVisible()
    })

    test('does not offer retry from failure on a completed run', async ({ app }) => {
      await openExecutionDetail(app, COMPLETED_EXECUTION_ID)

      await expect(app.getByTestId('retry-from-failure-button')).toHaveCount(0)
      await expect(app.getByRole('button', { name: 'Retry run' })).toBeVisible()
    })
  })

  test.describe('Retry review panel', () => {
    test('opens the retry plan and cancel closes it without retrying', async ({ app }) => {
      await stubWorkflowEditPermission(app, true)
      await openExecutionDetail(app, FAILED_EXECUTION_ID)

      await openRetryActionsMenu(app)
      await app.getByTestId('retry-from-failure-button').click()

      const panel = app.getByRole('complementary', { name: 'Retry run from failure review' })
      await expect(panel).toBeVisible()
      await expect(panel.getByRole('heading', { name: 'Retry run from failure' })).toBeVisible()
      await expect(panel.getByRole('heading', { name: 'How retry works' })).toBeVisible()
      await expect(panel.getByRole('heading', { name: 'Retry plan' })).toBeVisible()
      await expect(app.getByRole('tab', { name: 'Details' })).toHaveAttribute('aria-selected', 'true')
      await expect(panel.getByRole('button', { name: 'Retry 2 steps' })).toBeVisible()
      await expect(app.getByRole('button', { name: 'Copy to editor' })).toHaveCount(0)
      await expect(app.getByRole('button', { name: 'Back to editor' })).toHaveCount(0)
      await expect(app.getByRole('button', { name: 'Run history' })).toHaveCount(0)

      await panel.getByRole('button', { name: 'Cancel' }).click()
      await expect(panel).not.toBeVisible()
      // Cancelling must not navigate away from the source run.
      await expect(app).toHaveURL(new RegExp(`/executions/${FAILED_EXECUTION_ID}$`))
    })

    test('canvas selection does not change retry scope and the origin marker stays clear of its step', async ({
      app,
    }) => {
      await stubMultipleRetryFailurePoints(app)
      await openExecutionDetail(app, FAILED_EXECUTION_ID)
      const failedStep = app.getByTestId('rf__node-step2').getByRole('heading', { name: 'Second Step', level: 2 })
      await failedStep.click()
      await openRetryActionsMenu(app)
      await app.getByTestId('retry-from-failure-button').click()

      const panel = app.getByRole('complementary', { name: 'Retry run from failure review' })
      const allPoints = panel.getByRole('radio', { name: 'All eligible failure points' })
      const choosePoints = panel.getByRole('radio', { name: 'Choose failure points' })
      const retryOrigin = app.getByTestId('retry-origin-step2')
      const stepNode = app.locator('.react-flow__node[data-id="step2"]')

      await expect(allPoints).toBeChecked()
      await expect(choosePoints).not.toBeChecked()
      await expect(retryOrigin).toBeVisible()

      const markerBox = await retryOrigin.boundingBox()
      const stepNodeBox = await stepNode.boundingBox()
      if (markerBox === null || stepNodeBox === null) {
        throw new Error('Could not measure the retry origin marker and failed step')
      }
      const markerGap = stepNodeBox.y - (markerBox.y + markerBox.height)
      expect(markerGap).toBeGreaterThanOrEqual(0)
      expect(markerGap).toBeLessThanOrEqual(24)

      await failedStep.click()

      await expect(allPoints).toBeChecked()
      await expect(choosePoints).not.toBeChecked()
      await expect(panel.getByRole('button', { name: 'Retry 3 steps' })).toBeVisible()
    })

    test('confirming starts a retry and lands on a run marked "Retried from" @pr-check', async ({ app }) => {
      await openExecutionDetail(app, FAILED_EXECUTION_ID)

      await openRetryActionsMenu(app)
      await app.getByTestId('retry-from-failure-button').click()

      const panel = app.getByRole('complementary', { name: 'Retry run from failure review' })
      await expect(panel).toBeVisible()
      await panel.getByTestId('retry-from-failure-confirm').click()

      await expect(app.getByText('Retry started')).toBeVisible()

      // The new run opens on its own detail page, distinct from the source.
      await expect(() => {
        const url = app.url()
        expect(url).toMatch(/\/executions\/[^/]+$/)
        expect(url).not.toContain(FAILED_EXECUTION_ID)
      }).toPass({ timeout: 10_000, intervals: [500] })

      await expect(app.getByTestId('retried-from-badge')).toBeVisible()
      await expect(app.getByTestId('retried-from-badge')).toContainText('Retried from:')
    })

    test('edits resolved inputs in Run details and labels them for retry', async ({ app }, testInfo) => {
      await stubWorkflowEditPermission(app, true)
      await openExecutionDetail(app, FAILED_EXECUTION_ID)
      await app.getByRole('tab', { name: 'Details' }).click()
      await app.getByRole('row', { name: /First Step/ }).click()
      await openRetryActionsMenu(app)
      await app.getByTestId('retry-from-failure-button').click()

      await expect(app.getByRole('tab', { name: 'Details' })).toHaveAttribute('aria-selected', 'true')
      await expect(app.getByText(/"language": "bash"/, { exact: false })).toBeVisible()
      await app.getByRole('button', { name: 'Edit inputs' }).click()

      const editor = app.getByRole('textbox', { name: /Input overrides for/ })
      await editor.fill('{"code":"echo retry"}')
      await expect(editor).toBeInViewport()
      await app.screenshot({ path: testInfo.outputPath('retry-input-overrides-editing.png') })
      const retryButton = app.getByRole('button', { name: 'Retry 2 steps' })
      await expect(retryButton).toBeDisabled()
      await app.getByRole('button', { name: 'Save inputs' }).click()

      await expect(app.getByText('Effective inputs for retry')).toBeInViewport()
      await expect(app.getByText(/"code": "echo retry"/, { exact: false })).toBeVisible()
      await expect(retryButton).toBeEnabled()
      await app.screenshot({ path: testInfo.outputPath('retry-input-overrides-saved.png') })

      const retryRequestPromise = app.waitForRequest(
        (request) =>
          request.method() === 'POST' &&
          request.url().endsWith(`/api/v1/executions/${FAILED_EXECUTION_ID}/retry_from_failure`)
      )
      await retryButton.click()
      const retryRequest = await retryRequestPromise
      expect(retryRequest.postDataJSON()).toMatchObject({
        input_parameter_overrides: { step2: { code: 'echo retry' } },
      })
      await expect(app.getByText('Retry started')).toBeVisible()
    })

    test('allows a normal retry but hides input overrides without workflow edit permission', async ({ app }) => {
      await stubWorkflowEditPermission(app, false)

      await openExecutionDetail(app, FAILED_EXECUTION_ID)
      await openRetryActionsMenu(app)
      await app.getByTestId('retry-from-failure-button').click()

      const panel = app.getByRole('complementary', { name: 'Retry run from failure review' })
      await expect(panel).toBeVisible()
      await expect(app.getByRole('tab', { name: 'Details' })).toHaveAttribute('aria-selected', 'true')
      await expect(app.getByText('Workflow edit permission is required to override retry inputs.')).toBeVisible()
      await expect(app.getByRole('button', { name: 'Edit inputs' })).toHaveCount(0)
      await panel.getByTestId('retry-from-failure-confirm').click()
      await expect(app.getByText('Retry started')).toBeVisible()
    })
  })

  test.describe('Replay indicators', () => {
    test('shows a "Retried from" badge on an already-retried run', async ({ app }) => {
      await openExecutionDetail(app, RETRIED_EXECUTION_ID)

      const badge = app.getByTestId('retried-from-badge')
      await expect(badge).toBeVisible()
      await expect(badge).toContainText('Retried from: exec-3')
    })

    test('marks a replayed step with the "Reused output" badge', async ({ app }) => {
      // exec-3-retry reused check_temperature from the source run (its start time
      // predates this run's creation) and ran the downstream steps fresh. The
      // badge renders wherever that replayed step is listed; assert at least one
      // appears regardless of which activity-panel layout is active.
      await openExecutionDetail(app, RETRIED_EXECUTION_ID)

      await expect.poll(() => app.getByTestId('replayed-output-badge').count(), { timeout: 10_000 }).toBeGreaterThan(0)
    })
  })

  test.describe('Accessibility', () => {
    test('open retry review panel has no axe violations', async ({ app }) => {
      await openExecutionDetail(app, FAILED_EXECUTION_ID)

      await openRetryActionsMenu(app)
      await app.getByTestId('retry-from-failure-button').click()
      const panel = app.getByTestId('retry-from-failure-panel')
      await expect(panel).toBeVisible()
      await expect(panel.getByText('Retained results')).toBeVisible()
      await expectRetryPanelHasNoA11yViolations(app)
    })
  })
})
