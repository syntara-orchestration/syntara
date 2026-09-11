/**
 * Regression tests for the `clickSaveAndWait` helper itself.
 *
 * Every builder spec used to gate a save on `toHaveURL(/workflow-builder\/.+/)`.
 * `.+` matches the literal `new` segment, so that assertion passed the instant
 * the click was dispatched and before any request went out; the test then
 * navigated away and aborted the write. On a rename there is no navigation at
 * all, so no URL guard is even possible. The helper replaces both with a wait on
 * the create/update response, and these tests pin that against a synthetic page
 * rather than waiting for the race to resurface in the merge queue.
 */
import { test, expect, toAppUrl, type Page } from './fixtures'
import { clickSaveAndWait, isWorkflowSaveResponse } from './helpers/workflow-save'

const CREATE_FIXTURE = '/e2e-fixtures/workflow-save-create'
const UPDATE_FIXTURE = '/e2e-fixtures/workflow-save-update'
const DISABLED_FIXTURE = '/e2e-fixtures/workflow-save-disabled'
const FAILING_FIXTURE = '/e2e-fixtures/workflow-save-failing'

const WORKFLOW_UUID = '11111111-2222-3333-4444-555555555555'

/**
 * The create path, with the URL deliberately racing the request.
 *
 * The button pushes `/workflow-builder/<id>` synchronously and only POSTs 800ms
 * later, which is the ordering that made the old URL guard a false pass. A
 * `POST /workflows/validate` goes out first so the helper has a near-miss to
 * reject — the Verify action fires exactly that request against a path a naive
 * `**\/api/v1/workflows*` glob would match.
 */
const CREATE_HTML = `<!doctype html>
<html lang="en">
  <body>
    <button type="button" onclick="save()">Save</button>
    <script>
      function save() {
        void fetch('/api/v1/workflows/validate', { method: 'POST' })
        history.pushState({}, '', '/workflow-builder/${WORKFLOW_UUID}')
        setTimeout(() => {
          void fetch('/api/v1/workflows', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: 'created' }),
          })
        }, 800)
      }
    </script>
  </body>
</html>`

/** The rename path: a PATCH after a delay, and no navigation ever. */
const UPDATE_HTML = `<!doctype html>
<html lang="en">
  <body>
    <button type="button" onclick="save()">Save</button>
    <script>
      function save() {
        setTimeout(() => {
          void fetch('/api/v1/workflows/${WORKFLOW_UUID}', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: 'renamed' }),
          })
        }, 800)
      }
    </script>
  </body>
</html>`

/**
 * A Save button that stays `aria-disabled` forever and fires nothing.
 *
 * PatternFly renders the real button this way whenever the workflow is clean or
 * the node editor is open, and Playwright honours `aria-disabled` in its
 * actionability wait — so an unbounded click here would consume the whole test.
 */
const DISABLED_HTML = `<!doctype html>
<html lang="en">
  <body>
    <button type="button" aria-disabled="true">Save</button>
  </body>
</html>`

/** A save the server rejects, which must not read as "persisted". */
const FAILING_HTML = `<!doctype html>
<html lang="en">
  <body>
    <button type="button" onclick="void fetch('/api/v1/workflows', { method: 'POST' })">Save</button>
  </body>
</html>`

/** Serve one synthetic page and record every request the helper cares about. */
async function serveFixture(
  page: Page,
  path: string,
  html: string,
  { saveStatus = 201 }: { saveStatus?: number } = {}
): Promise<string[]> {
  const seen: string[] = []
  await page.route(`**${path}`, (route) => route.fulfill({ status: 200, contentType: 'text/html', body: html }))
  await page.route('**/api/v1/workflows**', (route) => {
    const request = route.request()
    const { pathname } = new URL(request.url())
    seen.push(`${request.method()} ${pathname}`)
    const isValidate = pathname.endsWith('/validate')
    return route.fulfill({
      status: isValidate ? 200 : saveStatus,
      contentType: 'application/json',
      body: JSON.stringify(isValidate ? { valid: true, errors: [] } : { id: WORKFLOW_UUID }),
    })
  })
  return seen
}

test.describe('clickSaveAndWait helper', () => {
  // No login needed: the helper is driven against synthetic pages, not the app.
  test('waits for the create POST rather than the URL change', async ({ page }) => {
    const seen = await serveFixture(page, CREATE_FIXTURE, CREATE_HTML)

    await page.goto(toAppUrl(CREATE_FIXTURE))
    await clickSaveAndWait(page)

    // The old `toHaveURL(/workflow-builder\/.+/)` gate would have resolved here
    // with only the validate call on the wire.
    expect(seen, 'the create POST must have landed before the helper returned').toContain('POST /api/v1/workflows')
  })

  test('waits for the update PATCH when the URL never changes', async ({ page }) => {
    const seen = await serveFixture(page, UPDATE_FIXTURE, UPDATE_HTML)

    await page.goto(toAppUrl(UPDATE_FIXTURE))
    const urlBefore = page.url()
    await clickSaveAndWait(page)

    expect(page.url(), 'a rename does not navigate — this is why no URL guard can work').toBe(urlBefore)
    expect(seen).toContain(`PATCH /api/v1/workflows/${WORKFLOW_UUID}`)
  })

  test('gives up instead of hanging when Save stays aria-disabled', async ({ page }) => {
    test.setTimeout(60_000)
    await serveFixture(page, DISABLED_FIXTURE, DISABLED_HTML)
    await page.goto(toAppUrl(DISABLED_FIXTURE))

    const settled = await Promise.race([
      clickSaveAndWait(page).then(
        () => 'resolved' as const,
        () => 'rejected' as const
      ),
      page.waitForTimeout(30_000).then(() => 'still-waiting' as const),
    ])

    expect(settled, 'an aria-disabled Save must fail fast, not consume the test timeout').toBe('rejected')
  })

  test('surfaces a failed save instead of treating it as persisted', async ({ page }) => {
    await serveFixture(page, FAILING_FIXTURE, FAILING_HTML, { saveStatus: 500 })
    await page.goto(toAppUrl(FAILING_FIXTURE))

    await expect(clickSaveAndWait(page)).rejects.toThrow(/500/)
  })

  test('isWorkflowSaveResponse ignores every neighbouring /workflows request', () => {
    const stub = (method: string, url: string) =>
      ({ request: () => ({ method: () => method }), url: () => url }) as never

    expect(isWorkflowSaveResponse(stub('POST', 'https://app/api/v1/workflows'))).toBe(true)
    expect(isWorkflowSaveResponse(stub('PATCH', `https://app/api/v1/workflows/${WORKFLOW_UUID}`))).toBe(true)

    // The Verify action posts this, and it is what a `/api/v1/workflows*` glob
    // would wrongly accept as a save.
    expect(isWorkflowSaveResponse(stub('POST', 'https://app/api/v1/workflows/validate'))).toBe(false)
    expect(isWorkflowSaveResponse(stub('GET', `https://app/api/v1/workflows/${WORKFLOW_UUID}`))).toBe(false)
    expect(
      isWorkflowSaveResponse(stub('POST', `https://app/api/v1/workflows/${WORKFLOW_UUID}/versions/1/publish`))
    ).toBe(false)
  })
})
