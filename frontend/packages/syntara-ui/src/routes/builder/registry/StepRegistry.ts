import type { ComponentType, ReactNode } from 'react'

import type { StepCategory } from './categories'

/**
 * Base form props that all step forms must accept
 */
export type BaseStepFormProps<TData = unknown> = {
  onSubmit: (data: TData) => void
  onCancel: () => void
  initialData?: Partial<TData>
  submitButtonText?: string
  onHeaderContentChange?: (content: ReactNode | null) => void
  projectId?: string
}

export type StepSubtypeDefinition<TFormData = unknown> = {
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
  formComponent?: ComponentType<BaseStepFormProps<TFormData> & Record<string, unknown>>
  /** Optional form props for subtype-specific defaults */
  formProps?: Record<string, unknown>
  /** Optional initial form data */
  initialData?: Partial<TFormData>
}

/**
 * Step type definition for the registry
 */
export type StepTypeDefinition<TFormData = unknown> = {
  /** Unique identifier for this step type */
  id: string

  /** Display label in UI */
  label: string

  /** Icon component to display */
  icon: ComponentType

  /** Category for grouping (optional) */
  category?: StepCategory

  /** Description shown in UI (optional) */
  description?: string

  /** Keywords for search (optional) */
  keywords?: string[]

  /** Form component to render when selected */
  formComponent: ComponentType<BaseStepFormProps<TFormData> & Record<string, unknown>>

  /** Optional subtype options */
  subtypes?: StepSubtypeDefinition<TFormData>[]

  /** Optional selection panel title */
  selectionTitle?: string

  /** Handler function when form is submitted */
  onSubmit: (
    data: TFormData,
    onSuccess: (newStepId?: string) => void,
    onError: (error: string) => void,
    subtypeId?: string
  ) => void

  /** Whether this step type is enabled (default: true) */
  enabled?: boolean

  /** Order for display (lower = earlier, default: 100) */
  order?: number
}

/**
 * Global step registry - stores all registered step types
 */
class StepRegistryClass {
  private readonly steps = new Map<string, StepTypeDefinition>()

  /**
   * Register a new step type
   */
  register<TFormData = unknown>(definition: StepTypeDefinition<TFormData>): void {
    if (this.steps.has(definition.id)) {
      // Step type is already registered, overwriting
    }

    this.steps.set(definition.id, {
      enabled: true,
      order: 100,
      ...definition,
    } as StepTypeDefinition)
  }

  /**
   * Unregister a step type
   */
  unregister(id: string): boolean {
    return this.steps.delete(id)
  }

  /**
   * Get a specific step type by ID
   */
  get(id: string): StepTypeDefinition | undefined {
    return this.steps.get(id)
  }

  /**
   * Get all registered step types
   */
  getAll(): StepTypeDefinition[] {
    return Array.from(this.steps.values())
      .filter((step) => step.enabled !== false)
      .sort((a, b) => (a.order ?? 100) - (b.order ?? 100))
  }

  /**
   * Get step types by category
   */
  getByCategory(category: StepTypeDefinition['category']): StepTypeDefinition[] {
    return this.getAll().filter((step) => step.category === category)
  }

  /**
   * Search step types by query
   */
  search(query: string): StepTypeDefinition[] {
    const lowerQuery = query.toLowerCase()
    return this.getAll().filter((step) => {
      const matchLabel = step.label.toLowerCase().includes(lowerQuery)
      const matchKeywords = step.keywords?.some((keyword) => keyword.toLowerCase().includes(lowerQuery)) ?? false
      const matchId = step.id.toLowerCase().includes(lowerQuery)
      return matchLabel || matchKeywords || matchId
    })
  }

  /**
   * Clear all registered steps (useful for testing)
   */
  clear(): void {
    this.steps.clear()
  }
}

// Export singleton instance
export const StepRegistry = new StepRegistryClass()
