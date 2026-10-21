/**
 * Pre-computed deterministic timestamps for mock data.
 *
 * All dates are relative to a fixed "now" of 2026-06-15T10:00:00.000Z so that
 * mock API responses are stable across CI runs and visual-regression baselines.
 *
 * Naming convention:
 *   - `now`            -- the reference instant
 *   - `minutesAgoN`    -- N minutes before now
 *   - `hoursAgoN`      -- N hours before now
 *   - `daysAgoN`       -- N days before now
 *   - `hoursFromNowN`  -- N hours after now
 *   - Suffixes like `Plus1s`, `Plus2500ms` add small offsets for started_at / completed_at
 */

const NOW = new Date('2026-06-15T10:00:00.000Z').getTime()

const MINUTE = 60 * 1000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

function iso(offsetMs: number): string {
  return new Date(NOW + offsetMs).toISOString()
}

export const mockDate = {
  // -- reference --
  now: iso(0),

  // -- minutes ago --
  minutesAgo10: iso(-10 * MINUTE),
  minutesAgo15: iso(-15 * MINUTE),
  minutesAgo30: iso(-30 * MINUTE),
  minutesAgo45: iso(-45 * MINUTE),

  // -- hours ago --
  hoursAgo1: iso(-1 * HOUR),
  hoursAgo2: iso(-2 * HOUR),
  hoursAgo3: iso(-3 * HOUR),
  hoursAgo4: iso(-4 * HOUR),
  hoursAgo5: iso(-5 * HOUR),
  hoursAgo6: iso(-6 * HOUR),
  hoursAgo7: iso(-7 * HOUR),
  hoursAgo8: iso(-8 * HOUR),
  hoursAgo9: iso(-9 * HOUR),
  hoursAgo10: iso(-10 * HOUR),
  hoursAgo11: iso(-11 * HOUR),
  hoursAgo12: iso(-12 * HOUR),
  hoursAgo13: iso(-13 * HOUR),
  hoursAgo14: iso(-14 * HOUR),
  hoursAgo15: iso(-15 * HOUR),
  hoursAgo16: iso(-16 * HOUR),
  hoursAgo17: iso(-17 * HOUR),
  hoursAgo18: iso(-18 * HOUR),
  hoursAgo19: iso(-19 * HOUR),
  hoursAgo20: iso(-20 * HOUR),
  hoursAgo21: iso(-21 * HOUR),
  hoursAgo22: iso(-22 * HOUR),
  hoursAgo23: iso(-23 * HOUR),
  hoursAgo24: iso(-24 * HOUR),
  hoursAgo25: iso(-25 * HOUR),
  hoursAgo26: iso(-26 * HOUR),
  hoursAgo27: iso(-27 * HOUR),
  hoursAgo28: iso(-28 * HOUR),
  hoursAgo29: iso(-29 * HOUR),
  hoursAgo30: iso(-30 * HOUR),
  hoursAgo31: iso(-31 * HOUR),
  hoursAgo32: iso(-32 * HOUR),
  hoursAgo33: iso(-33 * HOUR),
  hoursAgo34: iso(-34 * HOUR),
  hoursAgo35: iso(-35 * HOUR),
  hoursAgo36: iso(-36 * HOUR),
  hoursAgo37: iso(-37 * HOUR),
  hoursAgo38: iso(-38 * HOUR),
  hoursAgo39: iso(-39 * HOUR),
  hoursAgo40: iso(-40 * HOUR),
  hoursAgo41: iso(-41 * HOUR),
  hoursAgo42: iso(-42 * HOUR),
  hoursAgo43: iso(-43 * HOUR),
  hoursAgo44: iso(-44 * HOUR),

  // -- days ago --
  daysAgo1: iso(-1 * DAY),
  daysAgo2: iso(-2 * DAY),
  daysAgo3: iso(-3 * DAY),
  daysAgo4: iso(-4 * DAY),
  daysAgo5: iso(-5 * DAY),
  daysAgo6: iso(-6 * DAY),
  daysAgo7: iso(-7 * DAY),

  // -- days ago with small offsets (execution started_at / completed_at) --
  daysAgo2Plus1s: iso(-2 * DAY + 1000),
  daysAgo2Plus2500ms: iso(-2 * DAY + 2500),
  daysAgo2Plus4s: iso(-2 * DAY + 4000),
  daysAgo2Plus5s: iso(-2 * DAY + 5000),

  daysAgo1Plus1s: iso(-1 * DAY + 1000),
  daysAgo1Plus1500ms: iso(-1 * DAY + 1500),
  daysAgo1Plus2500ms: iso(-1 * DAY + 2500),
  daysAgo1Plus3s: iso(-1 * DAY + 3000),

  daysAgo3Plus1s: iso(-3 * DAY + 1000),
  daysAgo3Plus2s: iso(-3 * DAY + 2000),
  daysAgo3Plus2500ms: iso(-3 * DAY + 2500),
  daysAgo3Plus4s: iso(-3 * DAY + 4000),
  daysAgo3Plus8s: iso(-3 * DAY + 8000),

  daysAgo4Plus1s: iso(-4 * DAY + 1000),
  daysAgo4Plus12s: iso(-4 * DAY + 12000),

  daysAgo5Plus1s: iso(-5 * DAY + 1000),
  daysAgo5Plus15s: iso(-5 * DAY + 15000),

  // -- hours ago with small offsets --
  hoursAgo6Plus1s: iso(-6 * HOUR + 1000),
  hoursAgo6Plus2s: iso(-6 * HOUR + 2000),

  hoursAgo2Plus1s: iso(-2 * HOUR + 1000),

  hoursAgo3Plus1s: iso(-3 * HOUR + 1000),
  hoursAgo3Plus2s: iso(-3 * HOUR + 2000),
  hoursAgo3Plus3s: iso(-3 * HOUR + 3000),
  hoursAgo3Plus4s: iso(-3 * HOUR + 4000),

  hoursAgo12Plus1s: iso(-12 * HOUR + 1000),

  hoursAgo1Plus1s: iso(-1 * HOUR + 1000),

  // -- hours from now (future) --
  hoursFromNow1: iso(1 * HOUR),
  hoursFromNow2: iso(2 * HOUR),
  hoursFromNow4: iso(4 * HOUR),
  hoursFromNow6: iso(6 * HOUR),
  hoursFromNow8: iso(8 * HOUR),
  hoursFromNow10: iso(10 * HOUR),
  hoursFromNow12: iso(12 * HOUR),
  hoursFromNow14: iso(14 * HOUR),
  hoursFromNow16: iso(16 * HOUR),
  hoursFromNow18: iso(18 * HOUR),
  hoursFromNow20: iso(20 * HOUR),
  hoursFromNow22: iso(22 * HOUR),
  hoursFromNow23: iso(23 * HOUR),
  hoursFromNow24: iso(24 * HOUR),
  hoursFromNow36: iso(36 * HOUR),
  hoursFromNow48: iso(48 * HOUR),
  hoursFromNow72: iso(72 * HOUR),
  hoursFromNow96: iso(96 * HOUR),

  // -- days from now (future) --
  daysFromNow180: iso(180 * DAY),
} as const
