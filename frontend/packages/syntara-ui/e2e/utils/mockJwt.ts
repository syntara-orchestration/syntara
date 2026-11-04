import { createMockJwt, MOCK_USER_ID_BY_USERNAME, mockUserIdForUsername } from '../../../syntara-mock-api/src/mockJwt'

/** Stable user ids for assertions — sourced from mock-api `MOCK_USER_ID_BY_USERNAME`. */
export const MOCK_E2E_USER_IDS = {
  admin: MOCK_USER_ID_BY_USERNAME.admin,
  demo: MOCK_USER_ID_BY_USERNAME.demo,
  auditor: MOCK_USER_ID_BY_USERNAME.auditor,
  viewer: MOCK_USER_ID_BY_USERNAME.viewer,
  user: MOCK_USER_ID_BY_USERNAME.user,
  projectAdmin: MOCK_USER_ID_BY_USERNAME['project-admin'],
} as const

/** Unsigned JWT (alg: none) matching syntara-mock-api `createMockJwt` for E2E role fixtures. */
export function mockAccessTokenForUsername(username: string): string {
  return createMockJwt({ username, userId: mockUserIdForUsername(username) })
}
