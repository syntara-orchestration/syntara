/**
 * Page registry for visual regression testing.
 *
 * Every implemented route in the app should have an entry here.
 * The baseline enforcement script (`scripts/visual-regression/check-visual-baselines.ts`)
 * validates that this registry stays in sync with the TanStack route tree.
 *
 * Entries are organized by section (matching the route directory structure)
 * and include multiple states per page where relevant:
 *   - Default list view (with data)
 *   - Empty state (no data / filters returning nothing)
 *   - Modals and dialogs (create, edit, delete confirmations)
 *   - Detail pages with tabs
 */
import { type Page, expect } from '@playwright/test'

import * as routeRefs from '../../src/app/routes/routeReferences'
import { APP_TITLE } from '../helpers/appTitle'
import { routePaths } from '../routePaths'

import { MOCK_IDENTITY_PROVIDER_ID } from './mock-ids'
import {
  approvalInteractivePages,
  authenticationInteractivePages,
  builderInteractivePages,
  credentialDialogPages,
  credentialEditPages,
  detailTabPages,
  EXECUTION_STATUS_BADGE_TOLERANCE,
  integrationDialogPages,
  integrationSecurityPages,
  integrationWizardPages,
  oidcProviderWizardPages,
  openWorkflowKebab,
  selectDefaultProject,
  settingsTabPages,
  statusVariantPages,
  transferIdentityWizardPages,
  userCreateFormPages,
  waitForCanvasReady,
  workflowDialogPages,
} from './page-entries-interactive'

export type PageEntry = {
  /** Directory grouping for snapshot organization */
  section: string
  /** Screenshot filename slug */
  name: string
  /** Concrete URL path (parameterized routes use mock API IDs) */
  path: string
  /** Locator-based check to confirm page has loaded */
  waitFor: (page: Page) => Promise<void>
  /** Optional interaction before screenshot (e.g., open modal, apply filter) */
  setup?: (page: Page) => Promise<void>
  /** Mask the `.react-flow` canvas with a solid rectangle before comparison — required for any page rendering a ReactFlow canvas, since node/edge layout and `fitView()` output aren't pixel-deterministic */
  perceptual?: boolean
  /**
   * When `perceptual` is true, mask `.react-flow` (default). Set to `false` when the
   * screenshot subject is `StepEditorOverlay` (step/trigger forms): that overlay is
   * `position:absolute; inset:0` over the same box as `.react-flow`, so a canvas mask
   * paints solid grey over the form and `--update-snapshots` commits empty baselines.
   */
  maskCanvas?: boolean
  /** Override the default maxDiffPixelRatio for pages with non-deterministic rendering (e.g. canvas) */
  maxDiffPixelRatio?: number
  /** Mock API role to log in as (default: admin). Used for permission gating screenshots. */
  role?: 'viewer' | 'auditor' | 'user'
}

/**
 * Canvas entries require `perceptual: true` so the screenshot runner masks
 * `.react-flow` with a solid rectangle — node/edge layout and `fitView()` are
 * not pixel-deterministic. Use for any page that renders a ReactFlow canvas
 * (builder, execution visualizer, etc.). Set `maskCanvas: false` when the
 * subject is `StepEditorOverlay` (see `PageEntry.maskCanvas`).
 */
export type CanvasPageEntry = PageEntry & {
  perceptual: true
}

async function applyNameFilter(page: Page, value: string) {
  await page.getByPlaceholder('Filter by name').fill(value)
  await page.getByPlaceholder('Filter by name').press('Enter')
}

// ---------------------------------------------------------------------------
// Mock API IDs for parameterized routes
// ---------------------------------------------------------------------------
// Derived from the example YAML's own file path (see
// syntara-mock-api/src/resources/workflows.ts) — stable even after `devel` merges in
// new example fixtures, unlike a positional index.
const MOCK_WORKFLOW_ID = 'basic-conditional-demo'
const MOCK_EXECUTION_ID = 'exec-1'
const MOCK_USER_ID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
const MOCK_GROUP_ID = 'g1a2b3c4-d5e6-7890-abcd-ef1234567890'
const MOCK_PROJECT_ID = 'p-001'
const MOCK_CREDENTIAL_ID = 'cred-001'
const MOCK_SERVICE_ACCOUNT_ID = 'sa-001'

