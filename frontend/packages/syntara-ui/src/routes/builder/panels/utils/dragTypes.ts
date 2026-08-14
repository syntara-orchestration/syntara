export const DRAG_TYPE_FIELD = 'syntara/input-field'
export const DRAG_TYPE_CONTEXT = 'syntara/context-variable'

export const DROP_TARGET_OUTLINE: React.CSSProperties = {
  outline: '2px solid var(--pf-t--global--color--brand--default)',
  outlineOffset: '-2px',
}

export const DROP_TARGET_OUTLINE_ROUNDED: React.CSSProperties = {
  outline: '2px solid var(--pf-t--global--color--brand--default)',
  borderRadius: 'var(--pf-t--global--border--radius--small)',
}

export const EXPRESSION_FIELD_PLACEHOLDER = 'Enter or drag and drop value'

export type FieldDragData = {
  type: typeof DRAG_TYPE_FIELD
  nodeId: string
  fieldPath: string[]
}

export type ContextDragData = {
  type: typeof DRAG_TYPE_CONTEXT
  contextPath: string
}

export type DragData = FieldDragData | ContextDragData

export function isDragData(value: unknown): value is DragData {
  if (typeof value !== 'object' || value === null) return false
  const obj = value as Record<string, unknown>
  if (obj.type === DRAG_TYPE_FIELD) {
    return typeof obj.nodeId === 'string' && Array.isArray(obj.fieldPath)
  }
  if (obj.type === DRAG_TYPE_CONTEXT) {
    return typeof obj.contextPath === 'string'
  }
  return false
}
