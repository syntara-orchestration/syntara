import type { ComponentType } from 'react'

import type { NodeCategory } from '../categories'
import type { BaseNodeFormProps, NodeSubtypeDefinition, NodeTypeDefinition } from '../NodeRegistry'

/**
 * Configuration for creating a node type
 */
type NodeConfig<TFormData = unknown> = {
  /** Unique identifier for this node type */
  id: string
  /** Display label in UI */
  label: string
  /** Icon component to display */
  icon: ComponentType
  /** Category for grouping */
  category?: NodeCategory
  /** Description shown in UI */
  description: string
  /** Keywords for search */
  keywords: string[]
  /** Order for display (lower = earlier) */
  order?: number
  /** Form component to render when selected */
  formComponent: ComponentType<BaseNodeFormProps<TFormData> & Record<string, unknown>>
  /** Optional subtype options */
  subtypes?: NodeSubtypeDefinition<TFormData>[]
  /** Optional selection panel title */
  selectionTitle?: string
  /** Whether this node type is enabled (default: true) */
  enabled?: boolean
}

/**
 * Creates a node with custom submission logic.
 * Useful for nodes that need to interact with stores or perform complex operations.
 *
 * @param config - Node configuration
 * @param onSubmit - Custom submission handler
 */
export function createCustomNode<TFormData = unknown>(
  config: NodeConfig<TFormData>,
  onSubmit: (
    data: TFormData,
    onSuccess: (newNodeId?: string) => void,
    onError: (error: string) => void,
    subtypeId?: string
  ) => void
): NodeTypeDefinition<TFormData> {
  return {
    ...config,
    onSubmit,
  }
}
