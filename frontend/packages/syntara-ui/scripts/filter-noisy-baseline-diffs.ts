/**
 * Filter noisy visual-regression baseline PNG diffs.
 *
 * After `--update-snapshots=all`, git byte-diffs pick up 1-pixel AA noise.
 * This script restores baselines that fail the hybrid "meaningful change" rule
 * (validated on PR #213), keeping only real UI/content diffs (or new files).
 *
 * KEEP when:
 *   ratio >= 0.005  (Playwright maxDiffPixelRatio)
 *   OR (ratio >= 0.001 AND max_channel_delta >= 30)  // small but high-contrast
 * then RESTORE if the only diffs are in a dimmed modal backdrop (the dialog
 * card itself is unchanged — otherwise list-page edits fan out into every
 * overlay screenshot on that page).
 * else RESTORE (AA noise).
 *
 * Decode with pngjs; classify with exact RGBA diffs (ratio + max channel delta).
 * The hybrid rule was validated on exact equality, not YIQ / anti-alias ignore.
 *
 * Usage:
 *   npm exec tsx -- scripts/filter-noisy-baseline-diffs.ts
 *   npm exec tsx -- scripts/filter-noisy-baseline-diffs.ts --dry-run
 *   npm exec tsx -- scripts/filter-noisy-baseline-diffs.ts --base-ref HEAD
 *   npm exec tsx -- scripts/filter-noisy-baseline-diffs.ts \
 *     --compare-refs origin/devel origin/visual-regression/weekly-refresh
 *
 * Exit codes:
 *   0 — success
 *   1 — usage / comparison error
 */

import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { PNG } from 'pngjs'

/** Matches `SCREENSHOT_OPTIONS.maxDiffPixelRatio` in page-screenshots.spec.ts */
export const DEFAULT_MAX_DIFF_PIXEL_RATIO = 0.005

/**
 * Soft band: below Playwright's ratio but high-contrast enough to keep
 * (webhook UUID text, small chrome) — AA noise on PR #213 had max_delta <= 7.
 */
export const SOFT_KEEP_MIN_RATIO = 0.001
export const SOFT_KEEP_MIN_CHANNEL_DELTA = 30

/**
 * PatternFly dialog cards are near-white; the backdrop is dimmed (~60%).
 * Flood-fill uses this luma floor so the card is isolated from the overlay.
 */
export const OVERLAY_CARD_LUMA_MIN = 230
/** Dialog cards occupy a slice of the viewport, not the full page or the sidebar. */
export const OVERLAY_CARD_MIN_AREA_RATIO = 0.06
export const OVERLAY_CARD_MAX_AREA_RATIO = 0.65
export const OVERLAY_CARD_MAX_WIDTH_RATIO = 0.82
export const OVERLAY_CARD_MAX_HEIGHT_RATIO = 0.97
export const OVERLAY_CARD_MIN_LEFT_RATIO = 0.08
/** Border AA on a tall modal; real form copy changes are far above this. */
export const OVERLAY_CARD_MAX_INTERIOR_CHANGE_RATIO = 0.002

export const SNAPSHOT_DIR_REL = 'e2e/visual-regression/page-screenshots.spec.ts-snapshots'

export type ClassifyAction = 'keep' | 'restore' | 'new'

export type ClassifyResult = {
  path: string
  action: ClassifyAction
  /** Differing pixels / total pixels; null for new files or size mismatches kept as real. */
  changedPixelRatio: number | null
  changedPixels: number | null
  totalPixels: number | null
  maxChannelDelta: number | null
  reason: string
}

export type FilterSummary = {
  kept: ClassifyResult[]
  restored: ClassifyResult[]
  newFiles: ClassifyResult[]
}

export type DecodedPng = {
  width: number
  height: number
  /** RGBA, row-major, 4 bytes per pixel */
  data: Uint8Array
}

/** Decode a PNG buffer into RGBA pixel data via pngjs. */
export function decodePng(png: Uint8Array | Buffer): DecodedPng {
  const img = PNG.sync.read(Buffer.from(png))
  return {
    width: img.width,
    height: img.height,
    // Copy so callers own a plain Uint8Array (pngjs returns a Buffer view).
    data: Uint8Array.from(img.data),
  }
}

/**
 * Count differing pixels and max channel delta via exact RGBA equality.
 * Returns null when dimensions differ (treated as a meaningful keep).
 *
 * Ratio and soft-keep both come from this scan so classification cannot drift
 * from the PR #213 hybrid rule (YIQ/AA libraries disagree on transparent pixels).
 */
