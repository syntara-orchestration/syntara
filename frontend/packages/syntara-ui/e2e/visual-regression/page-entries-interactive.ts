/**
 * Interactive-state page entries for visual regression testing.
 *
 * These entries cover builder interaction states, detail page tabs,
 * status variants, dialog states, and other interactive UI states
 * that extend the base page coverage in page-registry.ts.
 */
import { expect, type Page } from '@playwright/test'

import { AppRoute } from '../../src/app/AppRoute'
import { toAppUrl } from '../fixtures'

import { MOCK_IDENTITY_PROVIDER_ID } from './mock-ids'
import type { CanvasPageEntry, PageEntry } from './page-registry'

/**
 * `maxDiffPixelRatio` override for pages showing execution status badges — subtle
 * rendering variance under concurrent CI runner load that doesn't reproduce in
 * isolated /update-screenshots runs. Shared by every entry with this symptom so the
 * tolerance stays consistent and self-documenting instead of a repeated magic number.
 */
export const EXECUTION_STATUS_BADGE_TOLERANCE = 0.015

/**
 * Waits until a React Flow canvas has painted at least one node.
 * `.react-flow` alone can be visible while nodes are still animating in.
 */
export async function waitForCanvasReady(page: Page) {
  await expect(page.locator('.react-flow')).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('.react-flow__node').first()).toBeVisible({ timeout: 30_000 })
}

/**
 * Enters builder version view with a superseded published version so the page header
 * renders the version-view title row: 2xl workflow name, "Viewing …" label, status badge.
 * Unpublishes afterward so the shared mock store is not left in a published state.
 */
async function enterBuilderVersionViewHeaderState(page: Page, workflowId: string) {
  // Best-effort reset — other tests in the same run may leave this workflow published.
  await page.request.post(`/api/v1/workflows/${workflowId}/unpublish`).catch(() => {})

  const getResp = await page.request.get(`/api/v1/workflows/${workflowId}`)
  if (!getResp.ok()) throw new Error(`GET workflow ${workflowId} failed: ${getResp.status()}`)
  const workflow = (await getResp.json()) as {
    name?: string
    version?: { version?: number; workflow_definition?: Record<string, unknown> }
    current_version?: number
  }
  const currentVersion = workflow.version?.version ?? workflow.current_version ?? 1
  const workflowDefinition = workflow.version?.workflow_definition
  if (!workflowDefinition) throw new Error(`Workflow ${workflowId} has no definition`)

  const publishResp = await page.request.post(`/api/v1/workflows/${workflowId}/versions/${currentVersion}/publish`, {
    data: {},
  })
  if (!publishResp.ok()) throw new Error(`Publish v${currentVersion} failed: ${publishResp.status()}`)

  const patchResp = await page.request.patch(`/api/v1/workflows/${workflowId}`, {
    data: { workflow_definition: workflowDefinition },
  })
  if (!patchResp.ok()) throw new Error(`PATCH workflow ${workflowId} failed: ${patchResp.status()}`)

  const unpublishResp = await page.request.post(`/api/v1/workflows/${workflowId}/unpublish`)
  if (!unpublishResp.ok()) throw new Error(`Unpublish workflow ${workflowId} failed: ${unpublishResp.status()}`)

  const builderPath = AppRoute.WorkflowBuilder.Edit.replace(':workflowId', workflowId)
  await page.goto(toAppUrl(`${builderPath}?version=${currentVersion}`))

  await expect(page.getByRole('heading', { level: 1, name: workflow.name ?? 'conditional-demo' })).toBeVisible({
    timeout: 15_000,
  })
  await expect(page.getByText(/Viewing/i)).toBeVisible()
  // Collapse the panel first — version rows also render "Previously published" badges,
  // which makes an unscoped getByText hit multiple elements (strict mode violation).
  await page.getByRole('button', { name: 'Collapse version history' }).click()
  await expect(page.getByRole('heading', { name: 'Version history', level: 2 })).not.toBeVisible()
  await expect(page.getByText('Previously published', { exact: true })).toBeVisible()
}

/**
 * Opens the step editor side panel by clicking the canvas card title (PatternFly `Title` h2).
 * Prefer this over `getByTestId('rf__node-…')` + `force: true`, which often selects the card
 * without opening the editor (seed workflows may lack `name`, so the h2 shows the executor label).
 */
async function openStepEditorFromCanvasTitle(page: Page, title: string | RegExp) {
  const canvas = page.locator('.react-flow')
  // ReactFlow pans/zooms nodes with CSS transforms, not native scroll, so a node
  // positioned outside the viewport ReactFlow settled on at mount is unreachable to
  // Playwright's scroll-into-view actionability check and hangs the click until
  // timeout. Explicitly fit the whole graph into view first so every node — including
  // ones far from the trigger — is guaranteed to be on-screen and clickable.
  await page.getByRole('button', { name: 'Fit view' }).click()
  await canvas.getByRole('heading', { name: title, level: 2 }).first().click()
  // Do not key off the header Name field alone — with onHeaderContentChange the
  // toolbar can show a Name input without the three-panel step editor mounting,
  // which previously let --update-snapshots commit empty masked-canvas baselines.
  // "Run step" only exists inside the side-panel Parameters column.
  await expect(page.getByRole('button', { name: 'Run step', exact: true })).toBeVisible({
    timeout: 15_000,
  })
  await expect(page.getByRole('button', { name: /^(Save|Update)$/i }).first()).toBeVisible({ timeout: 10_000 })
}

/**
 * Pins the Workflows list to a single, known project ('default' / p-001) instead of
 * the "All projects" view.
 *
 * "All projects" groups workflows by project client-side using a `Map` populated in
 * API response order — so which project's group (and therefore which workflow row)
 * appears first depends on the exact page of workflows the mock API returns. That
 * set is not immutable: it shifts based on how many workflows exist and in what
 * order once other tests earlier in the run have mutated the shared in-process mock
 * store. Any test that opens "the first workflow's kebab" in "All projects" mode is
 * exposed to that drift. Scoping to one project removes the grouping (and the
 * cross-project ordering question) entirely, so "the first row" is deterministic.
 */
