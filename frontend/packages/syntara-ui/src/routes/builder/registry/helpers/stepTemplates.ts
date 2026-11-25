import type { ComponentType } from 'react'

import type { StepCategory } from '../categories'
import type { BaseStepFormProps, StepSubtypeDefinition, StepTypeDefinition } from '../StepRegistry'

/**
 * Configuration for creating a step type
 */
type StepConfig<TFormData = unknown> = {
  /** Unique identifier for this step type */
  id: string
  /** Display label in UI */
  label: string
  /** Icon component to display */
  icon: ComponentType
  /** Category for grouping */
  category?: StepCategory
  /** Description shown in UI */
  description: string
  /** Keywords for search */
  keywords: string[]
  /** Order for display (lower = earlier) */
  order?: number
  /** Form component to render when selected */
  formComponent: ComponentType<BaseStepFormProps<TFormData> & Record<string, unknown>>
  /** Optional subtype options */
  subtypes?: StepSubtypeDefinition<TFormData>[]
  /** Optional selection panel title */
  selectionTitle?: string
  /** Whether this step type is enabled (default: true) */
  enabled?: boolean
}

/**
 * Creates a step with custom submission logic.
 * Useful for steps that need to interact with stores or perform complex operations.
 *
 * @param config - Step configuration
 * @param onSubmit - Custom submission handler
 */
export function createCustomStep<TFormData = unknown>(
  config: StepConfig<TFormData>,
  onSubmit: (data: TFormData, onSuccess: (newStepId?: string) => void, onError: (error: string) => void) => void
): StepTypeDefinition<TFormData> {
  return {
    ...config,
    onSubmit,
  }
}
