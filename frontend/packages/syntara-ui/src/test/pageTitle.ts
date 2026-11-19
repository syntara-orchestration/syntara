import { expect } from 'vitest'

import { toPageTitle } from '../utils/toPageTitle'

// React 19 hoists <title> to document.head in happy-dom, so document.title works in unit tests.
export function expectPageTitle(expectedTitle: string | (string | null | undefined)[]) {
  if (Array.isArray(expectedTitle)) {
    expect(document.title).toBe(toPageTitle(expectedTitle))
    return
  }
  expect(document.title).toBe(expectedTitle)
}
