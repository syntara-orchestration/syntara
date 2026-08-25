/**
 * E2E Tests: Permission Gating (AAP-74439)
 *
 * Validates that navigation items, page tabs, action buttons, and route guards
 * are correctly shown, hidden, or disabled based on the user's role/permissions.
 *
 * Dual-mode: runs against both mock API (via token interception) and a real
 * backend (via dynamically created users — see roleSetup.ts / fixtures.ts).
 *
 * All tests are self-contained: they create any required seed data via the
 * admin API and clean up in `finally` blocks, so they pass on an empty backend.
 *
 * Roles tested:
 * - admin:   full access to all features
 * - viewer:  read-only on workflow, execution, approval, credential
 * - auditor: read-only on all resources except user_identity
 * - user:    read on workflow, execution, approval, credential, user, group, role, policy, authz
 */

import { type Page, test, expect, toAppUrl, appBaseUrl } from './fixtures'
import { buildUniqueName } from './helpers/workflows'
import {
  apiRequest,
  createCredentialViaApi,
  createGroupViaApi,
  createIdentityProviderViaApi,
  createServiceAccountViaApi,
  createUserViaApi,
  deleteCredentialViaApi,
  deleteGroupViaApi,
  deleteIdentityProviderViaApi,
  deleteServiceAccountViaApi,
  deleteUserViaApi,
  ensureProject,
  getAuthToken,
} from './utils/api'

const AM_URL = '/system-administration/access-management'
const AUTH_URL = '/system-administration/authentication'

// ── Shared helpers ────────────────────────────────────────────────────────

