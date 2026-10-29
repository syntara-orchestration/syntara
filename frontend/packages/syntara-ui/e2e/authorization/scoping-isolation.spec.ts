/**
 * E2E Tests: Scoping & Isolation (AAP-76532)
 *
 * Tests verifying that permission scope controls
 * Create button visibility for different personas.
 *
 * TC-1.6: Persona with global read + create sees Create button.
 *         Read-only persona can still access the workflows page.
 * TC-1.7: Writer persona sees Create button.
 *         Reader persona can still access the workflows page.
 */
import { test } from '../fixtures'
import { buildUniqueName } from '../helpers/workflows'

import { expect, createPersona, cleanupPersona, loginAsUser, PERSONA_ACTIONS, toAppUrl } from './fixtures'

test.describe('AAP-76532: Scoping & Isolation', () => {
  test('TC-1.6: persona with read + create sees Create button; read-only persona sees workflows page', async ({
    app,
    browser,
  }) => {
    const creator = await createPersona(app, buildUniqueName('creator'), [
      'workflow:read',
      'workflow:create',
      'project:read',
    ])
    const reader = await createPersona(app, buildUniqueName('reader'), PERSONA_ACTIONS.projectReader)

    const creatorCtx = await browser.newContext()
    const creatorPage = await creatorCtx.newPage()

    try {
      await loginAsUser(creatorPage, creator)
      await creatorPage.goto(toAppUrl('/workflows'))
      await expect(creatorPage.getByRole('heading', { level: 1, name: /Workflows/i })).toBeVisible({ timeout: 15_000 })
      await expect(creatorPage.getByRole('link', { name: /Create workflow/i })).toBeVisible()
    } finally {
      await creatorCtx.close()
    }

    const readerCtx = await browser.newContext()
    const readerPage = await readerCtx.newPage()

    try {
      await loginAsUser(readerPage, reader)
      await readerPage.goto(toAppUrl('/workflows'))
      await expect(readerPage.getByRole('heading', { level: 1, name: /Workflows/i })).toBeVisible({ timeout: 15_000 })
    } finally {
      await readerCtx.close()
      await cleanupPersona(app, reader)
      await cleanupPersona(app, creator)
    }
  })

  test('TC-1.7: writer persona sees Create button; reader persona sees workflows page', async ({ app, browser }) => {
    const writer = await createPersona(app, buildUniqueName('writer'), PERSONA_ACTIONS.projectWriter)
    const reader = await createPersona(app, buildUniqueName('reader'), PERSONA_ACTIONS.projectReader)

    const writerCtx = await browser.newContext()
    const writerPage = await writerCtx.newPage()

    try {
      await loginAsUser(writerPage, writer)
      await writerPage.goto(toAppUrl('/workflows'))
      await expect(writerPage.getByRole('heading', { level: 1, name: /Workflows/i })).toBeVisible({ timeout: 15_000 })
      await expect(writerPage.getByRole('link', { name: /Create workflow/i })).toBeVisible()
    } finally {
      await writerCtx.close()
    }

    const readerCtx = await browser.newContext()
    const readerPage = await readerCtx.newPage()

    try {
      await loginAsUser(readerPage, reader)
      await readerPage.goto(toAppUrl('/workflows'))
      await expect(readerPage.getByRole('heading', { level: 1, name: /Workflows/i })).toBeVisible({ timeout: 15_000 })
    } finally {
      await readerCtx.close()
      await cleanupPersona(app, reader)
      await cleanupPersona(app, writer)
    }
  })
})
