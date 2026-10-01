import Fuse, { type FuseOptionKey } from 'fuse.js'

import { COMMAND_PALETTE_MAX_RESULTS, type CommandPaletteItem } from './commandPaletteTypes'

const FUSE_KEYS: FuseOptionKey<CommandPaletteItem>[] = [
  { name: 'title', weight: 0.6 },
  { name: 'keywords', weight: 0.2 },
  { name: 'subtitle', weight: 0.15 },
  { name: 'categoryLabel', weight: 0.05 },
]

const FUSE_OPTIONS = {
  keys: FUSE_KEYS,
  threshold: 0.32,
  ignoreLocation: true,
  useTokenSearch: true,
  ignoreDiacritics: true,
  minMatchCharLength: 2,
  includeScore: true,
} as const

function emptyQueryItems(items: readonly CommandPaletteItem[]): CommandPaletteItem[] {
  return items.filter((item) => item.showWhenEmpty).slice(0, COMMAND_PALETTE_MAX_RESULTS)
}

/**
 * Rank items for the command palette.
 *
 * Empty query: pages and steps only (`showWhenEmpty`), so the first paint is
 * instant and does not dump thousands of remote rows.
 * Non-empty query: Fuse ranking across every loaded source, capped at
 * {@link COMMAND_PALETTE_MAX_RESULTS}.
 */
export function searchCommandPaletteItems(items: readonly CommandPaletteItem[], query: string): CommandPaletteItem[] {
  const trimmed = query.trim()
  if (!trimmed) return emptyQueryItems(items)

  const fuse = new Fuse([...items], FUSE_OPTIONS)
  return fuse
    .search(trimmed, { limit: COMMAND_PALETTE_MAX_RESULTS })
    .filter((result) => (result.score ?? 1) <= FUSE_OPTIONS.threshold)
    .map((result) => result.item)
}
