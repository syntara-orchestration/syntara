import { RhUiCheckClipboardIcon } from '@patternfly/react-icons'
import type { ComponentType } from 'react'

export type NodeCategory = 'trigger' | 'action' | 'logic' | 'integration' | 'human_tasks' | 'approval' | 'other'

/**
 * Metadata for a node category
 */
export type CategoryMetadata = {
  /** Unique category identifier */
  id: NodeCategory
  /** Display label for the category */
  label: string
  /** Icon component for the category */
  icon: ComponentType<{ className?: string }>
  /** Description of what this category contains */
  description: string
  /** Display order (lower = earlier) */
  order: number
  /** Color theme for the category (for potential future use) */
  color?: string
}

/** Display order for Add step panel category sections (lower = earlier). */
export const NODE_CATEGORY_DISPLAY_ORDER: NodeCategory[] = [
  'trigger',
  'action',
  'logic',
  'human_tasks',
  'integration',
  'other',
]

const HUMAN_TASKS_CATEGORY_METADATA: CategoryMetadata = {
  id: 'human_tasks',
  label: 'Human tasks',
  icon: RhUiCheckClipboardIcon,
  description: 'Steps that pause the workflow for a person to respond',
  order: 45,
}

const CATEGORY_METADATA_BY_ID: Partial<Record<NodeCategory, CategoryMetadata>> = {
  human_tasks: HUMAN_TASKS_CATEGORY_METADATA,
}

export function getCategoryMetadata(category: NodeCategory | undefined): CategoryMetadata | undefined {
  if (!category) return undefined
  return CATEGORY_METADATA_BY_ID[category]
}
