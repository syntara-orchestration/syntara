import type { ComponentType, ReactNode } from 'react'

import type { NodeCategory } from './categories'

/**
 * Base form props that all node forms must accept
 */
export type BaseNodeFormProps<TData = unknown> = {
  onSubmit: (data: TData) => void
  onCancel: () => void
  initialData?: Partial<TData>
  submitButtonText?: string
  onHeaderContentChange?: (content: ReactNode | null) => void
  projectId?: string
  workflowId?: string | null
}

export type NodeSubtypeDefinition<TFormData = unknown> = {
  /** Unique identifier for this subtype */
  id: string
  /** Display label in UI */
  label: string
  /** Icon component to display */
  icon: ComponentType
  /** Description shown in UI (optional) */
  description?: string
  /** Keywords for search (optional) */
  keywords?: string[]
  /**
   * Optional order for display (lower = earlier).
   * Subtypes fall back to declaration order when order is not set.
   */
  order?: number
  /** Optional form panel title */
  formTitle?: string
  /** Optional form component (if different from parent) */
  formComponent?: ComponentType<BaseNodeFormProps<TFormData> & Record<string, unknown>>
  /** Optional form props for subtype-specific defaults */
  formProps?: Record<string, unknown>
  /** Optional initial form data */
  initialData?: Partial<TFormData>
}

/**
 * Node type definition for the registry
 */
export type NodeTypeDefinition<TFormData = unknown> = {
  /** Unique identifier for this node type */
  id: string

  /** Display label in UI */
  label: string

  /** Icon component to display */
  icon: ComponentType

  /** Category for grouping (optional) */
  category?: NodeCategory

  /** Description shown in UI (optional) */
  description?: string

  /** Keywords for search (optional) */
  keywords?: string[]

  /** Form component to render when selected */
  formComponent: ComponentType<BaseNodeFormProps<TFormData> & Record<string, unknown>>

  /** Optional subtype options */
  subtypes?: NodeSubtypeDefinition<TFormData>[]

  /** Optional selection panel title */
  selectionTitle?: string

  /** Handler function when form is submitted */
  onSubmit: (
    data: TFormData,
    onSuccess: (newNodeId?: string) => void,
    onError: (error: string) => void,
    subtypeId?: string
  ) => void

  /** Whether this node type is enabled (default: true) */
  enabled?: boolean

  /** Order for display (lower = earlier, default: 100) */
  order?: number
}

/**
 * Global node registry - stores all registered node types
 */
class NodeRegistryClass {
  private readonly nodes = new Map<string, NodeTypeDefinition>()

  /**
   * Register a new node type
   */
  register<TFormData = unknown>(definition: NodeTypeDefinition<TFormData>): void {
    if (this.nodes.has(definition.id)) {
      // Node type is already registered, overwriting
    }

    this.nodes.set(definition.id, {
      enabled: true,
      order: 100,
      ...definition,
    } as NodeTypeDefinition)
  }

  /**
   * Unregister a node type
   */
  unregister(id: string): boolean {
    return this.nodes.delete(id)
  }

  /**
   * Get a specific node type by ID
   */
  get(id: string): NodeTypeDefinition | undefined {
    return this.nodes.get(id)
  }

  /**
   * Get all registered node types
   */
  getAll(): NodeTypeDefinition[] {
    return Array.from(this.nodes.values())
      .filter((node) => node.enabled !== false)
      .sort((a, b) => (a.order ?? 100) - (b.order ?? 100))
  }

  /**
   * Get node types by category
   */
  getByCategory(category: NodeTypeDefinition['category']): NodeTypeDefinition[] {
    return this.getAll().filter((node) => node.category === category)
  }

  /**
   * Search node types by query
   */
  search(query: string): NodeTypeDefinition[] {
    const lowerQuery = query.toLowerCase()
    return this.getAll().filter((node) => {
      const matchLabel = node.label.toLowerCase().includes(lowerQuery)
      const matchKeywords = node.keywords?.some((k) => k.toLowerCase().includes(lowerQuery)) ?? false
      const matchId = node.id.toLowerCase().includes(lowerQuery)
      return matchLabel || matchKeywords || matchId
    })
  }

  /**
   * Clear all registered nodes (useful for testing)
   */
  clear(): void {
    this.nodes.clear()
  }
}

// Export singleton instance
export const NodeRegistry = new NodeRegistryClass()