export function countDifferingPixels(
  oldPng: DecodedPng,
  newPng: DecodedPng
): { changedPixels: number; totalPixels: number; ratio: number; maxChannelDelta: number } | null {
  if (oldPng.width !== newPng.width || oldPng.height !== newPng.height) {
    return null
  }

  const totalPixels = oldPng.width * oldPng.height
  const a = oldPng.data
  const b = newPng.data

  let changedPixels = 0
  let maxChannelDelta = 0
  for (let i = 0; i < totalPixels; i++) {
    const o = i * 4
    const d0 = Math.abs(a[o]! - b[o]!)
    const d1 = Math.abs(a[o + 1]! - b[o + 1]!)
    const d2 = Math.abs(a[o + 2]! - b[o + 2]!)
    const d3 = Math.abs(a[o + 3]! - b[o + 3]!)
    if (d0 || d1 || d2 || d3) {
      changedPixels++
      const localMax = Math.max(d0, d1, d2, d3)
      if (localMax > maxChannelDelta) maxChannelDelta = localMax
    }
  }

  return {
    changedPixels,
    totalPixels,
    ratio: totalPixels === 0 ? 0 : changedPixels / totalPixels,
    maxChannelDelta,
  }
}

/** Hybrid keep rule validated on PR #213 (0 false negatives on real UI; 0 AA false positives). */
export function shouldKeepDiff(
  ratio: number,
  maxChannelDelta: number,
  maxDiffPixelRatio: number = DEFAULT_MAX_DIFF_PIXEL_RATIO
): boolean {
  if (ratio >= maxDiffPixelRatio) return true
  if (ratio >= SOFT_KEEP_MIN_RATIO && maxChannelDelta >= SOFT_KEEP_MIN_CHANNEL_DELTA) return true
  return false
}

function pixelLuma(data: Uint8Array, offset: number): number {
  return (data[offset]! * 299 + data[offset + 1]! * 587 + data[offset + 2]! * 114) / 1000
}

export type OverlayCard = {
  pixelCount: number
  x0: number
  y0: number
  x1: number
  y1: number
}

/**
 * Largest 4-connected region of pixels that are identical in both images and
 * bright enough to be a PatternFly dialog card (not the dimmed backdrop).
 */
export function largestBrightUnchangedCard(oldPng: DecodedPng, newPng: DecodedPng): OverlayCard | null {
  if (oldPng.width !== newPng.width || oldPng.height !== newPng.height) return null

  const { width, height } = oldPng
  const n = width * height
  const a = oldPng.data
  const b = newPng.data
  const visited = new Uint8Array(n)
  let best: OverlayCard | null = null

  const isSeed = (i: number): boolean => {
    const o = i * 4
    return (
      a[o] === b[o] &&
      a[o + 1] === b[o + 1] &&
      a[o + 2] === b[o + 2] &&
      a[o + 3] === b[o + 3] &&
      pixelLuma(b, o) >= OVERLAY_CARD_LUMA_MIN
    )
  }

  for (let start = 0; start < n; start++) {
    if (visited[start] || !isSeed(start)) continue

    const stack = [start]
    visited[start] = 1
    let count = 0
    let x0 = width
    let y0 = height
    let x1 = 0
    let y1 = 0

    while (stack.length > 0) {
      const i = stack.pop()!
      count++
      const x = i % width
      const y = (i / width) | 0
      if (x < x0) x0 = x
      if (y < y0) y0 = y
      if (x > x1) x1 = x
      if (y > y1) y1 = y

      const neighbors = [
        x > 0 ? i - 1 : -1,
        x + 1 < width ? i + 1 : -1,
        y > 0 ? i - width : -1,
        y + 1 < height ? i + width : -1,
      ]
      for (const nb of neighbors) {
        if (nb < 0 || visited[nb] || !isSeed(nb)) continue
        visited[nb] = 1
        stack.push(nb)
      }
    }

    if (!best || count > best.pixelCount) {
      best = { pixelCount: count, x0, y0, x1, y1 }
    }
  }

  return best
}

function isDialogCardShape(card: OverlayCard, width: number, height: number): boolean {
  const boxW = card.x1 - card.x0 + 1
  const boxH = card.y1 - card.y0 + 1
  const areaRatio = card.pixelCount / (width * height)
  if (areaRatio < OVERLAY_CARD_MIN_AREA_RATIO || areaRatio > OVERLAY_CARD_MAX_AREA_RATIO) return false
  if (boxW / width > OVERLAY_CARD_MAX_WIDTH_RATIO) return false
  if (boxH / height > OVERLAY_CARD_MAX_HEIGHT_RATIO) return false
  if (card.x0 / width < OVERLAY_CARD_MIN_LEFT_RATIO) return false
  const cx = (card.x0 + card.x1) / 2
  if (Math.abs(cx - width / 2) > width * 0.3) return false
  return true
}

