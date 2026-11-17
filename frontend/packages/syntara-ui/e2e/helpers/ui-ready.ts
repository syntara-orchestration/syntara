import { expect, type Page } from '../fixtures'

/**
 * Wait for UI to be ready by ensuring no toast notifications or loading overlays are blocking interactions
 */
export async function waitForUIReady(page: Page) {
  // Wait for ALL PF6 toast alerts to disappear, not just the first.
  // Scoped to the toast AlertGroup container (AlertGroup has no OUIA attribute);
  // inline page alerts (ValidationBanner, BuilderReadOnlyBanner, etc.) are excluded.
  await expect(page.locator('.pf-v6-c-alert-group [data-ouia-component-type="PF6/Alert"]'))
    .toHaveCount(0, { timeout: 5000 })
    .catch(() => {})

  // Wait for ALL loading indicators to clear, not just the first.
  await expect(page.getByLabel('Loading'))
    .toHaveCount(0, { timeout: 10000 })
    .catch(() => {})
}
