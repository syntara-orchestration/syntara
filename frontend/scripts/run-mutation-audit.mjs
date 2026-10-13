import { createHash } from 'node:crypto'
import { execFileSync, spawn } from 'node:child_process'
import { createWriteStream } from 'node:fs'
import { access, mkdir, readFile, readdir, rename, rm, writeFile } from 'node:fs/promises'
import { once } from 'node:events'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url))
const frontendDirectory = path.resolve(scriptDirectory, '..')
const repositoryDirectory = path.resolve(frontendDirectory, '..')
const runId = process.env.SYNTARA_MUTATION_RUN_ID ?? new Date().toISOString().replace(/[:.]/g, '-')
const batchSize = Number(process.env.SYNTARA_MUTATION_BATCH_SIZE ?? 25)
const vitestTimeoutMs = Number(process.env.SYNTARA_MUTATION_VITEST_TIMEOUT_MS ?? 60_000)
const ignoreStatic = ['1', 'true'].includes(process.env.SYNTARA_MUTATION_IGNORE_STATIC?.toLowerCase())
const maxBatches = process.env.SYNTARA_MUTATION_MAX_BATCHES
  ? Number(process.env.SYNTARA_MUTATION_MAX_BATCHES)
  : Number.POSITIVE_INFINITY

if (!/^[A-Za-z0-9._-]+$/.test(runId)) {
  throw new Error('SYNTARA_MUTATION_RUN_ID may contain only letters, numbers, dots, underscores, and dashes')
}
if (!Number.isInteger(batchSize) || batchSize < 1) {
  throw new Error('SYNTARA_MUTATION_BATCH_SIZE must be a positive integer')
}
if (!Number.isSafeInteger(vitestTimeoutMs) || vitestTimeoutMs < 1) {
  throw new Error('SYNTARA_MUTATION_VITEST_TIMEOUT_MS must be a positive integer')
}
if (!(maxBatches === Number.POSITIVE_INFINITY || (Number.isInteger(maxBatches) && maxBatches > 0))) {
  throw new Error('SYNTARA_MUTATION_MAX_BATCHES must be a positive integer')
}

const reportDirectory = path.join(frontendDirectory, 'mutation-reports', runId)
const packageRuns = [
  {
    name: 'UI',
    slug: 'ui',
    workspace: 'packages/syntara-ui',
    sourceRoots: ['src', 'eslint-plugin-syntara'],
    excludedFileSuffixes: ['.stories', '.testFixtures'],
    excludedDirectories: ['mockData'],
    excludedPaths: ['src/app/tanstackRouteTree.tsx'],
    reportName: 'ui',
  },
  {
    name: 'Mock API',
    slug: 'mock-api',
    workspace: 'packages/syntara-mock-api',
    sourceRoots: ['src'],
    excludedFileSuffixes: [],
    excludedDirectories: [],
    excludedPaths: ['src/resources'],
    reportName: 'mock-api',
  },
]

const codeExtensions = new Set([
  '.js',
  '.jsx',
  '.ts',
  '.tsx',
  '.mjs',
  '.cjs',
  '.json',
  '.css',
  '.scss',
  '.html',
  '.mdx',
  '.snap',
  '.txt',
  '.yaml',
  '.yml',
])
const commonExcludedDirectories = new Set(['__tests__', 'test', 'tests', 'fixtures', '__fixtures__'])
const mutationStatuses = [
  'Killed',
  'Survived',
  'NoCoverage',
  'Timeout',
  'CompileError',
  'RuntimeError',
  'Ignored',
  'Pending',
  'Error',
]

function commandOutput(command, args, cwd) {
  try {
    return execFileSync(command, args, { cwd, encoding: 'utf8' }).trim()
  } catch {
    return 'unavailable'
  }
}

function stableSort(values) {
  return values.sort((left, right) => (left < right ? -1 : left > right ? 1 : 0))
}

function isMutationExcluded(target, relativePath) {
  const normalizedPath = relativePath.replaceAll(path.sep, '/')
  const segments = normalizedPath.split('/')
  const fileName = path.posix.basename(normalizedPath)
  const extension = path.posix.extname(fileName)
  const stem = fileName.slice(0, -extension.length)

  if (!['.js', '.jsx', '.ts', '.tsx'].includes(extension)) return true
  if (fileName.endsWith('.d.ts')) return true
  if (stem.endsWith('.test') || stem.endsWith('.spec')) return true
  if (target.excludedFileSuffixes.some((suffix) => stem.endsWith(suffix))) return true
  if (
    segments.some((segment) => commonExcludedDirectories.has(segment) || target.excludedDirectories.includes(segment))
  ) {
    return true
  }
  if (
    target.excludedPaths.some(
      (excludedPath) => normalizedPath === excludedPath || normalizedPath.startsWith(`${excludedPath}/`)
    )
  ) {
    return true
  }

  return false
}