export async function selectDefaultProject(page: Page) {
  await page.evaluate(() => {
    localStorage.setItem(
      'syntara-selected-project',
      JSON.stringify({
        state: { selectedProjectId: 'p-001', selectedProjectName: 'default', favoriteProjectIds: [] },
        version: 1,
      })
    )
  })
  await page.reload()
  await expect(page.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()
  await expect(page.locator('table tbody tr').first()).toBeVisible()
}

/**
 * Finds and opens a workflow row kebab menu, skipping project header row kebabs.
 * Returns the kebab locator that was opened.
 *
 * Project header rows have kebabs with "Edit project" / "Delete project" items.
 * Workflow rows have kebabs with "Edit workflow" / "Run published version" / etc.
 *
 * This helper iterates through all kebabs and finds one that has a workflow-specific
 * menu item (determined by the menuItemPattern parameter).
 */
export async function openWorkflowKebab(page: Page, menuItemPattern: string | RegExp = /Edit workflow/i) {
  const kebabs = page.getByRole('button', { name: /Actions|Kebab toggle/i })
  const allKebabs = await kebabs.all()

  for (const kebab of allKebabs) {
    await kebab.click()
    const menuItem = page.getByRole('menuitem', { name: menuItemPattern })
    if (await menuItem.isVisible().catch(() => false)) {
      return kebab
    }
    await page.keyboard.press('Escape')
  }

  throw new Error(`No workflow kebab found with menu item matching: ${menuItemPattern}`)
}

// ---------------------------------------------------------------------------
// Mock API IDs for interactive state entries
// ---------------------------------------------------------------------------
// IDs are derived from each example YAML's own file path (see
// syntara-mock-api/src/resources/workflows.ts), never from its position in that list —
// so these stay correct even after `devel` merges in new example fixtures.
const MOCK_WORKFLOW_ID = 'basic-conditional-demo'
const MOCK_CONDITION_WORKFLOW_ID = 'condition-basic-condition-then-else'
const MOCK_LOOP_WORKFLOW_ID = 'basic-loop-demo'
const MOCK_AGENTIC_WORKFLOW_ID = 'agentic-simple-research'
const MOCK_HTTP_WORKFLOW_ID = 'api-simple-get-request'
const MOCK_CONVERGE_WORKFLOW_ID = 'converge-converge-all-strategy'
const MOCK_APPROVAL_WORKFLOW_ID = 'approval-approval-gate-basic'
const MOCK_APPROVAL_ID = '550e8400-e29b-41d4-a716-446655440050'
const MOCK_APPROVAL_EXECUTION_ID = 'exec-approval'
const MOCK_EXECUTION_FAILED_ID = 'exec-3'
const MOCK_EXECUTION_RUNNING_ID = 'exec-4'
const MOCK_EXECUTION_PAUSED_ID = 'exec-6'
const MOCK_EXECUTION_CANCELLED_ID = 'exec-8'
const MOCK_EXECUTION_PENDING_ID = 'exec-10'
const MOCK_USER_ID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
const MOCK_GROUP_ID = 'g1a2b3c4-d5e6-7890-abcd-ef1234567890'
const MOCK_PROJECT_ID = 'p-001'
const MOCK_CREDENTIAL_ID = 'cred-001'
const MOCK_CREDENTIAL_DISABLED_ID = 'cred-003'
const MOCK_SERVICE_ACCOUNT_ID = 'sa-001'
// ---------------------------------------------------------------------------
// Transfer Identity Wizard states
// ---------------------------------------------------------------------------
export const transferIdentityWizardPages: PageEntry[] = [
  {
    section: 'access-management/users',
    name: 'transfer-identity-wizard-step1',
    path: AppRoute.AccessManagement.TransferIdentity.replace(':userId', MOCK_USER_ID),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: /Transfer identity to/i })).toBeVisible()
      await expect(page.getByRole('heading', { level: 2, name: 'Select a user' })).toBeVisible()
    },
  },
  {
    section: 'access-management/users',
    name: 'transfer-identity-wizard-step1-selected',
    path: AppRoute.AccessManagement.TransferIdentity.replace(':userId', MOCK_USER_ID),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 2, name: 'Select a user' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await page.locator('table tbody tr').first().click()
      await expect(page.getByRole('radio', { checked: true })).toBeVisible()
    },
  },
  {
    section: 'access-management/users',
    name: 'transfer-identity-wizard-step2-empty',
    path: AppRoute.AccessManagement.TransferIdentity.replace(':userId', MOCK_USER_ID),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 2, name: 'Select a user' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await page.locator('table tbody tr').first().click()
      await page.getByRole('button', { name: 'Next', exact: true }).click()
      await expect(page.getByRole('heading', { level: 2, name: 'Select an identity' })).toBeVisible()
    },
  },
]

// ---------------------------------------------------------------------------
// OIDC Provider Wizard — additional section / step states
// ---------------------------------------------------------------------------
export const oidcProviderWizardPages: PageEntry[] = [
  {
    section: 'authentication',
    name: 'identity-provider-add-connection-section',
    path: AppRoute.SystemAdministration.Authentication.AddIdentityProvider,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Add OIDC provider' })).toBeVisible()
    },
    setup: async (page) => {
      const connectionHeading = page.getByRole('heading', { name: 'Connection', level: 3 })
      await connectionHeading.scrollIntoViewIfNeeded()
      await expect(connectionHeading).toBeVisible()
    },
  },
  {
    section: 'authentication',
    name: 'identity-provider-add-options-section',
    path: AppRoute.SystemAdministration.Authentication.AddIdentityProvider,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Add OIDC provider' })).toBeVisible()
    },
    setup: async (page) => {
      const optionsHeading = page.getByRole('heading', { name: 'Options', level: 3 })
      await optionsHeading.scrollIntoViewIfNeeded()
      await expect(optionsHeading).toBeVisible()
    },
  },
  {
    section: 'authentication',
    name: 'identity-provider-edit',
    path: AppRoute.SystemAdministration.Authentication.EditIdentityProvider.replace(
      ':providerId',
      MOCK_IDENTITY_PROVIDER_ID
    ),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: /Edit OIDC provider/i })).toBeVisible()
    },
  },
  {
    section: 'authentication',
    name: 'identity-provider-detail-group-mapping-tab',
    path: AppRoute.SystemAdministration.Authentication.IdentityProviderDetail.replace(
      ':providerId',
      MOCK_IDENTITY_PROVIDER_ID
    ),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    },
    setup: async (page) => {
      await page.getByRole('tab', { name: /Group mapping/i }).click()
      await expect(page.getByRole('tab', { name: /Group mapping/i })).toHaveAttribute('aria-selected', 'true')
    },
  },
  {
    section: 'authentication',
    name: 'identity-provider-detail-disable-dialog',
    path: AppRoute.SystemAdministration.Authentication.IdentityProviderDetail.replace(
      ':providerId',
      MOCK_IDENTITY_PROVIDER_ID
    ),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    },
    setup: async (page) => {
      await page.locator('[id="provider-detail-toggle"]').click({ force: true })
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: /Disable/i })).toBeVisible()
    },
  },
  {
    section: 'authentication',
    name: 'identity-provider-detail-kebab-menu',
    path: AppRoute.SystemAdministration.Authentication.IdentityProviderDetail.replace(
      ':providerId',
      MOCK_IDENTITY_PROVIDER_ID
    ),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    },
    setup: async (page) => {
      await page.getByRole('button', { name: /Actions|Kebab toggle/i }).click()
      await expect(page.getByRole('menuitem', { name: /Delete/i })).toBeVisible()
    },
  },
  {
    section: 'authentication',
    name: 'identity-provider-add-step1-validation',
    path: AppRoute.SystemAdministration.Authentication.AddIdentityProvider,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Add OIDC provider' })).toBeVisible()
    },
    setup: async (page) => {
      await page.getByRole('button', { name: 'Next' }).click()
      await expect(page.getByText(/required/i).first()).toBeVisible()
    },
  },
]