// ---------------------------------------------------------------------------
// Page entries — organized by section matching route directories
// ---------------------------------------------------------------------------
export const pages: PageEntry[] = [
  // ══════════════════════════════════════════════════════════════════════════
  // WORKFLOWS
  // ══════════════════════════════════════════════════════════════════════════
  {
    section: 'workflows',
    name: 'workflows-list',
    perceptual: true,
    path: routePaths.Workflows.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
  },
  {
    section: 'workflows',
    name: 'workflows-list-empty-filter',
    perceptual: true,
    path: routePaths.Workflows.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await applyNameFilter(page, 'zzz-no-match-zzz')
      await expect(page.getByText(/No results found|Adjust your filters/i)).toBeVisible()
    },
  },
  {
    section: 'workflows',
    name: 'workflows-delete-dialog',
    perceptual: true,
    path: routePaths.Workflows.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      // Pin to a single project so "the first workflow row" is deterministic — see
      // selectDefaultProject() for why "All projects" grouping is unsafe here.
      await selectDefaultProject(page)
      // Project header rows have their own kebab ("Delete project"), which also
      // matches a non-exact { name: 'Delete' } query — use openWorkflowKebab to
      // land on an actual workflow row instead of the wrong dialog.
      await openWorkflowKebab(page, 'Delete workflow')
      await page.getByRole('menuitem', { name: 'Delete workflow', exact: true }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByText('Delete workflow?')).toBeVisible()
      await expect(dialog.getByRole('button', { name: /Delete/i })).toBeVisible()
    },
  },

  ...workflowDialogPages,

  // ── Builder ──────────────────────────────────────────────────────────────
  // Note: builder-new excluded — ReactFlow + Zustand + lazy-load initialization
  // exceeds the 10s assertion timeout in CI. builder-edit covers the canvas.
  {
    section: 'workflows',
    name: 'builder-edit',
    path: routePaths.WorkflowBuilder.Edit(MOCK_WORKFLOW_ID),
    perceptual: true,
    waitFor: waitForCanvasReady,
  },
  ...builderInteractivePages,

  // ══════════════════════════════════════════════════════════════════════════
  // EXECUTIONS
  // ══════════════════════════════════════════════════════════════════════════
  {
    section: 'executions',
    name: 'executions-list',
    path: routePaths.Executions.Root,
    maxDiffPixelRatio: EXECUTION_STATUS_BADGE_TOLERANCE,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Workflow Runs' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
  },
  // Note: Executions uses SELECT/dropdown filters (not text input), so no empty-filter
  // screenshot — the dropdown filter doesn't produce a "no results" empty state easily.
  {
    section: 'executions',
    name: 'execution-detail',
    path: routePaths.Executions.Execution(MOCK_EXECUTION_ID),
    perceptual: true,
    // perceptual: true masks the .react-flow canvas in the screenshot — the
    // animated edge rendering variance is contained in the canvas and is now
    // irrelevant. No maxDiffPixelRatio override needed.
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    },
  },

  // ══════════════════════════════════════════════════════════════════════════
  // APPROVALS
  // ══════════════════════════════════════════════════════════════════════════
  {
    section: 'approvals',
    name: 'approvals-list',
    path: routePaths.Approvals.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Approvals' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
  },
  {
    section: 'approvals',
    name: 'approvals-list-empty-filter',
    path: routePaths.Approvals.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Approvals' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await applyNameFilter(page, 'zzz-no-match-zzz')
      await expect(page.getByText(/No results found|Adjust your filters/i)).toBeVisible()
    },
  },
  ...approvalInteractivePages,

  // ══════════════════════════════════════════════════════════════════════════
  // ACCESS MANAGEMENT — Users
  // ══════════════════════════════════════════════════════════════════════════
  {
    section: 'access-management/users',
    name: 'users-list',
    path: routePaths.AccessManagement.Users,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    maxDiffPixelRatio: 0.02,
  },
  {
    section: 'access-management/users',
    name: 'users-list-empty-filter',
    path: routePaths.AccessManagement.Users,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await page.getByRole('textbox', { name: /filter/i }).fill('zzz-no-match-zzz')
      await page.getByRole('textbox', { name: /filter/i }).press('Enter')
      await expect(page.getByText(/No results found|Adjust your filters/i)).toBeVisible()
    },
  },
  {
    section: 'access-management/users',
    name: 'users-delete-dialog',
    path: routePaths.AccessManagement.Users,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      const kebab = page.getByRole('button', { name: /Actions|Kebab toggle/i }).first()
      await kebab.click()
      await page.getByRole('menuitem', { name: 'Delete user' }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: /Delete/i })).toBeVisible()
    },
  },
  {
    section: 'access-management/users',
    name: 'user-create',
    path: routePaths.AccessManagement.CreateUser,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Create user' })).toBeVisible()
    },
  },
  {
    section: 'access-management/users',
    name: 'user-detail',
    path: routePaths.AccessManagement.UserDetail(MOCK_USER_ID),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    },
  },
  {
    section: 'access-management/users',
    name: 'user-edit',
    path: routePaths.AccessManagement.EditUser(MOCK_USER_ID),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Edit Demo Admin' })).toBeVisible()
    },
  },

  ...transferIdentityWizardPages,
  ...userCreateFormPages,

  // ══════════════════════════════════════════════════════════════════════════
  // ACCESS MANAGEMENT — Groups
  // ══════════════════════════════════════════════════════════════════════════
  {
    section: 'access-management/groups',
    name: 'groups-list',
    path: routePaths.AccessManagement.Groups,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
  },
  {
    section: 'access-management/groups',
    name: 'groups-list-empty-filter',
    path: routePaths.AccessManagement.Groups,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await page.getByRole('textbox', { name: /filter/i }).fill('zzz-no-match-zzz')
      await page.getByRole('textbox', { name: /filter/i }).press('Enter')
      await expect(page.getByText(/No results found|Adjust your filters/i)).toBeVisible()
    },
  },
  {
    section: 'access-management/groups',
    name: 'groups-create-modal',
    path: routePaths.AccessManagement.Groups,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await page.getByRole('button', { name: 'Create group' }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: /Create/i })).toBeVisible()
    },
  },
  {
    section: 'access-management/groups',
    name: 'groups-delete-dialog',
    path: routePaths.AccessManagement.Groups,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      // Find a non-builtin group row and open its kebab
      await page
        .locator('table tbody tr')
        .filter({ hasText: 'platform-admins' })
        .getByRole('button', { name: /Actions|Kebab toggle/i })
        .click()
      await page.getByRole('menuitem', { name: 'Delete group' }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: /Delete/i })).toBeVisible()
    },
  },
  {
    section: 'access-management/groups',
    name: 'group-detail',
    path: routePaths.AccessManagement.GroupDetail(MOCK_GROUP_ID),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    },
  },

  // ══════════════════════════════════════════════════════════════════════════
  // ACCESS MANAGEMENT — Projects
  // ══════════════════════════════════════════════════════════════════════════
  {
    section: 'access-management/projects',
    name: 'projects-list',
    path: routePaths.AccessManagement.Projects,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
  },
  {
    section: 'access-management/projects',
    name: 'projects-list-empty-filter',
    path: routePaths.AccessManagement.Projects,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      // Projects has two filter fields (name + description) — use placeholder to target name.
      // The mock API handler now accepts both 'name' and 'name[contains]' query params so the
      // FilterBar chip format (name[contains]=...) correctly returns empty results.
      await page.getByPlaceholder('Filter by name').fill('zzz-no-match-zzz')
      await page.getByPlaceholder('Filter by name').press('Enter')
      await expect(page.getByText(/No results found/i)).toBeVisible({ timeout: 10_000 })
    },
  },
  {
    section: 'access-management/projects',
    name: 'projects-create-modal',
    path: routePaths.AccessManagement.Projects,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await page.getByRole('button', { name: 'Create project' }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: /Create/i })).toBeVisible()
    },
  },
  {
    section: 'access-management/projects',
    name: 'project-detail',
    path: routePaths.AccessManagement.ProjectDetail(MOCK_PROJECT_ID),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    },
  },

  // ══════════════════════════════════════════════════════════════════════════
  // ACCESS MANAGEMENT — Service Accounts
  // ══════════════════════════════════════════════════════════════════════════
  {
    section: 'access-management/service-accounts',
    name: 'service-accounts-list',
    path: routePaths.AccessManagement.ServiceAccounts,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
  },
  {
    section: 'access-management/service-accounts',
    name: 'service-accounts-list-empty-filter',
    path: routePaths.AccessManagement.ServiceAccounts,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await page.getByRole('textbox', { name: /filter/i }).fill('zzz-no-match-zzz')
      await page.getByRole('textbox', { name: /filter/i }).press('Enter')
      await expect(page.getByText(/No results found|Adjust your filters/i)).toBeVisible()
    },
  },
  {
    section: 'access-management/service-accounts',
    name: 'service-accounts-create-modal',
    path: routePaths.AccessManagement.ServiceAccounts,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await page.getByRole('button', { name: 'Create service account' }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: /Create/i })).toBeVisible()
    },
  },
  {
    section: 'access-management/service-accounts',
    name: 'service-accounts-delete-dialog',
    path: routePaths.AccessManagement.ServiceAccounts,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
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
    section: 'access-management/service-accounts',
    name: 'service-account-detail',
    path: routePaths.AccessManagement.ServiceAccountDetail(MOCK_SERVICE_ACCOUNT_ID),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    },
  },

  // ══════════════════════════════════════════════════════════════════════════
  // ACCESS MANAGEMENT — Roles
  // ══════════════════════════════════════════════════════════════════════════
  {
    section: 'access-management/roles',
    name: 'roles-list',
    path: routePaths.AccessManagement.Roles,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
  },
  {
    section: 'access-management/roles',
    name: 'roles-list-empty-filter',
    path: routePaths.AccessManagement.Roles,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await page.getByRole('textbox', { name: /filter/i }).fill('zzz-no-match-zzz')
      await page.getByRole('textbox', { name: /filter/i }).press('Enter')
      await expect(page.getByText(/No results found|Adjust your filters/i)).toBeVisible()
    },
  },
  {
    section: 'access-management/roles',
    name: 'roles-add-dialog',
    path: routePaths.AccessManagement.Roles,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await page.getByRole('button', { name: 'Create role' }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: /Create/i })).toBeVisible()
    },
  },

  // ══════════════════════════════════════════════════════════════════════════
  // ACCESS MANAGEMENT — Policies
  // ══════════════════════════════════════════════════════════════════════════
  {
    section: 'access-management/policies',
    name: 'policies-list',
    path: routePaths.AccessManagement.Policies,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
  },
  {
    section: 'access-management/policies',
    name: 'policies-list-empty-filter',
    path: routePaths.AccessManagement.Policies,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await page.getByRole('textbox', { name: /filter/i }).fill('zzz-no-match-zzz')
      await page.getByRole('textbox', { name: /filter/i }).press('Enter')
      await expect(page.getByText(/No results found|Adjust your filters/i)).toBeVisible()
    },
  },

  // ══════════════════════════════════════════════════════════════════════════
  // ACCESS MANAGEMENT — Assignments
  // ══════════════════════════════════════════════════════════════════════════
  {
    section: 'access-management/assignments',
    name: 'assignments-list',
    path: routePaths.AccessManagement.Assignments,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
  },
  {
    section: 'access-management/assignments',
    name: 'assignments-list-empty-filter',
    path: routePaths.AccessManagement.Assignments,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      // Assignments uses API-based filtering (principal_name[contains]); target the
      // Principal Name filter explicitly so we don't hit a different toolbar input.
      const filterInput = page.getByRole('textbox', { name: /principal name filter/i })
      await filterInput.fill('zzz-no-match-zzz')
      await filterInput.press('Enter')
      await expect(page.getByRole('heading', { name: /No results found/i })).toBeVisible({
        timeout: 10_000,
      })
    },
  },

  // ══════════════════════════════════════════════════════════════════════════
  // ACCESS MANAGEMENT — Check access
  // ══════════════════════════════════════════════════════════════════════════
  {
    section: 'access-management/check-access',
    name: 'check-access',
    path: routePaths.AccessManagement.CheckAccess,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.getByRole('button', { name: 'More info for Resource type' })).toBeVisible()
    },
  },

  // ══════════════════════════════════════════════════════════════════════════
  // ACCESS MANAGEMENT — Authentication
  // ══════════════════════════════════════════════════════════════════════════
  {
    section: 'authentication',
    name: 'authentication',
    path: routePaths.SystemAdministration.Authentication.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Identity Providers' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
  },
  {
    section: 'authentication',
    name: 'authentication-delete-dialog',
    path: routePaths.SystemAdministration.Authentication.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Identity Providers' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      const kebab = page.getByRole('button', { name: /Actions|Kebab toggle/i }).first()
      await kebab.click()
      await page.getByRole('menuitem', { name: 'Delete identity provider' }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: /Delete/i })).toBeVisible()
    },
  },
  {
    section: 'authentication',
    name: 'identity-provider-add',
    path: routePaths.SystemAdministration.Authentication.AddIdentityProvider,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Add OIDC provider' })).toBeVisible()
    },
  },
  {
    section: 'authentication',
    name: 'identity-provider-add-claim-mapping',
    path: routePaths.SystemAdministration.Authentication.AddIdentityProvider,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Add OIDC provider' })).toBeVisible()
    },
    setup: async (page) => {
      await page.getByRole('button', { name: 'Claim mapping' }).click()
      await expect(page.getByRole('heading', { name: 'Claim mapping' })).toBeVisible()
    },
  },
  {
    section: 'authentication',
    name: 'identity-provider-add-template-dropdown',
    path: routePaths.SystemAdministration.Authentication.AddIdentityProvider,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Add OIDC provider' })).toBeVisible()
    },
    setup: async (page) => {
      await page.getByRole('button', { name: /Select a provider template/i }).click()
      await expect(page.getByRole('option', { name: /Ansible Automation Platform/i })).toBeVisible()
    },
  },
  {
    section: 'authentication',
    name: 'identity-provider-group-mapping-edit',
    path: routePaths.SystemAdministration.Authentication.EditGroupMapping(MOCK_IDENTITY_PROVIDER_ID),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Add group mapping' })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Save mapping' })).toBeVisible()
      await expect(page.getByRole('textbox', { name: 'IdP group value 1' })).toBeVisible()
    },
  },

  // ── Token Revocation ────────────────────────────────────────────────────
  {
    section: 'access-management/token-revocation',
    name: 'token-revocation',
    path: routePaths.AccessManagement.TokenRevocation,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.getByRole('tab', { name: 'Token revocation' })).toBeVisible()
    },
  },
  {
    section: 'access-management/token-revocation',
    name: 'token-revocation-confirm-dialog',
    path: routePaths.AccessManagement.TokenRevocation,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.getByRole('tab', { name: 'Token revocation' })).toBeVisible()
    },
    setup: async (page) => {
      await page.getByRole('button', { name: 'Revoke all tokens' }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: /Revoke/i })).toBeVisible()
    },
  },

  // ══════════════════════════════════════════════════════════════════════════
  // CONFIGURATION — Settings
  // ══════════════════════════════════════════════════════════════════════════
  {
    section: 'settings',
    name: 'settings',
    path: routePaths.SystemAdministration.Settings,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
      await expect(page.getByRole('tab').first()).toBeVisible()
    },
  },

  // ══════════════════════════════════════════════════════════════════════════
  // CONFIGURATION — Integrations (+ disconnect dialog, detail from interactive)
  // ══════════════════════════════════════════════════════════════════════════
  {
    section: 'configuration/integrations',
    name: 'integrations-list',
    path: routePaths.Configuration.Integrations.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
  },
  {
    section: 'configuration/integrations',
    name: 'integrations-list-empty-filter',
    path: routePaths.Configuration.Integrations.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      await page.getByRole('textbox', { name: /filter/i }).fill('zzz-no-match-zzz')
      await page.getByRole('textbox', { name: /filter/i }).press('Enter')
      await expect(page.getByText(/No results found|Adjust your filters/i)).toBeVisible()
    },
  },
  {
    section: 'configuration/integrations',
    name: 'integration-configure',
    path: routePaths.Configuration.Integrations.Configure,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Configure integration' })).toBeVisible()
    },
  },
  {
    section: 'configuration/integrations',
    name: 'integration-detail',
    path: routePaths.Configuration.Integrations.Detail('1'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByText('Server name / ID')).toBeVisible()
    },
  },
  {
    section: 'configuration/integrations',
    name: 'integration-detail-credential-disabled',
    path: routePaths.Configuration.Integrations.Detail('3'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByText('Credential disabled')).toBeVisible()
    },
  },
  {
    section: 'configuration/integrations',
    name: 'integration-tools',
    path: routePaths.Configuration.Integrations.DetailTab('1', 'resources'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByText('get_resource')).toBeVisible()
      await expect(page.getByRole('tab', { name: 'Details' })).toBeVisible()
    },
  },
  {
    section: 'configuration/integrations',
    name: 'integration-tools-empty',
    path: routePaths.Configuration.Integrations.DetailTab('4', 'resources'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByText('No resources discovered yet')).toBeVisible()
    },
  },
  {
    section: 'configuration/integrations',
    name: 'integration-edit',
    path: routePaths.Configuration.Integrations.Edit('1'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Edit integration' })).toBeVisible()
    },
  },
  {
    section: 'configuration/integrations',
    name: 'llm-provider-detail',
    path: routePaths.Configuration.Integrations.Detail('10'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Red Hat AI' })).toBeVisible()
      await expect(page.getByText('LLM Provider', { exact: true })).toBeVisible()
    },
  },
  {
    section: 'configuration/integrations',
    name: 'llm-provider-models',
    path: routePaths.Configuration.Integrations.DetailTab('10', 'resources'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByText('granite-3.3-8b-instruct')).toBeVisible()
      await expect(page.getByRole('tab', { name: 'Details' })).toBeVisible()
    },
  },
  {
    section: 'configuration/integrations',
    name: 'llm-provider-edit',
    path: routePaths.Configuration.Integrations.Edit('10'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Edit integration' })).toBeVisible()
    },
  },
  {
    section: 'configuration/integrations',
    name: 'aap-detail',
    path: routePaths.Configuration.Integrations.Detail('12'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Production AAP' })).toBeVisible()
      await expect(page.getByText('Ansible Automation Platform', { exact: true })).toBeVisible()
    },
  },
  {
    section: 'configuration/integrations',
    name: 'aap-edit',
    path: routePaths.Configuration.Integrations.Edit('12'),
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Edit integration' })).toBeVisible()
      await expect(page.locator('input[value="https://aap.prod.example.com"]')).toBeVisible()
    },
  },
  ...integrationDialogPages,
  ...integrationSecurityPages,
  ...integrationWizardPages,

  // ══════════════════════════════════════════════════════════════════════════
  // CONFIGURATION — Credentials
  // ══════════════════════════════════════════════════════════════════════════
  {
    section: 'configuration/credentials',
    name: 'credentials-list',
    path: routePaths.Configuration.Credentials.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
  },
  {
    section: 'configuration/credentials',
    name: 'credentials-list-empty-filter',
    path: routePaths.Configuration.Credentials.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      const filterInput = page.getByPlaceholder('Filter by keyword')
      await filterInput.fill('zzz-no-match-zzz')
      await filterInput.press('Enter')
      await expect(page.getByText(/No results found|Adjust your filters/i)).toBeVisible()
    },
  },
  {
    section: 'configuration/credentials',
    name: 'credentials-create-modal',
    path: routePaths.Configuration.Credentials.Root,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    },
    setup: async (page) => {
      // Pick a project so the modal's Project dropdown is pre-populated
      await page.getByRole('textbox', { name: 'Project' }).click()
      await page.getByRole('option', { name: 'default' }).click()
      await page.getByRole('button', { name: /create credential/i }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: /Create/i })).toBeVisible()
    },
  },
  {
    section: 'configuration/credentials',
    name: 'credential-detail',
    path: routePaths.Configuration.Credentials.Detail(MOCK_CREDENTIAL_ID),
    waitFor: async (page) => {
      // Credential detail uses ReactNode title (back button + name), not a heading
      await expect(page.getByText('Production API Auth').first()).toBeVisible()
    },
  },
  ...credentialDialogPages,
  ...credentialEditPages,

  // ══════════════════════════════════════════════════════════════════════════
  // INTERACTIVE STATES — status variants, detail tabs, settings tabs,
  // authentication (entries defined in page-entries-interactive.ts)
  // ══════════════════════════════════════════════════════════════════════════
  ...statusVariantPages,
  ...detailTabPages,
  ...settingsTabPages,
  ...authenticationInteractivePages,
  ...oidcProviderWizardPages,

  // ══════════════════════════════════════════════════════════════════════════
  // PERMISSION GATING — restricted role screenshots
  // ══════════════════════════════════════════════════════════════════════════
  {
    section: 'permission-gating',
    name: 'viewer-workflows-list',
    path: routePaths.Workflows.Root,
    role: 'viewer',
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()
      await expect(page.getByRole('row').nth(1)).toBeVisible()
    },
  },
  {
    section: 'permission-gating',
    name: 'viewer-credentials-list',
    path: routePaths.Configuration.Credentials.Root,
    role: 'viewer',
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()
      await expect(page.getByRole('row').nth(1)).toBeVisible()
    },
  },
  {
    section: 'permission-gating',
    name: 'auditor-users-list',
    path: routePaths.AccessManagement.Users,
    role: 'auditor',
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: 'Access Management' })).toBeVisible()
      await expect(page.getByRole('row').nth(1)).toBeVisible()
    },
  },
  {
    section: 'permission-gating',
    name: 'viewer-access-denied',
    path: routePaths.AccessManagement.Users,
    role: 'viewer',
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: /access denied/i })).toBeVisible()
    },
  },
  {
    section: 'permission-gating',
    name: 'viewer-builder-read-only',
    path: routePaths.WorkflowBuilder.Edit(MOCK_WORKFLOW_ID),
    role: 'viewer',
    perceptual: true,
    waitFor: waitForCanvasReady,
  },
  {
    section: 'permission-gating',
    name: 'auditor-authentication-list',
    path: routePaths.SystemAdministration.Authentication.Root,
    role: 'auditor',
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Identity Providers' })).toBeVisible()
      await expect(page.getByRole('row').nth(1)).toBeVisible()
    },
  },
  {
    section: 'permission-gating',
    name: 'user-workflows-list',
    path: routePaths.Workflows.Root,
    role: 'user',
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()
      await expect(page.getByRole('row').nth(1)).toBeVisible()
    },
  },
  {
    section: 'permission-gating',
    name: 'viewer-workflows-kebab-disabled',
    path: routePaths.Workflows.Root,
    role: 'viewer',
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()
      await expect(page.getByRole('row').nth(1)).toBeVisible()
    },
    setup: async (page) => {
      const kebab = page.getByRole('button', { name: /Actions|Kebab toggle/i }).first()
      await kebab.click({ force: true })
      await expect(page.getByRole('menuitem').first()).toBeVisible()
    },
  },
  {
    section: 'permission-gating',
    name: 'viewer-executions-list',
    path: routePaths.Executions.Root,
    role: 'viewer',
    maxDiffPixelRatio: EXECUTION_STATUS_BADGE_TOLERANCE,
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Workflow Runs' })).toBeVisible()
      await expect(page.getByRole('row').nth(1)).toBeVisible()
    },
  },
  {
    section: 'permission-gating',
    name: 'viewer-approvals-list',
    path: routePaths.Approvals.Root,
    role: 'viewer',
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Approvals' })).toBeVisible()
      await expect(page.getByRole('row').nth(1)).toBeVisible()
    },
  },
  {
    section: 'permission-gating',
    name: 'viewer-integrations-list',
    path: routePaths.Configuration.Integrations.Root,
    role: 'viewer',
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()
    },
  },
  {
    section: 'permission-gating',
    name: 'viewer-settings',
    path: routePaths.SystemAdministration.Settings,
    role: 'viewer',
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { level: 1, name: 'Settings' })).toBeVisible()
    },
  },
]

