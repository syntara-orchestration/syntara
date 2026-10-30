import { appendFileSync, readFileSync } from 'node:fs'

const reportPath = process.argv[2]
if (!reportPath) throw new Error('Pass the md-link-lint JSON report path.')

const report = JSON.parse(readFileSync(reportPath, 'utf8'))

/** Escape newlines so report text cannot start another workflow command. */
function escapeWorkflowData(value) {
  return String(value).replaceAll('%', '%25').replaceAll('\r', '%0D').replaceAll('\n', '%0A')
}

/** Escape separators in workflow command properties. */
function escapeWorkflowProperty(value) {
  return escapeWorkflowData(value).replaceAll(':', '%3A').replaceAll(',', '%2C')
}

/** Keep report values inside their Markdown table cells. */
function escapeSummaryCell(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('|', '&#124;')
    .replaceAll(String.fromCharCode(96), '&#96;')
    .replaceAll('\r', ' ')
    .replaceAll('\n', ' ')
}

for (const finding of report.findings) {
  const properties = [
    'file=' + escapeWorkflowProperty(finding.sourcePath),
    'line=' + finding.line,
    'col=' + finding.column,
    'title=' + escapeWorkflowProperty(finding.code),
  ].join(',')
  const message = finding.destination + ' — ' + finding.reason
  console.log('::error ' + properties + '::' + escapeWorkflowData(message))
}

for (const error of report.scanErrors) {
  const properties = []
  if (error.sourcePath) properties.push('file=' + escapeWorkflowProperty(error.sourcePath))
  if (error.line) properties.push('line=' + error.line)
  if (error.column) properties.push('col=' + error.column)
  if (error.code) properties.push('title=' + escapeWorkflowProperty(error.code))

  const location = error.sourcePath
    ? error.sourcePath + (error.line ? ':' + error.line + ':' + (error.column ?? 1) : '') + ' '
    : ''
  const message = location + error.code + ': ' + error.reason
  const command = properties.length > 0 ? '::error ' + properties.join(',') + '::' : '::error::'
  console.log(command + escapeWorkflowData(message))
}

const counts = report.counts
const lines = [
  '## Markdown link check',
  '',
  'Scanned **' +
    counts.filesScanned +
    '** Markdown files, checked **' +
    counts.linksChecked +
    '** links, and skipped **' +
    counts.linksSkipped +
    '** external links.',
  '',
  report.findings.length === 0 && report.scanErrors.length === 0
    ? 'No broken links found.'
    : 'Found **' + (report.findings.length + report.scanErrors.length) + '** problem(s).',
]

if (report.findings.length > 0) {
  lines.push(
    '',
    '| File | Location | Problem | Link |',
    '| --- | ---: | --- | --- |',
    ...report.findings.map(
      (finding) =>
        '| ' +
        escapeSummaryCell(finding.sourcePath) +
        ' | ' +
        finding.line +
        ':' +
        finding.column +
        ' | ' +
        escapeSummaryCell(finding.code + ': ' + finding.reason) +
        ' | ' +
        escapeSummaryCell(finding.destination) +
        ' |'
    )
  )
}

if (report.scanErrors.length > 0) {
  lines.push(
    '',
    '### Scan errors',
    '',
    '| File | Location | Problem |',
    '| --- | ---: | --- |',
    ...report.scanErrors.map((error) => {
      const location = error.line ? error.line + ':' + (error.column ?? 1) : '—'
      return (
        '| ' +
        escapeSummaryCell(error.sourcePath ?? 'Repository scan') +
        ' | ' +
        location +
        ' | ' +
        escapeSummaryCell(error.code + ': ' + error.reason) +
        ' |'
      )
    })
  )
}

const summary = lines.join('\n') + '\n'
if (process.env.GITHUB_STEP_SUMMARY) {
  appendFileSync(process.env.GITHUB_STEP_SUMMARY, summary)
} else {
  process.stdout.write(summary)
}

console.log(
  'Markdown link check: ' +
    counts.filesScanned +
    ' files, ' +
    counts.linksChecked +
    ' links checked, ' +
    (report.findings.length + report.scanErrors.length) +
    ' problem(s).'
)
