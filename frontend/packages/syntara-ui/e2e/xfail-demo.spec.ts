import { test, expect } from './fixtures'

test.describe('Xfail demo', () => {
  test('should always fail', async ({ app }) => {
    await app.goto('about:blank')
    expect(true).toBe(false)
  })
})
