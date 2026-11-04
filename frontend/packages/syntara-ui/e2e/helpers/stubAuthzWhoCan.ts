import type { Page } from '../fixtures'

export type WhoCanUserStub = Readonly<{ id: string; username: string }>

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function parseWhoCanPostBody(value: unknown): { action?: string; resource_type?: string } | null {
  if (!isRecord(value)) {
    return null
  }
  const action = value.action
  const resourceType = value.resource_type
  return {
    action: typeof action === 'string' ? action : undefined,
    resource_type: typeof resourceType === 'string' ? resourceType : undefined,
  }
}

/** Stub `who_can` for form_prompt submit responders (shared by builder and form-prompt E2E). */
export async function stubFormPromptSubmitWhoCanUsers(page: Page, users: ReadonlyArray<WhoCanUserStub>) {
  await page.route('**/api/v1/authz/who_can', async (route) => {
    const request = route.request()
    if (request.method() === 'POST') {
      const body = parseWhoCanPostBody(request.postDataJSON())
      if (body?.action === 'submit' && body?.resource_type === 'form_prompt') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            resources: users.map((user) => ({ id: user.id, username: user.username })),
            next: null,
          }),
        })
        return
      }
    }
    await route.continue()
  })
}

export const DEFAULT_FORM_PROMPT_WHO_CAN_USERS: WhoCanUserStub[] = [
  { id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', username: 'demo' },
  { id: 'b2c3d4e5-f6a7-8901-bcde-f12345678901', username: 'jdoe' },
]
