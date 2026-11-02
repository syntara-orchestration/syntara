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
import { fillCodeEditor } from '../helpers/workflows'
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
    test('opens the retry plan and cancel closes it without retrying', async ({ app }, testInfo) => {
      await stubWorkflowEditPermission(app, true)
      await app.setViewportSize({ width: 1600, height: 1000 })
      await openExecutionDetail(app, FAILED_EXECUTION_ID)

      await openRetryActionsMenu(app)
      await app.getByTestId('retry-from-failure-button').click()

      const panel = app.getByRole('complementary', { name: 'Retry run from failure review' })
      await expect(panel).toBeVisible()
      await expect(panel.getByRole('heading', { name: 'Retry run from failure' })).toBeVisible()
      await expect(panel.getByRole('heading', { name: 'How retry works' })).toBeVisible()
      await expect(
        panel.getByText(/This retry uses the same workflow version as this run, preserving the definition that ran/)
      ).toBeVisible()
      await expect(panel.getByText(/Nodes outside the selected retry scope will not re-execute/)).toBeVisible()
      await expect(panel.getByText(/may repeat external side effects/)).toBeVisible()
      await expect(panel.getByText(/To change the parameters for this retry, select the failed node/)).toBeVisible()
      await expect(panel.getByRole('heading', { name: 'Retry plan' })).toBeVisible()
      const retryPlanCard = panel.getByTestId('retry-plan-card')
      await expect(retryPlanCard).toBeVisible()
      const retryPlanHeadingBounds = await panel.getByRole('heading', { name: 'Retry plan' }).evaluate((element) => {
        return element.getBoundingClientRect()
      })
      const retryPlanCardBounds = await retryPlanCard.evaluate((element) => element.getBoundingClientRect())
      expect(retryPlanCardBounds.top - retryPlanHeadingBounds.bottom).toBeGreaterThan(4)
      await expect(retryPlanCard.getByText('2 steps will be retried')).toBeVisible()
      await expect(retryPlanCard.getByText('Includes affected steps and any downstream merge step')).toBeVisible()
      await expect(retryPlanCard.getByText('Retry starts at')).toBeVisible()
      await expect(retryPlanCard.getByText('Retained results')).toBeVisible()
      const retryPlanCardBorderWidth = await retryPlanCard.evaluate((element) =>
        Number.parseFloat(window.getComputedStyle(element).borderTopWidth)
      )
      expect(retryPlanCardBorderWidth).toBe(1)
      await expect(app.getByRole('tab', { name: 'Details' })).toHaveAttribute('aria-selected', 'true')
      await expect(panel.getByRole('button', { name: 'Retry 2 steps' })).toBeVisible()
      await expect(app.getByRole('button', { name: 'Copy to editor' })).toHaveCount(0)
      await expect(app.getByRole('button', { name: 'Back to editor' })).toHaveCount(0)
      await expect(app.getByRole('button', { name: 'Run history' })).toHaveCount(0)
      await app.screenshot({ path: testInfo.outputPath('retry-plan-prototype-copy.png') })

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
      const retryPlanCard = panel.getByTestId('retry-plan-card')
      await expect(retryPlanCard.getByRole('radiogroup', { name: 'Retry scope' })).toBeVisible()
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
      await app.setViewportSize({ width: 1600, height: 1000 })
      await openExecutionDetail(app, FAILED_EXECUTION_ID)
      await app.getByRole('tab', { name: 'Details' }).click()

      // Give the code editor the same vertical space shown in the retry prototype.
      const detailsPanelSplitter = app.getByRole('separator', { name: 'Resize canvas and details panel' })
      for (let resizeStep = 0; resizeStep < 12; resizeStep += 1) {
        await detailsPanelSplitter.press('ArrowUp')
      }
      await expect(detailsPanelSplitter).toHaveAttribute('aria-valuenow', '88')

      await app.getByRole('row', { name: /Second Step/ }).click()
      await openRetryActionsMenu(app)
      await app.getByTestId('retry-from-failure-button').click()

      await expect(app.getByRole('tab', { name: 'Details' })).toHaveAttribute('aria-selected', 'true')
      await expect(app.getByText(/^Elapsed time:/)).toHaveCount(1)
      await expect(app.getByText(/"language": "bash"/, { exact: false })).toBeVisible()
      await app.getByRole('button', { name: 'Edit parameters for retry' }).click()

      const saveButton = app.getByRole('button', { name: 'Save parameters for retry' })
      await expect(saveButton).toBeVisible()
      const saveButtonFitsEditorPane = await saveButton.evaluate((button) => {
        const editorPane = button.closest('[data-testid="retry-input-override-editor"]')
        if (!editorPane) return false

        const paneRect = editorPane.getBoundingClientRect()
        const buttonRect = button.getBoundingClientRect()
        return buttonRect.top >= paneRect.top && buttonRect.bottom <= paneRect.bottom
      })
      expect(saveButtonFitsEditorPane).toBe(true)
      await fillCodeEditor(app, { value: '{"code":"echo retry"}', label: 'Input parameters for Second Step' })
      await expect(app.getByTestId('inline-code-editor')).toBeInViewport()
      await app.screenshot({ path: testInfo.outputPath('retry-input-overrides-editing.png') })
      const retryButton = app.getByRole('button', { name: 'Retry 2 steps' })
      await expect(retryButton).toBeDisabled()
      await saveButton.click()

      await expect(app.getByText('Edited for retry')).toBeInViewport()
      await expect(app.getByText(/"code": "echo retry"/, { exact: false })).toBeVisible()
      await expect(retryButton).toBeEnabled()
      await app.screenshot({ path: testInfo.outputPath('retry-input-overrides-saved.png') })

      const inputTitle = app.getByText('Input parameters', { exact: true })
      const inputTitleBounds = await inputTitle.evaluate((element) => {
        const bounds = element.getBoundingClientRect()
        return { left: bounds.left, top: bounds.top, right: bounds.right, bottom: bounds.bottom }
      })
      const editedBadgeBounds = await app.getByText('Edited for retry').evaluate((element) => {
        const bounds = element.getBoundingClientRect()
        return { left: bounds.left, top: bounds.top }
      })
      expect(Math.abs(inputTitleBounds.top - editedBadgeBounds.top)).toBeLessThanOrEqual(4)

      const editButtonBounds = await app
        .getByRole('button', { name: 'Edit parameters for retry' })
        .evaluate((element) => {
          const bounds = element.getBoundingClientRect()
          return { left: bounds.left, top: bounds.top, bottom: bounds.bottom }
        })
      expect(editButtonBounds.top).toBeLessThan(inputTitleBounds.bottom)
      expect(editButtonBounds.bottom).toBeGreaterThan(inputTitleBounds.top)
      expect(editButtonBounds.left).toBeGreaterThan(inputTitleBounds.right)

      const searchInput = app.getByRole('textbox', { name: 'Search input parameters data' })
      const viewToggle = app.getByRole('group', { name: 'Input parameters view selection' })
      const searchBounds = await searchInput.evaluate((element) => {
        const bounds = element.getBoundingClientRect()
        return { left: bounds.left, top: bounds.top, bottom: bounds.bottom, width: bounds.width }
      })
      const viewToggleBounds = await viewToggle.evaluate((element) => {
        const bounds = element.getBoundingClientRect()
        return { left: bounds.left, top: bounds.top, width: bounds.width }
      })
      expect(viewToggleBounds.top).toBeGreaterThan(searchBounds.bottom)
      expect(Math.abs(searchBounds.left - viewToggleBounds.left)).toBeLessThan(2)
      expect(Math.abs(searchBounds.width - viewToggleBounds.width)).toBeLessThan(3)

      const outputSearchInput = app.getByRole('textbox', { name: 'Search output data' })
      const outputViewToggle = app.getByRole('group', { name: 'Output view selection' })
      const outputSearchBounds = await outputSearchInput.evaluate((element) => {
        const bounds = element.getBoundingClientRect()
        return { left: bounds.left, top: bounds.top, bottom: bounds.bottom, width: bounds.width }
      })
      const outputViewToggleBounds = await outputViewToggle.evaluate((element) => {
        const bounds = element.getBoundingClientRect()
        return { left: bounds.left, top: bounds.top, width: bounds.width }
      })
      expect(outputViewToggleBounds.top).toBeGreaterThan(outputSearchBounds.bottom)
      expect(Math.abs(outputSearchBounds.left - outputViewToggleBounds.left)).toBeLessThan(2)
      expect(Math.abs(outputSearchBounds.width - outputViewToggleBounds.width)).toBeLessThan(3)
      expect(Math.abs(outputSearchBounds.top - searchBounds.top)).toBeLessThanOrEqual(2)
      expect(Math.abs(outputViewToggleBounds.top - viewToggleBounds.top)).toBeLessThanOrEqual(2)

      await app.getByRole('button', { name: 'Edit parameters for retry' }).click()
      await expect(app.getByTestId('inline-code-editor').locator('.view-lines')).toContainText('echo retry')
      await expect(app.getByRole('button', { name: 'Reset parameters' })).toBeVisible()
      await fillCodeEditor(app, {
        value: `${JSON.stringify({ code: 'echo retry' }, null, 2)}${'\n'.repeat(80)}`,
        label: 'Input parameters for Second Step',
      })
      const monacoScrollTop = await app.getByTestId('inline-code-editor').evaluate((container) => {
        type ScrollableEditor = {
          getDomNode: () => HTMLElement | null
          getLayoutInfo: () => { height: number }
          getScrollHeight: () => number
          getScrollTop: () => number
          setScrollTop: (scrollTop: number) => void
        }
        const monacoWindow = window as Window & {
          monaco?: { editor: { getEditors: () => ScrollableEditor[] } }
        }
        const editor = monacoWindow.monaco?.editor.getEditors().find((candidate) => {
          const editorElement = candidate.getDomNode()
          return editorElement !== null && container.contains(editorElement)
        })
        if (!editor) throw new Error('Retry input Monaco editor was not found')
        const scrollHeight = editor.getScrollHeight()
        const viewportHeight = editor.getLayoutInfo().height
        editor.setScrollTop(editor.getScrollHeight())
        return { scrollHeight, viewportHeight, scrollTop: editor.getScrollTop() }
      })
      expect(monacoScrollTop.scrollHeight).toBeGreaterThan(monacoScrollTop.viewportHeight)
      expect(monacoScrollTop.scrollTop).toBeGreaterThan(0)
      await expect(app.getByRole('button', { name: 'Save parameters for retry' })).toBeInViewport()
      await app.screenshot({ path: testInfo.outputPath('retry-input-overrides-editing-scrolled.png') })
      await app.getByTestId('retry-input-override-editor').getByRole('button', { name: 'Cancel' }).click()
      await expect(app.getByText('Edited for retry')).toBeVisible()

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
      await expect(app.getByRole('button', { name: 'Edit parameters for retry' })).toHaveCount(0)
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