async function createTestWorkflow(adminApp: Page): Promise<{ id: string; name: string }> {
  const name = buildUniqueName('e2e-perm-wf')
  const project = await ensureProject(adminApp)
  if (!project) throw new Error('createTestWorkflow: could not ensure project')
  const resp = await apiRequest(adminApp, 'post', '/workflows', {
    data: {
      name,
      project_id: project.id,
      workflow_definition: {
        schema_version: '2.0.0',
        name,
        triggers: [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
        nodes: [],
        edges: [],
      },
    },
  })
  if (!resp.ok()) throw new Error(`Workflow creation failed: ${resp.status()}`)
  const body = (await resp.json()) as { id: string }
  return { id: body.id, name }
}

async function deleteTestWorkflow(adminApp: Page, workflowId: string): Promise<void> {
  await apiRequest(adminApp, 'delete', `/workflows/${workflowId}`)
}

async function createTestCredential(adminApp: Page): Promise<{ id: string; name: string }> {
  const project = await ensureProject(adminApp)
  if (!project) throw new Error('ensureProject failed')
  const name = buildUniqueName('e2e-perm-cred')
  const credId = await createCredentialViaApi(adminApp, { name, projectId: project.id })
  if (!credId) throw new Error('createCredentialViaApi failed')
  return { id: credId, name }
}

// ── Navigation visibility ────────────────────────────────────────────────

test.describe('Permission gating — Navigation visibility', () => {
  test('admin sees all navigation items', async ({ app }) => {
    const nav = app.getByRole('navigation', { name: 'Main navigation' })

    await expect(nav.getByRole('link', { name: 'Workflows' })).toBeVisible()
    await expect(nav.getByRole('link', { name: 'Workflow Runs' })).toBeVisible()
    await expect(nav.getByRole('link', { name: 'Approvals' })).toBeVisible()

    const configItem = nav.getByLabel('Configuration')
    await expect(configItem).toBeVisible()
    await configItem.click()
    await expect(app.getByRole('menuitem', { name: 'Integrations' })).toBeVisible()
    await expect(app.getByRole('menuitem', { name: 'Credentials' })).toBeVisible()
    await app.keyboard.press('Escape')
    // Wait for the Configuration flyout to fully close before opening the next one
    await expect(app.getByRole('menuitem', { name: 'Integrations' })).toBeHidden()

    const sysAdminItem = nav.getByLabel('System Administration')
    await expect(sysAdminItem).toBeVisible()
    await sysAdminItem.click()
    await expect(app.getByRole('menuitem', { name: 'Access Management' })).toBeVisible()
    await expect(app.getByRole('menuitem', { name: 'Identity Providers' })).toBeVisible()
    await expect(app.getByRole('menuitem', { name: 'Settings' })).toBeVisible()
  })

  test('viewer sees only operational items — no System Administration', async ({ viewerApp }) => {
    const nav = viewerApp.getByRole('navigation', { name: 'Main navigation' })

    await expect(nav.getByRole('link', { name: 'Workflows' })).toBeVisible()
    await expect(nav.getByRole('link', { name: 'Workflow Runs' })).toBeVisible()
    await expect(nav.getByRole('link', { name: 'Approvals' })).toBeVisible()
    await expect(nav.getByLabel('Configuration')).toBeVisible()

    await expect(nav.getByLabel('System Administration')).not.toBeVisible()
  })

  test('auditor sees all navigation items', async ({ auditorApp }) => {
    const nav = auditorApp.getByRole('navigation', { name: 'Main navigation' })

    await expect(nav.getByRole('link', { name: 'Workflows' })).toBeVisible()
    await expect(nav.getByRole('link', { name: 'Workflow Runs' })).toBeVisible()
    await expect(nav.getByRole('link', { name: 'Approvals' })).toBeVisible()
    await expect(nav.getByLabel('Configuration')).toBeVisible()

    const sysAdminItem = nav.getByLabel('System Administration')
    await expect(sysAdminItem).toBeVisible()
    await sysAdminItem.click()
    await expect(auditorApp.getByRole('menuitem', { name: 'Access Management' })).toBeVisible()
    await expect(auditorApp.getByRole('menuitem', { name: 'Identity Providers' })).toBeVisible()
    await expect(auditorApp.getByRole('menuitem', { name: 'Settings' })).toBeVisible()
  })

  test('user sees Access Management but not Identity Providers or Settings', async ({ userApp }) => {
    const nav = userApp.getByRole('navigation', { name: 'Main navigation' })

    await expect(nav.getByRole('link', { name: 'Workflows' })).toBeVisible()
    await expect(nav.getByRole('link', { name: 'Workflow Runs' })).toBeVisible()
    await expect(nav.getByRole('link', { name: 'Approvals' })).toBeVisible()
    await expect(nav.getByLabel('Configuration')).toBeVisible()

    // When only one SA child is visible (Access Management), the nav renders
    // a direct link instead of a flyout dropdown.
    const sysAdminLink = nav.getByLabel('System Administration')
    await expect(sysAdminLink).toBeVisible()
    await sysAdminLink.click()
    await expect(userApp.getByRole('heading', { name: 'Access Management' })).toBeVisible()
  })
})

// ── Access Management tab visibility ─────────────────────────────────────

test.describe('Permission gating — Access Management tabs', () => {
  const ALL_AM_TABS = [
    'Users',
    'Groups',
    'Projects',
    'Policies',
    'Roles',
    'Assignments',
    'Check access',
    'Token revocation',
  ] as const

  /** Auditors do not have query:authz permission, so Check access is hidden. */
  const AUDITOR_AM_TABS = ALL_AM_TABS.filter((tab) => tab !== 'Check access')

  test('admin sees all AM tabs', async ({ app }) => {
    await app.goto(toAppUrl(`${AM_URL}/users`))
    await expect(app.getByRole('heading', { name: 'Access Management' })).toBeVisible()

    for (const tab of ALL_AM_TABS) {
      await expect(app.getByRole('tab', { name: tab })).toBeVisible()
    }
  })

  test('auditor sees all AM tabs except Check access', async ({ auditorApp }) => {
    await auditorApp.goto(toAppUrl(`${AM_URL}/users`))
    await expect(auditorApp.getByRole('heading', { name: 'Access Management' })).toBeVisible()

    for (const tab of AUDITOR_AM_TABS) {
      await expect(auditorApp.getByRole('tab', { name: tab })).toBeVisible()
    }

    // Auditor lacks query:authz permission, so Check access tab is hidden
    await expect(auditorApp.getByRole('tab', { name: 'Check access' })).not.toBeVisible()
  })

  test('user sees Users, Groups, Policies, Roles, Check access — not Projects, Assignments, or Token Revocation', async ({
    userApp,
  }) => {
    await userApp.goto(toAppUrl(`${AM_URL}/users`))
    await expect(userApp.getByRole('heading', { name: 'Access Management' })).toBeVisible()

    const visibleTabs = ['Users', 'Groups', 'Policies', 'Roles', 'Check access'] as const
    for (const tab of visibleTabs) {
      await expect(userApp.getByRole('tab', { name: tab })).toBeVisible()
    }

    const hiddenTabs = ['Projects', 'Assignments', 'Token revocation'] as const
    for (const tab of hiddenTabs) {
      await expect(userApp.getByRole('tab', { name: tab })).not.toBeVisible()
    }
  })
})

// ── Detail page tab visibility ───────────────────────────────────────────

test.describe('Permission gating — Detail page tabs', () => {
  test('user: group detail hides Assignments tab when role-assignment:read is denied', async ({ app, userApp }) => {
    const groupId = await createGroupViaApi(app, { name: buildUniqueName('e2e-perm-group') })
    if (!groupId) throw new Error('createGroupViaApi failed to create group')

    try {
      await userApp.goto(toAppUrl(`${AM_URL}/groups/${groupId}`))
      await expect(userApp.getByRole('heading', { level: 1 })).toBeVisible()

      await expect(userApp.getByRole('tab', { name: /Details/ })).toBeVisible()
      await expect(userApp.getByRole('tab', { name: /Members/ })).toBeVisible()
      await expect(userApp.getByRole('tab', { name: /Assignments/ })).not.toBeVisible()
    } finally {
      await deleteGroupViaApi(app, groupId)
    }
  })

  test('auditor: group detail shows Assignments tab', async ({ app, auditorApp }) => {
    const groupId = await createGroupViaApi(app, { name: buildUniqueName('e2e-perm-group') })
    if (!groupId) throw new Error('createGroupViaApi failed to create group')

    try {
      await auditorApp.goto(toAppUrl(`${AM_URL}/groups/${groupId}`))
      await expect(auditorApp.getByRole('heading', { level: 1 })).toBeVisible()

      await expect(auditorApp.getByRole('tab', { name: /Details/ })).toBeVisible()
      await expect(auditorApp.getByRole('tab', { name: /Members/ })).toBeVisible()
      await expect(auditorApp.getByRole('tab', { name: /Assignments/ })).toBeVisible()
    } finally {
      await deleteGroupViaApi(app, groupId)
    }
  })
})

// ── Route-level guards ────────────────────────────────────────────────────

test.describe('Permission gating — Route guards', () => {
  const ACCESS_DENIED_ROUTES = [
    [`${AM_URL}/users/create`, 'Create User'],
    [`${AM_URL}/users/any-user-id/edit`, 'Edit User'],
    [`${AUTH_URL}/identity-providers/add`, 'Add Identity Provider'],
    [`${AUTH_URL}/identity-providers/any-provider-id/edit`, 'Edit Identity Provider'],
  ] as const

  for (const [url, label] of ACCESS_DENIED_ROUTES) {
    test(`user: direct URL to ${label} shows access denied`, async ({ userApp }) => {
      await userApp.goto(toAppUrl(url))
      await expect(userApp.getByRole('heading', { name: 'Access denied', level: 2 })).toBeVisible()
    })

    test(`auditor: direct URL to ${label} shows access denied`, async ({ auditorApp }) => {
      await auditorApp.goto(toAppUrl(url))
      await expect(auditorApp.getByRole('heading', { name: 'Access denied', level: 2 })).toBeVisible()
    })
  }

  test('viewer: direct URL to Create User shows access denied', async ({ viewerApp }) => {
    await viewerApp.goto(toAppUrl(`${AM_URL}/users/create`))

    await expect(viewerApp.getByRole('heading', { name: 'Access denied', level: 2 })).toBeVisible()
  })

  test('viewer: direct URL to Add Identity Provider shows access denied', async ({ viewerApp }) => {
    await viewerApp.goto(toAppUrl(`${AUTH_URL}/identity-providers/add`))

    await expect(viewerApp.getByRole('heading', { name: 'Access denied', level: 2 })).toBeVisible()
  })

  test('viewer: direct URL to Access Management shows access denied', async ({ viewerApp }) => {
    await viewerApp.goto(toAppUrl(`${AM_URL}/users`))

    await expect(viewerApp.getByRole('heading', { name: 'Access denied', level: 2 })).toBeVisible()
  })

  test('admin: direct URL to Create User renders the form', async ({ app }) => {
    await app.goto(toAppUrl(`${AM_URL}/users/create`))

    await expect(app.getByRole('heading', { name: 'Access denied' })).not.toBeVisible()
    await expect(app.getByRole('heading', { name: /Create User/i })).toBeVisible()
  })
})

// ── Action gating — Workflows ────────────────────────────────────────────

test.describe('Permission gating — Workflow actions', () => {
  test('viewer: Create workflow button is disabled with tooltip', async ({ app, viewerApp }) => {
    const { id: workflowId } = await createTestWorkflow(app)

    try {
      await viewerApp.goto(toAppUrl('/workflows'))
      await expect(viewerApp.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

      const createButton = viewerApp.getByRole('button', { name: /Create workflow/i })
      await expect(createButton).toBeVisible()
      await expect(createButton).toHaveAttribute('aria-disabled', 'true')

      await createButton.hover()
      await expect(viewerApp.getByRole('tooltip').filter({ hasText: 'workflow:create' })).toBeVisible()
    } finally {
      await deleteTestWorkflow(app, workflowId)
    }
  })

  test('auditor: Create workflow button is disabled', async ({ app, auditorApp }) => {
    const { id: workflowId } = await createTestWorkflow(app)

    try {
      await auditorApp.goto(toAppUrl('/workflows'))
      await expect(auditorApp.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

      const createButton = auditorApp.getByRole('button', { name: /Create workflow/i })
      await expect(createButton).toBeVisible()
      await expect(createButton).toHaveAttribute('aria-disabled', 'true')
    } finally {
      await deleteTestWorkflow(app, workflowId)
    }
  })

  test('viewer: Import workflow button is disabled', async ({ app, viewerApp }) => {
    const { id: workflowId } = await createTestWorkflow(app)

    try {
      await viewerApp.goto(toAppUrl('/workflows'))
      await expect(viewerApp.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

      const importButton = viewerApp.getByRole('button', { name: /Import workflow/i })
      await expect(importButton).toBeVisible()
      await expect(importButton).toHaveAttribute('aria-disabled', 'true')
    } finally {
      await deleteTestWorkflow(app, workflowId)
    }
  })

  test('auditor: Import workflow button is disabled', async ({ app, auditorApp }) => {
    const { id: workflowId } = await createTestWorkflow(app)

    try {
      await auditorApp.goto(toAppUrl('/workflows'))
      await expect(auditorApp.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

      const importButton = auditorApp.getByRole('button', { name: /Import workflow/i })
      await expect(importButton).toBeVisible()
      await expect(importButton).toHaveAttribute('aria-disabled', 'true')
    } finally {
      await deleteTestWorkflow(app, workflowId)
    }
  })

  test('viewer: all workflow row actions are aria-disabled', async ({ app, viewerApp }) => {
    const workflow = await createTestWorkflow(app)

    try {
      await viewerApp.goto(toAppUrl('/workflows'))
      await expect(viewerApp.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

      const workflowRow = viewerApp
        .getByRole('grid', { name: 'Workflows table' })
        .getByRole('row', { name: new RegExp(workflow.name) })
      await expect(workflowRow).toBeVisible({ timeout: 15_000 })
      const kebab = workflowRow.getByRole('button', { name: /Actions|Kebab toggle/i })
      await kebab.click({ force: true })

      await expect(viewerApp.getByRole('menuitem', { name: /Edit workflow/i })).toHaveAttribute('aria-disabled', 'true')
      await expect(viewerApp.getByRole('menuitem', { name: /Run published version/i })).toHaveAttribute(
        'aria-disabled',
        'true'
      )
      await expect(viewerApp.getByRole('menuitem', { name: /Duplicate workflow/i })).toHaveAttribute(
        'aria-disabled',
        'true'
      )
      await expect(viewerApp.getByRole('menuitem', { name: /^Publish workflow$/i })).toHaveAttribute(
        'aria-disabled',
        'true'
      )
      await expect(viewerApp.getByRole('menuitem', { name: /Delete workflow/i })).toHaveAttribute(
        'aria-disabled',
        'true'
      )

      // Non-gated actions remain enabled
      await expect(viewerApp.getByRole('menuitem', { name: /View run history/i })).not.toHaveAttribute(
        'aria-disabled',
        'true'
      )
      await expect(viewerApp.getByRole('menuitem', { name: /Export workflow/i })).not.toHaveAttribute(
        'aria-disabled',
        'true'
      )
    } finally {
      await deleteTestWorkflow(app, workflow.id)
    }
  })

  test('auditor: all workflow row actions are aria-disabled', async ({ app, auditorApp }) => {
    const workflow = await createTestWorkflow(app)

    try {
      await auditorApp.goto(toAppUrl('/workflows'))
      await expect(auditorApp.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

      const workflowRow = auditorApp
        .getByRole('grid', { name: 'Workflows table' })
        .getByRole('row', { name: new RegExp(workflow.name) })
      await expect(workflowRow).toBeVisible({ timeout: 15_000 })
      const kebab = workflowRow.getByRole('button', { name: /Actions|Kebab toggle/i })
      await kebab.click({ force: true })

      await expect(auditorApp.getByRole('menuitem', { name: /Edit workflow/i })).toHaveAttribute(
        'aria-disabled',
        'true'
      )
      await expect(auditorApp.getByRole('menuitem', { name: /Run published version/i })).toHaveAttribute(
        'aria-disabled',
        'true'
      )
      await expect(auditorApp.getByRole('menuitem', { name: /Duplicate workflow/i })).toHaveAttribute(
        'aria-disabled',
        'true'
      )
      await expect(auditorApp.getByRole('menuitem', { name: /^Publish workflow$/i })).toHaveAttribute(
        'aria-disabled',
        'true'
      )
      await expect(auditorApp.getByRole('menuitem', { name: /Delete workflow/i })).toHaveAttribute(
        'aria-disabled',
        'true'
      )
    } finally {
      await deleteTestWorkflow(app, workflow.id)
    }
  })

  test('viewer: workflow row action tooltip explains the denial', async ({ app, viewerApp }) => {
    const workflow = await createTestWorkflow(app)

    try {
      await viewerApp.goto(toAppUrl('/workflows'))
      await expect(viewerApp.getByRole('heading', { level: 1, name: 'Workflows' })).toBeVisible()

      const workflowRow = viewerApp
        .getByRole('grid', { name: 'Workflows table' })
        .getByRole('row', { name: new RegExp(workflow.name) })
      await expect(workflowRow).toBeVisible({ timeout: 15_000 })
      const kebab = workflowRow.getByRole('button', { name: /Actions|Kebab toggle/i })
      await kebab.click()

      const editItem = viewerApp.getByRole('menuitem', { name: /Edit workflow/i })
      await expect(editItem).toBeVisible()
      await editItem.hover()
      await expect(viewerApp.getByRole('tooltip').filter({ hasText: 'workflow:update' })).toBeVisible()
    } finally {
      await deleteTestWorkflow(app, workflow.id)
    }
  })
})

// ── Action gating — Project actions on Workflows page ────────────────────

test.describe('Permission gating — Project actions', () => {
  test('viewer: project kebab menu in all projects view is not visible', async ({ app, viewerApp }) => {
    // Create project and workflow so it appears in all projects view
    const projectName = buildUniqueName('e2e-viewer-proj')
    const workflowName = buildUniqueName('e2e-viewer-wf')

    try {
      // Create project as admin
      const createProjectResp = await apiRequest(app, 'post', '/projects', {
        data: { name: projectName },
      })
      if (!createProjectResp.ok()) throw new Error('Project creation failed')
      const project = (await createProjectResp.json()) as { id: string }

      // Create workflow in the project
      const createWorkflowResp = await apiRequest(app, 'post', '/workflows', {
        data: {
          name: workflowName,
          project_id: project.id,
          workflow_definition: {
            schema_version: '2.0.0',
            name: workflowName,
            triggers: [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
            nodes: [],
            edges: [],
          },
        },
      })
      if (!createWorkflowResp.ok()) throw new Error('Workflow creation failed')
      const workflow = (await createWorkflowResp.json()) as { id: string }

      // Navigate to All projects view as viewer
      await viewerApp.goto(toAppUrl('/workflows'))
      const projectSelector = viewerApp.getByRole('textbox', { name: 'Project' })
      await projectSelector.click()
      await viewerApp.getByRole('option', { name: 'All projects' }).click()

      // Find project row — viewer sees project ID instead of name in group headers
      const projectRow = viewerApp.getByRole('row').filter({ hasText: new RegExp(`${projectName}|${project.id}`) })
      await expect(projectRow).toBeVisible({ timeout: 15_000 })

      // Viewer has no project write permissions — kebab is completely hidden
      const projectKebab = projectRow.getByRole('button', { name: /Actions for.*project/i })
      await expect(projectKebab).not.toBeVisible()

      // Clean up
      await apiRequest(app, 'delete', `/workflows/${workflow.id}`)
      await apiRequest(app, 'delete', `/projects/${project.id}`)
    } catch (error) {
      // Best-effort cleanup on failure
      try {
        const listResp = await apiRequest(app, 'get', '/workflows')
        if (listResp.ok()) {
          const list = (await listResp.json()) as { resources: Array<{ id: string; name: string }> }
          const wf = list.resources.find((w) => w.name === workflowName)
          if (wf) await apiRequest(app, 'delete', `/workflows/${wf.id}`)
        }
        const projListResp = await apiRequest(app, 'get', '/projects')
        if (projListResp.ok()) {
          const projList = (await projListResp.json()) as { resources: Array<{ id: string; name: string }> }
          const proj = projList.resources.find((p) => p.name === projectName)
          if (proj) await apiRequest(app, 'delete', `/projects/${proj.id}`)
        }
      } catch {
        // Ignore cleanup errors
      }
      throw error
    }
  })

  test('auditor: project kebab menu in all projects view is not visible', async ({ app, auditorApp }) => {
    // Create project and workflow so it appears in all projects view
    const projectName = buildUniqueName('e2e-auditor-proj')
    const workflowName = buildUniqueName('e2e-auditor-wf')

    try {
      // Create project as admin
      const createProjectResp = await apiRequest(app, 'post', '/projects', {
        data: { name: projectName },
      })
      if (!createProjectResp.ok()) throw new Error('Project creation failed')
      const project = (await createProjectResp.json()) as { id: string }

      // Create workflow in the project
      const createWorkflowResp = await apiRequest(app, 'post', '/workflows', {
        data: {
          name: workflowName,
          project_id: project.id,
          workflow_definition: {
            schema_version: '2.0.0',
            name: workflowName,
            triggers: [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
            nodes: [],
            edges: [],
          },
        },
      })
      if (!createWorkflowResp.ok()) throw new Error('Workflow creation failed')
      const workflow = (await createWorkflowResp.json()) as { id: string }

      // Navigate to All projects view as auditor
      await auditorApp.goto(toAppUrl('/workflows'))
      const projectSelector = auditorApp.getByRole('textbox', { name: 'Project' })
      await projectSelector.click()
      await auditorApp.getByRole('option', { name: 'All projects' }).click()

      // Find project row — auditor sees project ID instead of name in group headers
      const projectRow = auditorApp.getByRole('row').filter({ hasText: new RegExp(`${projectName}|${project.id}`) })
      await expect(projectRow).toBeVisible({ timeout: 15_000 })

      // Auditor has no project write permissions — kebab is completely hidden
      const projectKebab = projectRow.getByRole('button', { name: /Actions for.*project/i })
      await expect(projectKebab).not.toBeVisible()

      // Clean up
      await apiRequest(app, 'delete', `/workflows/${workflow.id}`)
      await apiRequest(app, 'delete', `/projects/${project.id}`)
    } catch (error) {
      // Best-effort cleanup on failure
      try {
        const listResp = await apiRequest(app, 'get', '/workflows')
        if (listResp.ok()) {
          const list = (await listResp.json()) as { resources: Array<{ id: string; name: string }> }
          const wf = list.resources.find((w) => w.name === workflowName)
          if (wf) await apiRequest(app, 'delete', `/workflows/${wf.id}`)
        }
        const projListResp = await apiRequest(app, 'get', '/projects')
        if (projListResp.ok()) {
          const projList = (await projListResp.json()) as { resources: Array<{ id: string; name: string }> }
          const proj = projList.resources.find((p) => p.name === projectName)
          if (proj) await apiRequest(app, 'delete', `/projects/${proj.id}`)
        }
      } catch {
        // Ignore cleanup errors
      }
      throw error
    }
  })

  test(
    'viewer: project kebab menu in page header (selected project) is not visible',
    { tag: ['@konflux-skip'] },
    async ({ app, viewerApp }) => {
      const projectName = buildUniqueName('e2e-viewer-header-proj')
      const workflowName = buildUniqueName('e2e-viewer-header-wf')

      try {
        // Create project as admin
        const createProjectResp = await apiRequest(app, 'post', '/projects', {
          data: { name: projectName },
        })
        if (!createProjectResp.ok()) throw new Error('Project creation failed')
        const project = (await createProjectResp.json()) as { id: string }

        // Create workflow in the project
        const createWorkflowResp = await apiRequest(app, 'post', '/workflows', {
          data: {
            name: workflowName,
            project_id: project.id,
            workflow_definition: {
              schema_version: '2.0.0',
              name: workflowName,
              triggers: [{ id: 'trigger_1', type: 'manual_trigger', name: 'Manual trigger', parameters: {} }],
              nodes: [],
              edges: [],
            },
          },
        })
        if (!createWorkflowResp.ok()) throw new Error('Workflow creation failed')
        const workflow = (await createWorkflowResp.json()) as { id: string }

        // Viewer cannot select individual projects — dropdown only shows "All projects"
        await viewerApp.goto(toAppUrl('/workflows'))
        const projectSelector = viewerApp.getByRole('textbox', { name: 'Project' })
        await projectSelector.click()
        await expect(viewerApp.getByRole('option', { name: 'All projects' })).toBeVisible()
        await expect(viewerApp.getByRole('option', { name: projectName })).not.toBeVisible()
        await expect(viewerApp.getByRole('option', { name: project.id })).not.toBeVisible()
        await viewerApp.keyboard.press('Escape')

        // Clean up
        await apiRequest(app, 'delete', `/workflows/${workflow.id}`)
        await apiRequest(app, 'delete', `/projects/${project.id}`)
      } catch (error) {
        // Best-effort cleanup on failure
        try {
          const listResp = await apiRequest(app, 'get', '/workflows')
          if (listResp.ok()) {
            const list = (await listResp.json()) as { resources: Array<{ id: string; name: string }> }
            const wf = list.resources.find((w) => w.name === workflowName)
            if (wf) await apiRequest(app, 'delete', `/workflows/${wf.id}`)
          }
          const projListResp = await apiRequest(app, 'get', '/projects')
          if (projListResp.ok()) {
            const projList = (await projListResp.json()) as { resources: Array<{ id: string; name: string }> }
            const proj = projList.resources.find((p) => p.name === projectName)
            if (proj) await apiRequest(app, 'delete', `/projects/${proj.id}`)
          }
        } catch {
          // Ignore cleanup errors
        }
        throw error
      }
    }
  )
})

// ── Action gating — Credentials ──────────────────────────────────────────

test.describe('Permission gating — Credential actions', () => {
  test(
    'viewer: Create credential button is disabled with tooltip',
    { tag: ['@konflux-skip'] },
    async ({ app, viewerApp }) => {
      const { id: credId, name: credName } = await createTestCredential(app)

      try {
        await viewerApp.goto(toAppUrl('/configuration/credentials'))
        await expect(viewerApp.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()

        // Wait for credential data to load — the toolbar button only renders once credentials.length > 0
        await expect(
          viewerApp.getByRole('grid', { name: 'Credentials table' }).getByRole('row', { name: new RegExp(credName) })
        ).toBeVisible({ timeout: 15_000 })

        const createButton = viewerApp.getByRole('button', { name: /Create credential/i })
        await expect(createButton).toBeVisible()
        await expect(createButton).toHaveAttribute('aria-disabled', 'true')

        await createButton.hover()
        await expect(viewerApp.getByRole('tooltip').filter({ hasText: 'credential:create' })).toBeVisible()
      } finally {
        await deleteCredentialViaApi(app, credId)
      }
    }
  )

  test('auditor: Create credential button is disabled', { tag: ['@konflux-skip'] }, async ({ app, auditorApp }) => {
    const { id: credId } = await createTestCredential(app)

    try {
      await auditorApp.goto(toAppUrl('/configuration/credentials'))
      await expect(auditorApp.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()

      const createButton = auditorApp.getByRole('button', { name: /Create credential/i })
      await expect(createButton).toBeVisible()
      await expect(createButton).toHaveAttribute('aria-disabled', 'true')
    } finally {
      await deleteCredentialViaApi(app, credId)
    }
  })

  test('viewer: credential row actions are aria-disabled', async ({ app, viewerApp }) => {
    const credential = await createTestCredential(app)

    try {
      await viewerApp.goto(toAppUrl('/configuration/credentials'))
      await expect(viewerApp.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()

      const credRow = viewerApp
        .getByRole('grid', { name: 'Credentials table' })
        .getByRole('row', { name: new RegExp(credential.name) })
      await expect(credRow).toBeVisible({ timeout: 15_000 })
      const kebab = credRow.getByRole('button', { name: /Actions|Kebab toggle/i })
      await kebab.click({ force: true })

      await expect(viewerApp.getByRole('menuitem', { name: /Edit credential/i })).toHaveAttribute(
        'aria-disabled',
        'true'
      )
      await expect(viewerApp.getByRole('menuitem', { name: /Delete credential/i })).toHaveAttribute(
        'aria-disabled',
        'true'
      )
    } finally {
      await deleteCredentialViaApi(app, credential.id)
    }
  })

  // Dual-browser auditor session + kebab aria-disabled is flaky under Konflux load.
  // Still runs in GitHub compose E2E. Currents quarantines are not applied in Konflux.
  test('auditor: credential row actions are aria-disabled', { tag: ['@konflux-skip'] }, async ({ app, auditorApp }) => {
    const credential = await createTestCredential(app)

    try {
      await auditorApp.goto(toAppUrl('/configuration/credentials'))
      await expect(auditorApp.getByRole('heading', { level: 1, name: 'Credentials' })).toBeVisible()

      const credRow = auditorApp
        .getByRole('grid', { name: 'Credentials table' })
        .getByRole('row', { name: new RegExp(credential.name) })
      await expect(credRow).toBeVisible({ timeout: 15_000 })
      const kebab = credRow.getByRole('button', { name: /Actions|Kebab toggle/i })
      await kebab.click({ force: true })

      await expect(auditorApp.getByRole('menuitem', { name: /Edit credential/i })).toHaveAttribute(
        'aria-disabled',
        'true'
      )
      await expect(auditorApp.getByRole('menuitem', { name: /Delete credential/i })).toHaveAttribute(
        'aria-disabled',
        'true'
      )
    } finally {
      await deleteCredentialViaApi(app, credential.id)
    }
  })
})

// ── Action gating — Access Management ────────────────────────────────────

test.describe('Permission gating — Access Management actions', () => {
  test('auditor: Create group button is disabled', async ({ auditorApp }) => {
    await auditorApp.goto(toAppUrl(`${AM_URL}/groups`))
    await expect(auditorApp.getByRole('tab', { name: /Groups/i })).toBeVisible()

    const createButton = auditorApp.getByRole('button', { name: /Create group/i })
    await expect(createButton).toBeVisible()
    await expect(createButton).toHaveAttribute('aria-disabled', 'true')
  })

  test('auditor: Create user button is disabled', async ({ auditorApp }) => {
    await auditorApp.goto(toAppUrl(`${AM_URL}/users`))
    await expect(auditorApp.getByRole('tab', { name: /Users/i })).toBeVisible()

    const createButton = auditorApp.getByRole('button', { name: /Create user/i })
    await expect(createButton).toBeVisible()
    await expect(createButton).toHaveAttribute('aria-disabled', 'true')
  })

  test('user: Create group button is disabled', async ({ userApp }) => {
    await userApp.goto(toAppUrl(`${AM_URL}/groups`))
    await expect(userApp.getByRole('tab', { name: /Groups/i })).toBeVisible()

    const createButton = userApp.getByRole('button', { name: /Create group/i })
    await expect(createButton).toBeVisible()
    // aria-disabled is set after the permissions API resolves — give it extra time
    await expect(createButton).toHaveAttribute('aria-disabled', 'true', { timeout: 20_000 })
  })

  test('user: Create user button is disabled with tooltip', async ({ userApp }) => {
    await userApp.goto(toAppUrl(`${AM_URL}/users`))
    await expect(userApp.getByRole('tab', { name: /Users/i })).toBeVisible()

    const createButton = userApp.getByRole('button', { name: /Create user/i })
    await expect(createButton).toBeVisible()
    // aria-disabled is set after the permissions API resolves — give it extra time
    await expect(createButton).toHaveAttribute('aria-disabled', 'true', { timeout: 20_000 })

    await createButton.hover()
    await expect(userApp.getByRole('tooltip').filter({ hasText: 'user:create' })).toBeVisible()
  })
})

// ── Action gating — Detail page header actions ───────────────────────────

test.describe('Permission gating — Detail page header actions', () => {
  const E2E_USER_PASSWORD = 'E2eTestP@ssw0rd!'

  test('auditor: user detail Edit and kebab actions are aria-disabled', async ({ app, auditorApp }) => {
    const username = buildUniqueName('e2e-perm-user-detail')
    const user = await createUserViaApi(app, { username, password: E2E_USER_PASSWORD })
    if (!user) throw new Error('createUserViaApi failed')

    try {
      await auditorApp.goto(toAppUrl(`${AM_URL}/users/${user.id}`))
      await expect(auditorApp.getByRole('heading', { level: 1, name: username })).toBeVisible()

      // aria-disabled is set after the permissions API resolves — give it extra time
      await expect(auditorApp.getByRole('button', { name: 'Edit user' })).toHaveAttribute('aria-disabled', 'true', {
        timeout: 20_000,
      })

      await auditorApp.getByRole('button', { name: 'User actions' }).click()
      await expect(auditorApp.getByRole('menuitem', { name: 'Revoke tokens' })).toHaveAttribute(
        'aria-disabled',
        'true',
        { timeout: 15_000 }
      )
      await expect(auditorApp.getByRole('menuitem', { name: 'Delete user' })).toHaveAttribute('aria-disabled', 'true', {
        timeout: 15_000,
      })
    } finally {
      await deleteUserViaApi(app, user.id)
    }
  })

  test('auditor: group detail Edit and kebab actions are aria-disabled', async ({ app, auditorApp }) => {
    const groupId = await createGroupViaApi(app, { name: buildUniqueName('e2e-perm-group-detail') })
    if (!groupId) throw new Error('createGroupViaApi failed')

    try {
      await auditorApp.goto(toAppUrl(`${AM_URL}/groups/${groupId}`))
      await expect(auditorApp.getByRole('heading', { level: 1 })).toBeVisible()

      await expect(auditorApp.getByRole('button', { name: 'Edit group' })).toHaveAttribute('aria-disabled', 'true')

      await auditorApp.getByRole('button', { name: 'Group actions' }).click()
      await expect(auditorApp.getByRole('menuitem', { name: 'Delete group' })).toHaveAttribute('aria-disabled', 'true')
    } finally {
      await deleteGroupViaApi(app, groupId)
    }
  })

  test('auditor: project detail Edit and kebab actions are aria-disabled', async ({ app, auditorApp }) => {
    const project = await ensureProject(app, buildUniqueName('e2e-perm-project-detail'))
    if (!project) throw new Error('ensureProject failed')

    try {
      await auditorApp.goto(toAppUrl(`${AM_URL}/projects/${project.id}`))
      await expect(auditorApp.getByRole('heading', { level: 1, name: project.name })).toBeVisible()

      await expect(auditorApp.getByRole('button', { name: 'Edit project' })).toHaveAttribute('aria-disabled', 'true')

      await auditorApp.getByRole('button', { name: 'Project actions' }).click()
      await expect(auditorApp.getByRole('menuitem', { name: 'Delete project' })).toHaveAttribute(
        'aria-disabled',
        'true'
      )
    } finally {
      const token = await getAuthToken(app)
      if (token) await apiRequest(app, 'delete', `/projects/${project.id}`, { token })
    }
  })

  test('auditor: identity provider detail Edit and kebab actions are aria-disabled', async ({ app, auditorApp }) => {
    const idpName = buildUniqueName('e2e-perm-idp-detail')
    const idp = await createIdentityProviderViaApi(app, {
      name: idpName,
      enabled: false,
      configuration: {
        provider_type: 'oidc',
        client_id: 'e2e-test',
        client_secret: 'e2e-secret',
        issuer_url: 'https://idp.example.com',
        redirect_uri: `${appBaseUrl}/auth/callback`,
      },
    })
    if (!idp) throw new Error('createIdentityProviderViaApi failed')

    try {
      await auditorApp.goto(toAppUrl(`${AUTH_URL}/identity-providers/${idp.id}`))
      await expect(auditorApp.getByRole('heading', { level: 1, name: idpName })).toBeVisible()

      await expect(auditorApp.getByRole('button', { name: 'Edit provider' })).toHaveAttribute('aria-disabled', 'true')

      await auditorApp.getByRole('button', { name: 'Identity provider actions' }).click()
      await expect(auditorApp.getByRole('menuitem', { name: 'Edit group mapping' })).toHaveAttribute(
        'aria-disabled',
        'true'
      )
      await expect(auditorApp.getByRole('menuitem', { name: 'Revoke tokens' })).toHaveAttribute('aria-disabled', 'true')
      await expect(auditorApp.getByRole('menuitem', { name: 'Delete identity provider' })).toHaveAttribute(
        'aria-disabled',
        'true'
      )
    } finally {
      await deleteIdentityProviderViaApi(app, idp.id)
    }
  })
})

// ── Action gating — Service Accounts ───────────────────────────────────

test.describe('Permission gating — Service Account actions', () => {
  test('auditor: Create service account button is disabled', async ({ app, auditorApp }) => {
    const sa = await createServiceAccountViaApi(app, buildUniqueName('e2e-perm-sa'))

    try {
      await auditorApp.goto(toAppUrl(`${AM_URL}/service-accounts`))
      await expect(auditorApp.getByRole('tab', { name: /Service Accounts/i })).toBeVisible()

      const createButton = auditorApp.getByRole('button', { name: /Create service account/i })
      await expect(createButton).toBeVisible({ timeout: 15_000 })
      await expect(createButton).toHaveAttribute('aria-disabled', 'true')
    } finally {
      await deleteServiceAccountViaApi(app, sa.id)
    }
  })

  test('user: Service Accounts tab is not visible', async ({ userApp }) => {
    await userApp.goto(toAppUrl(`${AM_URL}/users`))
    await expect(userApp.getByRole('tab', { name: /Users/i })).toBeVisible()

    await expect(userApp.getByRole('tab', { name: /Service Accounts/i })).not.toBeVisible()
  })

  test('viewer: direct URL to Service Accounts shows access denied', async ({ viewerApp }) => {
    await viewerApp.goto(toAppUrl(`${AM_URL}/service-accounts`))

    await expect(viewerApp.getByRole('heading', { name: 'Access denied', level: 2 })).toBeVisible()
  })
})

// ── Action gating — Identity Providers ───────────────────────────────────

test.describe('Permission gating — Identity Provider actions', () => {
  test('auditor: Add OIDC provider button is disabled with tooltip', async ({ auditorApp }) => {
    await auditorApp.goto(toAppUrl(`${AUTH_URL}`))
    await expect(auditorApp.getByRole('heading', { name: 'Identity Providers', level: 1 })).toBeVisible()

    const addButton = auditorApp.getByRole('button', { name: /Add OIDC provider/i })
    await expect(addButton).toBeVisible()
    await expect(addButton).toHaveAttribute('aria-disabled', 'true')

    await addButton.hover()
    await expect(auditorApp.getByRole('tooltip').filter({ hasText: 'identity-provider:create' })).toBeVisible()
  })

  test('auditor: IdP row actions are aria-disabled', { tag: ['@konflux-skip'] }, async ({ app, auditorApp }) => {
    const idpName = buildUniqueName('e2e-perm-idp')
    const idp = await createIdentityProviderViaApi(app, {
      name: idpName,
      enabled: false,
      configuration: {
        provider_type: 'oidc',
        client_id: 'e2e-test',
        client_secret: 'e2e-secret',
        issuer_url: 'https://idp.example.com',
        redirect_uri: `${appBaseUrl}/auth/callback`,
      },
    })
    if (!idp) throw new Error('createIdentityProviderViaApi failed')

    try {
      await auditorApp.goto(toAppUrl(`${AUTH_URL}`))
      await expect(auditorApp.getByRole('heading', { name: 'Identity Providers', level: 1 })).toBeVisible()

      const idpRow = auditorApp
        .getByRole('grid', { name: 'Identity providers table' })
        .getByRole('row', { name: new RegExp(idpName) })
      await expect(idpRow).toBeVisible({ timeout: 15_000 })
      const kebab = idpRow.getByRole('button', { name: /Actions|Kebab toggle/i })
      await kebab.click({ force: true })

      await expect(auditorApp.getByRole('menuitem', { name: /Edit provider/i })).toHaveAttribute(
        'aria-disabled',
        'true'
      )
      await expect(auditorApp.getByRole('menuitem', { name: /Delete/i })).toHaveAttribute('aria-disabled', 'true')
      await expect(auditorApp.getByRole('menuitem', { name: /Revoke tokens/i })).toHaveAttribute(
        'aria-disabled',
        'true'
      )
    } finally {
      await deleteIdentityProviderViaApi(app, idp.id)
    }
  })
})

// ── Action gating — Builder ──────────────────────────────────────────────

test.describe('Permission gating — Builder read-only', () => {
  test('viewer: builder shows read-only info alert', async ({ app, viewerApp }) => {
    const { id: workflowId } = await createTestWorkflow(app)

    try {
      await viewerApp.goto(toAppUrl(`/workflow-builder/${workflowId}`))
      await viewerApp.getByRole('navigation', { name: 'Main navigation' }).waitFor()

      await expect(viewerApp.getByRole('heading', { name: /read-only mode/i, level: 4 })).toBeVisible({
        timeout: 15_000,
      })
    } finally {
      await deleteTestWorkflow(app, workflowId)
    }
  })

  test('auditor: builder shows read-only info alert', async ({ app, auditorApp }) => {
    const { id: workflowId } = await createTestWorkflow(app)

    try {
      await auditorApp.goto(toAppUrl(`/workflow-builder/${workflowId}`))
      await auditorApp.getByRole('navigation', { name: 'Main navigation' }).waitFor()

      await expect(auditorApp.getByRole('heading', { name: /read-only mode/i, level: 4 })).toBeVisible({
        timeout: 15_000,
      })
    } finally {
      await deleteTestWorkflow(app, workflowId)
    }
  })
})
