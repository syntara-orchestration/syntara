/**
 * E2E Tests: Supported screen resolution and cross-browser smoke
 *
 * Critical paths covered:
 * - Main pages load at the minimum supported viewport (1024px width)
 * - Workflow builder and execution detail are usable at minimum supported width (1024px)
 * - React Flow canvases show an empty state below 1024px width; other pages remain usable; height is not gated
 *
 * Cross-browser:
 * - chromium runs on mock API (PR) and real-backend (E2E) CI
 * - Firefox and WebKit run via playwright.config when the mock API webServer is used (PR CI)
 */
import { AppRoute } from '../src/app/AppRoute'
import { MIN_SUPPORTED_VIEWPORT, REACT_FLOW_VIEWPORT_EMPTY_STATE } from '../src/constants/viewport'

import { type Page } from './fixtures'
import { test, expect, toAppUrl } from './fixtures'
import { isSkipWebServerForPlaywrightTests } from './playwrightWebServerEnv'

const isRealBackend = isSkipWebServerForPlaywrightTests()

const reactFlowViewportEmptyState = (page: Page) =>
  page.getByRole('heading', { level: 2, name: REACT_FLOW_VIEWPORT_EMPTY_STATE.title })

const executionsTable = (page: Page) =>
  page.getByRole('grid').filter({ has: page.getByRole('columnheader', { name: 'Status' }) })

/** Mock API seed includes exec-1; real-backend CI may have no executions. */
const MOCK_EXECUTION_ID = 'exec-1'

const executionDetailPath = (executionId: string) => AppRoute.Executions.Execution.replace(':executionId', executionId)

async function openFirstExecutionDetail(page: Page): Promise<string | null> {
  await page.goto(toAppUrl(AppRoute.Executions.Root))
  await expect(page.getByRole('heading', { level: 1, name: 'Workflow Runs' })).toBeVisible()

  const table = executionsTable(page)
  try {
    await expect(table).toBeVisible()
  } catch {
    return null
  }

  const runLinks = table.getByRole('link').filter({ has: page.locator('code') })
  const runLinkElements = await runLinks.all()
  if (runLinkElements.length === 0) {
    return null
  }

  await runLinkElements[0].click()
  await expect(page).toHaveURL(/\/executions\/[^/]+$/)
  const executionId = new URL(page.url()).pathname.split('/').pop() ?? ''
  return executionId.length > 0 ? executionId : null
}

async function resolveExecutionId(page: Page): Promise<string | null> {
  if (!isRealBackend) {
    return MOCK_EXECUTION_ID
  }
  return openFirstExecutionDetail(page)
}

type SmokePage = {
  path: string
  waitFor: (page: Page) => Promise<void>
}

const SMOKE_PAGES: SmokePage[] = [
  {
    path: AppRoute.Workflows.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()
    },
  },
  {
    path: AppRoute.Executions.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Workflow Runs' })).toBeVisible()
    },
  },
  {
    path: AppRoute.Approvals.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Approvals' })).toBeVisible()
    },
  },
  {
    path: AppRoute.Configuration.Integrations.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()
    },
  },
  {
    path: AppRoute.Configuration.Credentials.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()
    },
  },
  {
    path: AppRoute.SystemAdministration.Settings,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Settings' })).toBeVisible()
    },
  },
  {
    path: AppRoute.AccessManagement.Users,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Access Management' })).toBeVisible()
    },
  },
]

