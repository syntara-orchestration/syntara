/**
 * Central registration point for all workflow step types (Add step panel).
 * Auto-discovers registration modules using import.meta.glob (each maps to React Flow node components).
 */

const stepModules = import.meta.glob<{ default: () => void }>(['./register*Step.ts', '!./*.test.ts', '!./*.spec.ts'], {
  eager: true,
})

/**
 * Register all workflow step types.
 * Call this once during app initialization.
 *
 * Discovers and registers every `register*Step.ts` module (each defines a canvas step type for the builder).
 */
export function registerAllSteps() {
  for (const module of Object.values(stepModules)) {
    module.default()
  }
}
