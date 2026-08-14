import { describe, expect, it } from 'vitest'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { PNG } from 'pngjs'

import {
  DEFAULT_MAX_DIFF_PIXEL_RATIO,
  SNAPSHOT_DIR_REL,
  SOFT_KEEP_MIN_CHANNEL_DELTA,
  classifyPngDiff,
  countDifferingPixels,
  decodePng,
  filterNoisyBaselineDiffs,
  formatRatio,
  isUnchangedDialogBackdropDiff,
  largestBrightUnchangedCard,
  shouldKeepDiff,
  summarizeResults,
  type ClassifyResult,
  type DecodedPng,
} from './filter-noisy-baseline-diffs'

/** Encode RGBA pixels as a PNG via pngjs (same library the filter uses to decode). */
function encodeRgbaPng(width: number, height: number, rgba: Uint8Array): Uint8Array {
  const png = new PNG({ width, height, colorType: 6, inputHasAlpha: true, fill: true })
  png.data.set(rgba)
  return Uint8Array.from(PNG.sync.write(png, { colorType: 6, inputHasAlpha: true }))
}

function solidRgba(width: number, height: number, r: number, g: number, b: number, a = 255): Uint8Array {
  const data = new Uint8Array(width * height * 4)
  for (let i = 0; i < width * height; i++) {
    const o = i * 4
    data[o] = r
    data[o + 1] = g
    data[o + 2] = b
    data[o + 3] = a
  }
  return data
}

/** Dimmed backdrop + centered near-white dialog card (synthetic PatternFly overlay). */
function overlayFixture(
  width: number,
  height: number
): {
  rgba: Uint8Array
  card: { x: number; y: number; w: number; h: number }
} {
  const rgba = solidRgba(width, height, 40, 40, 40)
  const card = {
    x: Math.floor(width * 0.25),
    y: Math.floor(height * 0.2),
    w: Math.floor(width * 0.5),
    h: Math.floor(height * 0.55),
  }
  for (let y = card.y; y < card.y + card.h; y++) {
    for (let x = card.x; x < card.x + card.w; x++) {
      const o = (y * width + x) * 4
      rgba[o] = 250
      rgba[o + 1] = 250
      rgba[o + 2] = 250
    }
  }
  return { rgba, card }
}

describe('decodePng / countDifferingPixels', () => {
  it('round-trips a solid RGBA PNG', () => {
    const rgba = solidRgba(2, 2, 10, 20, 30)
    const png = encodeRgbaPng(2, 2, rgba)
    const decoded = decodePng(png)
    expect(decoded.width).toBe(2)
    expect(decoded.height).toBe(2)
    expect([...decoded.data]).toEqual([...rgba])
  })

  it('reports zero ratio for identical images', () => {
    const rgba = solidRgba(4, 4, 1, 2, 3)
    const a: DecodedPng = { width: 4, height: 4, data: rgba }
    const b: DecodedPng = { width: 4, height: 4, data: rgba.slice() }
    expect(countDifferingPixels(a, b)).toEqual({
      changedPixels: 0,
      totalPixels: 16,
      ratio: 0,
      maxChannelDelta: 0,
    })
  })

  it('counts changed pixels, ratio, and max channel delta', () => {
    const aData = solidRgba(10, 10, 0, 0, 0)
    const bData = aData.slice()
    bData[0] = 1
    bData[4] = 40
    bData[8] = 255
    const diff = countDifferingPixels({ width: 10, height: 10, data: aData }, { width: 10, height: 10, data: bData })
    expect(diff).toEqual({ changedPixels: 3, totalPixels: 100, ratio: 0.03, maxChannelDelta: 255 })
  })

  it('counts RGB-only diffs even when both pixels are fully transparent', () => {
    const aData = solidRgba(10, 10, 0, 0, 0, 0)
    const bData = aData.slice()
    bData[0] = 255
    const diff = countDifferingPixels({ width: 10, height: 10, data: aData }, { width: 10, height: 10, data: bData })
    expect(diff).toEqual({ changedPixels: 1, totalPixels: 100, ratio: 0.01, maxChannelDelta: 255 })
  })

  it('returns null when dimensions differ', () => {
    expect(
      countDifferingPixels(
        { width: 1, height: 1, data: solidRgba(1, 1, 0, 0, 0) },
        { width: 2, height: 1, data: solidRgba(2, 1, 0, 0, 0) }
      )
    ).toBeNull()
  })
})

describe('shouldKeepDiff', () => {
  it('keeps when ratio is at Playwright threshold', () => {
    expect(shouldKeepDiff(0.005, 1)).toBe(true)
  })

  it('restores AA noise (tiny ratio, tiny delta)', () => {
    expect(shouldKeepDiff(0.0004, 1)).toBe(false)
  })

  it('soft-keeps high-contrast sub-threshold text churn', () => {
    expect(shouldKeepDiff(0.002, SOFT_KEEP_MIN_CHANNEL_DELTA)).toBe(true)
    expect(shouldKeepDiff(0.002, SOFT_KEEP_MIN_CHANNEL_DELTA - 1)).toBe(false)
  })
})

