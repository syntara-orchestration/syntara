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
    [
      `Related to https://${jiraHost}/jira/core/projects/AAP/list?selectedIssue=AAP-12345.`,
      `https://${jiraHost}/jira/core/projects/AAP/list?selectedIssue=AAP-12345`,
      'AAP-12345',
    ],
    [
      `Board: https://${jiraHost}/jira/software/c/projects/AAP/boards/1?selectedIssue=AAP-7&quickFilter=2`,
      `https://${jiraHost}/jira/software/c/projects/AAP/boards/1?selectedIssue=AAP-7&quickFilter=2`,
      'AAP-7',
    ],
  ])('rejects Jira URLs in %j', (body, url, key) => {
    expect(checkPrDescription(body)).toEqual([
      `Jira URLs are not allowed in the PR description. Replace ${url} with the plain key ${key}.`,
    ])
  })

  it('rejects Jira URLs that name no issue', () => {
    expect(checkPrDescription(`Filter: https://${jiraHost}/issues/?filter=12345`)).toEqual([
      `Jira URLs are not allowed in the PR description. Replace https://${jiraHost}/issues/?filter=12345 with the plain issue key.`,
    ])
  })

  it('reports every Jira URL', () => {
    const body = `https://${jiraHost}/browse/AAP-1\nhttps://${jiraHost}/browse/AAP-2`

    expect(checkPrDescription(body)).toHaveLength(2)
  })
})
