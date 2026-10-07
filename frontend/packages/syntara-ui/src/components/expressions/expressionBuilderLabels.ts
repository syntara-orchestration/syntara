export type ExpressionEditorMode = 'visual' | 'raw'

export const EXPRESSION_EDITOR_MODE_ARIA_LABEL = 'Condition type'

export const EXPRESSION_MODE_LABELS: Record<ExpressionEditorMode, string> = {
  visual: 'Form builder',
  raw: 'Freeform text',
}

export const DEFAULT_BUILDER_GROUP_LABEL = 'Condition'