async function discoverSourceFiles(target) {
  const packageDirectory = path.join(frontendDirectory, target.workspace)
  const files = []

  async function walk(relativeDirectory) {
    const absoluteDirectory = path.join(packageDirectory, relativeDirectory)
    let entries
    try {
      entries = await readdir(absoluteDirectory, { withFileTypes: true })
    } catch (error) {
      if (error && typeof error === 'object' && 'code' in error && error.code === 'ENOENT') return
      throw error
    }

    for (const entry of entries) {
      if (entry.name.startsWith('.')) continue
      const relativePath = path.posix.join(relativeDirectory.replaceAll(path.sep, '/'), entry.name)

      if (entry.isDirectory()) {
        if (isMutationExcluded(target, `${relativePath}/placeholder.ts`)) continue
        await walk(relativePath)
      } else if (entry.isFile() && !isMutationExcluded(target, relativePath)) {
        files.push(relativePath)
      }
    }
  }

  for (const sourceRoot of target.sourceRoots) await walk(sourceRoot)
  return stableSort(files)
}

async function discoverContextDigest(target) {
  const packageDirectory = path.join(frontendDirectory, target.workspace)
  const contextFiles = []
  const excludedDirectories = new Set([
    '.git',
    '.stryker-tmp',
    '.vite',
    'coverage',
    'dist',
    'node_modules',
    'storybook-static',
  ])

  async function walk(relativeDirectory = '') {
    const absoluteDirectory = path.join(packageDirectory, relativeDirectory)
    let entries
    try {
      entries = await readdir(absoluteDirectory, { withFileTypes: true })
    } catch (error) {
      if (error && typeof error === 'object' && 'code' in error && error.code === 'ENOENT') return
      throw error
    }

    for (const entry of entries) {
      if (entry.name.startsWith('.')) continue
      const relativePath = relativeDirectory
        ? path.posix.join(relativeDirectory.replaceAll(path.sep, '/'), entry.name)
        : entry.name
      if (entry.isDirectory()) {
        if (!excludedDirectories.has(entry.name)) await walk(relativePath)
      } else if (entry.isFile() && codeExtensions.has(path.extname(entry.name))) {
        contextFiles.push(relativePath)
      }
    }
  }

  await walk()
  stableSort(contextFiles)
  const hash = createHash('sha256')
  for (const relativePath of contextFiles) {
    hash.update(relativePath)
    hash.update('\0')
    hash.update(await readFile(path.join(packageDirectory, relativePath)))
    hash.update('\0')
  }
  return { fileCount: contextFiles.length, sha256: hash.digest('hex') }
}

async function hashFile(relativePath) {
  try {
    return createHash('sha256')
      .update(await readFile(relativePath))
      .digest('hex')
  } catch {
    return 'unavailable'
  }
}

function splitBatches(files) {
  const batches = []
  for (let offset = 0; offset < files.length; offset += batchSize) {
    batches.push(files.slice(offset, offset + batchSize))
  }
  return batches
}

function createPackageScope(target, files, contextDigest) {
  const batches = splitBatches(files).map((batchFiles, index) => ({
    id: `${target.slug}-${String(index + 1).padStart(3, '0')}`,
    status: 'pending',
    files: batchFiles,
    startedAt: null,
    finishedAt: null,
    elapsedSeconds: null,
    exitCode: null,
    signal: null,
    error: null,
    htmlPath: null,
    jsonPath: null,
    incrementalPath: null,
  }))

  return {
    name: target.name,
    slug: target.slug,
    workspace: target.workspace,
    contextDigest,
    sourceFileCount: files.length,
    batchCount: batches.length,
    batches,
  }
}

function packageDirectory(target) {
  return path.join(frontendDirectory, target.workspace)
}

function batchDirectory(scope, batch) {
  return path.join(reportDirectory, 'batches', scope.slug, batch.id)
}

function batchReportPaths(scope, batch) {
  const directory = batchDirectory(scope, batch)
  const target = packageRuns.find((candidate) => candidate.slug === scope.slug)
  return {
    htmlPath: path.join(directory, `${target.reportName}.html`),
    jsonPath: path.join(directory, `${target.reportName}.json`),
    incrementalPath: path.join(directory, 'stryker-incremental.json'),
  }
}

