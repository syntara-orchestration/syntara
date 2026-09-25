/**
 * Central registration point for all workflow step types (Add step panel).
 * Auto-discovers registration modules using import.meta.glob (each maps to React Flow node components).
 */

const nodeModules = import.meta.glob<{ default: () => void }>(
  ['./register*Node.ts', './register*Node.tsx', '!./*.test.ts', '!./*.spec.ts', '!./*.test.tsx'],
  {
    eager: true,
  }
)

/**
 * Register all workflow step types.
 * Call this once during app initialization.
 *
 * Discovers and registers every `register*Node.ts` module (each defines a canvas step type for the builder).
 */
export function registerAllNodes() {
  for (const module of Object.values(nodeModules)) {
    module.default()
  }
}
