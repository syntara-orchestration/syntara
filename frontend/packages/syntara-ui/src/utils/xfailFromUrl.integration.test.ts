/**
 * End-to-end integration test for the Playwright xfail / quarantine mechanism.
 *
 * Unlike the pure-logic tests in `xfailFromUrl.test.ts`, this spawns a real
 * Playwright runner against a temp project that imports the actual e2e
 * `fixtures.ts` (the `_xfailCheck` auto-fixture) and points `SYNTARA_XFAIL_SOURCE`
 * at a generated `playwright.md`. It then asserts on the JSON report, validating
 * the whole chain: env → load list → build test id → match pattern → quarantine.
 *
 * No browser is launched (the specs never use `page`), so this needs no browser
 * download and runs in a couple of seconds.
 */
import { execFileSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { join, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const nodeRequire = createRequire(__filename)
const packageDir = resolve(__dirname, '../..') // packages/syntara-ui
const fixturesModule = resolve(__dirname, '../../e2e/fixtures')
const xfailReporterModule = resolve(__dirname, '../../e2e/xfailReporter')
const playwrightCli = nodeRequire.resolve('@playwright/test/cli')

type SpecResult = { title: string; ok: boolean; expectedStatus?: string; lastStatus?: string }
type RunResult = { exitCode: number; specs: SpecResult[]; output: string }
type JsonSpec = {
  title: string
  ok: boolean
  tests: { expectedStatus?: string; results?: { status?: string }[] }[]
}

function collectSpecs(node: { suites?: unknown[]; specs?: unknown[] }): SpecResult[] {
  const out: SpecResult[] = []
  for (const suite of (node.suites as { suites?: unknown[]; specs?: unknown[] }[]) ?? []) {
    out.push(...collectSpecs(suite))
  }
  for (const spec of (node.specs as JsonSpec[] | undefined) ?? []) {
    const results = spec.tests[0]?.results ?? []
    out.push({
      title: spec.title,
      ok: spec.ok,
      expectedStatus: spec.tests[0]?.expectedStatus,
      lastStatus: results.at(-1)?.status,
    })
  }
  return out
}

/** Run Playwright over `specSource` with `mdSource` as the xfail list; return exit code, parsed specs, and output. */
function runPlaywright(specSource: string, mdSource: string, extraConfig = ''): RunResult {
  // Keep the temp project under this package so Playwright loads the ESM reporter
  // the same way real e2e does. /tmp is CJS and cannot import e2e/xfailReporter.ts.
  const dir = mkdtempSync(join(packageDir, '.tmp-xfail-int-'))
  try {
    const specsDir = join(dir, 'specs')
    const xfailDir = join(dir, 'xfail')
    mkdirSync(specsDir)
    mkdirSync(xfailDir)
    const reportFile = join(dir, 'report.json')

    writeFileSync(join(xfailDir, 'playwright.md'), mdSource)
    writeFileSync(join(specsDir, 'mech.spec.ts'), specSource)
    writeFileSync(
      join(dir, 'pw.config.ts'),
      `import { defineConfig } from '@playwright/test'\n` +
        `export default defineConfig({ testDir: ${JSON.stringify(specsDir)}, ${extraConfig}` +
        `reporter: [['json', { outputFile: ${JSON.stringify(reportFile)} }], ` +
        `[${JSON.stringify(xfailReporterModule)}]] })\n`
    )

    let exitCode = 0
    let output = ''
    try {
      output = execFileSync(process.execPath, [playwrightCli, 'test', '--config', join(dir, 'pw.config.ts')], {
        cwd: packageDir,
        env: { ...process.env, SYNTARA_XFAIL_SOURCE: `${xfailDir}/` },
        stdio: 'pipe',
        encoding: 'utf-8',
      })
    } catch (error) {
      const err = error as { status?: number; stdout?: string; stderr?: string }
      exitCode = err.status ?? 1
      output = `${err.stdout ?? ''}${err.stderr ?? ''}`
    }

    let raw: string
    try {
      raw = readFileSync(reportFile, 'utf-8')
    } catch {
      throw new Error(`Playwright produced no report (exit ${exitCode}). Output:\n${output}`)
    }
    const report = JSON.parse(raw) as { suites?: unknown[] }
    return { exitCode, specs: collectSpecs(report), output }
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
}

describe('xfail mechanism (Playwright integration)', () => {
  it('quarantines a listed failing test and keeps the suite green', () => {
    const spec = [
      `import { test, expect } from ${JSON.stringify(fixturesModule)}`,
      `test.describe('xfail-mechanism', () => {`,
      `  test('listed failing', async () => { expect(1).toBe(2) })`,
      `  test('control passing', async () => { expect(1).toBe(1) })`,
      `})`,
    ].join('\n')
    const md = '# mech.spec.ts > xfail-mechanism > listed failing\nknown flaky\n'

    const { exitCode, specs, output } = runPlaywright(spec, md)

    expect(exitCode).toBe(0)
    const listed = specs.find((s) => s.title === 'listed failing')
    const control = specs.find((s) => s.title === 'control passing')
    expect(listed).toMatchObject({ ok: true, expectedStatus: 'passed', lastStatus: 'skipped' })
    expect(control).toMatchObject({ ok: true, expectedStatus: 'passed', lastStatus: 'passed' })
    expect(output).not.toContain('listed test(s) passed')
  }, 120_000)

  it('does not affect a failing test that is not listed (control)', () => {
    const spec = [
      `import { test, expect } from ${JSON.stringify(fixturesModule)}`,
      `test('unlisted failing', async () => { expect(1).toBe(2) })`,
    ].join('\n')
    const md = '# mech.spec.ts > some other test\nunrelated\n'

    const { exitCode, specs, output } = runPlaywright(spec, md)

    expect(exitCode).not.toBe(0)
    expect(specs.find((s) => s.title === 'unlisted failing')).toMatchObject({ ok: false, lastStatus: 'failed' })
    expect(output).not.toContain('listed test(s) passed')
  }, 120_000)

  it('prints listed tests that passed and keeps the suite green', () => {
    const spec = [
      `import { test, expect } from ${JSON.stringify(fixturesModule)}`,
      `test.describe('xfail-mechanism', () => {`,
      `  test('listed passing', async () => { expect(1).toBe(1) })`,
      `})`,
    ].join('\n')
    const md = '# mech.spec.ts > xfail-mechanism > listed passing\nknown flaky\n'

    const { exitCode, specs, output } = runPlaywright(spec, md)

    expect(exitCode).toBe(0)
    expect(specs.find((s) => s.title === 'listed passing')).toMatchObject({
      ok: true,
      expectedStatus: 'passed',
      lastStatus: 'passed',
    })
    expect(output).toContain('xpass: 1 listed test(s) passed (remove from playwright.md):')
    expect(output).toContain('mech.spec.ts > xfail-mechanism > listed passing — known flaky')
  }, 120_000)

  it('still fails the suite when a listed pass is mixed with a real failure', () => {
    const spec = [
      `import { test, expect } from ${JSON.stringify(fixturesModule)}`,
      `test.describe('xfail-mechanism', () => {`,
      `  test('listed passing', async () => { expect(1).toBe(1) })`,
      `  test('unlisted failing', async () => { expect(1).toBe(2) })`,
      `})`,
    ].join('\n')
    const md = '# mech.spec.ts > xfail-mechanism > listed passing\nknown flaky\n'

    const { exitCode, output } = runPlaywright(spec, md)

    expect(exitCode).not.toBe(0)
    expect(output).toContain('xpass: 1 listed test(s) passed (remove from playwright.md):')
  }, 120_000)

  it('quarantines a listed failure even when retries are configured', () => {
    const spec = [
      `import { test, expect } from ${JSON.stringify(fixturesModule)}`,
      `test('listed failing', async () => { expect(1).toBe(2) })`,
    ].join('\n')
    const md = '# mech.spec.ts > listed failing\nknown flaky\n'

    const { exitCode, specs } = runPlaywright(spec, md, 'retries: 1, ')

    expect(exitCode).toBe(0)
    expect(specs.find((s) => s.title === 'listed failing')).toMatchObject({
      ok: true,
      lastStatus: 'skipped',
    })
  }, 120_000)
})
