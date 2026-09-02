import { expect } from 'vitest'

import { toPageTitle } from '../utils/toPageTitle'

// React 19 hoists <title> to document.head in happy-dom, so document.title works in unit tests.
export function expectPageTitle(segments: (string | null | undefined)[]) {
  expect(document.title).toBe(toPageTitle(segments))
}