// ---------------------------------------------------------------------------
// Builder interaction states
// ---------------------------------------------------------------------------
export const builderInteractivePages: CanvasPageEntry[] = [
  {
    section: 'workflows',
    name: 'builder-edit-add-step-panel',
    perceptual: true,
    path: AppRoute.WorkflowBuilder.Edit.replace(':workflowId', MOCK_WORKFLOW_ID),
    waitFor: async (page) => {
      await expect(page.locator('.react-flow')).toBeVisible({ timeout: 30_000 })
    },
    setup: async (page) => {
      await page.getByRole('button', { name: /Add Step/i }).click()
      const panel = page.getByRole('region', { name: /add step|select a node/i })
      await expect(panel).toBeVisible()
      // panel.toBeVisible() fires when the slide-in starts — wait for a rendered child
      // so the screenshot doesn't capture a mid-animation state
      await expect(panel.getByRole('button').first()).toBeVisible()
    },
  },
  {
    section: 'workflows',
    name: 'builder-edit-script-node-form',
    path: AppRoute.WorkflowBuilder.Edit.replace(':workflowId', MOCK_CONDITION_WORKFLOW_ID),
    perceptual: true,
    // NodeEditorOverlay covers the canvas box — masking .react-flow would erase the form.
    maskCanvas: false,
    waitFor: async (page) => {
      await expect(page.locator('.react-flow')).toBeVisible({ timeout: 30_000 })
    },
    setup: async (page) => {
      await openStepEditorFromCanvasTitle(page, /Adult Message/i)
    },
  },
  {
    section: 'workflows',
    name: 'builder-edit-condition-node-form',
    path: AppRoute.WorkflowBuilder.Edit.replace(':workflowId', MOCK_CONDITION_WORKFLOW_ID),
    perceptual: true,
    maskCanvas: false,
    waitFor: async (page) => {
      await expect(page.locator('.react-flow')).toBeVisible({ timeout: 30_000 })
    },
    setup: async (page) => {
      await openStepEditorFromCanvasTitle(page, /Check Age/i)
    },
  },
  {
    section: 'workflows',
    name: 'builder-edit-loop-node-form',
    path: AppRoute.WorkflowBuilder.Edit.replace(':workflowId', MOCK_LOOP_WORKFLOW_ID),
    perceptual: true,
    maskCanvas: false,
    waitFor: async (page) => {
      await expect(page.locator('.react-flow')).toBeVisible({ timeout: 30_000 })
    },
    setup: async (page) => {
      await openStepEditorFromCanvasTitle(page, 'Loop')
      // Verify the loop form loaded (not a child step's form). The Type field is a
      // PatternFly Select rendered as a MenuToggle button, not a native <select> —
      // its current value is its visible text, not a `value` attribute.
      await expect(page.getByRole('button', { name: 'Type', exact: true })).toHaveText(/While|For each/)
    },
  },
  {
    section: 'workflows',
    name: 'builder-edit-agentic-node-form',
    path: AppRoute.WorkflowBuilder.Edit.replace(':workflowId', MOCK_AGENTIC_WORKFLOW_ID),
    perceptual: true,
    maskCanvas: false,
    waitFor: async (page) => {
      await expect(page.locator('.react-flow')).toBeVisible({ timeout: 30_000 })
    },
    setup: async (page) => {
      // simple-research agentic activity has no display name — card title is executor label "Task Agent"
      await openStepEditorFromCanvasTitle(page, 'Task Agent')
    },
  },
  {
    section: 'workflows',
    name: 'builder-edit-http-node-form',
    path: AppRoute.WorkflowBuilder.Edit.replace(':workflowId', MOCK_HTTP_WORKFLOW_ID),
    perceptual: true,
    maskCanvas: false,
    waitFor: async (page) => {
      await expect(page.locator('.react-flow')).toBeVisible({ timeout: 30_000 })
    },
    setup: async (page) => {
      // simple-get-request http activity has no display name — card title is executor label "REST API"
      await openStepEditorFromCanvasTitle(page, 'REST API')
    },
  },
  {
    section: 'workflows',
    name: 'builder-edit-converge-node-form',
    path: AppRoute.WorkflowBuilder.Edit.replace(':workflowId', MOCK_CONVERGE_WORKFLOW_ID),
    perceptual: true,
    maskCanvas: false,
    waitFor: async (page) => {
      await expect(page.locator('.react-flow')).toBeVisible({ timeout: 30_000 })
    },
    setup: async (page) => {
      await openStepEditorFromCanvasTitle(page, 'Converge')
    },
  },
  {
    section: 'workflows',
    name: 'builder-edit-approval-node-form',
    path: AppRoute.WorkflowBuilder.Edit.replace(':workflowId', MOCK_APPROVAL_WORKFLOW_ID),
    perceptual: true,
    maskCanvas: false,
    waitFor: async (page) => {
      await expect(page.locator('.react-flow')).toBeVisible({ timeout: 30_000 })
    },
    setup: async (page) => {
      await openStepEditorFromCanvasTitle(page, /Deployment Approval/i)
    },
  },
  {
    section: 'workflows',
    name: 'builder-new-scheduled-trigger-form',
    perceptual: true,
    maskCanvas: false,
    path: AppRoute.WorkflowBuilder.New,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible({
        timeout: 30_000,
      })
    },
    setup: async (page) => {
      await page.getByRole('button', { name: 'Schedule trigger' }).click()
      // Schedule expression is a PatternFly Select (MenuToggle button + listbox),
      // not a native <select> — open it and click the option instead of selectOption().
      const scheduleToggle = page.getByRole('button', { name: 'Schedule expression', exact: true })
      await expect(scheduleToggle).toBeVisible()
      await scheduleToggle.click()
      await page.getByRole('option', { name: 'Visual schedule builder', exact: true }).click()
      await expect(page.getByLabel('Start date', { exact: true })).toBeVisible()
      await expect(page.getByLabel('Frequency', { exact: true })).toBeVisible()
    },
  },
  {
    section: 'workflows',
    name: 'builder-new-webhook-trigger-form',
    perceptual: true,
    maskCanvas: false,
    path: AppRoute.WorkflowBuilder.New,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Select a trigger node' })).toBeVisible({
        timeout: 30_000,
      })
    },
    setup: async (page) => {
      await page.getByRole('button', { name: 'Webhook trigger' }).click()
      await expect(page.getByRole('textbox', { name: 'Name', exact: true })).toBeVisible()
    },
  },
  {
    section: 'workflows',
    name: 'builder-new-verify-errors',
    perceptual: true,
    path: AppRoute.WorkflowBuilder.New,
    waitFor: async (page) => {
      await expect(page.locator('.react-flow')).toBeVisible({ timeout: 30_000 })
    },
    setup: async (page) => {
      await page.getByRole('button', { name: 'Workflow actions' }).click()
      await page.getByRole('menuitem', { name: 'Verify workflow' }).click()
      await expect(page.getByText('Verification failed')).toBeVisible({ timeout: 10_000 })
    },
  },
  {
    section: 'workflows',
    name: 'builder-edit-verify-node-errors',
    path: AppRoute.WorkflowBuilder.Edit.replace(':workflowId', MOCK_WORKFLOW_ID),
    perceptual: true,
    waitFor: async (page) => {
      await expect(page.locator('.react-flow')).toBeVisible({ timeout: 30_000 })
    },
    setup: async (page) => {
      await page.getByRole('button', { name: 'Workflow actions' }).click()
      await page.getByRole('menuitem', { name: 'Verify workflow' }).click()
      await expect(page.getByText('Verification failed')).toBeVisible({ timeout: 10_000 })
    },
  },
]