// ---------------------------------------------------------------------------
// Login page entries — pre-auth, outside the authenticated route tree
// ---------------------------------------------------------------------------
export const loginPages: PageEntry[] = [
  {
    section: 'login',
    name: 'login-default',
    path: '/',
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: `Log in to ${APP_TITLE}` })).toBeVisible()
    },
  },
  {
    section: 'login',
    name: 'login-oidc-auth-error',
    path: '/?auth_error=email_already_linked',
    waitFor: async (page) => {
      await expect(page.getByText('This email is already associated with an existing account.')).toBeVisible()
    },
  },
  {
    section: 'login',
    name: 'login-local-form-expanded',
    path: '/',
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: `Log in to ${APP_TITLE}` })).toBeVisible()
    },
    setup: async (page) => {
      const localToggle = page.getByRole('button', { name: 'Sign in using local account' })
      if (await localToggle.isVisible()) {
        await localToggle.click()
      }
      await expect(page.getByLabel('Username')).toBeVisible()
    },
  },
  {
    section: 'login',
    name: 'login-error',
    path: '/',
    waitFor: async (page) => {
      await expect(page.getByRole('heading', { name: `Log in to ${APP_TITLE}` })).toBeVisible()
    },
    setup: async (page) => {
      // Expand the local login form (IDPs are seeded, so local login is behind a toggle)
      const localToggle = page.getByRole('button', { name: 'Sign in using local account' })
      if (await localToggle.isVisible()) {
        await localToggle.click()
      }
      // Submit with username but no password to trigger client-side validation error
      await page.getByLabel('Username').fill('admin')
      await page.getByRole('button', { name: 'Log in', exact: true }).click()
      await expect(page.getByText('Enter your password')).toBeVisible()
    },
  },
]