/**
 * True when a keep-sized diff is only in the dimmed page behind an unchanged
 * dialog card (list/table edits showing through create/edit/delete overlays).
 */
export function isUnchangedDialogBackdropDiff(oldPng: DecodedPng, newPng: DecodedPng): boolean {
  const card = largestBrightUnchangedCard(oldPng, newPng)
  if (!card || !isDialogCardShape(card, oldPng.width, oldPng.height)) return false

  const { width, height } = oldPng
  const a = oldPng.data
  const b = newPng.data
  const n = width * height
  let changedOnCard = 0
  let changedBackdrop = 0

  for (let i = 0; i < n; i++) {
    const o = i * 4
    if (a[o] === b[o] && a[o + 1] === b[o + 1] && a[o + 2] === b[o + 2] && a[o + 3] === b[o + 3]) {
      continue
    }
    const x = i % width
    const y = (i / width) | 0
    const onCard = x >= card.x0 && x <= card.x1 && y >= card.y0 && y <= card.y1
    if (onCard) changedOnCard++
    else changedBackdrop++
  }

  return changedOnCard / card.pixelCount <= OVERLAY_CARD_MAX_INTERIOR_CHANGE_RATIO && changedBackdrop > 0
}

export function classifyPngDiff(
  relativePath: string,
  oldBytes: Uint8Array | null,
  newBytes: Uint8Array,
  maxDiffPixelRatio: number = DEFAULT_MAX_DIFF_PIXEL_RATIO
): ClassifyResult {
  if (oldBytes === null) {
    return {
      path: relativePath,
      action: 'new',
      changedPixelRatio: null,
      changedPixels: null,
      totalPixels: null,
      maxChannelDelta: null,
      reason: 'untracked / not in base ref',
    }
  }

  const oldPng = decodePng(oldBytes)
  const newPng = decodePng(newBytes)
  const diff = countDifferingPixels(oldPng, newPng)

  if (diff === null) {
    return {
      path: relativePath,
      action: 'keep',
      changedPixelRatio: null,
      changedPixels: null,
      totalPixels: null,
      maxChannelDelta: null,
      reason: `dimensions changed (${oldPng.width}x${oldPng.height} → ${newPng.width}x${newPng.height})`,
    }
  }

  if (!shouldKeepDiff(diff.ratio, diff.maxChannelDelta, maxDiffPixelRatio)) {
    return {
      path: relativePath,
      action: 'restore',
      changedPixelRatio: diff.ratio,
      changedPixels: diff.changedPixels,
      totalPixels: diff.totalPixels,
      maxChannelDelta: diff.maxChannelDelta,
      reason: `noise (ratio=${formatRatio(diff.ratio)}, maxΔ=${diff.maxChannelDelta})`,
    }
  }

  if (isUnchangedDialogBackdropDiff(oldPng, newPng)) {
    return {
      path: relativePath,
      action: 'restore',
      changedPixelRatio: diff.ratio,
      changedPixels: diff.changedPixels,
      totalPixels: diff.totalPixels,
      maxChannelDelta: diff.maxChannelDelta,
      reason: `dialog backdrop only (ratio=${formatRatio(diff.ratio)}, maxΔ=${diff.maxChannelDelta})`,
    }
  }

  const viaSoft =
    diff.ratio < maxDiffPixelRatio &&
    diff.ratio >= SOFT_KEEP_MIN_RATIO &&
    diff.maxChannelDelta >= SOFT_KEEP_MIN_CHANNEL_DELTA

  return {
    path: relativePath,
    action: 'keep',
    changedPixelRatio: diff.ratio,
    changedPixels: diff.changedPixels,
    totalPixels: diff.totalPixels,
    maxChannelDelta: diff.maxChannelDelta,
    reason: viaSoft
      ? `soft-keep (ratio=${formatRatio(diff.ratio)}, maxΔ=${diff.maxChannelDelta})`
      : `meaningful (ratio=${formatRatio(diff.ratio)} >= ${formatRatio(maxDiffPixelRatio)})`,
  }
}

export function formatRatio(ratio: number): string {
  if (ratio === 0) return '0%'
  const pct = ratio * 100
  if (pct < 0.0001) return `${pct.toExponential(2)}%`
  if (pct < 0.01) return `${pct.toFixed(4)}%`
  return `${pct.toFixed(3)}%`
}

export function summarizeResults(results: ClassifyResult[]): FilterSummary {
  return {
    kept: results.filter((r) => r.action === 'keep'),
    restored: results.filter((r) => r.action === 'restore'),
    newFiles: results.filter((r) => r.action === 'new'),
  }
}