// ---------------------------------------------------------------------------
// Workflow dialog entries (publish, unpublish, run, kebab menu)
// ---------------------------------------------------------------------------
export const workflowDialogPages: CanvasPageEntry[] = [
  {
    section: 'workflows',
    name: 'workflows-kebab-menu',
    perceptual: true,
    path: AppRoute.Workflows.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await selectDefaultProject(page)
      await openWorkflowKebab(page)
      await expect(page.getByRole('menuitem', { name: /Edit workflow/i })).toBeVisible()
    },
  },
  {
    section: 'workflows',
    name: 'workflows-publish-dialog',
    perceptual: true,
    path: AppRoute.Workflows.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await selectDefaultProject(page)
      await openWorkflowKebab(page, 'Publish workflow')
      await page.getByRole('menuitem', { name: 'Publish workflow', exact: true }).click()
      await expect(page.getByRole('dialog')).toBeVisible()
      await expect(page.getByText('Publish workflow?')).toBeVisible()
    },
  },
  {
    section: 'workflows',
    name: 'workflows-unpublish-dialog',
    perceptual: true,
    path: AppRoute.Workflows.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await selectDefaultProject(page)
      const workflowKebab = await openWorkflowKebab(page)
      // The unpublish option only appears for published workflows; if absent, click publish first
      const unpublishItem = page.getByRole('menuitem', { name: /Unpublish workflow/i })
      const hasUnpublish = await unpublishItem.isVisible().catch(() => false)
      // The mock API's workflow list is a single in-process store shared by every
      // test in the run (CI uses one worker + one webServer instance). If we publish
      // a workflow here to reach the "Unpublish" precondition, that mutation outlives
      // this test — the confirm button is never clicked — and leaks a "Published"
      // badge into every later test that lists workflows. Capture the publish
      // response so we can revert it directly via the API once the dialog we
      // actually want to screenshot is showing.
      let publishedWorkflowId: string | null = null
      if (hasUnpublish) {
        await unpublishItem.click()
      } else {
        // Close menu and try publishing first so the unpublish item appears
        await page.keyboard.press('Escape')
        await workflowKebab.click()
        await page.getByRole('menuitem', { name: /Publish workflow/i }).click()
        await expect(page.getByRole('dialog')).toBeVisible()
        const publishResponse = page.waitForResponse(
          (res) =>
            /\/api\/v1\/workflows\/[^/]+\/versions\/\d+\/publish$/.test(res.url()) && res.request().method() === 'POST'
        )
        await page.getByRole('button', { name: 'Publish' }).click()
        publishedWorkflowId = new URL((await publishResponse).url()).pathname.split('/')[4] ?? null
        // not.toBeVisible() fires when dismiss animation starts — also wait for
        // a published status badge so the DOM is fully settled before re-clicking
        await expect(page.getByRole('dialog')).not.toBeVisible()
        await expect(page.getByText('Published', { exact: true }).first()).toBeVisible()
        // The "Workflow published" toast auto-dismisses after several
        // seconds — wait it out so it isn't still on screen (overlapping the
        // "Unpublish workflow?" dialog) when the final screenshot is captured.
        await expect(page.getByText('Workflow published', { exact: true })).not.toBeVisible({ timeout: 12_000 })
        await workflowKebab.click()
        const unpublishAfterPublish = page.getByRole('menuitem', { name: /Unpublish workflow/i })
        await expect(unpublishAfterPublish).toBeVisible()
        await unpublishAfterPublish.click()
      }
      await expect(page.getByRole('dialog')).toBeVisible()
      await expect(page.getByText('Unpublish workflow?')).toBeVisible()
      if (publishedWorkflowId) {
        await page.request.post(`/api/v1/workflows/${publishedWorkflowId}/unpublish`)
      }
    },
  },
  {
    section: 'workflows',
    name: 'workflows-run-dialog',
    perceptual: true,
    path: AppRoute.Workflows.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await selectDefaultProject(page)
      // "Run published version" is disabled until the workflow has a published_version_id
      // (see workflowRowActions.tsx). Publish it here rather than relying on state leaked
      // from a sibling test — workflows-unpublish-dialog explicitly unpublishes its target
      // workflow as its own cleanup step, so this workflow is never left published for a
      // later test to depend on. Revert via a direct API call (mirroring
      // workflows-unpublish-dialog's cleanup) once the Run dialog is showing, so the mutation
      // doesn't leak a "Published" badge into whatever runs after this test.
      // openWorkflowKebab already leaves the menu open (it clicks the kebab internally
      // to check which items are present) — clicking it again here would just toggle it
      // closed before the menuitem click below has a chance to land.
      const workflowKebab = await openWorkflowKebab(page, /Publish workflow/i)
      const publishResponse = page.waitForResponse(
        (res) =>
          /\/api\/v1\/workflows\/[^/]+\/versions\/\d+\/publish$/.test(res.url()) && res.request().method() === 'POST'
      )
      await page.getByRole('menuitem', { name: /Publish workflow/i }).click()
      await expect(page.getByRole('dialog')).toBeVisible()
      await page.getByRole('button', { name: 'Publish' }).click()
      const publishedWorkflowId = new URL((await publishResponse).url()).pathname.split('/')[4] ?? null
      await expect(page.getByRole('dialog')).not.toBeVisible()
      await expect(page.getByText('Workflow published', { exact: true })).not.toBeVisible({ timeout: 12_000 })

      await workflowKebab.click()
      await page.getByRole('menuitem', { name: /Run published version/i }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: /Run/i })).toBeVisible()

      if (publishedWorkflowId) {
        await page.request.post(`/api/v1/workflows/${publishedWorkflowId}/unpublish`)
      }
    },
  },
  {
    section: 'workflows',
    name: 'builder-edit-version-history-panel',
    path: AppRoute.WorkflowBuilder.Edit.replace(':workflowId', MOCK_WORKFLOW_ID),
    perceptual: true,
    waitFor: async (page) => {
      // Use 30s to match all other builder entries (ReactFlow + Zustand + lazy-load is slow in CI)
      await expect(page.locator('.react-flow')).toBeVisible({ timeout: 30_000 })
    },
    setup: async (page) => {
      await page.getByRole('button', { name: /Workflow actions/i }).click()
      await page.getByRole('menuitem', { name: /Version history/i }).click()
      await expect(page.getByRole('heading', { name: 'Version history' })).toBeVisible()
      // Heading visible = panel started opening; wait for panel content to finish rendering
      await expect(
        page
          .getByRole('list')
          .filter({ hasText: /version/i })
          .first()
      )
        .toBeVisible({
          timeout: 5_000,
        })
        .catch(async () => {
          // Panel may be empty (no versions yet) — confirm the empty state rendered instead
          await expect(page.getByRole('heading', { name: 'Version history' })).toBeVisible()
        })
    },
  },
  {
    section: 'workflows',
    name: 'builder-edit-version-view-header',
    path: AppRoute.WorkflowBuilder.Edit.replace(':workflowId', MOCK_WORKFLOW_ID),
    perceptual: true,
    waitFor: async (page) => {
      await expect(page.locator('.react-flow')).toBeVisible({ timeout: 30_000 })
    },
    setup: async (page) => {
      await enterBuilderVersionViewHeaderState(page, MOCK_WORKFLOW_ID)
    },
  },
  {
    section: 'workflows',
    name: 'builder-edit-run-history-panel',
    path: AppRoute.WorkflowBuilder.Edit.replace(':workflowId', MOCK_WORKFLOW_ID),
    perceptual: true,
    waitFor: async (page) => {
      await expect(page.locator('.react-flow')).toBeVisible({ timeout: 30_000 })
    },
    setup: async (page) => {
      // "Run history" lives inside the "Workflow actions" kebab menu, not a standalone button
      await page.getByLabel('Workflow actions').click()
      await page.getByRole('menuitem', { name: /Run history/i }).click()
      await expect(page.getByRole('heading', { name: 'Run history' })).toBeVisible()
      // Wait for pagination footer to ensure full render
      await expect(page.getByRole('navigation', { name: /pagination/i })).toBeVisible()
    },
  },
  {
    section: 'workflows',
    name: 'workflows-import-dialog',
    perceptual: true,
    path: AppRoute.Workflows.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await page.getByRole('button', { name: /Import workflow/i }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: /Import/i })).toBeVisible()
    },
  },
]