test.describe('Supported resolution', () => {
  test.use({ viewport: { width: MIN_SUPPORTED_VIEWPORT.width, height: 720 } })

  for (const { path, waitFor } of SMOKE_PAGES) {
    test(`${path} loads at minimum supported resolution`, async ({ app }) => {
      await app.goto(toAppUrl(path))
      await waitFor(app)
      await expect(app.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
    })
  }

  test('workflow builder is usable at minimum supported width', async ({ app }) => {
    await app.goto(toAppUrl(AppRoute.WorkflowBuilder.New))
    await expect(app.getByPlaceholder('Workflow name')).toBeVisible()
    await expect(reactFlowViewportEmptyState(app)).not.toBeVisible()
    await expect(app.locator('.react-flow')).toBeVisible()
  })

  test('execution detail is usable at minimum supported width', async ({ app }) => {
    const executionId = await resolveExecutionId(app)
    if (!executionId) {
      test.skip(true, 'No executions available to open detail view')
      return
    }

    if (!isRealBackend) {
      await app.goto(toAppUrl(executionDetailPath(executionId)))
    }

    await expect(app.getByRole('heading', { level: 1 })).toBeVisible()
    await expect(app.getByRole('button', { name: 'Run history', exact: true })).toBeVisible()
    await expect(reactFlowViewportEmptyState(app)).not.toBeVisible()
    await expect(app.locator('.react-flow')).toBeVisible()
  })
})

test.describe('React Flow viewport guard', () => {
  test('shows full-page empty state on workflow builder below minimum width', async ({ app }) => {
    await app.setViewportSize({ width: MIN_SUPPORTED_VIEWPORT.width - 1, height: 720 })
    await app.goto(toAppUrl(AppRoute.WorkflowBuilder.New))
    await expect(app.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
    await expect(reactFlowViewportEmptyState(app)).toBeVisible()
    await expect(app.getByRole('button', { name: REACT_FLOW_VIEWPORT_EMPTY_STATE.returnLabel })).toBeVisible()
    await expect(app.getByPlaceholder('Workflow name')).not.toBeVisible()
    await expect(app.getByRole('button', { name: /^Add step$/ })).not.toBeVisible()
    await expect(app.locator('.react-flow')).not.toBeVisible()
  })

  test('workflow builder renders at minimum width regardless of height', async ({ app }) => {
    await app.setViewportSize({ width: 1024, height: 400 })
    await app.goto(toAppUrl(AppRoute.WorkflowBuilder.New))
    await expect(app.locator('.react-flow')).toBeVisible()
    await expect(reactFlowViewportEmptyState(app)).not.toBeVisible()
  })

  test('shows full-page empty state on execution detail below minimum width', async ({ app }) => {
    await app.setViewportSize({ width: MIN_SUPPORTED_VIEWPORT.width, height: 720 })
    const executionId = await resolveExecutionId(app)
    if (!executionId) {
      test.skip(true, 'No executions available to open detail view')
      return
    }

    await app.setViewportSize({ width: MIN_SUPPORTED_VIEWPORT.width - 1, height: 720 })
    await app.goto(toAppUrl(executionDetailPath(executionId)))
    await expect(app.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
    await expect(reactFlowViewportEmptyState(app)).toBeVisible()
    await expect(app.getByRole('button', { name: 'Run history', exact: true })).not.toBeVisible()
    await expect(app.locator('.react-flow')).not.toBeVisible()
  })

  test('workflows list remains usable below minimum width', async ({ app }) => {
    await app.setViewportSize({ width: MIN_SUPPORTED_VIEWPORT.width - 1, height: 720 })
    await app.goto(toAppUrl(AppRoute.Workflows.Root))
    await expect(app.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()
    await expect(app.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
    await expect(reactFlowViewportEmptyState(app)).not.toBeVisible()
  })

  test('executions list remains usable below minimum width', async ({ app }) => {
    await app.setViewportSize({ width: MIN_SUPPORTED_VIEWPORT.width - 1, height: 720 })
    await app.goto(toAppUrl(AppRoute.Executions.Root))
    await expect(app.getByRole('heading', { level: 1, name: 'Workflow Runs' })).toBeVisible()
    await expect(app.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
    await expect(reactFlowViewportEmptyState(app)).not.toBeVisible()
  })

  test('Return to Workflows navigates from builder empty state', async ({ app }) => {
    await app.setViewportSize({ width: MIN_SUPPORTED_VIEWPORT.width - 1, height: 720 })
    await app.goto(toAppUrl(AppRoute.WorkflowBuilder.New))
    await app.getByRole('button', { name: REACT_FLOW_VIEWPORT_EMPTY_STATE.returnLabel }).click()
    await expect(app).toHaveURL(/\/workflows$/)
    await expect(app.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()
  })
})