// ---------------------------------------------------------------------------
// Git helpers
// ---------------------------------------------------------------------------

function git(args: string[], cwd: string, encoding: 'buffer'): Buffer
function git(args: string[], cwd: string, encoding?: 'utf8'): string
function git(args: string[], cwd: string, encoding: 'utf8' | 'buffer' = 'utf8'): string | Buffer {
  if (encoding === 'buffer') {
    return execFileSync('git', args, { cwd, encoding: 'buffer', maxBuffer: 50 * 1024 * 1024 })
  }
  return execFileSync('git', args, { cwd, encoding: 'utf8', maxBuffer: 50 * 1024 * 1024 }).trimEnd()
}

function gitShowBlob(cwd: string, ref: string, repoRelativePath: string): Uint8Array | null {
  try {
    const buf = git(['show', `${ref}:${repoRelativePath}`], cwd, 'buffer')
    return new Uint8Array(buf)
  } catch {
    return null
  }
}

function listDiffPngsBetweenRefs(cwd: string, oldRef: string, newRef: string, snapshotRepoRel: string): string[] {
  const out = git(['diff', '--name-only', '--diff-filter=AM', `${oldRef}...${newRef}`, '--', snapshotRepoRel], cwd)
  if (!out) return []
  return out.split('\n').filter((p) => p.endsWith('.png'))
}

function listWorkingTreeDiffPngs(
  cwd: string,
  baseRef: string,
  snapshotRepoRel: string
): {
  modified: string[]
  untracked: string[]
} {
  const modifiedOut = git(['diff', '--name-only', '--diff-filter=AM', baseRef, '--', snapshotRepoRel], cwd)
  const modified = modifiedOut ? modifiedOut.split('\n').filter((p) => p.endsWith('.png')) : []

  const untrackedOut = git(['ls-files', '--others', '--exclude-standard', '--', snapshotRepoRel], cwd)
  const untracked = untrackedOut ? untrackedOut.split('\n').filter((p) => p.endsWith('.png')) : []

  return { modified, untracked }
}

function findGitRoot(start: string): string {
  return git(['rev-parse', '--show-toplevel'], start)
}

// ---------------------------------------------------------------------------
// Core filter
// ---------------------------------------------------------------------------

export type FilterOptions = {
  /** Repo root (git toplevel). */
  repoRoot: string
  /** Absolute path to the snapshots directory inside syntara-ui. */
  snapshotDirAbs: string
  /** Repo-relative path to snapshots (for git). */
  snapshotRepoRel: string
  /** Git ref for "old" baseline content. Default HEAD. */
  baseRef: string
  /**
   * When set, read "new" PNG bytes from this git ref instead of the working tree.
   * Implies dry-run classification only (no restores).
   */
  compareToRef?: string
  maxDiffPixelRatio: number
  dryRun: boolean
}

export function filterNoisyBaselineDiffs(options: FilterOptions): FilterSummary {
  const { repoRoot, snapshotDirAbs, snapshotRepoRel, baseRef, compareToRef, maxDiffPixelRatio, dryRun } = options

  const results: ClassifyResult[] = []

  if (compareToRef) {
    const paths = listDiffPngsBetweenRefs(repoRoot, baseRef, compareToRef, snapshotRepoRel)
    for (const repoRel of paths) {
      const oldBytes = gitShowBlob(repoRoot, baseRef, repoRel)
      const newBytes = gitShowBlob(repoRoot, compareToRef, repoRel)
      if (!newBytes) {
        throw new Error(`Missing blob for ${compareToRef}:${repoRel}`)
      }
      results.push(classifyPngDiff(repoRel, oldBytes, newBytes, maxDiffPixelRatio))
    }
  } else {
    const { modified, untracked } = listWorkingTreeDiffPngs(repoRoot, baseRef, snapshotRepoRel)

    for (const repoRel of modified) {
      const abs = resolve(repoRoot, repoRel)
      if (!existsSync(abs)) continue
      const oldBytes = gitShowBlob(repoRoot, baseRef, repoRel)
      const newBytes = new Uint8Array(readFileSync(abs))
      const result = classifyPngDiff(repoRel, oldBytes, newBytes, maxDiffPixelRatio)
      results.push(result)

      if (result.action === 'restore' && !dryRun && oldBytes) {
        mkdirSync(dirname(abs), { recursive: true })
        writeFileSync(abs, oldBytes)
      }
    }

    for (const repoRel of untracked) {
      const abs = resolve(repoRoot, repoRel)
      if (!existsSync(abs)) continue
      const newBytes = new Uint8Array(readFileSync(abs))
      results.push(classifyPngDiff(repoRel, null, newBytes, maxDiffPixelRatio))
    }

    // Touch snapshotDirAbs so unused-path lint stays quiet if tree is empty
    void snapshotDirAbs
  }

  return summarizeResults(results)
}

