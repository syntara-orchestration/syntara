/**
 * Visual regression tests for PF6 design token migration.
 *
 * Usage:
 *   1. Checkout main, run:  npx playwright test visual-regression --update-snapshots
 *   2. Checkout your branch, run:  npx playwright test visual-regression
 *   3. Playwright compares each screenshot pixel-by-pixel and fails on diff.
 */
import { test, expect, toAppUrl } from '../fixtures'
import { APP_TITLE } from '../helpers/appTitle'
import { addStepPanel } from '../helpers/workflows'

// Allow 0.01 (1%) pixel diff to tolerate sub-pixel text rendering / anti-aliasing noise
const screenshotOptions = { maxDiffPixelRatio: 0.01 } as const

// Baselines are OS-specific (darwin snapshots); skip in CI where runner OS differs
test.describe('Visual regression — PF6 token migration', { tag: '@local-only' }, () => {
  test.skip(!!process.env.CI, 'Visual regression baselines are OS-specific; run locally only')

  test('sidebar navigation (AppDockedNav)', async ({ app }) => {
    await app.goto(toAppUrl('/workflows'))
    const nav = app.getByRole('navigation', { name: 'Main navigation' })
    await expect(nav).toBeVisible()

    await expect(nav).toHaveScreenshot('sidebar-navigation.png', screenshotOptions)
  })

  test('glossary page', async ({ app }) => {
    await app.goto(toAppUrl('/support/glossary'))
    await expect(app.getByRole('heading', { name: 'Glossary' })).toBeVisible()
    await expect(app).toHaveTitle(`Glossary | ${APP_TITLE}`)

    await expect(app).toHaveScreenshot('glossary-page.png', screenshotOptions)
  })

  test('trigger node on canvas', async ({ app }) => {
    await app.goto(toAppUrl('/workflow-builder/new'))
    await expect(app.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible()

    // Add a manual trigger so a TriggerNode renders on the canvas
    await app.getByRole('button', { name: 'Manual trigger' }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Visual test trigger')
    await app.getByRole('button', { name: 'Create' }).click()

    // Screenshot the canvas area with the trigger node
    const canvas = app.locator('.react-flow')
    await expect(canvas).toBeVisible()
    await expect(canvas).toHaveScreenshot('trigger-node-canvas.png', screenshotOptions)
  })

  test('condition node with expression group', async ({ app }) => {
    await app.goto(toAppUrl('/workflow-builder/new'))
    await expect(app.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible()

    // Add manual trigger first
    await app.getByRole('button', { name: 'Manual trigger' }).click()
    await app.getByRole('textbox', { name: 'Name', exact: true }).fill('Trigger')
    await app.getByRole('button', { name: 'Create' }).click()

    // Add a condition node to show ExpressionGroup
    const addStepBtn = app.getByRole('button', { name: 'Add connected step' })
    await addStepBtn.waitFor({ state: 'visible' })
    await addStepBtn.click()
    const panel = addStepPanel(app)
    await expect(panel).toHaveCount(1)
    await panel.getByRole('button', { name: 'Logic', exact: true }).click()

    // After clicking Logic, the panel heading changes to "Select a logic node"
    await app.getByRole('button', { name: 'Conditional', exact: true }).click()

    // Wait for the condition form to render
    await expect(app.getByRole('textbox', { name: 'Name', exact: true })).toBeVisible()
    await expect(app).toHaveScreenshot('condition-expression-group.png', screenshotOptions)
  })

  test('scheduled trigger with schedule builder', async ({ app }) => {
    await app.goto(toAppUrl('/workflow-builder/new'))
    await expect(app.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible()

    // Add a scheduled trigger
    await app.getByRole('button', { name: 'Schedule trigger' }).click()

    // Select Visual schedule builder to show ScheduleBuilderFields
    const scheduleExpression = app.getByLabel('Schedule expression', { exact: true })
    await expect(scheduleExpression).toBeVisible()
    await scheduleExpression.click()
    await app.getByRole('option', { name: 'Visual schedule builder', exact: true }).click()

    // Wait for the schedule builder to render
    await expect(app.getByLabel('Start date', { exact: true })).toBeVisible()
    await expect(app).toHaveScreenshot('scheduled-trigger-schedule-builder.png', screenshotOptions)
  })
})