// ---------------------------------------------------------------------------
// Routes intentionally excluded from visual regression
// ---------------------------------------------------------------------------

/** Implemented routes that intentionally have no visual baseline. */
export const excludedUnimplemented: string[] = [routePaths.Configuration.Overview]

/** Routes excluded because they need dynamic setup or have no seeded mock data */
export const excludedDynamic: string[] = [
  routePaths.FeatureFlagDemo, // Temporary direct-link demo route; no baseline required.
  routePaths.WorkflowBuilder.New,
  routeRefs.editIdentityProviderRoute.fullPath, // covered by oidcProviderWizardPages
  routeRefs.identityProviderUnknownTabRoute.fullPath, // covered by identity-provider-detail interactive entries
  routePaths.AccessManagement.Root,
  routePaths.Auth.TestSignInCallback,
  routeRefs.transferIdentityRoute.fullPath, // covered by transferIdentityWizardPages (interactive entries)
  routeRefs.serviceAccountDetailUnknownTabRoute.fullPath, // covered by detailTabPages (interactive entries)
  routePaths.MyProfile.Root, // covered via user detail component — My Profile is a wrapper
  routeRefs.myProfileTabRoute.fullPath, // tab variant of the above
]

/** All excluded route patterns (union of both lists) */
export const allExcludedRoutes: string[] = [...excludedUnimplemented, ...excludedDynamic]
