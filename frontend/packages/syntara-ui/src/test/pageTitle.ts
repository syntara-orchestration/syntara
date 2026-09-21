import { expect } from 'vitest'

// React 19 hoists <title> to document.head in happy-dom, so document.title works in unit tests.
export function expectPageTitle(expectedTitle: string) {
  expect(document.title).toBe(expectedTitle)
}
