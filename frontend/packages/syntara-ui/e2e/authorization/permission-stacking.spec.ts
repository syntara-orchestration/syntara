/**
 * E2E Tests: Permission Stacking (AAP-76530)
 *
 * Tests verifying that stacked permissions correctly control
 * page accessibility across personas.
 *
 * TC-1.4: Reader persona sees workflows page.
 *         Writer persona also sees the Create workflow button.
 *         NOTE: the Create button is not yet gated behind can_i
 *         in the UI, so the reader negative assertion cannot be
 *         added until that gating is implemented.
 * TC-1.8: Persona with workflow:read + credential:read + workflow:create
 *         sees both Workflows and Credentials pages.
 * TC-1.9: Persona with workflow + credential read sees both pages.
 */
import { test } from '../fixtures'
import { buildUniqueName } from '../helpers/workflows'

import { expect, createPersona, cleanupPersona, loginAsUser, PERSONA_ACTIONS, toAppUrl } from './fixtures'

test.describe('AAP-76530: Permission Stacking', () => {
  test('TC-1.4: reader sees workflows page; writer also sees Create button', async ({ app, browser }) => {
    const reader = await createPersona(app, buildUniqueName('reader'), PERSONA_ACTIONS.projectReader)
    const writer = await createPersona(app, buildUniqueName('writer'), PERSONA_ACTIONS.projectWriter)

    const readerCtx = await browser.newContext()
    const readerPage = await readerCtx.newPage()

    try {
      await loginAsUser(readerPage, reader)
      await readerPage.goto(toAppUrl('/workflows'))
      await expect(readerPage.getByRole('heading', { level: 1, name: /Workflows/i })).toBeVisible({ timeout: 15_000 })
      // NOTE: Create button is not yet gated behind can_i — reader sees it too
    } finally {
      await readerCtx.close()
    }

    const writerCtx = await browser.newContext()
    const writerPage = await writerCtx.newPage()

    try {
      await loginAsUser(writerPage, writer)
      await writerPage.goto(toAppUrl('/workflows'))
      await expect(writerPage.getByRole('heading', { level: 1, name: /Workflows/i })).toBeVisible({ timeout: 15_000 })
      await expect(writerPage.getByRole('link', { name: /Create workflow/i })).toBeVisible()
    } finally {
      await writerCtx.close()
      await cleanupPersona(app, writer)
      await cleanupPersona(app, reader)
    }
  })

  test('TC-1.8: persona with workflow:read + credential:read + workflow:create sees both pages', async ({
    app,
    browser,
  }) => {
    const persona = await createPersona(app, buildUniqueName('mixed'), [
      'workflow:read',
      'workflow:create',
      'credential:read',
      'project:read',
    ])
    const ctx = await browser.newContext()
    const page = await ctx.newPage()

    try {
      await loginAsUser(page, persona)
      await page.goto(toAppUrl('/workflows'))
      await expect(page.getByRole('heading', { level: 1, name: /Workflows/i })).toBeVisible({ timeout: 15_000 })
      await page.goto(toAppUrl('/configuration/credentials'))
      await expect(page.getByRole('heading', { level: 1, name: /Credentials/i })).toBeVisible({ timeout: 15_000 })
    } finally {
      await ctx.close()
      await cleanupPersona(app, persona)
    }
  })

  test('TC-1.9: persona with workflow + credential read sees both pages', async ({ app, browser }) => {
    const persona = await createPersona(app, buildUniqueName('dual-reader'), [
      'workflow:read',
      'credential:read',
      'project:read',
    ])
    const ctx = await browser.newContext()
    const page = await ctx.newPage()

    try {
      await loginAsUser(page, persona)
      await page.goto(toAppUrl('/workflows'))
      await expect(page.getByRole('heading', { level: 1, name: /Workflows/i })).toBeVisible({ timeout: 15_000 })
      await page.goto(toAppUrl('/configuration/credentials'))
      await expect(page.getByRole('heading', { level: 1, name: /Credentials/i })).toBeVisible({ timeout: 15_000 })
    } finally {
      await ctx.close()
      await cleanupPersona(app, persona)
    }
  })
})