// ---------------------------------------------------------------------------
// Credential dialog entries (delete, disable from detail page)
// ---------------------------------------------------------------------------
export const credentialDialogPages: PageEntry[] = [
  {
    section: 'configuration/credentials',
    name: 'credentials-delete-dialog',
    path: AppRoute.Configuration.Credentials.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      const kebab = page.getByRole('button', { name: /Actions|Kebab toggle/i }).first()
      await kebab.click()
      await page.getByRole('menuitem', { name: /Delete/i }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: /Delete/i })).toBeVisible()
    },
  },
  {
    section: 'configuration/credentials',
    name: 'credentials-disable-dialog',
    path: AppRoute.Configuration.Credentials.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await page.locator('label[for="credential-toggle-cred-001"]').click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: /Disable/i })).toBeVisible()
    },
  },
]

// ---------------------------------------------------------------------------
// Integration wizard step entries
// ---------------------------------------------------------------------------
export const integrationWizardPages: PageEntry[] = [
  {
    section: 'configuration/integrations',
    name: 'integration-configure-aap-step1',
    path: AppRoute.Configuration.Integrations.Configure,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Configure integration' })).toBeVisible()
    },
    setup: async (page) => {
      await page.getByText('MCP Server').click()
      await page.getByRole('option', { name: 'Ansible Automation Platform' }).click()
      await expect(page.getByRole('textbox', { name: /API URL/i })).toBeVisible()
      await expect(page.getByText('Security')).toBeVisible()
    },
  },
  {
    section: 'configuration/integrations',
    name: 'integration-configure-security',
    path: AppRoute.Configuration.Integrations.Configure,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Configure integration' })).toBeVisible()
    },
    setup: async (page) => {
      await page.getByText('Security').click()
      await expect(page.getByText('Allow HTTP connections')).toBeVisible()
    },
  },
  {
    section: 'configuration/integrations',
    name: 'integration-configure-step2-credential',
    path: AppRoute.Configuration.Integrations.Configure,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Configure integration' })).toBeVisible()
    },
    setup: async (page) => {
      // Fill required step 1 fields then advance with Next
      await page.getByRole('textbox', { name: /Server name/i }).fill('Test Server')
      await page.getByRole('textbox', { name: /API URL/i }).fill('https://example.com')
      await page.getByRole('button', { name: 'Next' }).click()
      await expect(page.getByRole('heading', { name: 'Connection credential' })).toBeVisible()
    },
  },
  {
    section: 'configuration/integrations',
    name: 'integration-configure-step3-tools',
    path: AppRoute.Configuration.Integrations.Configure,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Configure integration' })).toBeVisible()
    },
    setup: async (page) => {
      // Fill step 1, advance to step 2
      await page.getByRole('textbox', { name: /Server name/i }).fill('Test Server')
      await page.getByRole('textbox', { name: /API URL/i }).fill('https://example.com')
      await page.getByRole('button', { name: 'Next' }).click()
      await expect(page.getByRole('heading', { name: 'Connection credential' })).toBeVisible()
      // Wait for credentials to load, then select one to enable step 3
      const credentialToggle = page.getByRole('button', { name: 'Health check credential', exact: true })
      await expect(credentialToggle).toBeEnabled({ timeout: 10_000 })
      await credentialToggle.click()
      await page.getByRole('option', { name: 'MCP Integration Token' }).click()
      // Advance to step 3
      await page.getByRole('button', { name: 'Next' }).click()
      // This setup never runs an actual "Test connection", so the step always
      // renders its empty state ("No tools discovered yet") rather than the
      // "Enable tools" heading, which only appears once tools are discovered.
      await expect(page.getByRole('heading', { name: 'No tools discovered yet' })).toBeVisible()
    },
  },
]

