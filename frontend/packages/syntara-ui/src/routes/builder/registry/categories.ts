import type { ComponentType } from 'react'

export type StepCategory = 'trigger' | 'action' | 'logic' | 'integration' | 'approval' | 'other'

/**
 * Metadata for a node category
 */
export type CategoryMetadata = {
  /** Unique category identifier */
  id: StepCategory
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
