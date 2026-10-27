import { describe, it, expect } from 'vitest'
import { JIRA_HOSTS } from '../jira.js'
import { checkPrDescription } from '../pr-description.js'

/** Current and legacy Jira hosts; tests build URLs from them so the repo holds no literal Jira URL. */
const [jiraHost, legacyJiraHost] = JIRA_HOSTS

describe('checkPrDescription', () => {
  it.each([
    '',
    '## Related Issues\n\nRelated to AAP-99723',
    'Fixes AAP-99723 and ANSTRAT-1934',
    'Upstream report: https://github.com/syntara-orchestration/syntara/issues/12',
  ])('accepts %j', (body) => {
    expect(checkPrDescription(body)).toEqual([])
  })

  it.each([
    [`Related to https://${jiraHost}/browse/AAP-99723`, `https://${jiraHost}/browse/AAP-99723`, 'AAP-99723'],
    [`See [AAP-1](https://${legacyJiraHost}/browse/AAP-1)`, `https://${legacyJiraHost}/browse/AAP-1`, 'AAP-1'],
    [`Ticket: ${jiraHost}/browse/ANSTRAT-1934`, `${jiraHost}/browse/ANSTRAT-1934`, 'ANSTRAT-1934'],
  ])('rejects Jira URLs in %j', (body, url, key) => {
    expect(checkPrDescription(body)).toEqual([
      `Jira URLs are not allowed in the PR description. Replace ${url} with the plain key ${key}.`,
    ])
  })

  it('reports every Jira URL', () => {
    const body = `https://${jiraHost}/browse/AAP-1\nhttps://${jiraHost}/browse/AAP-2`

    expect(checkPrDescription(body)).toHaveLength(2)
  })
})