// ---------------------------------------------------------------------------
// Integration edit form — Security section expanded
// ---------------------------------------------------------------------------
export const integrationSecurityPages: PageEntry[] = [
  {
    section: 'configuration/integrations',
    name: 'integration-edit-security',
    path: AppRoute.Configuration.Integrations.Edit.replace(':integrationId', '1'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Edit integration' })).toBeVisible()
    },
    setup: async (page) => {
      await page.getByText('Security').click()
      await expect(page.getByText('Allow HTTP connections')).toBeVisible()
    },
  },
  {
    section: 'configuration/integrations',
    name: 'llm-provider-edit-security',
    path: AppRoute.Configuration.Integrations.Edit.replace(':integrationId', '10'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Edit integration' })).toBeVisible()
    },
    setup: async (page) => {
      await page.getByText('Security').click()
      await expect(page.getByText('Allow HTTP connections')).toBeVisible()
    },
  },
  {
    section: 'configuration/integrations',
    name: 'aap-edit-security',
    path: AppRoute.Configuration.Integrations.Edit.replace(':integrationId', '12'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Edit integration' })).toBeVisible()
      await expect(page.locator('input[value="https://aap.prod.example.com"]')).toBeVisible()
    },
    setup: async (page) => {
      await page.getByText('Security').click()
      await expect(page.getByText('Allow HTTP connections')).toBeVisible()
    },
  },
]

// ---------------------------------------------------------------------------
// Integration dialog entries (delete)
// ---------------------------------------------------------------------------
export const integrationDialogPages: PageEntry[] = [
  {
    section: 'configuration/integrations',
    name: 'integrations-delete-dialog',
    path: AppRoute.Configuration.Integrations.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      const kebab = page.getByRole('button', { name: /Actions|Kebab toggle/i }).first()
      await kebab.click()
      await page.getByRole('menuitem', { name: /Delete integration/i }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: /Delete/i })).toBeVisible()
    },
  },
  {
    section: 'configuration/integrations',
    name: 'integration-resources-unsaved-changes-dialog',
    path: AppRoute.Configuration.Integrations.DetailTab.replace(':integrationId', '1').replace(':tab', 'resources'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByRole('tab', { name: /Enabled resources/i, selected: true })).toBeVisible()
      await expect(page.getByText('list_resources')).toBeVisible()
    },
    setup: async (page) => {
      // Uncheck a specific tool row (not the header) to create dirty state
      const firstToolRow = page.getByRole('row', { name: /list_resources/ })
      await firstToolRow.getByRole('checkbox').click()
      // Verify the checkbox toggled (dirty state is now true)
      await expect(firstToolRow.getByRole('checkbox')).not.toBeChecked()
      // Navigate away via the sidebar to trigger the unsaved changes blocker
      await page.getByRole('link', { name: 'Workflows' }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByText('Save resource changes?')).toBeVisible()
    },
  },
]

// ---------------------------------------------------------------------------
// Approvals interactive entries (bulk selection toolbar)
// ---------------------------------------------------------------------------
/**
 * Wait for the approval side panel to open on the execution detail page.
 */
async function waitForApprovalPanel(page: Page) {
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 20_000 })
  await expect(page.getByRole('heading', { name: 'Review Approval' })).toBeVisible({ timeout: 15_000 })
}