export function printSummary(summary: FilterSummary, dryRun: boolean): void {
  const mode = dryRun ? 'DRY-RUN' : 'APPLY'
  console.log(`\nFilter noisy baseline diffs [${mode}]`)
  console.log(`  kept:     ${summary.kept.length}`)
  console.log(`  restored: ${summary.restored.length}`)
  console.log(`  new:      ${summary.newFiles.length}`)

  const printGroup = (label: string, items: ClassifyResult[]) => {
    if (items.length === 0) return
    console.log(`\n--- ${label} ---`)
    for (const item of items.sort((a, b) => a.path.localeCompare(b.path))) {
      const ratio =
        item.changedPixelRatio === null
          ? ''
          : ` ratio=${formatRatio(item.changedPixelRatio)} (${item.changedPixels}/${item.totalPixels}) maxΔ=${item.maxChannelDelta}`
      console.log(`  ${item.action.toUpperCase().padEnd(7)} ${item.path}${ratio}`)
      console.log(`          ${item.reason}`)
    }
  }

  printGroup('KEPT (meaningful)', summary.kept)
  printGroup('RESTORED', summary.restored)
  printGroup('NEW', summary.newFiles)
  console.log('')
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function parseArgs(argv: string[]): {
  dryRun: boolean
  baseRef: string
  compareToRef?: string
  maxDiffPixelRatio: number
  help: boolean
} {
  let dryRun = false
  let baseRef = 'HEAD'
  let compareToRef: string | undefined
  let maxDiffPixelRatio = DEFAULT_MAX_DIFF_PIXEL_RATIO
  let help = false

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i]!
    if (arg === '--dry-run') {
      dryRun = true
    } else if (arg === '--help' || arg === '-h') {
      help = true
    } else if (arg === '--base-ref') {
      baseRef = argv[++i] ?? 'HEAD'
    } else if (arg === '--threshold') {
      maxDiffPixelRatio = Number(argv[++i])
      if (!Number.isFinite(maxDiffPixelRatio) || maxDiffPixelRatio < 0) {
        throw new Error(`Invalid --threshold: ${argv[i]}`)
      }
    } else if (arg === '--compare-refs') {
      baseRef = argv[++i] ?? ''
      compareToRef = argv[++i]
      if (!baseRef || !compareToRef) {
        throw new Error('--compare-refs requires <old-ref> <new-ref>')
      }
      dryRun = true
    } else {
      throw new Error(`Unknown argument: ${arg}`)
    }
  }

  return { dryRun, baseRef, compareToRef, maxDiffPixelRatio, help }
}

function printHelp(): void {
  console.log(`Usage: filter-noisy-baseline-diffs.ts [options]

Options:
  --dry-run                         Report classifications without restoring files
  --base-ref <ref>                  Old baseline ref (default: HEAD)
  --compare-refs <old> <new>        Classify PNG diffs between two refs (implies --dry-run)
  --threshold <ratio>               maxDiffPixelRatio cutoff (default: ${DEFAULT_MAX_DIFF_PIXEL_RATIO})
  -h, --help                        Show this help
`)
}

function isMain(): boolean {
  const entry = process.argv[1]
  if (!entry) return false
  return resolve(entry) === fileURLToPath(import.meta.url)
}

if (isMain()) {
  try {
    const args = parseArgs(process.argv.slice(2))
    if (args.help) {
      printHelp()
      process.exit(0)
    }

    const __dirname = dirname(fileURLToPath(import.meta.url))
    const pkgRoot = resolve(__dirname, '..')
    const snapshotDirAbs = resolve(pkgRoot, SNAPSHOT_DIR_REL)
    const repoRoot = findGitRoot(pkgRoot)
    const snapshotRepoRel = relative(repoRoot, snapshotDirAbs).replaceAll('\\', '/')

    const summary = filterNoisyBaselineDiffs({
      repoRoot,
      snapshotDirAbs,
      snapshotRepoRel,
      baseRef: args.baseRef,
      compareToRef: args.compareToRef,
      maxDiffPixelRatio: args.maxDiffPixelRatio,
      dryRun: args.dryRun,
    })

    printSummary(summary, args.dryRun)
    process.exit(0)
  } catch (err) {
    console.error(err instanceof Error ? err.message : err)
    process.exit(1)
  }
}
