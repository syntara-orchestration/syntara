import { describe, expect, it } from 'vitest'
import { deflateSync } from 'node:zlib'

import {
  DEFAULT_MAX_DIFF_PIXEL_RATIO,
  SOFT_KEEP_MIN_CHANNEL_DELTA,
  classifyPngDiff,
  countDifferingPixels,
  decodePng,
  formatRatio,
  shouldKeepDiff,
  summarizeResults,
  type ClassifyResult,
  type DecodedPng,
} from './filter-noisy-baseline-diffs'

/** Minimal CRC32 + PNG encoder for synthetic test fixtures (RGBA only). */
function crc32(buf: Uint8Array): number {
  let c = 0xffffffff
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i]!
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? (0xedb88320 ^ (c >>> 1)) : c >>> 1
    }
  }
  return (c ^ 0xffffffff) >>> 0
}

function chunk(type: string, data: Uint8Array): Uint8Array {
  const typeBytes = Uint8Array.from(type, (ch) => ch.charCodeAt(0))
  const len = new Uint8Array(4)
  new DataView(len.buffer).setUint32(0, data.length)
  const crcInput = new Uint8Array(typeBytes.length + data.length)
  crcInput.set(typeBytes)
  crcInput.set(data, typeBytes.length)
  const crc = new Uint8Array(4)
  new DataView(crc.buffer).setUint32(0, crc32(crcInput))
  const out = new Uint8Array(4 + 4 + data.length + 4)
  out.set(len, 0)
  out.set(typeBytes, 4)
  out.set(data, 8)
  out.set(crc, 8 + data.length)
  return out
}

/** Encode an RGBA buffer (width*height*4) as a PNG. */
function encodeRgbaPng(width: number, height: number, rgba: Uint8Array): Uint8Array {
  const stride = width * 4
  const raw = new Uint8Array((stride + 1) * height)
  for (let y = 0; y < height; y++) {
    raw[y * (stride + 1)] = 0 // filter None
    raw.set(rgba.subarray(y * stride, (y + 1) * stride), y * (stride + 1) + 1)
  }

  const ihdr = new Uint8Array(13)
  const dv = new DataView(ihdr.buffer)
  dv.setUint32(0, width)
  dv.setUint32(4, height)
  ihdr[8] = 8 // bit depth
  ihdr[9] = 6 // RGBA
  ihdr[10] = 0
  ihdr[11] = 0
  ihdr[12] = 0

  const signature = Uint8Array.of(137, 80, 78, 71, 13, 10, 26, 10)
  const parts = [signature, chunk('IHDR', ihdr), chunk('IDAT', deflateSync(raw)), chunk('IEND', new Uint8Array())]
  const total = parts.reduce((n, p) => n + p.length, 0)
  const out = new Uint8Array(total)
  let offset = 0
  for (const p of parts) {
    out.set(p, offset)
    offset += p.length
  }
  return out
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
    const diff = countDifferingPixels(
      { width: 10, height: 10, data: aData },
      { width: 10, height: 10, data: bData }
    )
    expect(diff).toEqual({ changedPixels: 3, totalPixels: 100, ratio: 0.03, maxChannelDelta: 255 })
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
  })
})