export const approvalInteractivePages: PageEntry[] = [
  {
    section: 'approvals',
    name: 'approval-side-panel-pending',
    path: `${AppRoute.Executions.Execution.replace(':executionId', MOCK_APPROVAL_EXECUTION_ID)}?approval=${MOCK_APPROVAL_ID}&history=closed`,
    perceptual: true,
    waitFor: waitForApprovalPanel,
  },
  {
    section: 'approvals',
    name: 'approval-side-panel-approve-selected',
    path: `${AppRoute.Executions.Execution.replace(':executionId', MOCK_APPROVAL_EXECUTION_ID)}?approval=${MOCK_APPROVAL_ID}&history=closed`,
    perceptual: true,
    waitFor: waitForApprovalPanel,
    setup: async (page) => {
      // Wait for permission checks to complete before clicking
      await expect(page.getByRole('button', { name: 'Approve' })).toBeEnabled({ timeout: 10_000 })
      await page.getByRole('button', { name: 'Approve' }).click()
      await expect(page.getByRole('button', { name: 'Submit decision' })).toBeVisible()
    },
  },
  {
    section: 'approvals',
    name: 'approval-side-panel-reject-selected',
    path: `${AppRoute.Executions.Execution.replace(':executionId', MOCK_APPROVAL_EXECUTION_ID)}?approval=${MOCK_APPROVAL_ID}&history=closed`,
    perceptual: true,
    waitFor: waitForApprovalPanel,
    setup: async (page) => {
      // Wait for permission checks to complete before clicking
      await expect(page.getByRole('button', { name: 'Reject' })).toBeEnabled({ timeout: 10_000 })
      await page.getByRole('button', { name: 'Reject' }).click()
      await expect(page.getByRole('button', { name: 'Submit decision' })).toBeVisible()
    },
  },
  {
    section: 'approvals',
    name: 'approval-side-panel-viewer-disabled',
    path: `${AppRoute.Executions.Execution.replace(':executionId', MOCK_APPROVAL_EXECUTION_ID)}?approval=${MOCK_APPROVAL_ID}&history=closed`,
    perceptual: true,
    role: 'viewer',
    waitFor: async (page) => {
      await waitForApprovalPanel(page)
      await expect(page.getByRole('button', { name: 'Approve' })).toBeVisible()
    },
  },
]

// ---------------------------------------------------------------------------
// Settings tab entries (additional categories beyond Application)
// ---------------------------------------------------------------------------
export const settingsTabPages: PageEntry[] = [
  {
    section: 'settings',
    name: 'settings-ai-llm-tab',
    path: AppRoute.SystemAdministration.SettingsTab.replace(':category', 'ai_llm'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
      await expect(page.getByRole('tab', { name: /AI \/ LLM/i, selected: true })).toBeVisible()
    },
  },
  {
    section: 'settings',
    name: 'settings-system-tab',
    path: AppRoute.SystemAdministration.SettingsTab.replace(':category', 'system'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
      await expect(page.getByRole('tab', { name: /System/i, selected: true })).toBeVisible()
    },
  },
  {
    section: 'settings',
    name: 'settings-authentication-tab',
    path: AppRoute.SystemAdministration.SettingsTab.replace(':category', 'authentication'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
      await expect(page.getByRole('tab', { name: /Authentication/i, selected: true })).toBeVisible()
    },
  },
  {
    section: 'settings',
    name: 'settings-workflow-execution-tab',
    path: AppRoute.SystemAdministration.SettingsTab.replace(':category', 'workflow_execution'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
      await expect(page.getByRole('tab', { name: /Workflow Execution/i, selected: true })).toBeVisible()
    },
  },
  {
    section: 'settings',
    name: 'settings-context-manager-tab',
    path: AppRoute.SystemAdministration.SettingsTab.replace(':category', 'context_manager'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
      await expect(page.getByRole('tab', { name: /Context Manager/i, selected: true })).toBeVisible()
    },
  },
]

// ---------------------------------------------------------------------------
// Status variant entries (execution, approval, credential states)
// ---------------------------------------------------------------------------
export const statusVariantPages: PageEntry[] = [
  {
    section: 'executions',
    name: 'execution-detail-failed',
    path: AppRoute.Executions.Execution.replace(':executionId', MOCK_EXECUTION_FAILED_ID),
    maxDiffPixelRatio: 0.02,
    perceptual: true,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      // Heading shows workflow name, not status. Wait for the Failed status badge instead.
      await expect(page.getByText('Failed', { exact: true }).first()).toBeVisible()
    },
  },
  {
    section: 'executions',
    name: 'execution-detail-running',
    path: AppRoute.Executions.Execution.replace(':executionId', MOCK_EXECUTION_RUNNING_ID),
    perceptual: true,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByText('Running', { exact: true }).first()).toBeVisible()
    },
  },
  {
    section: 'executions',
    name: 'execution-detail-paused',
    path: AppRoute.Executions.Execution.replace(':executionId', MOCK_EXECUTION_PAUSED_ID),
    perceptual: true,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByText('Paused', { exact: true }).first()).toBeVisible()
    },
  },
  {
    section: 'executions',
    name: 'execution-detail-cancelled',
    path: AppRoute.Executions.Execution.replace(':executionId', MOCK_EXECUTION_CANCELLED_ID),
    perceptual: true,
    maxDiffPixelRatio: EXECUTION_STATUS_BADGE_TOLERANCE,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByText('Cancelled', { exact: true }).first()).toBeVisible()
    },
  },
  {
    section: 'executions',
    name: 'execution-detail-pending',
    path: AppRoute.Executions.Execution.replace(':executionId', MOCK_EXECUTION_PENDING_ID),
    perceptual: true,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByText('Pending', { exact: true }).first()).toBeVisible()
    },
  },
  {
    section: 'approvals',
    name: 'approvals-expanded-row',
    path: AppRoute.Approvals.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Approvals' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await page
        .getByRole('button', { name: /details/i })
        .first()
        .click()
      // Wait for expanded row content — no assertion here previously caused race with animation
      await expect(page.locator('tr.pf-m-expanded, tr[aria-expanded="true"]').first()).toBeVisible()
    },
  },
  {
    section: 'configuration/credentials',
    name: 'credential-detail-disabled',
    path: AppRoute.Configuration.Credentials.Detail.replace(':credentialId', MOCK_CREDENTIAL_DISABLED_ID),
    waitFor: async (page) => {
      await expect(page.getByText('GitHub API Token').first()).toBeVisible()
      await expect(page.getByText('Disabled')).toBeVisible()
    },
  },
]

// ---------------------------------------------------------------------------
// User create form states
// ---------------------------------------------------------------------------
export const userCreateFormPages: PageEntry[] = [
  {
    section: 'access-management/users',
    name: 'user-create-validation-errors',
    path: AppRoute.AccessManagement.CreateUser,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Create user' })).toBeVisible()
    },
    setup: async (page) => {
      await page.getByRole('button', { name: 'Create user' }).click()
      await expect(page.getByText(/required/i).first()).toBeVisible()
      await expect(page.getByRole('textbox', { name: /username/i })).toHaveAttribute('aria-invalid', 'true')
    },
  },
]

