export type SearchableNodeOption = {
  id?: string
  label: string
  description?: string
  keywords?: string[]
  subtypes?: SearchableNodeOption[]
}

export type CatalogMatch<T extends SearchableNodeOption = SearchableNodeOption> = {
  option: T
  /** Registry id of the catalog entry that owns this card. */
  parentId: string
  /** Set when the card is a matching action inside a catalog category. */
  subtypeId?: string
}

function optionTextMatches(option: SearchableNodeOption, query: string): boolean {
  const fields = [option.label, option.description, ...(option.keywords ?? [])]
  return fields.some((field) => field?.toLowerCase().includes(query))
}

/** Keep entries whose own label, description, or keywords match. */
export function filterNodeOptions<T extends SearchableNodeOption>(options: T[], query: string): T[] {
  const normalized = query.trim().toLowerCase()
  if (!normalized) return options
  return options.filter((option) => optionTextMatches(option, normalized))
}

/**
 * Catalog search. A blank query returns each category card.
 * A query returns every category whose own text matches, plus each nested action that matches,
 * so a search on the Add step list can surface Terraform actions without opening the category.
 */
export function collectCatalogMatches<T extends SearchableNodeOption>(options: T[], query: string): CatalogMatch<T>[] {
  const normalized = query.trim().toLowerCase()
  const matches: CatalogMatch<T>[] = []

  for (const option of options) {
    const parentId = option.id ?? option.label
    if (!normalized) {
      matches.push({ option, parentId })
      continue
    }

    if (optionTextMatches(option, normalized)) {
      matches.push({ option, parentId })
    }

    for (const subtype of option.subtypes ?? []) {
      if (!optionTextMatches(subtype, normalized)) continue
      matches.push({ option: subtype as T, parentId, subtypeId: subtype.id })
    }
  }

  return matches
}