describe('isUnchangedDialogBackdropDiff', () => {
  it('returns no card when image sizes differ', () => {
    expect(
      largestBrightUnchangedCard(
        { width: 1, height: 1, data: solidRgba(1, 1, 250, 250, 250) },
        { width: 2, height: 1, data: solidRgba(2, 1, 250, 250, 250) }
      )
    ).toBeNull()
  })

  it('detects an unchanged centered card with backdrop-only edits', () => {
    const w = 40
    const h = 30
    const { rgba: oldRgba } = overlayFixture(w, h)
    const newRgba = oldRgba.slice()
    newRgba[4] = 200
    expect(
      isUnchangedDialogBackdropDiff({ width: w, height: h, data: oldRgba }, { width: w, height: h, data: newRgba })
    ).toBe(true)
  })

  it('does not treat a full-page light layout as a dialog card', () => {
    const w = 40
    const h = 30
    const oldRgba = solidRgba(w, h, 250, 250, 250)
    const newRgba = oldRgba.slice()
    newRgba[0] = 0
    expect(
      isUnchangedDialogBackdropDiff({ width: w, height: h, data: oldRgba }, { width: w, height: h, data: newRgba })
    ).toBe(false)
  })
})

describe('classifyPngDiff', () => {
  it('keeps new (untracked) files', () => {
    const png = encodeRgbaPng(1, 1, solidRgba(1, 1, 255, 0, 0))
    const result = classifyPngDiff('snapshots/new.png', null, png)
    expect(result.action).toBe('new')
  })

  it('restores AA noise (1px, delta 1)', () => {
    const w = 20
    const h = 50
    const oldRgba = solidRgba(w, h, 100, 100, 100)
    const newRgba = oldRgba.slice()
    newRgba[0] = 101 // maxΔ=1, ratio=0.001
    const result = classifyPngDiff(
      'snapshots/noise.png',
      encodeRgbaPng(w, h, oldRgba),
      encodeRgbaPng(w, h, newRgba),
      DEFAULT_MAX_DIFF_PIXEL_RATIO
    )
    expect(result.action).toBe('restore')
    expect(result.maxChannelDelta).toBe(1)
  })

  it('soft-keeps high-contrast change under 0.5% ratio', () => {
    const w = 20
    const h = 50
    const oldRgba = solidRgba(w, h, 0, 0, 0)
    const newRgba = oldRgba.slice()
    newRgba[0] = 255 // ratio=0.001, maxΔ=255
    const result = classifyPngDiff(
      'snapshots/uuid.png',
      encodeRgbaPng(w, h, oldRgba),
      encodeRgbaPng(w, h, newRgba),
      DEFAULT_MAX_DIFF_PIXEL_RATIO
    )
    expect(result.action).toBe('keep')
    expect(result.reason).toMatch(/soft-keep/)
  })

  it('keeps when changed_pixel_ratio is at or above threshold', () => {
    const w = 20
    const h = 50
    const oldRgba = solidRgba(w, h, 0, 0, 0)
    const newRgba = oldRgba.slice()
    for (let i = 0; i < 6; i++) {
      newRgba[i * 4] = 255
    }
    const result = classifyPngDiff(
      'snapshots/real.png',
      encodeRgbaPng(w, h, oldRgba),
      encodeRgbaPng(w, h, newRgba),
      DEFAULT_MAX_DIFF_PIXEL_RATIO
    )
    expect(result.action).toBe('keep')
    expect(result.changedPixelRatio).toBeCloseTo(0.006)
  })

  it('keeps dimension mismatches as meaningful', () => {
    const result = classifyPngDiff(
      'snapshots/resized.png',
      encodeRgbaPng(1, 1, solidRgba(1, 1, 0, 0, 0)),
      encodeRgbaPng(2, 2, solidRgba(2, 2, 0, 0, 0))
    )
    expect(result.action).toBe('keep')
    expect(result.reason).toMatch(/dimensions changed/)
  })

  it('restores keep-sized diffs that only hit a dimmed dialog backdrop', () => {
    const w = 40
    const h = 30
    const { rgba: oldRgba, card } = overlayFixture(w, h)
    const newRgba = oldRgba.slice()
    for (let y = 1; y <= 8; y++) {
      const o = (y * w + 1) * 4
      newRgba[o] = 255
      newRgba[o + 1] = 255
      newRgba[o + 2] = 255
    }
    expect(card.x).toBeGreaterThan(1)
    const result = classifyPngDiff(
      'snapshots/credentials-edit-modal.png',
      encodeRgbaPng(w, h, oldRgba),
      encodeRgbaPng(w, h, newRgba)
    )
    expect(result.action).toBe('restore')
    expect(result.reason).toMatch(/dialog backdrop only/)
  })

  it('keeps diffs on the dialog card itself', () => {
    const w = 40
    const h = 30
    const { rgba: oldRgba, card } = overlayFixture(w, h)
    const newRgba = oldRgba.slice()
    for (let i = 0; i < 8; i++) {
      const o = ((card.y + 2) * w + (card.x + 2 + i)) * 4
      newRgba[o] = 0
      newRgba[o + 1] = 0
      newRgba[o + 2] = 0
    }
    const result = classifyPngDiff(
      'snapshots/credentials-edit-modal.png',
      encodeRgbaPng(w, h, oldRgba),
      encodeRgbaPng(w, h, newRgba)
    )
    expect(result.action).toBe('keep')
  })
})