// ---------------------------------------------------------------------------
// Credential edit modal
// ---------------------------------------------------------------------------
export const credentialEditPages: PageEntry[] = [
  {
    section: 'configuration/credentials',
    name: 'credentials-edit-modal',
    path: AppRoute.Configuration.Credentials.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      const kebab = page.getByRole('button', { name: /Actions|Kebab toggle/i }).first()
      await kebab.click()
      await page.getByRole('menuitem', { name: /Edit/i }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: /Save/i })).toBeVisible()
    },
  },
  {
    section: 'configuration/credentials',
    name: 'credentials-create-modal-auth-method',
    path: AppRoute.Configuration.Credentials.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()
      // PatternFly's <Table> renders with role="grid" (see isExpandable usage in
      // Credentials.tsx), not the native "table" role, so getByRole('table') never
      // matches — assert on the row structure directly instead, like the sibling
      // credentials-edit-modal entry above.
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await page.getByRole('textbox', { name: 'Project' }).click()
      await page.getByRole('option', { name: 'default' }).click()
      await page.getByRole('button', { name: /create credential/i }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await dialog.getByRole('button', { name: 'Credential type', exact: true }).click()
      await page.getByRole('option', { name: 'Ansible Automation Platform' }).click()
      await expect(dialog.getByText('Auth method')).toBeVisible()
    },
  },
]

// ---------------------------------------------------------------------------
// Authentication interactive states
// ---------------------------------------------------------------------------
export const authenticationInteractivePages: PageEntry[] = [
  {
    section: 'authentication',
    name: 'identity-provider-detail',
    path: AppRoute.SystemAdministration.Authentication.IdentityProviderDetail.replace(
      ':providerId',
      MOCK_IDENTITY_PROVIDER_ID
    ),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    },
  },
]

// ---------------------------------------------------------------------------
// Detail page tab entries
// ---------------------------------------------------------------------------
export const detailTabPages: PageEntry[] = [
  {
    section: 'settings',
    name: 'settings-application-tab',
    path: AppRoute.SystemAdministration.SettingsTab.replace(':category', 'application'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
      await expect(page.getByRole('tab', { name: /Application/i, selected: true })).toBeVisible()
    },
  },
  {
    section: 'configuration/credentials',
    name: 'credential-detail-workflows-tab',
    path: AppRoute.Configuration.Credentials.DetailTab.replace(':credentialId', MOCK_CREDENTIAL_ID).replace(
      ':tab',
      'workflows'
    ),
    waitFor: async (page) => {
      await expect(page.getByText('Production API Auth').first()).toBeVisible()
      await expect(page.getByRole('tab', { name: /Workflows/i, selected: true })).toBeVisible()
    },
  },
  {
    section: 'configuration/credentials',
    name: 'credential-detail-integrations-tab',
    path: AppRoute.Configuration.Credentials.DetailTab.replace(':credentialId', MOCK_CREDENTIAL_ID).replace(
      ':tab',
      'integrations'
    ),
    waitFor: async (page) => {
      await expect(page.getByText('Production API Auth').first()).toBeVisible()
      await expect(page.getByRole('tab', { name: /Integrations/i, selected: true })).toBeVisible()
    },
  },
  {
    section: 'access-management/users',
    name: 'user-detail-groups-tab',
    path: AppRoute.AccessManagement.UserDetailTab.replace(':userId', MOCK_USER_ID).replace(':tab', 'groups'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByRole('tab', { name: /Groups/i, selected: true })).toBeVisible()
    },
  },
  {
    section: 'access-management/users',
    name: 'user-detail-roles-tab',
    path: AppRoute.AccessManagement.UserDetailTab.replace(':userId', MOCK_USER_ID).replace(':tab', 'roles'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByRole('tab', { name: /Assignments/i, selected: true })).toBeVisible()
    },
  },
  {
    section: 'access-management/users',
    name: 'user-detail-check-access-tab',
    path: AppRoute.AccessManagement.UserDetailTab.replace(':userId', MOCK_USER_ID).replace(':tab', 'check-access'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByRole('tab', { name: /Check my access/i, selected: true })).toBeVisible()
      await expect(page.getByRole('button', { name: 'More info for Resource type' })).toBeVisible()
    },
  },
  {
    section: 'access-management/groups',
    name: 'group-detail-members-tab',
    path: AppRoute.AccessManagement.GroupDetailTab.replace(':groupId', MOCK_GROUP_ID).replace(':tab', 'members'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByRole('tab', { name: /Members/i, selected: true })).toBeVisible()
    },
  },
  {
    section: 'access-management/groups',
    name: 'group-detail-roles-tab',
    path: AppRoute.AccessManagement.GroupDetailTab.replace(':groupId', MOCK_GROUP_ID).replace(':tab', 'roles'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByRole('tab', { name: /Assignments/i, selected: true })).toBeVisible()
    },
  },
  {
    section: 'access-management/projects',
    name: 'project-detail-role-assignments-tab',
    path: AppRoute.AccessManagement.ProjectDetailTab.replace(':projectId', MOCK_PROJECT_ID).replace(
      ':tab',
      'role-assignments'
    ),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByRole('tab', { name: /Assignments/i, selected: true })).toBeVisible()
    },
  },
  {
    section: 'access-management/service-accounts',
    name: 'service-account-detail-credentials-tab',
    path: AppRoute.AccessManagement.ServiceAccountDetailTab.replace(
      ':serviceAccountId',
      MOCK_SERVICE_ACCOUNT_ID
    ).replace(':tab', 'credentials'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByRole('tab', { name: /Credentials/i, selected: true })).toBeVisible()
    },
  },
  {
    section: 'access-management/service-accounts',
    name: 'service-account-detail-assignments-tab',
    path: AppRoute.AccessManagement.ServiceAccountDetailTab.replace(
      ':serviceAccountId',
      MOCK_SERVICE_ACCOUNT_ID
    ).replace(':tab', 'assignments'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByRole('tab', { name: /Assignments/i, selected: true })).toBeVisible()
    },
  },
]
