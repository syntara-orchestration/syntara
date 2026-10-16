/**
 * E2E Tests: Persona-based UI visibility (AAP-76536: TC-1.12 through TC-1.18)
 *
 * Each persona role can access the UI sections its policies grant.
 */
import { test } from '../fixtures'
import { buildUniqueName } from '../helpers/workflows'

import { expect, createPersona, cleanupPersona, loginAsUser, PERSONA_ACTIONS, toAppUrl } from './fixtures'

test.describe('Persona visibility', () => {
  test('TC-1.3: Reader persona can navigate to workflows and see the list', async ({ app, browser }) => {
    const persona = await createPersona(app, buildUniqueName('reader'), PERSONA_ACTIONS.projectReader)
    const ctx = await browser.newContext()
    const page = await ctx.newPage()

    try {
      await loginAsUser(page, persona)
      await page.goto(toAppUrl('/workflows'))
      await expect(page.getByRole('heading', { level: 1, name: /Workflows/i })).toBeVisible({ timeout: 10_000 })
    } finally {
      await ctx.close()
      await cleanupPersona(app, persona)
    }
  })

  test('TC-1.12: Credentials manager sees credentials page', async ({ app, browser }) => {
    const persona = await createPersona(app, buildUniqueName('cred-mgr'), PERSONA_ACTIONS.credentialsManager)
    const ctx = await browser.newContext()
    const page = await ctx.newPage()

    try {
      await loginAsUser(page, persona)
      await page.goto(toAppUrl('/configuration/credentials'))
      await expect(page.getByRole('heading', { level: 1, name: /Credentials/i })).toBeVisible({ timeout: 10_000 })
    } finally {
      await ctx.close()
      await cleanupPersona(app, persona)
    }
  })

  test('TC-1.13: Workflow manager sees workflows page', async ({ app, browser }) => {
    const persona = await createPersona(app, buildUniqueName('wf-mgr'), PERSONA_ACTIONS.workflowManager)
    const ctx = await browser.newContext()
    const page = await ctx.newPage()

    try {
      await loginAsUser(page, persona)
      await page.goto(toAppUrl('/workflows'))
      await expect(page.getByRole('heading', { level: 1, name: /Workflows/i })).toBeVisible({ timeout: 10_000 })
    } finally {
      await ctx.close()
      await cleanupPersona(app, persona)
    }
  })

  test('TC-1.14: Execution operator sees workflows page', async ({ app, browser }) => {
    const persona = await createPersona(app, buildUniqueName('exec-op'), PERSONA_ACTIONS.executionOperator)
    const ctx = await browser.newContext()
    const page = await ctx.newPage()

    try {
      await loginAsUser(page, persona)
      await page.goto(toAppUrl('/workflows'))
      await expect(page.getByRole('heading', { level: 1, name: /Workflows/i })).toBeVisible({ timeout: 10_000 })
    } finally {
      await ctx.close()
      await cleanupPersona(app, persona)
    }
  })

  test('TC-1.15: Approval operator sees approvals in navigation', async ({ app, browser }) => {
    const persona = await createPersona(app, buildUniqueName('approval-op'), PERSONA_ACTIONS.approvalOperator)
    const ctx = await browser.newContext()
    const page = await ctx.newPage()

    try {
      await loginAsUser(page, persona)
      const nav = page.getByRole('navigation', { name: 'Main navigation' })
      await expect(nav.getByRole('link', { name: 'Tasks' })).toBeVisible({ timeout: 10_000 })
    } finally {
      await ctx.close()
      await cleanupPersona(app, persona)
    }
  })

  test('TC-1.16: Project manager sees main navigation', async ({ app, browser }) => {
    const persona = await createPersona(app, buildUniqueName('proj-mgr'), PERSONA_ACTIONS.projectManager)
    const ctx = await browser.newContext()
    const page = await ctx.newPage()

    try {
      await loginAsUser(page, persona)
      await page.goto(toAppUrl('/'))
      const nav = page.getByRole('navigation', { name: 'Main navigation' })
      await expect(nav).toBeVisible({ timeout: 10_000 })
    } finally {
      await ctx.close()
      await cleanupPersona(app, persona)
    }
  })

  test('TC-1.17: Role-assignment manager sees Access Management', async ({ app, browser }) => {
    const persona = await createPersona(app, buildUniqueName('role-assign-mgr'), PERSONA_ACTIONS.roleAssignmentManager)
    const ctx = await browser.newContext()
    const page = await ctx.newPage()

    try {
      await loginAsUser(page, persona)
      await page.goto(toAppUrl('/system-administration/access-management'))
      await expect(page.getByRole('heading', { level: 1, name: 'Access Management' })).toBeVisible({ timeout: 10_000 })
    } finally {
      await ctx.close()
      await cleanupPersona(app, persona)
    }
  })

  test('TC-1.18: User manager sees Access Management', async ({ app, browser }) => {
    const persona = await createPersona(app, buildUniqueName('user-mgr'), PERSONA_ACTIONS.userManager)
    const ctx = await browser.newContext()
    const page = await ctx.newPage()

    try {
      await loginAsUser(page, persona)
      await page.goto(toAppUrl('/system-administration/access-management'))
      await expect(page.getByRole('heading', { level: 1, name: 'Access Management' })).toBeVisible({ timeout: 10_000 })
    } finally {
      await ctx.close()
      await cleanupPersona(app, persona)
    }
  })
})