function relativeReportPath(absolutePath) {
  return path.relative(reportDirectory, absolutePath).split(path.sep).join('/')
}

function serializeMetadataPath(absolutePath) {
  return absolutePath ? relativeReportPath(absolutePath) : null
}

function percentage(numerator, denominator) {
  return denominator === 0 ? 'n/a' : `${((numerator / denominator) * 100).toFixed(2)}%`
}

function csvCell(value) {
  const stringValue = String(value ?? '')
  return /[",\n]/.test(stringValue) ? `"${stringValue.replaceAll('"', '""')}"` : stringValue
}

function batchEntries(metadata) {
  return Array.from(allBatches(metadata))
}

function elapsedSeconds(batch) {
  if (typeof batch.elapsedSeconds === 'number') return batch.elapsedSeconds
  if (batch.status === 'running' && batch.startedAt) {
    return Math.max(0, (Date.now() - Date.parse(batch.startedAt)) / 1000)
  }
  return null
}

function formatDuration(seconds) {
  if (seconds === null) return '—'
  const wholeSeconds = Math.floor(seconds)
  const hours = Math.floor(wholeSeconds / 3600)
  const minutes = Math.floor((wholeSeconds % 3600) / 60)
  const remainingSeconds = wholeSeconds % 60
  return hours > 0
    ? `${hours}h ${minutes}m ${remainingSeconds}s`
    : minutes > 0
      ? `${minutes}m ${remainingSeconds}s`
      : `${remainingSeconds}s`
}

function completedBatchCount(metadata) {
  return batchEntries(metadata).filter(({ batch }) => batch.status === 'completed').length
}

function batchNumber(metadata, scope, batch) {
  return batchEntries(metadata).findIndex((entry) => entry.scope.slug === scope.slug && entry.batch.id === batch.id) + 1
}

function printBatchQueue(metadata, logStream) {
  const entries = batchEntries(metadata)
  const complete = entries.filter(({ batch }) => batch.status === 'completed').length
  const running = entries.filter(({ batch }) => batch.status === 'running').length
  const pending = entries.filter(({ batch }) => batch.status === 'pending').length
  const other = entries.length - complete - running - pending

  logLine(logStream, `Frontend mutation audit ${runId}: ${entries.length} sequential batches.`)
  logLine(
    logStream,
    `Status: ${complete} complete, ${running} running, ${pending} pending, ${other} failed or interrupted.`
  )
  logLine(logStream, 'Batch queue (reports appear as each batch finishes):')
  logLine(logStream, 'Batch       Package    Files  Status         Time')
  for (const [index, { scope, batch }] of entries.entries()) {
    logLine(
      logStream,
      `${String(index + 1).padStart(2, '0')}/${String(entries.length).padStart(2, '0')}  ${batch.id.padEnd(11)} ${scope.name.padEnd(10)} ${String(batch.files.length).padStart(5)}  ${batch.status.padEnd(14)} ${formatDuration(elapsedSeconds(batch))}`
    )
  }
  logLine(logStream, `Live report index: ${path.join(reportDirectory, 'index.md')}`)
  logLine(logStream, `Resume this run with: SYNTARA_MUTATION_RUN_ID=${runId} npm --prefix frontend run mutation:audit`)
}

async function readJsonReport(batch) {
  if (!batch.jsonPath) return null
  try {
    return JSON.parse(await readFile(path.join(reportDirectory, batch.jsonPath), 'utf8'))
  } catch {
    return null
  }
}

function fileCounts(fileReport) {
  const counts = Object.fromEntries(mutationStatuses.map((status) => [status, 0]))
  let other = 0
  for (const mutant of fileReport?.mutants ?? []) {
    if (Object.hasOwn(counts, mutant.status)) counts[mutant.status] += 1
    else other += 1
  }

  const total = Object.values(counts).reduce((sum, count) => sum + count, 0) + other
  const covered = Math.max(0, total - counts.NoCoverage - counts.Ignored)
  return { ...counts, other, total, covered }
}

function normalizeReportFile(fileName, workspace) {
  const normalized = String(fileName).replaceAll('\\', '/')
  if (path.isAbsolute(fileName)) {
    return path.relative(path.join(frontendDirectory, workspace), fileName).split(path.sep).join('/')
  }
  return normalized.replace(/^\.\//, '')
}

async function writeCombinedSummary(metadata) {
  const packageTotals = new Map()
  const rows = []
  const availableReports = []

  for (const scope of metadata.packages) {
    const totals = fileCounts(null)
    const completedFiles = scope.batches
      .filter((batch) => batch.status === 'completed')
      .reduce((sum, batch) => sum + batch.files.length, 0)

    for (const batch of scope.batches) {
      const report = await readJsonReport(batch)
      if (!report) continue

      const reportFiles = new Map(
        Object.entries(report.files ?? {}).map(([fileName, fileReport]) => [
          normalizeReportFile(fileName, scope.workspace),
          fileReport,
        ])
      )
      const reportLinks = {
        htmlPath: batch.htmlPath,
        jsonPath: batch.jsonPath,
      }
      availableReports.push({ scope, batch, ...reportLinks })

      for (const fileName of batch.files) {
        const counts = fileCounts(reportFiles.get(fileName))
        for (const status of mutationStatuses) totals[status] += counts[status]
        totals.other += counts.other
        totals.total += counts.total
        totals.covered += counts.covered
        rows.push({ scope, batch, fileName, counts })
      }

      for (const [fileName, fileReport] of reportFiles) {
        if (batch.files.includes(fileName)) continue
        const counts = fileCounts(fileReport)
        rows.push({ scope, batch, fileName, counts, unexpected: true })
      }
    }

    const covered = totals.covered
    const killed = totals.Killed
    packageTotals.set(scope.slug, {
      ...totals,
      killed,
      completedFiles,
      completedBatchCount: scope.batches.filter((batch) => batch.status === 'completed').length,
      mutationScore: percentage(killed, totals.total),
      coveredMutationScore: percentage(killed, covered),
      coverage: percentage(covered, totals.total),
    })
  }

  const columns = [
    'package',
    'batch',
    'file',
    'total',
    'killed',
    'survived',
    'no_coverage',
    'timeout',
    'compile_error',
    'runtime_error',
    'ignored',
    'pending',
    'error',
    'other',
    'mutation_score_all_pct',
    'mutation_score_covered_pct',
    'coverage_pct',
    'unexpected_report_file',
  ]
  const csv = [columns.join(',')]
  for (const row of rows) {
    const { counts } = row
    const values = [
      row.scope.name,
      row.batch.id,
      row.fileName,
      counts.total,
      counts.Killed,
      counts.Survived,
      counts.NoCoverage,
      counts.Timeout,
      counts.CompileError,
      counts.RuntimeError,
      counts.Ignored,
      counts.Pending,
      counts.Error,
      counts.other,
      percentage(counts.Killed, counts.total),
      percentage(counts.Killed, counts.covered),
      percentage(counts.covered, counts.total),
      row.unexpected ? 'yes' : 'no',
    ]
    csv.push(values.map(csvCell).join(','))
  }
  await writeFile(path.join(reportDirectory, 'combined-summary.csv'), `${csv.join('\n')}\n`)

  const packageTable = metadata.packages
    .map((scope) => {
      const totals = packageTotals.get(scope.slug)
      const status = scope.batches.length === totals.completedBatchCount ? 'complete' : 'incomplete'
      return `| ${scope.name} | ${status} | ${totals.completedFiles}/${scope.sourceFileCount} | ${totals.completedBatchCount}/${scope.batchCount} | ${totals.total} | ${totals.mutationScore} | ${totals.coveredMutationScore} | ${totals.coverage} |`
    })
    .join('\n')

  const batchTable = batchEntries(metadata)
    .map(({ scope, batch }, index) => {
      const htmlLink = batch.htmlPath ? `[HTML](${batch.htmlPath})` : '—'
      const jsonLink = batch.jsonPath ? `[JSON](${batch.jsonPath})` : '—'
      return `| ${index + 1} | \`${batch.id}\` | ${scope.name} | ${batch.files.length} | ${batch.status} | ${formatDuration(elapsedSeconds(batch))} | ${htmlLink} · ${jsonLink} |`
    })
    .join('\n')

  const reportLinks =
    availableReports
      .map(({ scope, batch, htmlPath, jsonPath }) => {
        const htmlLink = htmlPath ? `[HTML](${htmlPath})` : 'HTML unavailable'
        const jsonLink = jsonPath ? `[JSON](${jsonPath})` : 'JSON unavailable'
        return `- **${scope.name} ${batch.id}:** ${htmlLink} · ${jsonLink} (${batch.status})`
      })
      .join('\n') || '- No batch reports have finished yet.'

  const findings = rows
    .filter(
      ({ counts }) =>
        counts.Survived +
          counts.NoCoverage +
          counts.Timeout +
          counts.CompileError +
          counts.RuntimeError +
          counts.Error >
        0
    )
    .sort((left, right) => {
      const leftCount =
        left.counts.Survived +
        left.counts.NoCoverage +
        left.counts.Timeout +
        left.counts.CompileError +
        left.counts.RuntimeError +
        left.counts.Error
      const rightCount =
        right.counts.Survived +
        right.counts.NoCoverage +
        right.counts.Timeout +
        right.counts.CompileError +
        right.counts.RuntimeError +
        right.counts.Error
      return rightCount - leftCount || left.fileName.localeCompare(right.fileName)
    })
    .slice(0, 30)
    .map(({ scope, batch, fileName, counts }) => {
      const details = [
        counts.Survived ? `${counts.Survived} survived` : null,
        counts.NoCoverage ? `${counts.NoCoverage} uncovered` : null,
        counts.Timeout ? `${counts.Timeout} timed out` : null,
        counts.CompileError ? `${counts.CompileError} compile errors` : null,
        counts.RuntimeError ? `${counts.RuntimeError} runtime errors` : null,
        counts.Error ? `${counts.Error} errors` : null,
      ]
        .filter(Boolean)
        .join(', ')
      return `| ${scope.name} | \`${fileName}\` | ${details} | [${batch.id}](${batch.htmlPath ?? batch.jsonPath ?? '#'}) |`
    })
    .join('\n')

  const completedBatchCount = metadata.packages.reduce(
    (sum, scope) => sum + scope.batches.filter((batch) => batch.status === 'completed').length,
    0
  )
  const totalBatchCount = metadata.packages.reduce((sum, scope) => sum + scope.batchCount, 0)
  const reportedSourceFiles = rows.length
  const indexMarkdown = `# StrykerJS audit: ${runId}

Status: **${metadata.status}**

Mutation mode: **${metadata.ignoreStatic ? 'fast preview; static mutants marked Ignored, so this is not the complete audit' : 'all generated mutants, including static mutants'}**

Audited revision: \`${metadata.sourceRevision}\`

Started: ${metadata.startedAt}<br>
Last updated: ${metadata.updatedAt}<br>
Node: \`${metadata.nodeVersion}\`; npm: \`${metadata.npmVersion}\`; Vitest: \`${metadata.vitestVersion}\`; StrykerJS: \`${metadata.strykerVersion}\`
Vitest test/hook timeout during audit: **${metadata.vitestTimeoutMs} ms**

Source batches completed: **${completedBatchCount}/${totalBatchCount}**. The audit is complete only when every listed batch completes successfully.

| Package | Scope status | Source files completed | Batches completed | Mutants in available reports | Mutation score (all) | Mutation score (covered) | Coverage |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
${packageTable}

## Batch status

All batches are listed in run order. This table and the combined CSV update after each batch.

| # | Batch | Package | Source files | Status | Time | Reports |
| ---: | --- | --- | ---: | --- | --- | --- |
${batchTable}

## Batch reports

${reportLinks}

## Largest current findings

These entries are candidates to inspect in the linked batch reports; survived mutations can also be equivalent changes or tool issues.

| Package | Source file | Findings | Report |
| --- | --- | --- | --- |
${findings || '| No survived, uncovered, or error findings in available reports. | — | — | — |'}

- [Combined per-file CSV summary](combined-summary.csv) (${reportedSourceFiles} report rows)
- [Run metadata](run.json)
- [Audit log](audit.log)
`
  await writeFile(path.join(reportDirectory, 'index.md'), indexMarkdown)
}

async function writeRunMetadata(metadata) {
  metadata.updatedAt = new Date().toISOString()
  const metadataPath = path.join(reportDirectory, 'run.json')
  const temporaryPath = `${metadataPath}.tmp`
  await writeFile(temporaryPath, `${JSON.stringify(metadata, null, 2)}\n`)
  await rename(temporaryPath, metadataPath)
}

function logLine(logStream, message) {
  const line = `${new Date().toISOString()} ${message}\n`
  process.stdout.write(line)
  logStream.write(line)
}

function runStrykerBatch(target, scope, batch, logStream) {
  const relativeReportDirectory = path.relative(packageDirectory(target), batchDirectory(scope, batch))
  const args = ['run', 'mutate', '--', '--mutate', batch.files.join(',')]
  if (ignoreStatic) args.push('--ignoreStatic')
  const environment = {
    ...process.env,
    SYNTARA_MUTATION_REPORT_DIR: relativeReportDirectory,
    SYNTARA_MUTATION_VITEST_TIMEOUT_MS: String(vitestTimeoutMs),
  }

  return new Promise((resolve) => {
    let spawnError = null
    const child = spawn('npm', args, {
      cwd: packageDirectory(target),
      env: environment,
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    activeChild = child

    child.stdout.on('data', (chunk) => {
      process.stdout.write(chunk)
      logStream.write(`[${batch.id}] ${chunk.toString()}`)
    })
    child.stderr.on('data', (chunk) => {
      process.stderr.write(chunk)
      logStream.write(`[${batch.id}] ${chunk.toString()}`)
    })
    child.on('error', (error) => {
      spawnError = error
    })
    child.on('close', (code, signal) => {
      activeChild = null
      resolve({ code, signal, error: spawnError })
    })
  })
}

let activeChild = null
let requestedSignal = null
let signalCount = 0

function handleSignal(signal) {
  signalCount += 1
  if (signalCount > 1) process.exit(signal === 'SIGINT' ? 130 : 143)
  requestedSignal = signal
  if (activeChild && !activeChild.killed) activeChild.kill(signal)
}

process.on('SIGINT', () => handleSignal('SIGINT'))
process.on('SIGTERM', () => handleSignal('SIGTERM'))

async function buildInitialMetadata() {
  const scopes = []
  for (const target of packageRuns) {
    const files = await discoverSourceFiles(target)
    const contextDigest = await discoverContextDigest(target)
    scopes.push(createPackageScope(target, files, contextDigest))
  }

  return {
    runId,
    status: 'running',
    sourceRevision: commandOutput('git', ['rev-parse', 'HEAD'], repositoryDirectory),
    workingTree: commandOutput('git', ['status', '--short'], repositoryDirectory).split('\n').filter(Boolean),
    dependencyContext: {
      frontendPackageJson: await hashFile(path.join(frontendDirectory, 'package.json')),
      frontendLockfile: await hashFile(path.join(frontendDirectory, 'package-lock.json')),
    },
    nodeVersion: process.version,
    npmVersion: commandOutput('npm', ['--version'], frontendDirectory),
    vitestVersion: await readPackageVersion('node_modules/vitest/package.json').catch(() => 'unknown'),
    strykerVersion: await readPackageVersion('node_modules/@stryker-mutator/core/package.json').catch(() => 'unknown'),
    batchSize,
    vitestTimeoutMs,
    ignoreStatic,
    mutationMode: ignoreStatic
      ? 'fast preview; static mutants are marked Ignored and not executed'
      : 'full; static mutants are included',
    batchExecution: 'sequential across packages; Stryker concurrency is capped at 2',
    mutationScope: 'all eligible handwritten JavaScript/TypeScript production source in both package configurations',
    exclusions: {
      common: ['test/spec files', 'declaration files', '__tests__, test, tests, fixtures, __fixtures__ directories'],
      ui: ['story files', 'test fixture files', 'mockData directories', 'src/app/tanstackRouteTree.tsx'],
      mockApi: ['src/resources/**'],
    },
    startedAt: new Date().toISOString(),
    resumePolicy:
      'Completed batches are retained and skipped. An unfinished batch is rerun from scratch; it never shares an incremental result file with another batch.',
    packages: scopes,
    currentBatch: null,
    interruption: null,
  }
}

function validateResume(existing, expected) {
  if (existing.sourceRevision !== expected.sourceRevision) {
    throw new Error(
      `Run ${runId} belongs to revision ${existing.sourceRevision}; current revision is ${expected.sourceRevision}. Choose a new run ID.`
    )
  }
  if (JSON.stringify(existing.dependencyContext) !== JSON.stringify(expected.dependencyContext)) {
    throw new Error(`Dependency manifests changed since run ${runId} began. Choose a new run ID.`)
  }
  if (existing.batchSize !== batchSize) {
    throw new Error(
      `Run ${runId} uses batch size ${existing.batchSize}; current setting is ${batchSize}. Keep the same size or choose a new run ID.`
    )
  }
  if (existing.ignoreStatic !== ignoreStatic) {
    throw new Error(
      `Run ${runId} uses ignoreStatic=${existing.ignoreStatic}; current setting is ${ignoreStatic}. Keep the same mode or choose a new run ID.`
    )
  }
  if (existing.vitestTimeoutMs !== vitestTimeoutMs) {
    throw new Error(
      `Run ${runId} uses Vitest test/hook timeouts of ${existing.vitestTimeoutMs} ms; current setting is ${vitestTimeoutMs} ms. Keep the same setting or choose a new run ID.`
    )
  }

  for (const expectedScope of expected.packages) {
    const existingScope = existing.packages.find((scope) => scope.slug === expectedScope.slug)
    if (!existingScope || existingScope.contextDigest.sha256 !== expectedScope.contextDigest.sha256) {
      throw new Error(
        `The ${expectedScope.name} source, tests, or configuration changed since run ${runId} began. Choose a new run ID.`
      )
    }
    const oldBatches = existingScope.batches.map((batch) => batch.files)
    const newBatches = expectedScope.batches.map((batch) => batch.files)
    if (JSON.stringify(oldBatches) !== JSON.stringify(newBatches)) {
      throw new Error(
        `The ${expectedScope.name} source scope or batch boundaries changed since run ${runId} began. Choose a new run ID.`
      )
    }
  }

  return existing
}

function* allBatches(metadata) {
  const scopes = metadata.packages
  const maxBatchCount = Math.max(0, ...scopes.map((scope) => scope.batches.length))
  for (let index = 0; index < maxBatchCount; index += 1) {
    for (const scope of scopes) {
      if (scope.batches[index]) yield { scope, batch: scope.batches[index] }
    }
  }
}

async function refreshBatchPaths(scope, batch) {
  const paths = batchReportPaths(scope, batch)
  batch.htmlPath = (await exists(paths.htmlPath)) ? serializeMetadataPath(paths.htmlPath) : null
  batch.jsonPath = (await exists(paths.jsonPath)) ? serializeMetadataPath(paths.jsonPath) : null
  batch.incrementalPath = (await exists(paths.incrementalPath)) ? serializeMetadataPath(paths.incrementalPath) : null
}

async function exists(filePath) {
  try {
    await access(filePath)
    return true
  } catch {
    return false
  }
}

async function main() {
  const initialMetadata = await buildInitialMetadata()

  if (process.argv.includes('--plan')) {
    for (const scope of initialMetadata.packages) {
      process.stdout.write(
        `${scope.name}: ${scope.sourceFileCount} eligible source files, ${scope.batchCount} batches of up to ${batchSize}\n`
      )
    }
    process.stdout.write(`Mutation mode: ${initialMetadata.mutationMode}\n`)
    return
  }

  await mkdir(reportDirectory, { recursive: true })
  const metadataPath = path.join(reportDirectory, 'run.json')
  let metadata = initialMetadata

  if (await exists(metadataPath)) {
    const existing = JSON.parse(await readFile(metadataPath, 'utf8'))
    metadata = validateResume(existing, initialMetadata)
    metadata.resumeEvents = [
      ...(metadata.resumeEvents ?? []),
      {
        at: new Date().toISOString(),
        workingTree: commandOutput('git', ['status', '--short'], repositoryDirectory).split('\n').filter(Boolean),
      },
    ]
    metadata.status = 'running'
    metadata.finishedAt = null
    metadata.interruption = null
    metadata.currentBatch = null
    for (const scope of metadata.packages) {
      for (const batch of scope.batches) {
        if (batch.status === 'running') {
          batch.status = 'interrupted'
          batch.finishedAt = null
          batch.elapsedSeconds = null
          batch.exitCode = null
          batch.signal = null
          batch.error = 'Previous run stopped before this batch finished; it will be rerun.'
        }
      }
    }
  }

  const logStream = createWriteStream(path.join(reportDirectory, 'audit.log'), { flags: 'a' })
  await once(logStream, 'open')
  let completedThisInvocation = 0
  let stoppedAtBatchLimit = false

  try {
    await writeRunMetadata(metadata)
    await writeCombinedSummary(metadata)
    printBatchQueue(metadata, logStream)

    for (const { scope, batch } of allBatches(metadata)) {
      if (batch.status === 'completed' && batch.jsonPath && batch.htmlPath) continue
      if (requestedSignal) break
      if (completedThisInvocation >= maxBatches) {
        stoppedAtBatchLimit = true
        break
      }

      const target = packageRuns.find((candidate) => candidate.slug === scope.slug)
      const currentContextDigest = await discoverContextDigest(target)
      if (currentContextDigest.sha256 !== scope.contextDigest.sha256) {
        metadata.status = 'incomplete'
        metadata.finishedAt = new Date().toISOString()
        metadata.interruption = `The ${scope.name} source, tests, or configuration changed during the audit. Earlier reports are preserved; start a new run ID to continue with a consistent snapshot.`
        await writeRunMetadata(metadata)
        await writeCombinedSummary(metadata)
        logLine(logStream, metadata.interruption)
        process.exitCode = 1
        return
      }

      await rm(batchDirectory(scope, batch), { recursive: true, force: true })
      await mkdir(batchDirectory(scope, batch), { recursive: true })
      batch.status = 'running'
      batch.startedAt = new Date().toISOString()
      batch.finishedAt = null
      batch.elapsedSeconds = null
      batch.exitCode = null
      batch.signal = null
      batch.error = null
      batch.htmlPath = null
      batch.jsonPath = null
      batch.incrementalPath = null
      metadata.currentBatch = { package: scope.slug, batch: batch.id, files: batch.files.length }
      await writeRunMetadata(metadata)
      await writeCombinedSummary(metadata)

      const startedAt = process.hrtime.bigint()
      const number = batchNumber(metadata, scope, batch)
      const total = batchEntries(metadata).length
      logLine(
        logStream,
        `Starting batch ${number}/${total}: ${scope.name} ${batch.id}, ${batch.files.length} source files. ${completedBatchCount(metadata)}/${total} batches complete.`
      )
      const heartbeat = setInterval(() => {
        const runningFor = Number(process.hrtime.bigint() - startedAt) / 1_000_000_000
        logLine(
          logStream,
          `Still running batch ${number}/${total}: ${scope.name} ${batch.id} (${formatDuration(runningFor)}). ${completedBatchCount(metadata)}/${total} batches complete. Reports are saved after this batch finishes.`
        )
      }, 60_000)
      heartbeat.unref()
      let result
      try {
        result = await runStrykerBatch(target, scope, batch, logStream)
      } finally {
        clearInterval(heartbeat)
      }
      batch.finishedAt = new Date().toISOString()
      batch.elapsedSeconds = Number(process.hrtime.bigint() - startedAt) / 1_000_000_000
      batch.exitCode = result.code
      batch.signal = result.signal
      if (result.error) batch.error = result.error.message
      await refreshBatchPaths(scope, batch)

      if (requestedSignal || result.signal) {
        batch.status = 'interrupted'
        metadata.interruption = `${requestedSignal ?? result.signal} received while ${batch.id} was running. That batch will be rerun from scratch; earlier completed batch reports are retained.`
      } else if (result.error) {
        batch.status = 'failed'
      } else if (result.code !== 0) {
        batch.status = 'failed'
        batch.error = `Stryker exited with status ${result.code}`
      } else if (!batch.jsonPath || !batch.htmlPath) {
        batch.status = 'missing-report'
        batch.error = 'Stryker finished without both JSON and HTML reports'
      } else {
        batch.status = 'completed'
      }

      completedThisInvocation += 1
      metadata.currentBatch = null
      await writeRunMetadata(metadata)
      await writeCombinedSummary(metadata)
      const reports = [batch.htmlPath, batch.jsonPath]
        .filter(Boolean)
        .map((reportPath) => path.join(reportDirectory, reportPath))
      logLine(
        logStream,
        `Batch ${number}/${total}: ${scope.name} ${batch.id} ${batch.status} after ${formatDuration(batch.elapsedSeconds)}. ${completedBatchCount(metadata)}/${total} batches complete. Reports: ${reports.join(', ') || 'not available'}. Updated index: ${path.join(reportDirectory, 'index.md')}`
      )

      if (batch.status === 'interrupted') break
    }

    metadata.finishedAt = new Date().toISOString()
    const everyBatchCompleted = metadata.packages.every((scope) =>
      scope.batches.every((batch) => batch.status === 'completed')
    )
    metadata.status = everyBatchCompleted ? 'complete' : requestedSignal ? 'interrupted' : 'incomplete'
    if (requestedSignal)
      metadata.interruption = `${requestedSignal} received; rerun the same command and run ID to resume.`
    if (stoppedAtBatchLimit)
      metadata.pauseReason = `Stopped after ${completedThisInvocation} newly run batch(es) due to SYNTARA_MUTATION_MAX_BATCHES.`
    delete metadata.currentBatch
    await writeRunMetadata(metadata)
    await writeCombinedSummary(metadata)
    logLine(logStream, `Mutation audit ${metadata.status}: ${reportDirectory}`)

    if (metadata.status !== 'complete') process.exitCode = 1
  } finally {
    logStream.end()
    await once(logStream, 'finish')
  }
}

async function readPackageVersion(relativePath) {
  const contents = await readFile(path.join(frontendDirectory, relativePath), 'utf8')
  return JSON.parse(contents).version
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.stack : String(error)}\n`)
  process.exitCode = 1
})
