/**
 * A single result in the global command palette.
 *
 * `category` is an open string so new sources (credentials, users, executions, …)
 * can be added without changing this type. Use {@link COMMAND_PALETTE_CATEGORY}
 * for built-in values.
 */
export type CommandPaletteItem = {
  /** Stable identity used as the menu item id and React key. */
  id: string
  /** Source kind, e.g. `page`, `workflow`, or a future `credential`. */
  category: string
  /** User-visible group label, e.g. `Pages` or `Workflows`. */
  categoryLabel: string
  /** Primary searchable / displayed name. */
  title: string
  /** Secondary line (parent path, description, category). */
  subtitle?: string
  /** Extra tokens Fuse matches besides title/subtitle. */
  keywords?: string[]
  /** In-app route to open. Always a concrete path, never a `:param` template. */
  to: string
  /**
   * When true, the item is listed before the user types. Remote catalogs
   * should leave this unset so empty-query results stay small.
   */
  showWhenEmpty?: boolean
}

/**
 * Built-in source ids. Future sources add their own string; they do not have
 * to be listed here.
 */
export const COMMAND_PALETTE_CATEGORY = {
  PAGE: 'page',
  PROJECT: 'project',
  WORKFLOW: 'workflow',
  SETTING: 'setting',
  NODE: 'node',
} as const

export const COMMAND_PALETTE_CATEGORY_LABEL: Record<
  (typeof COMMAND_PALETTE_CATEGORY)[keyof typeof COMMAND_PALETTE_CATEGORY],
  string
> = {
  [COMMAND_PALETTE_CATEGORY.PAGE]: 'Pages',
  [COMMAND_PALETTE_CATEGORY.PROJECT]: 'Projects',
  [COMMAND_PALETTE_CATEGORY.WORKFLOW]: 'Workflows',
  [COMMAND_PALETTE_CATEGORY.SETTING]: 'Settings',
  [COMMAND_PALETTE_CATEGORY.NODE]: 'Steps',
}

/** Max ranked hits shown after a query. Keeps the menu cheap to render. */
export const COMMAND_PALETTE_MAX_RESULTS = 50