describe('summarizeResults / formatRatio', () => {
  it('buckets by action', () => {
    const results: ClassifyResult[] = [
      {
        path: 'a',
        action: 'keep',
        changedPixelRatio: 0.01,
        changedPixels: 1,
        totalPixels: 100,
        maxChannelDelta: 10,
        reason: 'x',
      },
      {
        path: 'b',
        action: 'restore',
        changedPixelRatio: 0.0001,
        changedPixels: 1,
        totalPixels: 10000,
        maxChannelDelta: 1,
        reason: 'y',
      },
      {
        path: 'c',
        action: 'new',
        changedPixelRatio: null,
        changedPixels: null,
        totalPixels: null,
        maxChannelDelta: null,
        reason: 'z',
      },
    ]
    const summary = summarizeResults(results)
    expect(summary.kept).toHaveLength(1)
    expect(summary.restored).toHaveLength(1)
    expect(summary.newFiles).toHaveLength(1)
  })

  it('formats small ratios', () => {
    expect(formatRatio(0)).toBe('0%')
    expect(formatRatio(0.005)).toBe('0.500%')
    expect(formatRatio(0.00005)).toBe('0.0050%')
    expect(formatRatio(0.0000001)).toBe('1.00e-5%')
  })
})

describe('filterNoisyBaselineDiffs', () => {
  it('restores AA noise on disk and keeps high-contrast diffs', () => {
    const repoRoot = mkdtempSync(join(tmpdir(), 'vr-filter-'))
    const git = (args: string[]) => execFileSync('git', args, { cwd: repoRoot, encoding: 'utf8' })

    try {
      git(['init'])
      git(['config', 'user.email', 'test@example.com'])
      git(['config', 'user.name', 'Test'])
      git(['config', 'commit.gpgsign', 'false'])

      const snapshotRepoRel = `frontend/packages/syntara-ui/${SNAPSHOT_DIR_REL}`
      const snapshotDirAbs = join(repoRoot, snapshotRepoRel)
      mkdirSync(snapshotDirAbs, { recursive: true })

      const w = 20
      const h = 50
      const oldRgba = solidRgba(w, h, 100, 100, 100)
      const noiseRgba = oldRgba.slice()
      noiseRgba[0] = 101
      const keepRgba = oldRgba.slice()
      keepRgba[0] = 255

      const noisePath = join(snapshotDirAbs, 'noise-linux.png')
      const keepPath = join(snapshotDirAbs, 'keep-linux.png')
      const oldPng = encodeRgbaPng(w, h, oldRgba)
      writeFileSync(noisePath, oldPng)
      writeFileSync(keepPath, oldPng)
      git(['add', '.'])
      git(['commit', '-m', 'baselines'])

      writeFileSync(noisePath, encodeRgbaPng(w, h, noiseRgba))
      writeFileSync(keepPath, encodeRgbaPng(w, h, keepRgba))

      const summary = filterNoisyBaselineDiffs({
        repoRoot,
        snapshotDirAbs,
        snapshotRepoRel,
        baseRef: 'HEAD',
        maxDiffPixelRatio: DEFAULT_MAX_DIFF_PIXEL_RATIO,
        dryRun: false,
      })

      expect(summary.restored).toHaveLength(1)
      expect(summary.kept).toHaveLength(1)
      expect(summary.restored[0]?.path).toBe(`${snapshotRepoRel}/noise-linux.png`)
      expect(summary.kept[0]?.path).toBe(`${snapshotRepoRel}/keep-linux.png`)
      expect([...decodePng(readFileSync(noisePath)).data]).toEqual([...oldRgba])
      expect([...decodePng(readFileSync(keepPath)).data]).toEqual([...keepRgba])
    } finally {
      rmSync(repoRoot, { recursive: true, force: true })
    }
  })
})
